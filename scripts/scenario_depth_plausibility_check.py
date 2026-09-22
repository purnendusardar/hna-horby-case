"""Depth-plausibility gate (project lead, 2026-09-22): the published Ågatan (3.46 m @ 40 mm) and
Tvärgatan (2.23 m) maxima look inconsistent with the Nov 2023 event record (comparable rainfall,
36.9 mm; official notice describes parts of Ågatan as submerged, not multi-metre inundation).

READ-ONLY DIAGNOSIS. Does not touch the model, the DEM, or the forcing. Does not modify the
website or any published file.

1. Metric definition: exact footprint geometry + statistic per location (reusing
   scripts/scenario_postprocess_run.py's own `locations()`, so this describes what's actually
   published, not a re-derived approximation), and whether each footprint intersects the burned-
   channel mask.
2. Street-surface depth: for each location x scenario, water surface elevation (the model's own
   conditioned 5 m ground + LISFLOOD .max depth) minus the UNCONDITIONED ground (the raw clipped
   1 m Lantmäteriet DTM, mean-aggregated to 5 m — no channel burn, no building raise), over the
   footprint with the burned-channel mask + 1-cell buffer removed. Reports max/p90/median next to
   the published value.
3. Proposed statistic (not applied): p90 of street-surface depth, flagged as project-defined,
   pending approval.
4. Hydraulic diagnosis, only if Ågatan's 40 mm street-surface p90 still exceeds 1.0 m (project-
   defined trigger): longitudinal WSE/bed profile per reach (east arm, south arm, below
   confluence) for the 40 mm run, backwater reaches (near-zero WSE slope) and the terrain feature
   at each one's downstream end, and peak inflow vs burned-channel bankfull capacity.

Runs in the data-prep venv, after the three final_aoi_5m_<mm>mm runs and their post-processing:
    .venv\\Scripts\\python.exe scripts\\scenario_depth_plausibility_check.py
"""
import json
import math
import os
import pathlib
import sys

for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.mask import mask as rio_mask
from shapely.geometry import box as shp_box

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scenario_prep_dem as prep  # noqa: E402
import scenario_postprocess_run as post  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER = ROOT / "data/scenario/derived"
CELL = 5
GATE_LOCATIONS = ["Ågatan", "Tvärgatan"]
GATE_TRIGGER_M = 1.0
TO3006 = Transformer.from_crs(4326, 3006, always_xy=True)


def read_asc(path):
    with open(path, encoding="ascii") as f:
        h = {k.lower(): float(v) for k, v in (f.readline().split() for _ in range(6))}
        a = np.fromstring(f.read(), sep=" ", dtype="float64").astype("float32").reshape(int(h["nrows"]), int(h["ncols"]))
    return np.where(a <= -9990, np.nan, a), h


def dilate(m, n=1):
    out = m.copy()
    for _ in range(n):
        p = np.pad(out, 1)
        out = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] | p[:-2, :-2] | p[2:, 2:] | p[:-2, 2:] | p[2:, :-2]
    return out


