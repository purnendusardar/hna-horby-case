"""Explain the straight flood-boundary segments in the contiguous >0.5 m area south of the river,
west of the confluence (70 mm and 100 mm runs) — project-lead request, 2026-09-22.

READ-ONLY. Does not change the DEM, the model, or any published file. Reports only.

Method: street-surface depth (unconditioned ground basis, channel + buildings excluded — same as
the published area_gt_0p5_km2 statistic) > 0.5 m, restricted to columns west of the confluence
(EPSG:3006 x < 416583) and rows south of the river's local alignment (per-column nearest channel
row, nearest-neighbour filled across columns with no channel cell). Connected-component labelling
(4-connected BFS; no scipy in this venv) on that mask, largest component's exterior boundary
(rasterio.features.shapes -> polygon ring, which is pixel-edge-aligned so truly straight raster-
aligned runs are already explicit in the ring's own vertices). Straight runs >100 m: for each,
sample the DEM just outside the wet region (dry side) and the local water surface just inside (wet
side) for a crest height, and look for the nearest OSM road within 20 m of the run's midpoint.
Railways were never fetched into this project's OSM extract (ASSUMPTIONS.md, "Release batch" §1) —
that gap is reported explicitly wherever it is relevant, not silently assumed absent.

Runs in the data-prep venv, after the 70/100 mm final runs:
    .venv\\Scripts\\python.exe scripts\\scenario_boundary_diagnosis.py
"""
import json
import math
import os
import pathlib
import sys
from collections import deque

for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio import features
from rasterio.transform import from_origin

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scenario_prep_dem as prep  # noqa: E402
import scenario_depth_plausibility_check as plaus  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER = ROOT / "data/scenario/derived"
CELL = 5
DEPTH_THRESH = 0.5
MIN_RUN_M = 100.0
ROAD_SEARCH_M = 20.0
TO3006 = Transformer.from_crs(4326, 3006, always_xy=True)
CONFLUENCE_3006 = TO3006.transform(13.66771, 55.84725)


def read_asc(path):
    with open(path, encoding="ascii") as f:
        h = {k.lower(): float(v) for k, v in (f.readline().split() for _ in range(6))}
        a = np.fromstring(f.read(), sep=" ", dtype="float64").astype("float32").reshape(int(h["nrows"]), int(h["ncols"]))
    return np.where(a <= -9990, np.nan, a), h


def south_of_river_mask(chan_mask, shape):
    h, w = shape
    river_row = np.full(w, np.nan)
    for c in range(w):
        rows = np.nonzero(chan_mask[:, c])[0]
        if len(rows):
            river_row[c] = rows.max()  # southernmost channel cell in this column
    # nearest-neighbour fill across columns with no channel cell
    valid = np.nonzero(~np.isnan(river_row))[0]
    if len(valid) == 0:
        return np.zeros(shape, bool)
    filled = np.interp(np.arange(w), valid, river_row[valid])
    row_idx = np.arange(h)[:, None]
    return row_idx > filled[None, :]


def connected_components(mask):
    h, w = mask.shape
    seen = np.zeros(mask.shape, bool)
    comps = []
    for r0 in range(h):
        for c0 in range(w):
            if mask[r0, c0] and not seen[r0, c0]:
                q, cells = deque([(r0, c0)]), []
                seen[r0, c0] = True
                while q:
                    r, c = q.popleft()
                    cells.append((r, c))
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < h and 0 <= cc < w and mask[rr, cc] and not seen[rr, cc]:
                            seen[rr, cc] = True
                            q.append((rr, cc))
                comps.append(cells)
    return comps


PERP_TOL_M = 5.0  # one cell: how far the boundary may wander off a straight chord and still count as "straight"


