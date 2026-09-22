"""Perpendicular elevation profiles across the 101 m possible-artefact segment (midpoint EPSG:3006
415665, 6190188), project lead, 2026-09-22. READ-ONLY: no DEM change, no model run.

For each of six points along the segment (20 m intervals: t=0,20,40,60,80,100 of its 101 m length),
sample a profile perpendicular to the segment, -30 m to +30 m at 1 m steps, from both the
CONDITIONED model DEM (the grid the 100 mm solver actually used) and the UNCONDITIONED raw DTM.
Reports, per profile: max water-surface elevation (conditioned ground + LISFLOOD depth) on the
flooded side; the crest (highest conditioned-DEM cell across the whole profile) — its elevation,
offset, and cell type (building-raised / burned-channel / culvert-cut / unmodified terrain); and
the unconditioned ground elevation on the dry side.

Classification (applied mechanically, per the project lead's fixed rule — not re-judged here):
  A - crest cells are all building-raised -> "physical by model construction"
  B - no intervening crest in the conditioned DEM at some profile -> "diagnosis sampling error"
  C - any crest cell is burned-channel or culvert-cut -> "conditioning error": report and stop

Runs in the data-prep venv, after the 100 mm final run and scripts/scenario_boundary_diagnosis.py:
    .venv\\Scripts\\python.exe scripts\\scenario_boundary_profile_diagnosis.py
"""
import json
import math
import os
import pathlib
import sys

for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import numpy as np
from rasterio.transform import from_origin

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scenario_prep_dem as prep  # noqa: E402
import scenario_depth_plausibility_check as plaus  # noqa: E402
import scenario_boundary_diagnosis as bd  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER = ROOT / "data/scenario/derived"
RUN = "final_aoi_5m_100mm"
SEG_FROM, SEG_TO = (415715.0, 6190195.0), (415615.0, 6190180.0)  # from boundary_diagnosis.json, 100 mm segment #1
STEP_ALONG_M = 20.0
PROFILE_HALF_M = 30.0
PROFILE_STEP_M = 1.0
CULVERT_CUT_BUFFER_M = 3.0  # width margin around each applied cut's centreline, for the cell-type test


def culvert_cut_mask(tf, shape):
    p = DER / "culvert_cut_decisions.json"
    if not p.exists():
        return np.zeros(shape, bool)
    dec = json.loads(p.read_text(encoding="utf8"))
    mask = np.zeros(shape, bool)
    inv = ~tf
    for d in dec.get("decisions", []):
        if d["decision"] != "APPLIED":
            continue
        c = d["representative_candidate"]
        geo = json.loads((ROOT / "model/outputs" / c["source_run"] / "proposed_corrections_UNAPPLIED.geojson").read_text(encoding="utf8"))
        feat = next(f for f in geo["features"] if f["properties"]["candidate"] == c["_candidate_index_in_run"])
        pts = prep.line_samples(feat["geometry"]["coordinates"], step=1.0)
        half = c["proposed_correction"]["width_m"] / 2.0 + CULVERT_CUT_BUFFER_M
        for x, y in pts:
            col, row = inv * (x, y)
            col, row = int(round(col)), int(round(row))
            rr = int(math.ceil(half / abs(tf.a))) + 1
            r_lo, r_hi = max(0, row - rr), min(shape[0], row + rr + 1)
            c_lo, c_hi = max(0, col - rr), min(shape[1], col + rr + 1)
            for r in range(r_lo, r_hi):
                for cidx in range(c_lo, c_hi):
                    cx, cy = tf * (cidx + 0.5, r + 0.5)
                    if math.hypot(cx - x, cy - y) <= half:
                        mask[r, cidx] = True
    return mask


def cell_type(r, c, shape, bmask, chan_mask, cut_mask):
    if not (0 <= r < shape[0] and 0 <= c < shape[1]):
        return "outside domain"
    if cut_mask[r, c]:
        return "culvert-cut"
    if chan_mask[r, c]:
        return "burned-channel"
    if bmask[r, c]:
        return "building-raised"
    return "unmodified terrain"


