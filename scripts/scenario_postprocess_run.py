"""Post-process one completed LISFLOOD-FP run (idle priority, single thread).

    .venv\\Scripts\\python.exe scripts\\scenario_postprocess_run.py <run_name> <storm_mm> [--wall-s N]

Writes (never deploys):
  model/outputs/<run>/run_stats.json, criteria.json      run timing, timestep stats, volume closure, C1-C7 pass/fail
  model/outputs/<run>/maxdepth_steps/*.tif                running-max depth grids every 2 simulated hours (needs snapshots)
  web/data/results/<storm>mm/maxdepth.png + meta.json    EPSG:4326 depth PNG (channel cells shown as a separate river layer,
                                                          not depth-classified), exact bounds, project-defined display classes
  web/data/results/<storm>mm/impacts.json                 street_surface_p90_m + wetted_fraction (project-defined, see
                                                          ASSUMPTIONS.md "Depth-plausibility gate") at the four reporting
                                                          locations, channel + building-raised cells excluded
Success criteria C1-C7 are those written in ASSUMPTIONS.md ("Pilot success criteria").
"""
import os
import sys

os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
if sys.platform == "win32":
    import ctypes
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x40)  # IDLE_PRIORITY_CLASS
for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import argparse
import json
import pathlib
import re
import struct
import sys
import zlib

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio import features
from rasterio.transform import from_bounds, from_origin
from rasterio.warp import reproject, Resampling

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scenario_prep_dem as prep  # noqa: E402
import scenario_depth_plausibility_check as plaus  # noqa: E402  (unconditioned_ground_5m / channel_mask_5m / building_mask_5m)

ROOT = pathlib.Path(__file__).resolve().parent.parent
TO3006 = Transformer.from_crs(4326, 3006, always_xy=True)
TO4326 = Transformer.from_crs(3006, 4326, always_xy=True)
CLASSES = [  # project-defined display intervals (m), RGBA
    (0.05, 0.10, (173, 216, 230, 210), "0.05-0.10 m"), (0.10, 0.30, (107, 174, 214, 225), "0.10-0.30 m"),
    (0.30, 0.50, (33, 113, 181, 235), "0.30-0.50 m"), (0.50, 1e9, (8, 48, 107, 245), "> 0.50 m")]
# Uniform "river" layer colour for burned-channel cells — a hue clearly OUTSIDE the blue depth ramp
# (the site's own brand teal, #087e83), not a lighter/darker blue that could be mistaken for a depth
# class. A darker outline is painted on the river's edge cells for a visible border against both the
# pale background and the darkest (> 0.50 m) blue class.
RIVER_COLOR = (8, 126, 131, 255)
RIVER_OUTLINE_COLOR = (4, 61, 64, 255)
RIVER_LABEL = "River (permanent channel, not depth-classified)"
MASS_COLS = ["t", "dt", "mindt", "nsteps", "area", "vol", "qin", "hds", "qout", "qerr", "verr", "rain"]


def read_asc(path):
    with open(path, encoding="ascii") as f:
        hdr = {k.lower(): float(v) for k, v in (f.readline().split() for _ in range(6))}
        body = f.read()
    a = np.fromstring(body, sep=" ", dtype="float64").astype("float32")
    a = a.reshape(int(hdr["nrows"]), int(hdr["ncols"]))
    return np.where(a <= -9990, np.nan, a), hdr


def write_png(path, rgba):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[r].tobytes() for r in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
                     chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def dilate(m, n):
    out = m.copy()
    for _ in range(n):
        p = np.pad(out, 1)
        out = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] | p[:-2, :-2] | p[2:, 2:] | p[:-2, 2:] | p[2:, :-2]
    return out


def mask_centroid_lonlat(mask, tf):
    rows, cols = np.nonzero(mask)
    x, y = tf * (cols + 0.5, rows + 0.5)
    cx, cy = float(np.mean(x)), float(np.mean(y))
    lon, lat = TO4326.transform(cx, cy)
    return [round(cx), round(cy)], [round(lon, 5), round(lat, 5)]


