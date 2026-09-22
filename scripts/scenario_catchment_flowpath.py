"""Longest flow path (ell) and mean catchment slope (Y) for the NRCS lag equation,
from Copernicus GLO-30, for each Hörbyån inflow catchment.

**Limitation, stated per the release instructions, not a validated parameter:** the NRCS lag
equation (NEH Part 630, Ch. 15) is developed and validated for SMALL catchments, typically a few
hundred to a few thousand acres (roughly <8 km2 in common practice guidance). Both catchments here
(60-77 km2) are one to two orders of magnitude larger. The result below is a documented
extrapolation outside the equation's usual range, not a calibrated lag time.

Method: reproject the GLO-30 tile (EPSG:4326) to EPSG:3006 at native ~30 m resolution over each
catchment's extent -> priority-flood fill -> D8 flow directions -> mean slope from the filled DEM's
gradient -> longest flow path as the maximum flow-length-to-outlet, computed by a single
topological (ascending-elevation) dynamic-programming pass over the D8 tree (exact for a
DEM-derived flow network, not a straight-line or main-channel-only approximation).

Runs in the data-prep venv, after scripts/scenario_catchment_cn.py (reuses its catchment geometries):
    .venv\\Scripts\\python.exe scripts\\scenario_catchment_flowpath.py
"""
import heapq
import json
import math
import os
import pathlib

for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio import features
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject, Resampling

ROOT = pathlib.Path(__file__).resolve().parent.parent
GLO30 = ROOT / "data/scenario/raw/Copernicus_DSM_COG_10_N55_00_E013_00_DEM.tif"
OUT_DIR = ROOT / "data/scenario/derived"
CELL_M = 30.0
NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
TO3006 = Transformer.from_crs(4326, 3006, always_xy=True)

INFLOW_POINTS = {"east_184": (55.84823, 13.68501), "south_64474": (55.83990, 13.66812)}  # (lat, lon)


def fill(dem):
    h, w = dem.shape
    z = dem.astype("float64").copy()
    seen = np.zeros(dem.shape, bool)
    heap = []
    for r in range(h):
        for c in (0, w - 1):
            heapq.heappush(heap, (z[r, c], r, c)); seen[r, c] = True
    for c in range(1, w - 1):
        for r in (0, h - 1):
            heapq.heappush(heap, (z[r, c], r, c)); seen[r, c] = True
    while heap:
        zc, r, c = heapq.heappop(heap)
        for dr, dc in NB:
            rr, cc = r + dr, c + dc
            if 0 <= rr < h and 0 <= cc < w and not seen[rr, cc]:
                seen[rr, cc] = True
                z[rr, cc] = max(z[rr, cc], zc + 1e-4)
                heapq.heappush(heap, (z[rr, cc], rr, cc))
    return z


def d8_down(z, cell):
    h, w = z.shape
    best = np.full(z.shape, -np.inf)
    down = np.full(z.shape, -1, dtype=np.int64)
    down_dist = np.zeros(z.shape)
    idx = np.arange(h * w).reshape(h, w)
    for dr, dc in NB:
        dist = math.hypot(dr, dc) * cell
        zn = np.full(z.shape, np.inf)
        rs, re = max(0, -dr), h - max(0, dr)
        cs, ce = max(0, -dc), w - max(0, dc)
        zn[rs:re, cs:ce] = z[rs + dr:re + dr, cs + dc:ce + dc]
        slope = (z - zn) / dist
        take = slope > best
        best = np.where(take, slope, best)
        nid = np.full(z.shape, -1, dtype=np.int64)
        nid[rs:re, cs:ce] = idx[rs + dr:re + dr, cs + dc:ce + dc]
        down = np.where(take & (slope > 0), nid, down)
        down_dist = np.where(take & (slope > 0), dist, down_dist)
    return down, down_dist


def mean_slope_pct(z, cell, mask=None):
    gy, gx = np.gradient(z, cell)
    sl = np.hypot(gx, gy) * 100
    return float(sl[mask].mean()) if mask is not None else float(sl.mean())


def flow_length_to_mask_exit(z, down, down_dist, mask):
    """Flow-path length from each cell to the point its D8 path first leaves `mask` (the catchment) —
    not to a terminal sink, which may lie far beyond the real watershed outlet. A cell whose downstream
    neighbour is outside `mask` (or a true sink) IS the exit/pour point: distance 0 there."""
    h, w = z.shape
    order = np.argsort(z.ravel())  # ascending elevation: downstream cells resolved before upstream ones
    dist = np.zeros(h * w)
    down_flat, dd_flat, mask_flat = down.ravel(), down_dist.ravel(), mask.ravel()
    for i in order:
        d = down_flat[i]
        dist[i] = 0.0 if (d < 0 or not mask_flat[d]) else dist[d] + dd_flat[i]
    return dist.reshape(h, w)


