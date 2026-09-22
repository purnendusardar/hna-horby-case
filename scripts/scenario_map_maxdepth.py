"""Max-depth map with road/rail centrelines + OSM waterways, and missing-culvert candidates.

Idle priority, single thread. Does NOT modify the DEM.
    .venv\\Scripts\\python.exe scripts\\scenario_map_maxdepth.py <run_name> [--min-depth 0.3] [--min-cells 8]

Reads model/outputs/<run>/<run>.max and the conditioned DEM the run used. Writes to model/outputs/<run>/:
  maxdepth_map.png                        depth over hillshade, roads dark red, waterways blue, candidates as yellow boxes
  artefact_candidates.json                every connected area > min-depth whose downstream edge coincides with a road/rail embankment
  proposed_corrections_UNAPPLIED.geojson  one proposed cut (EPSG:3006 line + dimensions) per candidate, never applied

Downstream-edge rule (project-defined): for each connected pond (4-connected, max depth >= 0.3 m) take its rim
(8-neighbour cells outside it); the "downstream edge" is the rim cells within 0.25 m of the lowest rim elevation
(the spill sill); the pond is a candidate when >= 50 % of those cells lie within 1 cell (5 m) of a road or railway
centreline. `sill_gap_m` = sill elevation - pond water-surface elevation (small = pond is full to the sill).
"""
import os
import sys

os.environ.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
if sys.platform == "win32":
    import ctypes
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x40)
for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import argparse
import json
import math
import pathlib
import struct
import zlib
from collections import deque

import numpy as np
from pyproj import Transformer
from rasterio import features
from rasterio.transform import from_origin

ROOT = pathlib.Path(__file__).resolve().parent.parent
TO3006 = Transformer.from_crs(4326, 3006, always_xy=True)
TO4326 = Transformer.from_crs(3006, 4326, always_xy=True)
S = 3
RAMP = [(0.05, (173, 216, 230)), (0.25, (100, 170, 220)), (0.5, (40, 110, 200)), (1.0, (10, 50, 150)), (2.0, (60, 0, 110))]
ROAD_TYPES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service", "trunk_link", "living_street"}
NB8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def read_asc(path):
    with open(path, encoding="ascii") as f:
        h = {k.lower(): float(v) for k, v in (f.readline().split() for _ in range(6))}
        a = np.fromstring(f.read(), sep=" ", dtype="float64").astype("float32").reshape(int(h["nrows"]), int(h["ncols"]))
    return np.where(a <= -9990, np.nan, a), h


def png(path, rgb):
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[r].tobytes() for r in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def hillshade(z, cell):
    gy, gx = np.gradient(z, cell)
    slope, aspect = np.arctan(np.hypot(gx, gy)), np.arctan2(-gx, gy)
    az, alt = math.radians(315), math.radians(45)
    return np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)


