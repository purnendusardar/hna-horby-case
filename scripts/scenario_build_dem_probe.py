"""Stage a LISFLOOD-FP run (speed probe or pilot) on the conditioned DEM.

Runs in the data-prep venv after scripts/scenario_prep_dem.py:
    .venv\\Scripts\\python.exe scripts\\scenario_build_dem_probe.py --domain aoi --cell 5 --storm 70 --hours 2 --window peak
    .venv\\Scripts\\python.exe scripts\\scenario_build_dem_probe.py --domain aoi --cell 5 --storm 70 --hours 36 --window full --name pilot_...

Inputs mirror the earlier pilot (Manning from NMD class, uniform rain, `acceleration`
solver). --window peak = the sim-length window of the design storm with the largest
total; --window full = storm from t=0, then dry. Land cover has no cells outside the
AOI, so those get the grass/agricultural default n. Boundary inflows are constant point
sources at the two Hörbyån inflow points by default (--q), or the computed event
hydrograph (--bdy, QVAR from data/scenario/derived/hydrograph_<storm>mm.bdy — SCS-CN +
SCS unit hydrograph + station-2128 baseflow, see ASSUMPTIONS.md "Release batch"). Use
--free-west for the production boundary condition (everything else closed edges).
"""
import argparse
import csv
import json
import os
import pathlib
import sys