def main():
    idir, od = ROOT / "model/inputs" / RUN, ROOT / "model/outputs" / RUN
    dem_c, hd = bd.read_asc(idir / f"{RUN}.dem.asc")   # CONDITIONED — the grid the solver used
    depth, _ = bd.read_asc(od / f"{RUN}.max")
    tf = from_origin(hd["xllcorner"], hd["yllcorner"] + hd["nrows"] * hd["cellsize"], hd["cellsize"], hd["cellsize"])
    shape = dem_c.shape
    wse_c = dem_c + depth

    full, _ = prep.domain_bounds(5)
    dem_u = plaus.unconditioned_ground_5m(full, tf, shape)          # UNCONDITIONED raw DTM
    chan_mask = plaus.channel_mask_5m(full, tf, shape)
    bmask = plaus.building_mask_5m(full, shape)
    cut_mask = culvert_cut_mask(tf, shape)
    region = json.loads((DER / "boundary_diagnosis.json").read_text(encoding="utf8"))["100"]
    # re-derive the qualifying >0.5 m region (same definition as scripts/scenario_boundary_diagnosis.py) to know which side is flooded
    unc = dem_u
    street = wse_c - unc
    south = bd.south_of_river_mask(chan_mask, shape)
    x0 = hd["xllcorner"]
    cols = np.arange(shape[1])
    west2d = np.broadcast_to((x0 + (cols + 0.5) * 5) < bd.CONFLUENCE_3006[0], shape)
    chan_buf = plaus.dilate(chan_mask, 1)
    qual_region = (street > 0.5) & south & west2d & ~chan_buf & ~bmask & np.isfinite(street)

    seg = np.array(SEG_TO) - np.array(SEG_FROM)
    seg_len = float(np.hypot(*seg))
    seg_u = seg / seg_len
    normal = np.array([-seg_u[1], seg_u[0]])

    inv = ~tf
    profiles = []
    t_vals = list(np.arange(0, seg_len, STEP_ALONG_M))
    if t_vals[-1] < seg_len - 1:
        t_vals.append(seg_len)
    for t in t_vals:
        base = np.array(SEG_FROM) + seg_u * t
        offsets = np.arange(-PROFILE_HALF_M, PROFILE_HALF_M + 1e-6, PROFILE_STEP_M)
        rows = []
        for off in offsets:
            px, py = base + normal * off
            col, row = inv * (px, py)
            col, row = int(round(col)), int(round(row))
            in_domain = 0 <= row < shape[0] and 0 <= col < shape[1]
            zc = float(dem_c[row, col]) if in_domain else None
            zu = float(dem_u[row, col]) if in_domain else None
            wet = bool(qual_region[row, col]) if in_domain else False
            ctype = cell_type(row, col, shape, bmask, chan_mask, cut_mask) if in_domain else "outside domain"
            rows.append(dict(offset_m=round(float(off), 1), epsg3006=[round(px), round(py)], conditioned_z=zc, unconditioned_z=zu, wet=wet, cell_type=ctype))
        wet_rows = [r for r in rows if r["wet"] and r["conditioned_z"] is not None]
        dry_rows = [r for r in rows if not r["wet"] and r["conditioned_z"] is not None]
        wse_at_wet = []
        for r in wet_rows:
            col, row = inv * (r["epsg3006"][0], r["epsg3006"][1])
            col, row = int(round(col)), int(round(row))
            if 0 <= row < shape[0] and 0 <= col < shape[1]:
                wse_at_wet.append(float(wse_c[row, col]))
        max_wse_flooded = max(wse_at_wet) if wse_at_wet else None
        crest = max((r for r in rows if r["conditioned_z"] is not None), key=lambda r: r["conditioned_z"], default=None)
        dry_ground_u = dry_rows[-1]["unconditioned_z"] if dry_rows else None
        no_crest = crest is None or (max_wse_flooded is not None and crest["conditioned_z"] <= max_wse_flooded)
        profiles.append(dict(t_along_segment_m=round(float(t)), base_epsg3006=[round(base[0]), round(base[1])],
                             max_wse_flooded_m=round(max_wse_flooded, 3) if max_wse_flooded is not None else None,
                             crest=crest, no_intervening_crest=bool(no_crest), dry_side_unconditioned_ground_m=round(dry_ground_u, 3) if dry_ground_u is not None else None))

    types_seen = set()
    for p in profiles:
        if p["no_intervening_crest"]:
            continue
        if p["crest"]:
            types_seen.add(p["crest"]["cell_type"])
    if "burned-channel" in types_seen or "culvert-cut" in types_seen:
        overall = "C - conditioning error"
    elif any(p["no_intervening_crest"] for p in profiles):
        overall = "B - diagnosis sampling error"
    elif types_seen == {"building-raised"}:
        overall = "A - physical by model construction"
    else:
        overall = f"mixed/unclear: crest types seen = {sorted(types_seen)}"

    out = dict(segment_from=list(SEG_FROM), segment_to=list(SEG_TO), segment_length_m=round(seg_len),
               overall_classification=overall, profiles=profiles)
    (DER / "boundary_profile_diagnosis.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf8")
    print(f"Overall classification: {overall}\n")
    for p in profiles:
        print(f"t={p['t_along_segment_m']} m, base {p['base_epsg3006']}: max WSE (flooded side) = {p['max_wse_flooded_m']} m; "
              f"no_intervening_crest={p['no_intervening_crest']}")
        if p["crest"]:
            c = p["crest"]
            print(f"    crest: offset {c['offset_m']} m, {c['epsg3006']}, conditioned z={c['conditioned_z']}, "
                  f"unconditioned z={c['unconditioned_z']}, type={c['cell_type']}")
        print(f"    dry-side unconditioned ground (+30 m out): {p['dry_side_unconditioned_ground_m']} m")
    print(f"\nWrote {DER / 'boundary_profile_diagnosis.json'}")


if __name__ == "__main__":
    main()