def straight_runs(ring):
    """ring: (x, y) exterior-ring vertices (pixel-edge-aligned, from rasterio.features.shapes). At 5 m
    resolution a straight DIAGONAL feature (e.g. a road not aligned with the grid) rasterises into a
    staircase of short alternating horizontal/vertical edges, never strictly collinear pair to pair —
    so this does not test raw-edge collinearity. Instead: for each starting vertex, extend forward as
    far as every intermediate vertex stays within PERP_TOL_M of the straight chord from start to the
    current end point (a standard tolerance-band line-following test, robust to staircasing). Returns
    the longest non-overlapping runs with chord length >= MIN_RUN_M."""
    pts = np.array(ring, dtype=float)
    n = len(pts)
    if n < 3:
        return []
    runs = []
    i = 0
    while i < n - 1:
        best_j = i + 1
        j = i + 2
        while j < n:
            chord = pts[j] - pts[i]
            clen = math.hypot(*chord)
            if clen < 1e-9:
                j += 1
                continue
            ux, uy = chord / clen
            seg = pts[i + 1:j] - pts[i]
            perp = np.abs(seg[:, 0] * uy - seg[:, 1] * ux)  # perpendicular distance of each intermediate point from the chord
            if perp.max() <= PERP_TOL_M:
                best_j = j
                j += 1
            else:
                break
        length = math.hypot(*(pts[best_j] - pts[i]))
        if length >= MIN_RUN_M:
            runs.append((pts[i], pts[best_j], length))
            i = best_j  # don't re-use the same stretch of boundary for the next run
        else:
            i += 1
    return runs


def nearest_road(x, y, road_shapes):
    best = (1e18, None)
    for name, coords in road_shapes:
        pts = np.array(coords)
        d = np.hypot(pts[:, 0] - x, pts[:, 1] - y).min()
        if d < best[0]:
            best = (d, name)
    return best


