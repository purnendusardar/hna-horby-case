"""Look up SMHI S-HYPE SUBIDs near a WGS84 coordinate, using Vattenwebb
HydroNu's own nearest-point endpoint -- supersedes the "no scriptable
lookup exists" claim in scripts/scenario_fetch_streamflow.py's docstring
(written 2026-09-17, before this endpoint was found on 2026-09-18).

Usage:
    python scripts/scenario_lookup_subid.py LAT LON

How this was found: reading vattenwebb.smhi.se/hydronu/'s own client code
(https://vattenwebb.smhi.se/hydronu/9b203093c2f5d9e820dd2f86d1eec9ab.js,
the requirejs data-main bundle) shows the map's click handler calls:

    data/point?x={SWEREF99TM_x}&y={SWEREF99TM_y}

i.e. exactly scripts/scenario_fetch_streamflow.py's existing ENDPOINT, just
with x/y instead of subid -- the server does its own nearest-reach search.

IMPORTANT caveat, confirmed empirically 2026-09-18: this nearest search is
NOT simply "closest SUBID's own outlet to x,y" -- querying several points
1-9 km apart within the Hörbyån headwaters all returned the SAME distant
poiCenter (~55.86, 13.575, near Ringsjön/Höör, upstreamArea 356 km^2).
What actually works is reading the QUERY RESPONSE's own "stations" dict:
it contains every station node used to build that response's network
diagram (not just the one nearest to x,y), keyed by SUBID, each with a
"pos" ([x,y] in EPSG:3006) and upstream/downstream SUBID links. This
script queries once with the given coordinate, then finds the nearest
entry in that response's "stations" dict -- which is how the Hörbyån
mainstem (SUBID 184) and southern-arm (SUBID 64474) inflow SUBIDs were
actually identified, not from the top-level poiCenter/subid of the
initial query itself.

Cross-check used to trust the match (not just nearest-distance): each
candSUBID's own chartData upstreamArea was compared against the
independent SVAR-delineation AREA_UPSTREAM figure for the corresponding
named catchment (scripts/scenario_fetch_subcatchments.py's output) --
agreement within ~5% for two different delineations/vintages, not exact
equality, is treated as a real match. See ASSUMPTIONS.md.

License: SMHI's general open-data terms (CC BY 4.0), as already used for
scripts/scenario_fetch_streamflow.py's SUBID-based query of this endpoint.

UNSUPPORTED ENDPOINT: see scripts/_hydronu_cache.py's docstring — this
script caches every raw response and rate-limits requests through it.
Pass --force to bypass the cache and re-query.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _hydronu_cache import fetch_json_cached

root = pathlib.Path(__file__).resolve().parents[1]
ENDPOINT = "https://vattenwebb.smhi.se/hydronu/data/point"

# SWEREF99 TM (EPSG:3006) parameters for a WGS84->SWEREF99 TM transverse
# Mercator projection -- avoids a hard pyproj/GDAL dependency, matching
# this repo's stdlib-only Python convention. Verified against QGIS's own
# EPSG:4326->EPSG:3006 transform for the three points used in this
# project (agreement to <0.01 m).
import math

_A = 6378137.0
_F = 1 / 298.257222101  # GRS80
_K0 = 0.9996
_LON0 = 15.0 * math.pi / 180.0
_FN = 0.0
_FE = 500000.0


def wgs84_to_sweref99tm(lat_deg, lon_deg):
    a, f, k0 = _A, _F, _K0
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    t = math.tan(lat) ** 2
    c = ep2 * math.cos(lat) ** 2
    ap = (lon - _LON0) * math.cos(lat)

    m = a * (
        (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * lat
        - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * lat)
        + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * lat)
        - (35 * e2 ** 3 / 3072) * math.sin(6 * lat)
    )

    x = k0 * n * (
        ap + (1 - t + c) * ap ** 3 / 6
        + (5 - 18 * t + t ** 2 + 72 * c - 58 * ep2) * ap ** 5 / 120
    ) + _FE
    y = k0 * (
        m + n * math.tan(lat) * (
            ap ** 2 / 2
            + (5 - t + 9 * c + 4 * c ** 2) * ap ** 4 / 24
            + (61 - 58 * t + t ** 2 + 600 * c - 330 * ep2) * ap ** 6 / 720
        )
    ) + _FN
    return x, y


def query(x, y, force=False):
    url = f"{ENDPOINT}?x={x}&y={y}"
    return fetch_json_cached(url, force=force)


def nearest_stations(stations, x, y, n=5):
    ranked = []
    for subid, info in stations.items():
        sx, sy = info["pos"]
        d = ((sx - x) ** 2 + (sy - y) ** 2) ** 0.5
        ranked.append((d, subid, info))
    ranked.sort(key=lambda r: r[0])
    return ranked[:n]


def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    if len(args) != 2:
        sys.exit("Usage: python scripts/scenario_lookup_subid.py LAT LON [--force]")
    lat, lon = float(args[0]), float(args[1])
    x, y = wgs84_to_sweref99tm(lat, lon)
    data, request_url, from_cache = query(x, y, force=force)
    stations = data.get("stations", {})
    candidates = nearest_stations(stations, x, y, n=5)
    print(f"Query point: lat={lat}, lon={lon} -> SWEREF99 TM x={x:.1f}, y={y:.1f}")
    print(f"Request: {request_url}" + (" (served from cache — pass --force to re-fetch)" if from_cache else ""))
    print(
        "Nearest-distance is NOT automatically the right SUBID for a named "
        "catchment: a headwater sub-piece can sit closer than the aggregation "
        "point that actually matches the target catchment's full upstream "
        "area. Compare each candidate's own upstreamArea (fetch it with "
        "scripts/scenario_fetch_streamflow.py SUBID) against the independent "
        "SVAR AREA_UPSTREAM figure before picking one -- see ASSUMPTIONS.md "
        "for how SUBID 184 vs 64473 vs 64474 were disambiguated this way."
    )
    for dist_m, subid, info in candidates:
        print(f"  SUBID {subid:>6}  {dist_m:6.0f} m away  upstreamPOI={info.get('upstreamPOI')!s:5}  "
              f"normalQ={info.get('normalQ'):.3f} m3/s  upstream={info.get('upstream')}  "
              f"downstream={info.get('downstream')}")


if __name__ == "__main__":
    main()