def locations(tf, shape):
    """Reporting-location masks on the model grid. Lines/points are dilated ~15 m, parking ~5 m."""
    lm = json.load(open(ROOT / "data/scenario/landmarks.json", encoding="utf8"))["landmarks"]
    conv = lambda co: [TO3006.transform(x, y) for x, y in co]
    def rast(geoms, closed):
        return features.rasterize([(g, 1) for g in geoms], out_shape=shape, transform=tf, fill=0, dtype="uint8", all_touched=True).astype(bool)
    line = lambda l: {"type": "LineString", "coordinates": conv(l["coords_lonlat"])}
    poly = lambda l: {"type": "Polygon", "coordinates": [conv(l["coords_lonlat"])]}
    pt = lambda l: {"type": "Point", "coordinates": conv(l["coords_lonlat"])[0]}
    out = {}
    out["Ågatan"] = dilate(rast([line(l) for l in lm if l["name"] == "Ågatan"], False), 3)
    out["Tvärgatan"] = dilate(rast([line(l) for l in lm if l["name"] == "Tvärgatan"], False), 3)
    ica = [l for l in lm if l["group"] == "ICA" and "car park" in l["name"]]
    out["ICA car park"] = dilate(rast([poly(l) for l in ica], True), 1)
    skatt = next(l for l in lm if l["group"] == "skattkistan_forskola")  # resolved via horby.se, Ågatan 2B — see landmarks.json "source"
    out["Skattkistans förskola"] = dilate(rast([pt(skatt)], True), 3)
    return out


