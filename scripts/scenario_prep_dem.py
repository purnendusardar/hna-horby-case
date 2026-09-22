"""Mosaic, clip, check and condition the 1 m Lantmäteriet DEM for the Hörby model.

Runs in the data-prep venv only (rasterio/numpy/pyproj, see requirements-dataprep.txt):
    .venv\\Scripts\\python.exe scripts\\scenario_prep_dem.py [--cell 5] [--glo30 path]

Heights stay in RH 2000 exactly as delivered. No geoid conversion and no display
tiles here (post-launch, see LAUNCH_CHECKLIST.md).

Steps: mosaic the six mhm-61_4 tiles -> clip to AOI + 500 m (EPSG:3006) -> condition at
1 m (channels, buildings; brief 4.5) -> aggregate to the model cell size for two domains:
"aoi" (full AOI, extended just enough to hold the three river boundary points) and
"core" (same, north edge trimmed to the landmarks + 200 m). Channel cells aggregate by
MINIMUM so the burned channel survives coarsening; everything else by mean.

Channel burn depths (2026-09-22 release batch) are bankfull depths solved from Manning's
equation by scripts/scenario_channel_capacity.py, per reach, not one uniform value for the
whole mainstem — see EAST_ARM_SPEC / BELOW_CONFLUENCE_SPEC / SOUTH_ARM_SPEC below.
"""
import argparse
import json
import math
import os
import pathlib

for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):  # machine-scope values point at PostgreSQL 18's older copies
    os.environ.pop(_v, None)

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio import features
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import reproject

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data/scenario/raw"
OUT = ROOT / "data/scenario/derived"
WEB = ROOT / "web/data"
AOI_WGS84 = (13.64, 55.84, 13.685, 55.865)  # W, S, E, N — same bbox as fetch_geography.py
BOUNDARY_POINTS = {  # scenarios.yaml inflow.boundary_inflows / boundary_outflow (lat, lon)
    "east inflow": (55.84823, 13.68501), "south inflow": (55.83990, 13.66812), "west outflow": (55.84508, 13.63971)}
CONFLUENCE = (55.84725, 13.66771)
BUFFER_M = 500.0
BOUNDARY_PAD_M = 15.0  # boundary points must sit inside the domain with room for a source cell
CORE_MARGIN_M = 200.0

# Channel dimensions from scripts/scenario_channel_capacity.py: bankfull (Manning's equation, n=0.035,
# trapezoidal 6 m bottom width, banks 1:2) sized so capacity equals each reach's S-HYPE mean high flow.
# Width 6 m throughout (the Lantmäteriet breakgeometry asset that could give a measured width is not
# accessible — HTTP 401, same credentials that fail the DEM download — see ASSUMPTIONS.md).
SPLIT_WAY = 77387390          # "Hörbyån": one OSM way spanning BOTH the east arm and the below-confluence reach
EAST_ARM_SPEC = dict(width=6.0, depth=0.585)          # Q=6.25 m3/s, slope 0.00712 (AOI edge -> confluence)
BELOW_CONFLUENCE_SPEC = dict(width=6.0, depth=1.404)  # Q=11.01 m3/s, slope 0.00096 (confluence -> west edge)
SOUTH_ARM_WAYS = {77387397}
SOUTH_ARM_SPEC = dict(width=6.0, depth=0.571)         # Q=4.76 m3/s, slope 0.00449 (AOI edge -> confluence)
OTHER_WATERWAY = dict(width=1.5, depth=0.5)
WATERWAY_TYPES = {"river", "stream", "drain", "ditch"}  # weirs are not channels
BANK_RUN_PER_RISE = 2.0  # 1:2
BUILDING_RAISE_M = 10.0
BUILDING_COVER_MIN = 0.5
LC_GROUPS = {
    "built-up (51 building, 52 anlagd mark)": lambda a: (a == 51) | (a == 52),
    "road/rail (53)": lambda a: a == 53,
    "forest (111-128)": lambda a: (a >= 111) & (a <= 128),
    "open land (3 arable, 411, 42xx)": lambda a: (a == 3) | (a == 411) | ((a >= 4211) & (a <= 4233)),
}
TO3006 = Transformer.from_crs(4326, 3006, always_xy=True)


def snap(v, k, f):
    return f(v / k) * k


def aoi_bounds_3006():
    w, s, e, n = AOI_WGS84
    xs, ys = zip(*[TO3006.transform(x, y) for x, y in [(w, s), (w, n), (e, s), (e, n)]])
    return min(xs), min(ys), max(xs), max(ys)