def analyse(mm, run):
    idir, od = ROOT / "model/inputs" / run, ROOT / "model/outputs" / run
    dem, hd = read_asc(idir / f"{run}.dem.asc")
    tf = from_origin(hd["xllcorner"], hd["yllcorner"] + hd["nrows"] * hd["cellsize"], hd["cellsize"], hd["cellsize"])
    depth, _ = read_asc(od / f"{run}.max")
    shape = dem.shape

    full, _ = prep.domain_bounds(CELL)
    unc = plaus.unconditioned_ground_5m(full, tf, shape)
    chan = plaus.channel_mask_5m(full, tf, shape)
    chan_buf = plaus.dilate(chan, 1)
    bmask = plaus.building_mask_5m(full, shape)
    wse = dem + depth
    street_depth = wse - unc

    south = south_of_river_mask(chan, shape)
    x0, y1 = hd["xllcorner"], hd["yllcorner"] + hd["nrows"] * hd["cellsize"]
    cols = np.arange(shape[1])
    west_of_confluence = (x0 + (cols + 0.5) * CELL) < CONFLUENCE_3006[0]
    west2d = np.broadcast_to(west_of_confluence, shape)

    region = (street_depth > DEPTH_THRESH) & south & west2d & ~chan_buf & ~bmask & np.isfinite(street_depth)
    comps = connected_components(region)
    comps.sort(key=len, reverse=True)
    if not comps:
        return dict(storm_mm=mm, run=run, region_cells=0, note="no qualifying area found")

    biggest = comps[0]
    rr, cc = np.array(biggest).T
    m = np.zeros(shape, "uint8")
    m[rr, cc] = 1
    shapes_out = list(features.shapes(m, mask=m.astype(bool), transform=tf))
    if not shapes_out:
        return dict(storm_mm=mm, run=run, region_cells=len(biggest), note="shapes() produced no polygon")
    geom = max((g for g, v in shapes_out), key=lambda g: len(g["coordinates"][0]))
    ring = geom["coordinates"][0]
    runs = straight_runs(ring)

    g = json.loads((ROOT / "web/data/geography.geojson").read_text(encoding="utf8"))
    road_ok = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service", "trunk_link", "living_street"}
    road_shapes = [(f"{p.get('name', p['highway'])} ({p['highway']}, way {p['osm_id']})", [TO3006.transform(x, y) for x, y in ft["geometry"]["coordinates"]])
                   for ft in g["features"] for p in [ft["properties"]] if p.get("highway") in road_ok]
    railway_present = any("railway" in ft["properties"] for ft in g["features"])

    findings = []
    for (x0p, y0p), (x1p, y1p), length in runs:
        mx, my = (x0p + x1p) / 2, (y0p + y1p) / 2
        dx, dy = x1p - x0p, y1p - y0p
        norm = math.hypot(dx, dy)
        nx, ny = -dy / norm, dx / norm  # unit normal, one of two directions
        c_here, r_here = ~tf * (mx, my)
        c_here, r_here = int(round(c_here)), int(round(r_here))
        # sample a few cells along +normal and -normal to find which side is wet vs dry
        def sample(sign, dist):
            px, py = mx + sign * nx * dist, my + sign * ny * dist
            c, r = ~tf * (px, py)
            c, r = int(round(c)), int(round(r))
            return (r, c) if (0 <= r < shape[0] and 0 <= c < shape[1]) else None
        plus3, minus3 = sample(1, 3), sample(-1, 3)
        if plus3 is not None and region[plus3]:
            wet_pt, wet_sign = plus3, 1
        elif minus3 is not None and region[minus3]:
            wet_pt, wet_sign = minus3, -1
        else:
            wet_pt, wet_sign = None, 1
        dry_pt = sample(-wet_sign, 6)
        wse_wet = float(street_depth[wet_pt] + unc[wet_pt]) if wet_pt else None
        dem_dry_unconditioned = float(unc[dry_pt]) if dry_pt else None
        dem_dry_conditioned = float(dem[dry_pt]) if dry_pt else None
        crest_height = round(dem_dry_unconditioned - wse_wet, 2) if (dem_dry_unconditioned is not None and wse_wet is not None) else None
        rdist, rname = nearest_road(mx, my, road_shapes)
        near_channel = bool(chan_buf[max(0, r_here - 4):r_here + 5, max(0, c_here - 4):c_here + 5].any())
        near_building = bool(bmask[max(0, r_here - 2):r_here + 3, max(0, c_here - 2):c_here + 3].any())
        at_domain_edge = c_here <= 2 or c_here >= shape[1] - 3 or r_here <= 2 or r_here >= shape[0] - 3
        classification = "possible artefact"
        basis = []
        if rdist <= ROAD_SEARCH_M and crest_height is not None and crest_height > 0:
            classification = "physical (mapped embankment)"
            basis.append(f"OSM road {rname} at {rdist:.0f} m, crest {crest_height:+.2f} m above the flooded surface confirms a barrier")
        elif rdist <= ROAD_SEARCH_M:
            basis.append(f"OSM road {rname} at {rdist:.0f} m, BUT crest height {crest_height} m does not confirm a barrier "
                         "(not positive — the 'dry' sample is not actually higher than the flooded water surface): proximity to a road alone is not treated as confirmation")
        elif at_domain_edge:
            classification = "physical (domain boundary)"
            basis.append("coincides with the model domain edge")
        elif near_building:
            classification = "physical (raised building)"
            basis.append("coincides with a building-raised cell block")
        elif near_channel:
            classification = "physical (burned-channel discontinuity)"
            basis.append("coincides with the burned-channel mask (a conditioning edge, not open terrain)")
        else:
            basis.append(f"no mapped road within {ROAD_SEARCH_M:g} m, not at the domain edge, not adjacent to a building or the channel")
        findings.append(dict(from_epsg3006=[round(x0p), round(y0p)], to_epsg3006=[round(x1p), round(y1p)], length_m=round(length),
                             midpoint_epsg3006=[round(mx), round(my)], nearest_road_m=round(rdist) if rdist < 1e17 else None, nearest_road=rname,
                             crest_height_above_flooded_surface_m=crest_height, classification=classification, basis="; ".join(basis)))
    return dict(storm_mm=mm, run=run, region_cells=len(biggest), region_area_km2=round(len(biggest) * CELL * CELL / 1e6, 4),
                ring_vertices=len(ring), straight_runs_over_100m=len(runs), railway_data_available=railway_present, segments=findings)


def main():
    out = {}
    for mm, run in ((70, "final_aoi_5m_70mm"), (100, "final_aoi_5m_100mm")):
        res = analyse(mm, run)
        out[mm] = res
        print(f"\n{mm} mm: region {res.get('region_area_km2')} km2 ({res.get('region_cells')} cells), "
              f"{res.get('straight_runs_over_100m', 0)} straight run(s) > 100 m, railway data available: {res.get('railway_data_available')}")
        for seg in res.get("segments", []):
            print(f"  {seg['length_m']} m run, midpoint {seg['midpoint_epsg3006']}, crest {seg['crest_height_above_flooded_surface_m']} m -> "
                  f"{seg['classification']} ({seg['basis']})")
    (DER / "boundary_diagnosis.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf8")
    print(f"\nWrote {DER / 'boundary_diagnosis.json'}")


if __name__ == "__main__":
    main()