for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import numpy as np
import rasterio
from pyproj import Transformer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import model_build_pilot_inputs as pilot  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
TO3006 = Transformer.from_crs(4326, 3006, always_xy=True)
INFLOWS = {"east inflow (Hörbyån mainstem)": (55.84823, 13.68501), "south inflow (southern arm)": (55.83990, 13.66812)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", choices=["aoi", "core"], required=True)
    ap.add_argument("--cell", type=int, default=5)
    ap.add_argument("--storm", type=int, choices=[40, 70, 100], default=70)
    ap.add_argument("--hours", type=float, default=2)
    ap.add_argument("--window", choices=["peak", "full"], default="peak")
    ap.add_argument("--q", type=float, nargs=2, default=[30.0, 20.0], help="constant inflow, m3/s (east, south) — ignored if --bdy is given")
    ap.add_argument("--bdy", action="store_true", help="use the computed event hydrograph (data/scenario/derived/hydrograph_<storm>mm.bdy, QVAR) instead of a constant --q")
    ap.add_argument("--cn", type=float, help="apply SCS losses with this uniform Curve Number (default: raw rain)")
    ap.add_argument("--free-west", action="store_true", help="free (normal-depth) outflow along the whole west edge, where Hörbyån leaves the domain")
    ap.add_argument("--name")
    ap.add_argument("--saveint", type=int, default=3600)
    a = ap.parse_args()
    sim_s = int(a.hours * 3600)
    run = a.name or f"probe_{a.domain}_{a.cell}m_{a.storm}mm_{a.hours:g}h"
    out = ROOT / "model/inputs" / run
    out.mkdir(parents=True, exist_ok=True)

    der = ROOT / "data/scenario/derived"
    stem = f"dem_rh2000_{a.cell}m_{a.domain}_conditioned"
    (out / f"{run}.dem.asc").write_bytes((der / f"{stem}.asc").read_bytes())
    with rasterio.open(der / f"{stem}.tif") as d:
        tf, shape = d.transform, (d.height, d.width)

    kinds = {c["value"]: c["kind"] for c in json.loads(pilot.LANDCOVER_CLASSES_JSON.read_text(encoding="utf-8"))["classes"]}
    n_by_val = {v: (pilot.MANNING_FOREST if v in pilot.FOREST_NMD_VALUES else
                    pilot.MANNING_SEALED if k == "sealed" else pilot.MANNING_GRASS_OR_CHANNEL) for v, k in kinds.items()}
    with rasterio.open(ROOT / "web/data/scenario_landcover.tif") as lc:
        lcv, lct = lc.read(1), lc.transform
    rows, cols = np.indices(shape)
    x, y = tf * (cols + 0.5, rows + 0.5)
    lc_c, lc_r = ~lct * (x, y)
    lc_c, lc_r = np.floor(lc_c).astype(int), np.floor(lc_r).astype(int)
    inside = (lc_c >= 0) & (lc_c < lcv.shape[1]) & (lc_r >= 0) & (lc_r < lcv.shape[0])
    vals = np.where(inside, lcv[np.clip(lc_r, 0, lcv.shape[0] - 1), np.clip(lc_c, 0, lcv.shape[1] - 1)], 0)
    lut = np.full(int(max(max(n_by_val), vals.max())) + 1, pilot.MANNING_GRASS_OR_CHANNEL)
    for v, n in n_by_val.items():
        lut[v] = n
    with open(out / f"{run}.n", "w", newline="\n") as f:
        f.write(f"ncols {shape[1]}\nnrows {shape[0]}\nxllcorner {tf.c:.3f}\nyllcorner {tf.f - shape[0] * tf.a:.3f}\ncellsize {tf.a:g}\nNODATA_value -9999\n")
        np.savetxt(f, lut[vals], fmt="%g")

    hy = list(csv.DictReader((ROOT / f"docs/hyetographs/hyetograph_{a.storm}mm.csv").open(encoding="utf-8")))
    step = float(hy[0]["t_end_min"]) - float(hy[0]["t_start_min"])
    inten = np.array([float(r["intensity_mm_per_h"]) for r in hy])
    if a.window == "peak":
        k = int(round(sim_s / 60 / step))
        i0 = int(np.convolve(inten, np.ones(k), "valid").argmax())
        sel, t0 = hy[i0:i0 + k], float(hy[i0]["t_start_min"])
    else:
        sel, t0 = hy, 0.0
    depth = np.array([float(r["block_depth_mm"]) for r in sel])
    if a.cn:  # SCS effective rain from cumulative storm depth, one spatially uniform CN (pilot simplification)
        s_mm = 25400.0 / a.cn - 254.0
        cum = np.cumsum(depth)
        q_cum = np.where(cum > 0.2 * s_mm, (cum - 0.2 * s_mm) ** 2 / (cum + 0.8 * s_mm), 0.0)
        depth = np.diff(np.r_[0.0, q_cum])
    with open(out / f"{run}.rain", "w", newline="\n") as f:
        f.write(f"{a.storm} mm design storm, window={a.window}, spatially uniform"
                f"{f', SCS effective rain CN={a.cn:g}' if a.cn else ', raw rain (no losses)'}\n{len(sel) + 1} minutes\n")
        for r, d in zip(sel, depth):
            f.write(f"{d / step * 60:.4f} {float(r['t_start_min']) - t0:g}\n")
        f.write(f"0.0 {float(sel[-1]['t_end_min']) - t0:g}\n")
    mm = float(depth.sum())

    bdy_labels = {"east inflow (Hörbyån mainstem)": "east184", "south inflow (southern arm)": "south64474"}
    with open(out / f"{run}.bci", "w", newline="\n") as f:
        if a.bdy:
            bdy_src = ROOT / f"data/scenario/derived/hydrograph_{a.storm}mm.bdy"
            (out / f"{run}.bdy").write_bytes(bdy_src.read_bytes())
            for name, (lat, lon) in INFLOWS.items():
                px, py = TO3006.transform(lon, lat)
                f.write(f"P {px:.1f} {py:.1f} QVAR {bdy_labels[name]}\n")
        else:
            for (name, (lat, lon)), q in zip(INFLOWS.items(), a.q):
                px, py = TO3006.transform(lon, lat)
                f.write(f"P {px:.1f} {py:.1f} QFIX {q / a.cell:.6g}\n")  # LISFLOOD-FP multiplies point-source QFIX by dx (iterateq.cpp): file value is m2/s
        if a.free_west:  # brief 4.4: downstream boundary is free outflow. LISFLOOD syntax: side, start, end northing, FREE [slope]; no slope = local slope
            f.write(f"W {tf.f - shape[0] * tf.a:.1f} {tf.f:.1f} FREE\n")
    bdyfile_line = f"bdyfile {run}.bdy\n" if a.bdy else ""
    (out / f"{run}.par").write_text(
        f"DEMfile {run}.dem.asc\nresroot {run}\ndirroot results\nsim_time {sim_s}\ninitial_tstep 1\n"
        f"massint 300\nsaveint {a.saveint}\nmanningfile {run}.n\nrainfall {run}.rain\nbcifile {run}.bci\n{bdyfile_line}fpfric 0.035\nacceleration\n",
        encoding="ascii")
    (out / "run_metadata.json").write_text(json.dumps(dict(
        run=run, domain=a.domain, cell_m=a.cell, shape=list(shape), storm_mm=a.storm, sim_hours=a.hours, rain_window=a.window,
        rain_mm_in_window=round(mm, 1),
        inflow=(f"event hydrograph, data/scenario/derived/hydrograph_{a.storm}mm.bdy (SCS-CN + SCS UH + station-2128 baseflow)" if a.bdy
                else "constant placeholder"),
        inflow_m3s_constant=(None if a.bdy else dict(zip(INFLOWS, a.q))),
        dem="Lantmateriet 1 m (mhm-61_4, scan 2025-02-18), RH 2000, conditioned (per-reach bankfull channel + 2 confirmed culvert cuts, 2026-09-22), no geoid conversion",
        west_edge="free outflow (FREE, local slope)" if a.free_west else "closed",
        inflow_is_placeholder=not a.bdy, usable_for_flood_analysis=False), indent=2), encoding="utf8")
    print(f"staged {run}: {shape[1]}x{shape[0]} cells @ {tf.a:g} m, {a.window} rain window {mm:.1f} mm, sim {a.hours:g} h")


if __name__ == "__main__":
    main()
