"""How much of the strip trimmed from the AOI to make the core drains toward the core?

Runs in the data-prep venv after scenario_prep_dem.py, on the conditioned 5 m AOI DEM
(RH 2000 heights, buildings +10 m, channels burned): priority-flood depression filling,
D8 flow directions, then every trimmed cell is followed downstream until it enters the
core, leaves the AOI or ends in a sink.
    .venv\\Scripts\\python.exe scripts\\scenario_core_drainage.py
"""
import heapq
import json
import os
import pathlib

for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import numpy as np
import rasterio

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER = ROOT / "data/scenario/derived"
K = 5
NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def fill(dem):
    """Priority-flood (Barnes) fill seeded from the domain edge, epsilon-free (flats resolved by D8 tie order)."""
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


def d8_down(z):
    """Flat index of the steepest-descent neighbour; -1 for edge cells (drain out of the domain)."""
    h, w = z.shape
    best = np.full(z.shape, -np.inf)
    down = np.full(z.shape, -1, dtype=np.int64)
    idx = np.arange(h * w).reshape(h, w)
    for dr, dc in NB:
        dist = np.hypot(dr, dc)
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
    return down


def main():
    rep = json.loads((DER / "dem_prep_report.json").read_text(encoding="utf8"))
    with rasterio.open(DER / f"dem_rh2000_{K}m_aoi_conditioned.tif") as d:
        dem, tf = d.read(1).astype("float64"), d.transform
    h, w = dem.shape
    core_north = rep["core"]["bounds_3006"][3]
    rows = np.arange(h)
    core_rows = (tf.f - (rows + 0.5) * K) <= core_north
    in_core = np.repeat(core_rows[:, None], w, axis=1)

    z = fill(dem)
    down = d8_down(z).ravel()
    core_flat = in_core.ravel()
    reach = core_flat.copy()  # a cell "reaches the core" if it is in it or its downstream neighbour does
    for _ in range(h * w):
        nxt = core_flat | np.where(down >= 0, reach[np.where(down >= 0, down, 0)], False)
        if (nxt == reach).all():
            break
        reach = nxt
    trimmed = ~core_flat
    to_core = reach & trimmed
    strip = trimmed.reshape(h, w)
    tc = to_core.reshape(h, w)

    cell_km2 = K * K / 1e6
    res = dict(trimmed_area_km2=round(trimmed.sum() * cell_km2, 3), trimmed_draining_to_core_km2=round(to_core.sum() * cell_km2, 3),
               trimmed_draining_to_core_pct=round(100 * to_core.sum() / trimmed.sum(), 1))
    # contribution by 100 m northing band inside the trimmed strip
    bands = []
    y_top = tf.f
    ys = y_top - (rows + 0.5) * K
    edges = np.arange(core_north, ys.max() + 100, 100)
    for lo in edges[:-1]:
        m = strip & ((ys[:, None] > lo) & (ys[:, None] <= lo + 100))
        if m.any():
            bands.append(dict(northing_from=int(lo), northing_to=int(lo + 100), pct_to_core=round(100 * (tc & m).sum() / m.sum(), 1)))
    res["by_100m_band_north_of_core_edge"] = bands
    # where does that water actually cross into the core: count the drainage of trimmed cells entering via the core's north edge
    (DER / "core_drainage_report.json").write_text(json.dumps(res, indent=2), encoding="utf8")
    np.save(DER / "core_drainage_trimmed_to_core.npy", tc)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