def unconditioned_ground_5m(bounds, tf5, shape5):
    """Mean-aggregate the RAW, unconditioned 1 m clipped DTM to the model's own 5 m grid/bounds."""
    x0, y0, x1, y1 = bounds
    with rasterio.open(DER / "dem_rh2000_1m_clip.tif") as src:
        arr, tf1 = rio_mask(src, [shp_box(x0, y0, x1, y1)], crop=True, all_touched=True, filled=True, nodata=np.nan)
    arr = arr[0]
    # snap the masked window onto an exact multiple of CELL, matching to_model_grid's own crop convention
    c0 = int(round((x0 - tf1.c) / 1.0))
    r0 = int(round((tf1.f - y1) / 1.0))
    arr = arr[r0:r0 + shape5[0] * CELL, c0:c0 + shape5[1] * CELL]
    h, w = (arr.shape[0] // CELL) * CELL, (arr.shape[1] // CELL) * CELL
    block = arr[:h, :w].reshape(h // CELL, CELL, w // CELL, CELL)
    return np.nanmean(block, axis=(1, 3))


def channel_mask_5m(bounds, tf5, shape5):
    state = np.load(DER / "dem_1m_conditioned_state.npz")
    burned1 = state["burned"].astype(bool)
    _, tf1, _ = prep.mosaic_clip(prep.clip_bounds())
    x0, y0, x1, y1 = bounds
    c0 = int(round((x0 - tf1.c) / 1.0))
    r0 = int(round((tf1.f - y1) / 1.0))
    nc, nr = shape5[1] * CELL, shape5[0] * CELL
    sub = burned1[r0:r0 + nr, c0:c0 + nc]
    h, w = (sub.shape[0] // CELL) * CELL, (sub.shape[1] // CELL) * CELL
    block = sub[:h, :w].reshape(h // CELL, CELL, w // CELL, CELL)
    return block.max(axis=(1, 3)).astype(bool)


def metric_definitions(tf5, shape5, chan_mask):
    masks = post.locations(tf5, shape5)
    out = {}
    for name, m in masks.items():
        out[name] = dict(
            footprint_cells=int(m.sum()),
            intersects_burned_channel_mask=bool((m & chan_mask).any()),
            channel_cells_in_footprint=int((m & chan_mask).sum()),
        )
    return out, masks


def street_surface_depths(run, mm, tf5, unc_ground, chan_buf, bmask5):
    idir, od = ROOT / "model/inputs" / run, ROOT / "model/outputs" / run
    dem, _ = read_asc(idir / f"{run}.dem.asc")   # conditioned ground actually used by the model
    depth, _ = read_asc(od / f"{run}.max")        # LISFLOOD max water depth above that conditioned ground
    wse = dem + depth
    street_depth = wse - unc_ground                # water surface minus the UNCONDITIONED ground
    _, masks = metric_definitions(tf5, dem.shape, chan_buf)
    imp = json.loads((ROOT / "web/data/results" / f"{mm}mm/impacts.json").read_text(encoding="utf8"))
    published = {l["location"]: l["max_depth_m"] for l in imp["locations"]}
    out = {}
    for name, m in masks.items():
        keep = m & ~chan_buf   # per instruction: channel mask + 1-cell buffer only
        vals = street_depth[keep]
        vals = vals[np.isfinite(vals)]
        keep_nb = keep & ~bmask5   # secondary variant: ALSO excludes building-raised cells (+10 m) — see finding below
        vals_nb = street_depth[keep_nb]
        vals_nb = vals_nb[np.isfinite(vals_nb)]
        out[name] = dict(published_max_m=published.get(name), footprint_cells=int(m.sum()),
                         channel_or_buffer_excluded_cells=int((m & chan_buf).sum()), street_cells_used=int(keep.sum()),
                         street_surface_max_m=round(float(vals.max()), 3) if len(vals) else None,
                         street_surface_p90_m=round(float(np.percentile(vals, 90)), 3) if len(vals) else None,
                         street_surface_median_m=round(float(np.median(vals)), 3) if len(vals) else None,
                         street_surface_min_m=round(float(vals.min()), 3) if len(vals) else None,
                         building_raised_cells_in_kept_footprint=int((keep & bmask5).sum()),
                         street_surface_excl_buildings_max_m=round(float(vals_nb.max()), 3) if len(vals_nb) else None,
                         street_surface_excl_buildings_p90_m=round(float(np.percentile(vals_nb, 90)), 3) if len(vals_nb) else None,
                         street_surface_excl_buildings_median_m=round(float(np.median(vals_nb)), 3) if len(vals_nb) else None)
    return out, wse, dem


def building_mask_5m(bounds, shape5):
    state = np.load(DER / "dem_1m_conditioned_state.npz")
    bmask1 = state["bmask"].astype(bool)
    _, tf1, _ = prep.mosaic_clip(prep.clip_bounds())
    x0, y0, x1, y1 = bounds
    c0 = int(round((x0 - tf1.c) / 1.0))
    r0 = int(round((tf1.f - y1) / 1.0))
    nc, nr = shape5[1] * CELL, shape5[0] * CELL
    sub = bmask1[r0:r0 + nr, c0:c0 + nc]
    h, w = (sub.shape[0] // CELL) * CELL, (sub.shape[1] // CELL) * CELL
    return sub[:h, :w].reshape(h // CELL, CELL, w // CELL, CELL).mean(axis=(1, 3)) >= 0.5


def reach_profile(coords_lonlat, dem_arr, depth_arr, tf5, step=5.0):
    pts_ll = coords_lonlat
    pts3006 = [TO3006.transform(lon, lat) for lon, lat in pts_ll]
    pts3006 = prep.line_samples([(x, y) for x, y in pts3006], step=step)
    inv = ~tf5
    rows, cols = [], []
    s, cum = 0.0, [0.0]
    for i in range(1, len(pts3006)):
        s += math.hypot(*(pts3006[i] - pts3006[i - 1]))
        cum.append(s)
    prof = []
    for (x, y), sdist in zip(pts3006, cum):
        c, r = inv * (x, y)
        c, r = int(round(c)), int(round(r))
        if 0 <= r < dem_arr.shape[0] and 0 <= c < dem_arr.shape[1]:
            bed = float(dem_arr[r, c])
            d = float(depth_arr[r, c])
            if np.isfinite(bed) and np.isfinite(d):
                prof.append((sdist, x, y, bed, bed + d))
    return prof


def find_backwater(prof, flat_slope_thresh=0.0005, min_len_m=30):
    reaches = []
    cur = None
    for i in range(1, len(prof)):
        s0, s1 = prof[i - 1][0], prof[i][0]
        wse0, wse1 = prof[i - 1][4], prof[i][4]
        if s1 - s0 <= 0:
            continue
        slope = (wse0 - wse1) / (s1 - s0)
        flat = abs(slope) <= flat_slope_thresh
        if flat:
            if cur is None:
                cur = [i - 1, i]
            else:
                cur[1] = i
        else:
            if cur is not None and prof[cur[1]][0] - prof[cur[0]][0] >= min_len_m:
                reaches.append(tuple(cur))
            cur = None
    if cur is not None and prof[cur[1]][0] - prof[cur[0]][0] >= min_len_m:
        reaches.append(tuple(cur))
    return reaches


def nearest_road_feature(x, y, road_shapes, max_dist=30.0):
    best = (1e18, None)
    for name, coords in road_shapes:
        pts = np.array(coords)
        d = np.hypot(pts[:, 0] - x, pts[:, 1] - y).min()
        if d < best[0]:
            best = (d, name)
    return best if best[0] <= max_dist else (best[0], None)


def main():
    full, _ = prep.domain_bounds(CELL)
    run40 = ROOT / "model/inputs/final_aoi_5m_40mm"
    dem0, hd = read_asc(run40 / "final_aoi_5m_40mm.dem.asc")
    tf5 = rasterio.transform.from_origin(hd["xllcorner"], hd["yllcorner"] + hd["nrows"] * hd["cellsize"], hd["cellsize"], hd["cellsize"])
    shape5 = dem0.shape

    unc = unconditioned_ground_5m(full, tf5, shape5)
    chan = channel_mask_5m(full, tf5, shape5)
    chan_buf = dilate(chan, 1)

    metric_defs, masks = metric_definitions(tf5, shape5, chan)
    bmask5 = building_mask_5m(full, shape5)
    building_ov = {name: int((m & bmask5).sum()) for name, m in masks.items()}

    report = dict(gate="depth plausibility (Ågatan/Tvärgatan vs Nov 2023 record)",
                  metric_definition=dict(
                      how_published_values_are_computed="max(water depth) over the footprint mask, from scripts/scenario_postprocess_run.py::locations() "
                                                          "and impacts.json — footprints: Ågatan/Tvärgatan = OSM street centreline dilated to +-15 m "
                                                          "(3 cells @ 5 m); ICA car park = OSM parking polygons dilated +-5 m (1 cell); Skattkistans förskola "
                                                          "= a single geocoded point (horby.se) dilated +-15 m (3 cells). Statistic: MAXIMUM depth over all "
                                                          "footprint cells (not mean/percentile).",
                      per_location=metric_defs, building_raised_cells_in_footprint=building_ov),
                  street_surface_definition="water surface elevation (model conditioned ground + LISFLOOD .max depth) minus the UNCONDITIONED "
                                             "(raw, un-burned, un-raised) 1 m Lantmäteriet DTM mean-aggregated to 5 m; burned-channel mask + 1-cell "
                                             "(5 m) buffer excluded from the footprint before taking statistics, exactly as instructed",
                  finding_building_artifact="The instructed exclusion (channel mask + 1-cell buffer only) leaves building-raised cells (+10 m, "
                                             "scripts/scenario_prep_dem.py's conditioning) inside the dilated Ågatan/Tvärgatan street footprints, "
                                             "because these dense town-centre streets are lined with buildings within the +-15 m dilation radius. "
                                             "A building cell's water surface = unconditioned ground + 10 m + a small real depth, so subtracting "
                                             "the UNCONDITIONED ground gives ~10 m there — a raise-height artifact, not real water depth. This "
                                             "swamps the max and often the p90 too (see 'street_surface_max/p90_m' below, all ~10.0x m). A second, "
                                             "ALSO-excludes-buildings variant is reported alongside ('street_surface_excl_buildings_*_m') as the "
                                             "one that actually answers the plausibility question; the gate trigger below uses that variant.",
                  by_storm={})

    triggered = False
    for mm, run in ((40, "final_aoi_5m_40mm"), (70, "final_aoi_5m_70mm"), (100, "final_aoi_5m_100mm")):
        vals, wse, dem = street_surface_depths(run, mm, tf5, unc, chan_buf, bmask5)
        report["by_storm"][mm] = vals
        if mm == 40:
            dem40 = dem
            depth40, _ = read_asc(ROOT / f"model/outputs/{run}/{run}.max")
            if vals.get("Ågatan", {}).get("street_surface_excl_buildings_p90_m") and vals["Ågatan"]["street_surface_excl_buildings_p90_m"] > GATE_TRIGGER_M:
                triggered = True
        print(f"{mm} mm:")
        for name in GATE_LOCATIONS + ["ICA car park", "Skattkistans förskola"]:
            v = vals.get(name)
            if v:
                print(f"  {name}: published {v['published_max_m']} m | per-instruction (channel-excl only) max/p90/median = "
                      f"{v['street_surface_max_m']}/{v['street_surface_p90_m']}/{v['street_surface_median_m']} m "
                      f"({v['street_cells_used']} kept, {v['building_raised_cells_in_kept_footprint']} of those are building-raised cells) | "
                      f"ALSO excl. buildings: max/p90/median = {v['street_surface_excl_buildings_max_m']}/{v['street_surface_excl_buildings_p90_m']}/{v['street_surface_excl_buildings_median_m']} m")

    report["proposed_statistic"] = dict(
        statistic="p90 of street-surface depth over the footprint, excluding the burned-channel mask + 1-cell buffer",
        status="PROPOSED ONLY — not applied to the website, pending approval",
        rationale="A maximum is set by a single cell and is sensitive to local depressions and to the channel itself; "
                  "the 90th percentile represents conditions over most of the street surface, not its single worst point.")

    if triggered:
        print("\nGate trigger met (Ågatan 40 mm street-surface p90 > 1.0 m) — running hydraulic diagnosis.")
        cc = json.loads((DER / "channel_capacity.json").read_text(encoding="utf8"))
        hy = json.loads((DER / "inflow_hydrographs_summary.json").read_text(encoding="utf8"))["storms"]["40"]
        g = json.loads((ROOT / "web/data/geography.geojson").read_text(encoding="utf8"))
        ways = {ft["properties"]["osm_id"]: ft for ft in g["features"] if "osm_id" in ft["properties"]}
        road_ok = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service", "trunk_link"}
        road_shapes = [(f"{p.get('name', p['highway'])} ({p['highway']}, way {p['osm_id']})", [TO3006.transform(x, y) for x, y in ft["geometry"]["coordinates"]])
                       for ft in g["features"] for p in [ft["properties"]] if p.get("highway") in road_ok]

        mainstem = ways[77387390]["geometry"]["coordinates"]
        from scenario_channel_capacity import split_at_confluence, CONFLUENCE_LONLAT
        si = split_at_confluence(mainstem, CONFLUENCE_LONLAT)
        reaches = {"east_arm": mainstem[:si + 1], "south_arm": ways[77387397]["geometry"]["coordinates"], "below_confluence": mainstem[si:]}
        diag = {}
        for key, coords in reaches.items():
            prof = reach_profile(coords, dem40, depth40, tf5)
            backwater = find_backwater(prof)
            bw_out = []
            for i0, i1 in backwater:
                x, y = prof[i1][1], prof[i1][2]
                dist, feat = nearest_road_feature(x, y, road_shapes)
                bw_out.append(dict(from_m_along_reach=round(prof[i0][0]), to_m_along_reach=round(prof[i1][0]),
                                   downstream_epsg3006=[round(x), round(y)],
                                   wse_m=round(prof[i1][4], 2), bed_m=round(prof[i1][3], 2),
                                   nearest_road_m=round(dist) if feat else None, nearest_road=feat,
                                   note="no road/rail within 30 m — check for a burned-channel discontinuity or a genuine natural flat reach" if not feat else None))
            diag[key] = dict(profile_points=len(prof), profile_length_m=round(prof[-1][0]) if prof else 0,
                             bed_drop_m=round(prof[0][3] - prof[-1][3], 2) if prof else None,
                             wse_drop_m=round(prof[0][4] - prof[-1][4], 2) if prof else None,
                             backwater_reaches=bw_out)
        diag["capacity_vs_peak_inflow"] = dict(
            east=dict(peak_inflow_m3s=hy["east"]["peak_total_m3s"], bankfull_capacity_m3s=6.25, ratio=round(hy["east"]["peak_total_m3s"] / 6.25, 2)),
            south=dict(peak_inflow_m3s=hy["south"]["peak_total_m3s"], bankfull_capacity_m3s=4.76, ratio=round(hy["south"]["peak_total_m3s"] / 4.76, 2)),
            below_confluence=dict(peak_inflow_m3s=hy["peak_combined_timeseries_m3s"], bankfull_capacity_m3s=11.01, ratio=round(hy["peak_combined_timeseries_m3s"] / 11.01, 2)))
        report["hydraulic_diagnosis_40mm"] = diag
        for key, d in diag.items():
            if key == "capacity_vs_peak_inflow":
                continue
            print(f"\n{key}: {d['profile_points']} pts, {d['profile_length_m']} m, bed drop {d['bed_drop_m']} m, WSE drop {d['wse_drop_m']} m, "
                  f"{len(d['backwater_reaches'])} backwater reach(es)")
            for bw in d["backwater_reaches"]:
                print(f"   backwater {bw['from_m_along_reach']}-{bw['to_m_along_reach']} m along reach, downstream end at {bw['downstream_epsg3006']}, "
                      f"WSE {bw['wse_m']} m, nearest road {bw['nearest_road_m']} m: {bw['nearest_road'] or bw['note']}")
        print("\ncapacity vs peak inflow (40 mm):")
        for k, v in diag["capacity_vs_peak_inflow"].items():
            print(f"  {k}: peak {v['peak_inflow_m3s']} m3/s vs bankfull {v['bankfull_capacity_m3s']} m3/s -> {v['ratio']}x over capacity")
    else:
        print("\nGate trigger NOT met (Ågatan 40 mm street-surface p90 <= 1.0 m) — hydraulic diagnosis not run.")

    (DER / "depth_plausibility_gate.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf8")
    print(f"\nWrote {DER / 'depth_plausibility_gate.json'}")


if __name__ == "__main__":
    main()