def reproject_glo30(geom_3006, pad=300.0):
    with rasterio.open(GLO30) as src:
        west, south, east, north = geom_3006.bounds
        # bounds of the catchment, back to WGS84 to select the matching source window, then forward again
        to4326 = Transformer.from_crs(3006, 4326, always_xy=True)
        corners = [to4326.transform(x, y) for x in (west - pad, east + pad) for y in (south - pad, north + pad)]
        w4326 = (min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners))
        # Force plain lon/lat axis order: the tile's embedded CRS WKT declares AXIS["Latitude",NORTH]
        # first, which PROJ's strict authority-order handling takes literally and silently produces a
        # scrambled (near-constant) reprojection — confirmed by a side-by-side test. "EPSG:4326" as a
        # bare string uses GDAL's traditional GIS (lon,lat) order instead, which matches this file's
        # actual pixel grid (same fix needed for the NMD raster's own missing/local CRS, see scenario_catchment_cn.py).
        dst_transform, width, height = calculate_default_transform(
            "EPSG:4326", "EPSG:3006", src.width, src.height, *w4326, resolution=CELL_M)
        dst = np.full((height, width), np.nan, "float64")
        reproject(rasterio.band(src, 1), dst, src_transform=src.transform, src_crs="EPSG:4326",
                  dst_transform=dst_transform, dst_crs="EPSG:3006", dst_nodata=np.nan, resampling=Resampling.bilinear)
    return dst, dst_transform


def main():
    cn = json.loads((OUT_DIR / "catchment_cn.json").read_text(encoding="utf8"))
    out = {}
    for key in ("east_184", "south_64474"):
        geom = json.loads((OUT_DIR / f"catchment_{key}.geojson").read_text(encoding="utf8"))
        from shapely.geometry import shape as shp_shape
        g = shp_shape(geom["geometry"])
        dem, tf = reproject_glo30(g)
        mask = features.rasterize([(geom["geometry"], 1)], out_shape=dem.shape, transform=tf, fill=0, dtype="uint8").astype(bool)
        nan_frac = float(np.isnan(dem[mask]).mean())
        # Fill on the REAL padded terrain, priority-flood seeded from the array's true outer edge (standard
        # depression-filling). Do not wall off the area outside the catchment: the watershed boundary is a real
        # topographic divide, and the true pour point lies at the catchment's edge, not the array's edge — an
        # artificial high wall around just the catchment (tried first) forces the whole interior to fill up to
        # the wall's height, destroying the terrain. Restrict results to `mask` only after routing.
        dem_c = np.where(np.isnan(dem), np.nanmax(dem[np.isfinite(dem)]), dem)
        z = fill(dem_c)
        down, dd = d8_down(z, CELL_M)
        flen = flow_length_to_mask_exit(z, down, dd, mask)
        flen_masked = np.where(mask, flen, np.nan)
        ell_m = float(np.nanmax(flen_masked))
        # the longest flow path is measured from the farthest cell to the pour point its own path exits through
        r_far, c_far = np.unravel_index(int(np.nanargmax(flen_masked)), flen_masked.shape)
        x_far, y_far = tf * (c_far + 0.5, r_far + 0.5)
        # sanity check: how far is the nearest exit/pour-point cell from the known boundary-inflow point?
        lat, lon = INFLOW_POINTS[key]
        ox, oy = TO3006.transform(lon, lat)
        exits = np.argwhere(mask & (flen == 0))
        if len(exits):
            d2 = [(math.hypot((tf * (c + 0.5, r + 0.5))[0] - ox, (tf * (c + 0.5, r + 0.5))[1] - oy), r, c) for r, c in exits]
            d2.sort()
            outlet_offset_m = round(d2[0][0])
        else:
            outlet_offset_m = None
        n_exit_cells = int(len(exits))
        y_pct = mean_slope_pct(z, CELL_M, mask)
        ell_ft = ell_m * 3.28084
        s_prime = 1000.0 / cn["catchments"][key]["cn2"] - 10.0
        lag_h = (ell_ft ** 0.8) * ((s_prime + 1) ** 0.7) / (1900.0 * y_pct ** 0.5)
        out[key] = dict(cell_m=CELL_M, dem_pixels=int(mask.sum()), nan_fraction_before_fill=round(nan_frac, 4),
                        longest_flow_path_m=round(ell_m), longest_flow_path_ft=round(ell_ft),
                        farthest_cell_epsg3006=[round(x_far), round(y_far)], exit_cells_found=n_exit_cells,
                        outlet_offset_from_known_inflow_point_m=outlet_offset_m,
                        mean_slope_pct=round(y_pct, 3), cn2_used=cn["catchments"][key]["cn2"], s_prime_in=round(s_prime, 2),
                        nrcs_lag_h=round(lag_h, 3), limitation="catchment area far exceeds the NRCS lag equation's usual small-watershed range; see module docstring")
    (OUT_DIR / "catchment_flowpath.json").write_text(json.dumps(out, indent=1), encoding="utf8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