def domain_bounds(k):
    """(aoi, core) model-domain bounds in EPSG:3006, snapped outward to multiples of k."""
    x0, y0, x1, y1 = aoi_bounds_3006()
    for lat, lon in BOUNDARY_POINTS.values():
        px, py = TO3006.transform(lon, lat)
        x0, y0, x1, y1 = min(x0, px - BOUNDARY_PAD_M), min(y0, py - BOUNDARY_PAD_M), max(x1, px + BOUNDARY_PAD_M), max(y1, py + BOUNDARY_PAD_M)
    full = (snap(x0, k, math.floor), snap(y0, k, math.floor), snap(x1, k, math.ceil), snap(y1, k, math.ceil))
    lm = json.load(open(ROOT / "data/scenario/landmarks.json", encoding="utf8"))["landmarks"]
    top = [TO3006.transform(x, y)[1] for l in lm for x, y in l["coords_lonlat"]]
    top.append(TO3006.transform(CONFLUENCE[1], CONFLUENCE[0])[1])
    core_n = min(full[3], snap(max(top) + CORE_MARGIN_M, k, math.ceil))
    return full, (full[0], full[1], full[2], core_n)


def clip_bounds():
    b = aoi_bounds_3006()
    b = (b[0] - BUFFER_M, b[1] - BUFFER_M, b[2] + BUFFER_M, b[3] + BUFFER_M)
    return tuple(snap(v, 10, f) for v, f in zip(b, (math.floor, math.floor, math.ceil, math.ceil)))  # multiple of 10: aligns 2/5/10 m blocks


def mosaic_clip(bounds):
    srcs = [rasterio.open(p) for p in sorted(RAW.glob("*_25.tif"))]
    arr, tf = merge(srcs, bounds=bounds, res=1.0, nodata=srcs[0].nodata, resampling=Resampling.nearest)
    meta = {"crs": srcs[0].crs, "nodata": srcs[0].nodata, "n_tiles": len(srcs)}
    for s in srcs:
        s.close()
    return arr[0].astype("float32"), tf, meta