def dilate(m, n):
    out = m.copy()
    for _ in range(n):
        p = np.pad(out, 1)
        out = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] | p[:-2, :-2] | p[2:, 2:] | p[:-2, 2:] | p[2:, :-2]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--min-depth", type=float, default=0.3)
    ap.add_argument("--min-cells", type=int, default=8)
    a = ap.parse_args()
    od = ROOT / "model/outputs" / a.run
    depth, hd = read_asc(od / f"{a.run}.max")
    dem, _ = read_asc(ROOT / "model/inputs" / a.run / f"{a.run}.dem.asc")
    cell = hd["cellsize"]
    x0, y1 = hd["xllcorner"], hd["yllcorner"] + hd["nrows"] * cell
    tf = from_origin(x0, y1, cell, cell)
    h, w = depth.shape
    at = lambda r, c: (x0 + (c + 0.5) * cell, y1 - (r + 0.5) * cell)

    g = json.load(open(ROOT / "web/data/geography.geojson", encoding="utf8"))
    road_shapes, road_names, ww_shapes, ww_info, embank_shapes = [], [], [], [], []
    for ft in g["features"]:
        p = ft["properties"]
        line = {"type": "LineString", "coordinates": [TO3006.transform(x, y) for x, y in ft["geometry"]["coordinates"]]}
        if p.get("highway") in ROAD_TYPES or "railway" in p and p.get("railway") in {"rail", "light_rail", "narrow_gauge", "tram", "abandoned", "disused"}:
            road_names.append(f"{p.get('name', p.get('highway') or p.get('railway'))} ({p.get('highway') or 'railway:' + p.get('railway')}, way {p['osm_id']})")
            road_shapes.append((line, len(road_names)))
            if p.get("bridge") != "yes":  # a bridge deck is not an embankment in a ground model
                embank_shapes.append((line, len(road_names)))
        elif p.get("waterway") in {"river", "stream", "drain", "ditch"}:
            ww_shapes.append((line, 1))
            ww_info.append((p["waterway"], p.get("name"), p["osm_id"], np.array(line["coordinates"])))
    road_id = features.rasterize(road_shapes, out_shape=(h, w), transform=tf, fill=0, dtype="int32", all_touched=True)
    road_near = dilate(features.rasterize(embank_shapes, out_shape=(h, w), transform=tf, fill=0, dtype="uint8", all_touched=True) > 0, 1)

    # map
    hs = hillshade(np.where(np.isnan(dem), np.nanmean(dem), dem), cell)
    img = np.stack([np.repeat(np.repeat((90 + 150 * hs).astype("uint8"), S, 0), S, 1)] * 3, -1).astype("float32")
    d3 = np.repeat(np.repeat(depth, S, 0), S, 1)
    for i, (lo, col) in enumerate(RAMP):
        hi = RAMP[i + 1][0] if i + 1 < len(RAMP) else np.inf
        m = (d3 >= lo) & (d3 < hi)
        img[m] = 0.25 * img[m] + 0.75 * np.array(col, "float32")
    tf3 = from_origin(x0, y1, cell / S, cell / S)
    r3 = features.rasterize(road_shapes, out_shape=(h * S, w * S), transform=tf3, fill=0, dtype="uint8") > 0
    w3 = features.rasterize(ww_shapes, out_shape=(h * S, w * S), transform=tf3, fill=0, dtype="uint8") > 0
    img[r3] = (150, 20, 20)
    img[w3 & ~r3] = (0, 90, 255)

    # candidates
    wet = np.nan_to_num(depth, nan=0.0) >= a.min_depth
    seen = np.zeros_like(wet)
    comps = []
    for r in range(h):
        for c in range(w):
            if wet[r, c] and not seen[r, c]:
                q, cells = deque([(r, c)]), []
                seen[r, c] = True
                while q:
                    rr, cc = q.popleft()
                    cells.append((rr, cc))
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        r2, c2 = rr + dr, cc + dc
                        if 0 <= r2 < h and 0 <= c2 < w and wet[r2, c2] and not seen[r2, c2]:
                            seen[r2, c2] = True
                            q.append((r2, c2))
                comps.append(cells)
    comps.sort(key=len, reverse=True)
    cands, feats, n_big = [], [], 0
    for cells in comps:
        if len(cells) < a.min_cells:
            continue
        n_big += 1
        rr, cc = np.array(cells).T
        inside = np.zeros((h, w), bool)
        inside[rr, cc] = True
        rim = dilate(inside, 1) & ~inside
        rim_r, rim_c = np.nonzero(rim & np.isfinite(dem))
        if len(rim_r) == 0:
            continue  # touches the domain edge only
        rz = dem[rim_r, rim_c]
        sill_z = float(rz.min())
        ds = rz <= sill_z + 0.25
        on_road = road_near[rim_r[ds], rim_c[ds]]
        frac = float(on_road.mean())
        i_deep = int(np.argmax(depth[rr, cc]))
        mx = float(depth[rr[i_deep], cc[i_deep]])
        wse = float(np.nanmedian((dem + depth)[rr, cc][depth[rr, cc] >= a.min_depth]))
        sel = np.nonzero(ds)[0][int(np.argmax(on_road))] if on_road.any() else int(np.argmin(rz))
        sr, sc = int(rim_r[sel]), int(rim_c[sel])
        sx, sy = at(sr, sc)
        # nearest waterway
        best = (1e18, None)
        for kind, name, oid, co in ww_info:
            d = np.hypot(co[:, 0] - sx, co[:, 1] - sy).min()
            if d < best[0]:
                best = (d, (kind, name, oid))
        rec = dict(area_m2=int(len(cells) * cell * cell), cells=len(cells), max_depth_m=round(mx, 2),
                   deepest_cell_epsg3006=[round(v) for v in at(int(rr[i_deep]), int(cc[i_deep]))],
                   sill_epsg3006=[round(sx), round(sy)], sill_elevation_m=round(sill_z, 2), pond_surface_elevation_m=round(wse, 2),
                   sill_gap_m=round(sill_z - wse, 2), downstream_edge_cells=int(ds.sum()), downstream_edge_on_road_or_rail_pct=round(100 * frac),
                   roads_at_sill=sorted({road_names[v - 1] for v in np.unique(road_id[max(0, sr - 1): sr + 2, max(0, sc - 1): sc + 2]) if v})[:4],
                   nearest_waterway=dict(type=best[1][0], name=best[1][1], osm_id=best[1][2], distance_m=round(float(best[0]))) if best[1] else None)
        if frac < 0.5:
            continue
        # proposed cut (unapplied): from the pond-side floor next to the sill, over the sill, down the steepest descent outside the pond
        path = [(sr, sc)]
        cr, cc_ = sr, sc
        for _ in range(14):
            nbrs = [(cr + dr, cc_ + dc) for dr, dc in NB8 if 0 <= cr + dr < h and 0 <= cc_ + dc < w and not inside[cr + dr, cc_ + dc]
                    and np.isfinite(dem[cr + dr, cc_ + dc]) and (cr + dr, cc_ + dc) not in path]
            if not nbrs:
                break
            nxt = min(nbrs, key=lambda p: dem[p])
            if dem[nxt] >= dem[cr, cc_] and len(path) > 1:
                break
            path.append(nxt)
            cr, cc_ = nxt
            if dem[cr, cc_] <= sill_z - 0.4 and not road_near[cr, cc_]:
                break
        near_in = [(sr + dr, sc + dc) for dr, dc in NB8 if 0 <= sr + dr < h and 0 <= sc + dc < w and inside[sr + dr, sc + dc]]
        if near_in:
            path.insert(0, min(near_in, key=lambda p: dem[p]))
        width = 0.8 if best[1] and best[1][0] in ("drain", "ditch") else 1.5
        invert = float(min(dem[p] for p in path[:2]))
        rec["proposed_correction"] = dict(width_m=width, invert_elevation_m=round(invert, 2), length_m=round(len(path) * cell, 1),
                                          basis="culvert width per brief 4.5 (0.8 m ditch / 1.5 m tributary by nearest waterway type); invert = lower of the pond-side floor and the sill cell; UNAPPLIED")
        cands.append(rec)
        feats.append(dict(type="Feature", properties=dict(candidate=len(cands), **rec["proposed_correction"], status="UNAPPLIED proposal - do not apply without project-lead confirmation"),
                          geometry=dict(type="LineString", coordinates=[list(at(*p)) for p in path])))
        # marker box
        pr, pc = int((y1 - sy) / cell * S), int((sx - x0) / cell * S)
        img[max(0, pr - 6): pr + 7, max(0, pc - 6): pc + 7][[0, -1], :] = (255, 220, 0)
        img[max(0, pr - 6): pr + 7, max(0, pc - 6): pc + 7][:, [0, -1]] = (255, 220, 0)
    png(od / "maxdepth_map.png", np.clip(img, 0, 255).astype("uint8"))
    finite = depth[np.isfinite(depth)]
    out = dict(run=a.run, cell_m=cell, dem_modified=False, criteria="see module docstring (project-defined)",
               ponds_over_threshold_and_min_cells=n_big, candidates_found=len(cands),
               wet_area_gt_0p05_km2=round(float((finite > 0.05).sum() * cell * cell / 1e6), 3),
               area_gt_0p3_km2=round(float((finite > 0.3).sum() * cell * cell / 1e6), 3), max_depth_m=round(float(finite.max()), 2),
               candidates=cands, crs_of_all_coordinates="EPSG:3006")
    (od / "artefact_candidates.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf8")
    (od / "proposed_corrections_UNAPPLIED.geojson").write_text(json.dumps(dict(
        type="FeatureCollection", crs=dict(type="name", properties=dict(name="urn:ogc:def:crs:EPSG::3006")), features=feats), indent=1), encoding="utf8")
    print(json.dumps({k: v for k, v in out.items() if k != "candidates"}, indent=1))
    for i, c in enumerate(cands, 1):
        print(i, c["area_m2"], "m2 max", c["max_depth_m"], "m sill", c["sill_epsg3006"], "gap", c["sill_gap_m"], "edge on road", c["downstream_edge_on_road_or_rail_pct"], "%", c["roads_at_sill"][:1], c["nearest_waterway"])


if __name__ == "__main__":
    main()
