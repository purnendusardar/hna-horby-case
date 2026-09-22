"""Size Hörbyån's channel burn so bankfull capacity equals the S-HYPE mean high flow (MHQ) of
each reach — bankfull discharge approximates the mean annual flood (Leopold, Wolman & Miller, 1964).

Width stays 6 m (the Lantmäteriet breakgeometry asset that could supply a measured water-surface
width is NOT accessible: `dl1.lantmateriet.se` returns HTTP 401 for the same credentials that
already fail to download the DEM tiles — see ASSUMPTIONS.md). Depth is solved from Manning's
equation, Q=(1/n)*A*R^(2/3)*S^(1/2), n=0.035, trapezoidal section (bottom width 6 m, banks 1:2),
S = local bed slope along each reach from the conditioned 5 m DEM.

Reaches: east arm (Q=6.25 m3/s, OSM way 77387390, AOI edge to confluence), south arm
(Q=4.76 m3/s, way 77387397, AOI edge to confluence), combined mainstem below the confluence
(Q=6.25+4.76=11.01 m3/s, the "river"-tagged ways continuing from the confluence to the west edge).

Runs in the data-prep venv, after scripts/scenario_prep_dem.py (needs the 5 m conditioned AOI DEM):
    .venv\\Scripts\\python.exe scripts\\scenario_channel_capacity.py
"""
import json
import os
import pathlib

for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import numpy as np
import rasterio
from pyproj import Transformer

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEM = ROOT / "data/scenario/derived/dem_rh2000_5m_aoi_conditioned.tif"
GEOG = ROOT / "web/data/geography.geojson"
TO3006 = Transformer.from_crs(4326, 3006, always_xy=True)

WIDTH_M = 6.0  # bottom width; breakgeometry asset inaccessible (HTTP 401), so per the instruction, kept at 6 m
BANK_Z = 2.0   # 1:2 (horizontal:vertical)
MANNING_N = 0.035
CONFLUENCE_LONLAT = (13.66771, 55.84725)

# way 77387390 ("Hörbyån") is ONE OSM way running the full east-arm-through-to-west-edge length (its
# own coordinate list spans lon 13.5867-13.6892, i.e. both the east-arm reach AND the below-confluence
# reach). Split it at its vertex nearest the confluence rather than treating it as one east-arm reach.
REACHES_SPLIT_WAY = 77387390
REACHES = {
    "east_arm": dict(q_m3s=6.25, way_ids=[], label="Hörbyån mainstem, east arm (AOI edge to confluence)"),
    "south_arm": dict(q_m3s=4.76, way_ids=[77387397], label="Southern arm (AOI edge to confluence)"),
    "below_confluence": dict(q_m3s=6.25 + 4.76, way_ids=[], label="Combined mainstem, confluence to west edge"),
}


def line_length_and_profile(coords_lonlat, dem_ds):
    pts = [TO3006.transform(lon, lat) for lon, lat in coords_lonlat]
    length = sum(((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5 for i in range(len(pts) - 1))
    zs = [float(v[0]) for v in dem_ds.sample(pts)]
    zs = [z for z in zs if np.isfinite(z) and z > -9990]
    return length, zs


def solve_depth(q, n, b, z, s, lo=0.01, hi=20.0, tol=1e-5):
    def q_of(d):
        a = (b + z * d) * d
        p = b + 2 * d * (1 + z ** 2) ** 0.5
        r = a / p
        return (1.0 / n) * a * r ** (2.0 / 3.0) * s ** 0.5
    if q_of(hi) < q:
        return None  # channel can't be that deep within the search range at this slope
    for _ in range(100):
        mid = (lo + hi) / 2
        if q_of(mid) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    d = (lo + hi) / 2
    a = (b + z * d) * d
    p = b + 2 * d * (1 + z ** 2) ** 0.5
    return dict(depth_m=round(d, 3), area_m2=round(a, 3), wetted_perimeter_m=round(p, 3),
                hydraulic_radius_m=round(a / p, 3), velocity_ms=round(q / a, 3), top_width_m=round(b + 2 * z * d, 2))


def split_at_confluence(coords_lonlat, confluence_lonlat):
    """Index of the vertex closest to the confluence; caller slices before/after it."""
    cx, cy = TO3006.transform(*confluence_lonlat)
    pts = [TO3006.transform(lon, lat) for lon, lat in coords_lonlat]
    d2 = [(x - cx) ** 2 + (y - cy) ** 2 for x, y in pts]
    return d2.index(min(d2))


def main():
    g = json.loads(GEOG.read_text(encoding="utf8"))
    ways = {ft["properties"]["osm_id"]: ft for ft in g["features"] if "osm_id" in ft["properties"]}
    mainstem = ways[REACHES_SPLIT_WAY]["geometry"]["coordinates"]
    split_i = split_at_confluence(mainstem, CONFLUENCE_LONLAT)
    # OSM way runs east(13.6892) -> west(13.5867): the FIRST part (lower index) is the east arm, upstream of the split.
    REACHES["east_arm"]["coords"] = mainstem[:split_i + 1]
    REACHES["below_confluence"]["coords"] = mainstem[split_i:]

    out = {}
    with rasterio.open(DEM) as dem_ds:
        for key, r in REACHES.items():
            coords = list(r.get("coords", []))
            for wid in r["way_ids"]:
                ft = ways.get(wid)
                if ft is None:
                    continue
                coords.extend(ft["geometry"]["coordinates"])
            if not coords:
                out[key] = dict(error=f"OSM way(s) {r['way_ids']} not found in geography.geojson")
                continue
            length_m, zs = line_length_and_profile(coords, dem_ds)
            if len(zs) < 2 or length_m <= 0:
                out[key] = dict(error="insufficient DEM samples along this reach")
                continue
            drop_m = max(zs) - min(zs)
            slope = max(drop_m / length_m, 1e-4)  # floor: a zero/negative measured slope cannot go into Manning's equation
            sol = solve_depth(r["q_m3s"], MANNING_N, WIDTH_M, BANK_Z, slope)
            out[key] = dict(label=r["label"], q_m3s=r["q_m3s"], reach_length_m=round(length_m), elevation_drop_m=round(drop_m, 2),
                            bed_slope=round(slope, 5), manning_n=MANNING_N, width_m=WIDTH_M, bank_h_to_v=f"1:{BANK_Z:g}",
                            n_dem_samples=len(zs), **(sol or {"error": "Manning's equation has no solution <20 m depth at this slope/width — check inputs"}))
    (ROOT / "data/scenario/derived/channel_capacity.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf8")
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