def block(a, k, fn):
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    return fn(a[:h, :w].reshape(h // k, k, w // k, k), axis=(1, 3))


def write_tif(path, arr, tf, crs):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype="float32", crs=crs, transform=tf, nodata=-9999.0, compress="lzw", predictor=3, tiled=True) as d:
        d.write(np.where(np.isnan(arr), -9999.0, arr).astype("float32"), 1)


def write_asc(path, arr, tf):
    res = tf.a
    with open(path, "w", newline="\n") as f:
        f.write(f"ncols {arr.shape[1]}\nnrows {arr.shape[0]}\nxllcorner {tf.c:.3f}\n"
                f"yllcorner {tf.f - arr.shape[0] * res:.3f}\ncellsize {res:g}\nNODATA_value -9999\n")
        np.savetxt(f, np.where(np.isnan(arr), -9999.0, arr), fmt="%.2f")


def glo30_check(dem1m, tf1, crs, glo):
    """GLO-30 (DSM, EGM2008) minus the block-averaged 1 m DTM on the existing 10 m land-cover grid, per land-cover group."""
    with rasterio.open(WEB / "scenario_landcover.tif") as lc:
        lcv, ltf, lcrs, shape = lc.read(1), lc.transform, lc.crs, (lc.height, lc.width)
    mine = np.full(shape, np.nan, "float32")
    reproject(dem1m, mine, src_transform=tf1, src_crs=crs, dst_transform=ltf, dst_crs=lcrs,
              src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.average)
    theirs = np.full(shape, np.nan, "float32")
    with rasterio.open(glo) as g:
        reproject(rasterio.band(g, 1), theirs, dst_transform=ltf, dst_crs=lcrs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    diff = theirs - mine
    ok = np.isfinite(diff)
    rows = {"all valid cells": ok}
    rows.update({k: ok & f(lcv) for k, f in LC_GROUPS.items()})
    return {k: dict(n=int(m.sum()), mean=round(float(diff[m].mean()), 2), median=round(float(np.median(diff[m])), 2),
                    sd=round(float(diff[m].std()), 2)) for k, m in rows.items()}


def line_samples(coords, step=1.0):
    pts = np.asarray(coords, float)
    cum = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    t = np.arange(0, cum[-1], step)
    return np.c_[np.interp(t, cum, pts[:, 0]), np.interp(t, cum, pts[:, 1])]


def condition_1m(dem, tf):
    """Channel burn + building mask on the 1 m grid. Returns (burned DEM without buildings, burned mask, building mask, report)."""
    out = dem.copy()
    inv = ~tf
    g = json.load(open(WEB / "geography.geojson", encoding="utf8"))
    road_ok = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service", "trunk_link"}
    rmask = features.rasterize(
        [({"type": "LineString", "coordinates": [TO3006.transform(x, y) for x, y in ft["geometry"]["coordinates"]]}, 1)
         for ft in g["features"] if ft["properties"].get("highway") in road_ok],
        out_shape=dem.shape, transform=tf, fill=0, dtype="uint8", all_touched=True).astype(bool)

    burned = np.zeros(dem.shape, bool)
    lines, crossings, reversed_n = [], 0, 0

    def burn_segment(coords_lonlat, spec, waterway, osm_id, tunnel, reach_label):
        nonlocal crossings, reversed_n
        pts = line_samples([TO3006.transform(x, y) for x, y in coords_lonlat])
        cols, rows = inv * (pts[:, 0], pts[:, 1])
        inside = (cols >= 0) & (cols < dem.shape[1]) & (rows >= 0) & (rows < dem.shape[0])
        if inside.sum() < 5:
            return
        pts, ci, ri = pts[inside], cols[inside].astype(int), rows[inside].astype(int)
        z = dem[ri, ci].astype("float64")
        n_end = min(10, len(z) // 2)
        if z[:n_end].mean() < z[-n_end:].mean():  # orient each line downhill instead of trusting OSM way direction
            pts, ci, ri, z = pts[::-1], ci[::-1], ri[::-1], z[::-1]
            reversed_n += 1
        win = 15  # +-15 m reaches under embankments, so the bed carries through road/rail crossings (culverts, bridges)
        zmin = np.array([z[max(0, i - win): i + win + 1].min() for i in range(len(z))])
        bed = np.minimum.accumulate(zmin) - spec["depth"]
        half = spec["width"] / 2.0
        reach = half + BANK_RUN_PER_RISE * 3.0
        rr = int(math.ceil(reach))
        for (x, y), bz, c0, r0 in zip(pts, bed, ci, ri):
            r_lo, r_hi, c_lo, c_hi = max(0, r0 - rr), min(dem.shape[0], r0 + rr + 1), max(0, c0 - rr), min(dem.shape[1], c0 + rr + 1)
            cc, rw = np.meshgrid(np.arange(c_lo, c_hi), np.arange(r_lo, r_hi))
            cx, cy = tf * (cc + 0.5, rw + 0.5)
            d = np.hypot(cx - x, cy - y)
            zt = bz + np.maximum(0.0, d - half) / BANK_RUN_PER_RISE
            sub = out[r_lo:r_hi, c_lo:c_hi]
            m = (d <= reach) & (zt < sub)
            sub[m] = zt[m]
            burned[r_lo:r_hi, c_lo:c_hi] |= m
        crossings += int(rmask[ri, ci].any())
        lines.append((waterway, osm_id, reach_label, tunnel, len(pts)))

    def split_at_confluence(coords_lonlat):
        cx, cy = TO3006.transform(CONFLUENCE[1], CONFLUENCE[0])
        pts3006 = [TO3006.transform(x, y) for x, y in coords_lonlat]
        d2 = [(x - cx) ** 2 + (y - cy) ** 2 for x, y in pts3006]
        return d2.index(min(d2))

    for ft in g["features"]:
        p = ft["properties"]
        if p.get("waterway") not in WATERWAY_TYPES:
            continue
        coords = ft["geometry"]["coordinates"]
        tunnel = bool(p.get("tunnel"))
        if p["osm_id"] == SPLIT_WAY:
            i = split_at_confluence(coords)
            burn_segment(coords[:i + 1], EAST_ARM_SPEC, p["waterway"], p["osm_id"], tunnel, "east arm (bankfull-sized)")
            burn_segment(coords[i:], BELOW_CONFLUENCE_SPEC, p["waterway"], p["osm_id"], tunnel, "below confluence (bankfull-sized)")
        elif p["osm_id"] in SOUTH_ARM_WAYS:
            burn_segment(coords, SOUTH_ARM_SPEC, p["waterway"], p["osm_id"], tunnel, "south arm (bankfull-sized)")
        else:
            burn_segment(coords, OTHER_WATERWAY, p["waterway"], p["osm_id"], tunnel, "other")

    b = json.load(open(WEB / "scenario_buildings.geojson", encoding="utf8"))
    shapes = [({"type": "Polygon", "coordinates": [[TO3006.transform(x, y) for x, y in ft["geometry"]["coordinates"][0]]]}, 1)
              for ft in b["features"]]
    bmask = features.rasterize(shapes, out_shape=dem.shape, transform=tf, fill=0, dtype="uint8").astype(bool)
    rep = dict(channel_lines=len(lines), main_arm_lines=sum(1 for l in lines if l[2] != "other"),
               segments_by_reach={lbl: sum(1 for l in lines if l[2] == lbl) for lbl in sorted({l[2] for l in lines})},
               culvert_segments_burned=sum(1 for l in lines if l[3]), lines_reversed_to_flow_downhill=reversed_n,
               lines_touching_a_road=crossings, burned_cells_1m=int(burned.sum()), building_footprints=len(shapes),
               building_cells_1m=int(bmask.sum()), max_cut_m=round(float(np.nanmax(dem - out)), 2))
    return out, burned, bmask, rep


def to_model_grid(cond, burned, bmask, tf1, bounds, k):
    """Crop to `bounds` and aggregate to k m: mean, but MIN where any 1 m channel cell falls in the block; buildings +10 m if >=50 % covered."""
    x0, y0, x1, y1 = bounds
    c0, r0 = int(round((x0 - tf1.c) / 1.0)), int(round((tf1.f - y1) / 1.0))
    nc, nr = int(round((x1 - x0))), int(round((y1 - y0)))
    sl = (slice(r0, r0 + nr), slice(c0, c0 + nc))
    z, bu, bl = cond[sl], burned[sl], bmask[sl]
    out = block(z, k, np.mean)
    has_ch = block(bu.astype("uint8"), k, np.max).astype(bool)
    out = np.where(has_ch, block(np.where(bu, z, np.inf), k, np.min), out)
    out = np.where(block(bl.astype("float32"), k, np.mean) >= BUILDING_COVER_MIN, out + BUILDING_RAISE_M, out)
    return out.astype("float32"), from_origin(x0, y1, k, k), int(has_ch.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", type=int, default=5, help="model cell size in metres (divides 10)")
    ap.add_argument("--glo30", help="path to the Copernicus GLO-30 N55E013 tile for the sanity check")
    args = ap.parse_args()
    k = args.cell
    OUT.mkdir(parents=True, exist_ok=True)

    cb = clip_bounds()
    dem1, tf1, meta = mosaic_clip(cb)
    if meta["nodata"] is not None:
        dem1[dem1 == meta["nodata"]] = np.nan
    write_tif(OUT / "dem_rh2000_1m_clip.tif", dem1, tf1, meta["crs"])
    report = dict(tiles=meta["n_tiles"], src_crs=meta["crs"].to_string(), clip_bounds_3006=cb, buffer_m=BUFFER_M,
                  shape_1m=list(dem1.shape), nan_cells_1m=int(np.isnan(dem1).sum()),
                  z_min=round(float(np.nanmin(dem1)), 2), z_max=round(float(np.nanmax(dem1)), 2))
    if args.glo30:
        report["glo30_minus_lm_dtm"] = glo30_check(dem1, tf1, meta["crs"], args.glo30)

    cond, burned, bmask, rep = condition_1m(dem1, tf1)
    report["conditioning_1m"] = rep
    # Persisted so scripts/scenario_apply_culvert_cuts.py can edit `cond` directly and re-run the exact
    # same aggregation (to_model_grid) below, rather than re-deriving the 1 m conditioned state by hand.
    np.savez(OUT / "dem_1m_conditioned_state.npz", cond=cond.astype("float32"), burned=burned, bmask=bmask)
    full, core = domain_bounds(k)
    report["cell_m"] = k
    for name, b in (("aoi", full), ("core", core)):
        arr, tf, n_ch = to_model_grid(cond, burned, bmask, tf1, b, k)
        write_tif(OUT / f"dem_rh2000_{k}m_{name}_conditioned.tif", arr, tf, meta["crs"])
        write_asc(OUT / f"dem_rh2000_{k}m_{name}_conditioned.asc", arr, tf)
        report[name] = dict(bounds_3006=[round(v, 1) for v in b], shape=list(arr.shape), area_km2=round(arr.size * k * k / 1e6, 3), channel_cells=n_ch)
    report["core_area_fraction_of_aoi"] = round(report["core"]["area_km2"] / report["aoi"]["area_km2"], 3)
    (OUT / "dem_prep_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