def mass_stats(mass_path, total_inflow_vol, sim_s):
    rows = [dict(zip(MASS_COLS, map(float, ln.split()[:12]))) for ln in mass_path.read_text().splitlines()[1:] if ln.strip() and ln.split()[0][0].isdigit()]
    last = rows[-1]
    min_dt = min(r["mindt"] for r in rows)
    t_min = next(r["t"] for r in rows if abs(r["mindt"] - min_dt) < 1e-6)
    ts = np.array([r["t"] for r in rows]); qo = np.array([r["qout"] for r in rows])
    out_vol = float(np.sum((qo[1:] + qo[:-1]) / 2 * np.diff(ts))) if len(rows) > 1 else 0.0  # trapezoid over the 300 s mass rows
    expected = total_inflow_vol - out_vol
    return dict(outflow_volume_m3=round(out_vol), rows=len(rows), last_time_s=last["t"], min_timestep_s=min_dt, time_min_timestep_first_reached_s=t_min,
                mean_timestep_s=round(last["t"] / last["nsteps"], 4), n_timesteps=int(last["nsteps"]),
                final_domain_volume_m3=last["vol"], last_row_Verror_m3=last["verr"], last_row_Qerror=last["qerr"],
                max_abs_Verror_m3_any_row=max(abs(r["verr"]) for r in rows),
                independent_closure_error_m3=round(last["vol"] - expected, 1)), last  # domain volume - (inflow + rain - integrated outflow)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("storm", type=int)
    ap.add_argument("--wall-s", type=float, help="wall-clock seconds of the whole run incl. staging")
    ap.add_argument("--key", help="web results folder name (default <storm>mm), e.g. freeout_70mm")
    a = ap.parse_args()
    od, idir = ROOT / "model/outputs" / a.run, ROOT / "model/inputs" / a.run
    stage = ROOT / "web/data/results" / (a.key or f"{a.storm}mm")
    stage.mkdir(parents=True, exist_ok=True)
    par = dict(ln.split(None, 1) for ln in (idir / f"{a.run}.par").read_text().splitlines() if ln.strip() and not ln.startswith("#") and " " in ln)
    sim_s, saveint = float(par["sim_time"]), float(par["saveint"])
    meta_in = json.loads((idir / "run_metadata.json").read_text(encoding="utf8"))

    # inflow + rain volume for the closure check
    bci = [ln.split() for ln in (idir / f"{a.run}.bci").read_text().splitlines() if ln.startswith("P ")]
    dem, hd = read_asc(idir / f"{a.run}.dem.asc")
    cellsize, x0, y1 = hd["cellsize"], hd["xllcorner"], hd["yllcorner"] + hd["nrows"] * hd["cellsize"]
    tf = from_origin(x0, y1, cellsize, cellsize)
    shape = dem.shape
    if bci and bci[0][3] == "QVAR":
        bdy_vals = {}  # label -> (t_s array, value m3/s array)
        lines = (idir / f"{a.run}.bdy").read_text().splitlines()
        i = 0
        while i < len(lines):
            if lines[i].strip() and not lines[i].startswith("#") and i + 1 < len(lines) and lines[i + 1].split()[0].isdigit():
                label, n = lines[i].strip(), int(lines[i + 1].split()[0])
                rows = [lines[i + 2 + k].split() for k in range(n)]
                bdy_vals[label] = ([float(r[1]) * (60 if lines[i + 1].split()[1].lower().startswith("min") else 1) for r in rows],
                                   [float(r[0]) * cellsize for r in rows])
                i += 2 + n
            else:
                i += 1
        boundary_vol = 0.0
        for b in bci:
            t_s, q = bdy_vals[b[4]]
            t_clamped = [min(t, sim_s) for t in t_s]
            boundary_vol += sum((q[k] + q[k + 1]) / 2 * (t_clamped[k + 1] - t_clamped[k]) for k in range(len(t_s) - 1) if t_clamped[k] < sim_s)
        q_total_display = boundary_vol / sim_s  # average rate, for the same summary field a constant-Q run reports
    else:
        q_total = sum(float(b[4]) * cellsize for b in bci)  # QFIX is m2/s; LISFLOOD multiplies by dx -> m3/s
        boundary_vol = q_total * sim_s
        q_total_display = q_total
    rain_mm = meta_in["rain_mm_in_window"]
    rain_vol = rain_mm / 1000.0 * shape[0] * shape[1] * cellsize ** 2
    total_in = boundary_vol + rain_vol
    ms, last = mass_stats(od / f"{a.run}.mass", total_in, sim_s)
    log = (od / "run.log").read_text(errors="ignore")
    m = re.search(r"Total computation time:\s*([\d.]+)\s*mins", log)
    stats = dict(run=a.run, storm_mm=a.storm, compute_min=float(m.group(1)) if m else None, wall_s_incl_staging=a.wall_s,
                 total_inflow_volume_m3=round(total_in), boundary_inflow_volume_m3=round(boundary_vol),
                 boundary_inflow_mean_rate_m3s=round(q_total_display, 3), effective_rain_volume_m3=round(rain_vol),
                 outflow_boundary=("free outflow along the west edge (LISFLOOD FREE, local slope)" if meta_in.get("west_edge", "closed").startswith("free") else "none (all edges closed; the west outflow is NOT modelled)"), **ms)
    stats["closure_error_pct_of_total_inflow"] = round(100 * abs(ms["independent_closure_error_m3"]) / total_in, 4)
    stats["Verror_pct_of_total_inflow"] = round(100 * abs(ms["last_row_Verror_m3"]) / total_in, 4)

    depth, _ = read_asc(od / f"{a.run}.max")
    maxtm, _ = read_asc(od / f"{a.run}.maxtm")
    tscale = 3600.0 if np.nanmax(maxtm) <= sim_s / 3600.0 * 1.001 else 1.0  # maxtm unit: hours if its range fits 36, else seconds
    stats["maxtm_unit_assumed"] = "hours" if tscale == 3600.0 else "seconds"

    # running-max grids at 2 simulated hours from the snapshots
    steps_dir = od / "maxdepth_steps"
    snaps = sorted(od.glob(f"{a.run}-????.wd"))
    grid_notes = "no snapshots"
    if snaps:
        steps_dir.mkdir(exist_ok=True)
        run_max, written = np.zeros(shape, "float32"), []
        every = max(1, int(round(7200 / saveint))) if saveint <= 7200 else 1  # snapshot k is at t = k * saveint
        for k, p in enumerate(snaps):
            g, _ = read_asc(p)
            run_max = np.fmax(run_max, np.nan_to_num(g, nan=0.0))
            if k % every == 0 and k > 0:
                t_h = k * saveint / 3600
                with rasterio.open(steps_dir / f"maxdepth_to_t{t_h:04.1f}h.tif", "w", driver="GTiff", height=shape[0], width=shape[1], count=1,
                                   dtype="float32", crs="EPSG:3006", transform=tf, nodata=-9999.0, compress="lzw") as d:
                    d.write(run_max, 1)
                written.append(t_h)
        grid_notes = f"{len(written)} running-max grids at t = {written} h from {len(snaps)} snapshots every {saveint:g} s; exact final max is the .max file"
    stats["intermediate_max_grids"] = grid_notes

    # --- Street-surface basis (project-defined, 2026-09-22 depth-plausibility gate): water surface
    # elevation (this run's own conditioned ground + LISFLOOD .max depth) minus the UNCONDITIONED
    # (raw, un-burned, un-raised) DTM, with the burned-channel mask (+1-cell buffer) and building-
    # raised cells excluded. See ASSUMPTIONS.md "Depth-plausibility gate" for why: the raw per-cell
    # LISFLOOD depth and a naive footprint MAX both get swamped by in-channel depth and by the +10 m
    # building-raise artefact.
    full_bounds, _ = prep.domain_bounds(int(round(cellsize)))
    unc_ground = plaus.unconditioned_ground_5m(full_bounds, tf, shape)
    chan_mask = plaus.channel_mask_5m(full_bounds, tf, shape)
    chan_buf = dilate(chan_mask, 1)
    bmask5 = plaus.building_mask_5m(full_bounds, shape)
    excluded = chan_buf | bmask5
    wse = dem + depth
    street_depth = wse - unc_ground

    # EPSG:4326 PNG with exact bounds. Channel cells are excluded from the depth-class ramp and
    # rendered as a separate, uniformly-styled river layer instead (2026-09-22 instruction).
    xs = [x0, x0 + shape[1] * cellsize]
    ys = [y1 - shape[0] * cellsize, y1]
    corners = [TO4326.transform(x, y) for x in xs for y in ys]
    w_, e_ = min(c[0] for c in corners), max(c[0] for c in corners)
    s_, n_ = min(c[1] for c in corners), max(c[1] for c in corners)
    dlat = (cellsize / 2) / 111320.0
    dlon = dlat / np.cos(np.radians((s_ + n_) / 2))
    W, H = int(np.ceil((e_ - w_) / dlon)), int(np.ceil((n_ - s_) / dlat))
    dst_tf = from_bounds(w_, s_, e_, n_, W, H)
    depth_noriver = np.where(chan_mask, np.nan, depth)
    d4326 = np.full((H, W), np.nan, "float32")
    reproject(np.nan_to_num(depth_noriver, nan=-1.0), d4326, src_transform=tf, src_crs="EPSG:3006", dst_transform=dst_tf, dst_crs="EPSG:4326",
              src_nodata=-1.0, dst_nodata=np.nan, resampling=Resampling.nearest)
    river4326 = np.zeros((H, W), "uint8")
    reproject(chan_mask.astype("uint8"), river4326, src_transform=tf, src_crs="EPSG:3006", dst_transform=dst_tf, dst_crs="EPSG:4326",
              src_nodata=0, dst_nodata=0, resampling=Resampling.nearest)
    river_bool = river4326 > 0
    p = np.pad(river_bool, 1)
    river_interior = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]  # all 4 neighbours also river
    river_edge = river_bool & ~river_interior
    rgba = np.zeros((H, W, 4), "uint8")
    for lo, hi, col, _l in CLASSES:
        rgba[(d4326 >= lo) & (d4326 < hi)] = col
    rgba[river_bool] = RIVER_COLOR
    rgba[river_edge] = RIVER_OUTLINE_COLOR
    write_png(stage / "maxdepth.png", rgba)
    (stage / "meta.json").write_text(json.dumps(dict(
        run=a.run, storm_mm=a.storm, crs="EPSG:4326", bounds_west_south_east_north=[w_, s_, e_, n_], png_size_px=[W, H],
        transparent_below_m=0.05, classes=[dict(from_m=lo, to_m=(None if hi > 1e8 else hi), rgba=list(col), label=lab) for lo, hi, col, lab in CLASSES],
        classes_note="Display intervals are project-defined, not standards. Burned-channel cells are excluded from these classes and shown as the separate river layer below.",
        river_layer=dict(rgba=list(RIVER_COLOR), outline_rgba=list(RIVER_OUTLINE_COLOR), label=RIVER_LABEL),
        source_grid_epsg3006=dict(cell_m=cellsize, origin_x=x0, origin_y_top=y1, shape=list(shape)),
        placeholders=("constant placeholder inflows; " if meta_in.get("inflow_is_placeholder", True) else "computed event inflow hydrographs (still a numerical demonstration, not a forecast); ")
                     + "SCS effective rain from one uniform CN; not a flood hazard map"), indent=1), encoding="utf8")

    # impacts at the four reporting locations — project-defined statistics (2026-09-22): p90 of
    # street-surface depth, and wetted fraction (share of remaining cells > 0.05 m), both computed
    # with channel + building-raised cells excluded. The old channel/building-inclusive max is kept
    # under `street_max_m_reference_only` for reference but is not what the site displays.
    masks = locations(tf, shape)
    impacts, resolvable = [], True
    for name, mk in masks.items():
        keep = mk & ~excluded & np.isfinite(street_depth)
        if not keep.any():
            impacts.append(dict(location=name, resolvable=False))
            resolvable = False
            continue
        vals = street_depth[keep]
        p90 = float(np.percentile(vals, 90))
        wetted_frac = float((vals > 0.05).mean())
        d = np.where(keep, street_depth, -1.0)
        r, c = np.unravel_index(int(np.argmax(d)), d.shape)
        ref_max = float(street_depth[r, c])
        centroid_3006, centroid_lonlat = mask_centroid_lonlat(mk, tf)
        # "exceeds 0.05 m" uses the SAME published statistic (p90) as everything else this location displays —
        # not wetted_fraction, which is itself a separate published number, not a threshold test on its own.
        impacts.append(dict(location=name, group=name.split(" (")[0], street_surface_p90_m=round(p90, 3),
                            wetted_fraction=round(wetted_frac, 3), exceeds_0p05_m=bool(p90 > 0.05),
                            street_max_m_reference_only=round(ref_max, 3), time_of_max_h=round(float(maxtm[r, c]) * (tscale / 3600.0), 2),
                            cells_in_footprint=int(mk.sum()), cells_used_after_exclusions=int(keep.sum()),
                            channel_or_building_excluded_cells=int((mk & excluded).sum()),
                            fly_to_epsg3006=centroid_3006, fly_to_lonlat=centroid_lonlat))
    fin0 = street_depth[np.isfinite(street_depth) & ~excluded]
    fin0_old = depth[np.isfinite(depth)]  # old, unfiltered basis — kept only for the ASSUMPTIONS.md old-vs-new record
    if meta_in.get("inflow_m3s_constant"):
        inflow_summary = dict(type="constant placeholder", m3s=meta_in["inflow_m3s_constant"])
    else:
        hy = json.loads((ROOT / "data/scenario/derived/inflow_hydrographs_summary.json").read_text(encoding="utf8"))["storms"][str(a.storm)]
        inflow_summary = dict(type="event hydrograph (SCS-CN + SCS UH + station-2128 baseflow)",
                              peak_m3s={"east inflow (Hörbyån mainstem)": hy["east"]["peak_total_m3s"], "south inflow (southern arm)": hy["south"]["peak_total_m3s"]})
    summary = dict(sim_hours=sim_s / 3600, effective_rain_mm=round(rain_mm, 1), storm_mm=a.storm, boundary=meta_in.get("west_edge", "closed"),
                   inflow=inflow_summary,
                   area_stats_basis="street-surface depth (unconditioned ground), channel mask + 1-cell buffer and building-raised cells excluded from the domain before these areas are computed",
                   wet_area_gt_0p05_km2=round(float((fin0 > 0.05).sum() * cellsize ** 2 / 1e6), 3),
                   area_gt_0p3_km2=round(float((fin0 > 0.3).sum() * cellsize ** 2 / 1e6), 3), area_gt_0p5_km2=round(float((fin0 > 0.5).sum() * cellsize ** 2 / 1e6), 3),
                   area_stats_old_basis_reference_only=dict(
                       note="OLD basis (raw LISFLOOD depth above conditioned ground, whole domain incl. channel+buildings) — kept for the ASSUMPTIONS.md before/after record only",
                       wet_area_gt_0p05_km2=round(float((fin0_old > 0.05).sum() * cellsize ** 2 / 1e6), 3),
                       area_gt_0p3_km2=round(float((fin0_old > 0.3).sum() * cellsize ** 2 / 1e6), 3),
                       area_gt_0p5_km2=round(float((fin0_old > 0.5).sum() * cellsize ** 2 / 1e6), 3)),
                   domain_km2=round(shape[0] * shape[1] * cellsize ** 2 / 1e6, 2), max_depth_m=round(float(fin0_old.max()), 2), cell_m=cellsize)
    (stage / "impacts.json").write_text(json.dumps(dict(
        run=a.run, storm_mm=a.storm, summary=summary,
        note="Published statistics are project-defined (2026-09-22 depth-plausibility gate): street_surface_p90_m = 90th percentile of "
             "street-surface depth over the footprint (channel mask + 1-cell buffer and building-raised cells excluded); wetted_fraction = "
             "share of those remaining cells deeper than 0.05 m. street_max_m_reference_only is kept for reference but not displayed. "
             "fly_to_* is the footprint CENTROID, not the deepest cell (which may sit in the channel). "
             "Skattkistans förskola resolved via horby.se (Ågatan 2B); street-level geocode, see data/scenario/landmarks.json",
        locations=impacts), indent=1, ensure_ascii=False), encoding="utf8")

    # criteria C1-C7
    xy = [(float(b[1]), float(b[2])) for b in bci]
    near = []
    for x, y in xy:
        c0, r0 = int((x - x0) / cellsize), int((y1 - y) / cellsize)
        blk = depth[max(0, r0 - 3): r0 + 4, max(0, c0 - 3): c0 + 4]
        near.append(float(np.nanmax(blk)))
    fin = depth[np.isfinite(depth)]
    crit = {
        "C1 completion": dict(passed=bool(m and stats["last_time_s"] >= sim_s - 1), value=f"last row t={stats['last_time_s']:.0f} s of {sim_s:.0f}; 'Total computation time' {'found' if m else 'missing'}"),
        "C2 mass balance <=1% of total inflow": dict(passed=bool(stats["closure_error_pct_of_total_inflow"] <= 1 and stats["Verror_pct_of_total_inflow"] <= 1),
                                                     value=f"independent closure {stats['closure_error_pct_of_total_inflow']} %, last-row Verror {stats['Verror_pct_of_total_inflow']} % of {total_in:,.0f} m3"),
        "C3 wall-clock <=2 h": dict(passed=bool((a.wall_s or (stats['compute_min'] or 1e9) * 60) <= 7200), value=f"{(a.wall_s or 0):.0f} s wall (incl. staging); {stats['compute_min']} min compute"),
        "C4 min timestep >=0.1 s": dict(passed=bool(stats["min_timestep_s"] >= 0.1), value=f"{stats['min_timestep_s']} s first reached at t={stats['time_min_timestep_first_reached_s']:.0f} s"),
        "C5 valid grids": dict(passed=bool(np.isfinite(depth).all() and (fin >= 0).all() and depth.shape == dem.shape), value=f"shape {depth.shape}, min {fin.min():.3f}, max {fin.max():.2f} m, nan {int((~np.isfinite(depth)).sum())}"),
        "C6 inflow cells <=3 m": dict(passed=bool(max(near) <= 3.0), value=f"max depth within 15 m of the inflow points: {[round(v, 2) for v in near]} m"),
        "C7 reporting locations resolvable": dict(passed=resolvable, value=f"{len(impacts)} location footprints, all inside domain: {resolvable}"),
    }
    stats["stats_source"] = "computed by scripts/scenario_postprocess_run.py"
    (od / "run_stats.json").write_text(json.dumps(stats, indent=1, default=str, ensure_ascii=False), encoding="utf8")
    (od / "criteria.json").write_text(json.dumps(crit, indent=1, ensure_ascii=False), encoding="utf8")
    mf = [dict(key=d.parent.name, storm_mm=json.loads(d.read_text(encoding="utf8"))["storm_mm"], run=json.loads(d.read_text(encoding="utf8"))["run"])
          for d in sorted((ROOT / "web/data/results").glob("*/meta.json"))]
    (ROOT / "web/data/results/manifest.json").write_text(json.dumps(dict(scenarios=mf), indent=1), encoding="utf8")  # the web page lists only finished runs
    print(json.dumps(dict(stats=stats, criteria=crit, impacts=impacts), indent=1, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
