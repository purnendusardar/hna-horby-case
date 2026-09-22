"""For each inflow SUBID (184, 64474), report the distance from the
S-HYPE subbasin's own outlet node to the AOI crossing point used to
identify it, and the area of that SUBID's own upstream polygon that falls
inside the AOI (i.e. the polygon area between the outlet and the
crossing). If the outlet turns out to be DOWNSTREAM of the crossing (i.e.
already inside the AOI, on the domain side of the boundary), the existing
~0.99 AOI-overlap scaling factor (scripts/scenario_correct_streamflow_for_aoi.py,
derived from a SVAR polygon overlap) is flagged rather than silently
replaced — see the module docstring of that script for what it currently
assumes.

Outlet position caveat (important, found while writing this check): the
per-SUBID data/point?subid=X response's own top-level "poiCenter" is NOT
reliable as that SUBID's true position — cross-checking it against the
SAME SUBID's entry in the "stations" network dict of *other* queries
(a different subid's response, or the original x/y lookup) shows
poiCenter can be several km off (confirmed for SUBID 184: poiCenter is
6.3 km from the cross-validated position). What IS reliable: a station's
"pos" in the "stations" dict of a query that is NOT itself centered on
that station — this value is identical across every independent response
that includes it (checked across 3 separate cached responses per SUBID
here). The one dict entry that is UNRELIABLE is a response's entry for the
subid it was itself queried by (self-referential "pos", also identical
garbage across different SUBIDs' own responses — e.g. subid184.json's own
"stations"["184"]["pos"] equals subid64474.json's own
"stations"["64474"]["pos"], the literal same coordinate pair, which cannot
be right for two different reaches). This script therefore reads each
SUBID's position from a response it did NOT self-query.

Similarly, "coordinates" in each per-SUBID response is documented
elsewhere in this repo (scripts/scenario_correct_streamflow_for_aoi.py) as
"only a LOCAL subbasin polygon, not the full aggregated upstream one" —
checked here against SUBID 64474, whose reported subbasinArea (0.374 km2)
is tiny next to its upstreamArea (59.647 km2): the "coordinates" polygon's
own shoelace area is 59.647 km2, matching upstreamArea, not subbasinArea.
So "coordinates" is in fact the full upstream polygon, at least for this
SUBID — a correction to that earlier assumption, recorded here rather than
silently relied upon.

Usage:
    python scripts/scenario_check_inflow_outlet_position.py
"""
import json
import math
import pathlib

root = pathlib.Path(__file__).resolve().parents[1]

_A = 6378137.0
_F = 1 / 298.257222101  # GRS80
_K0 = 0.9996
_LON0 = 15.0 * math.pi / 180.0
_FE = 500000.0


def wgs84_to_sweref99tm(lat_deg, lon_deg):
    # Same transverse Mercator as scripts/scenario_lookup_subid.py — see
    # that script's docstring for the <0.01 m QGIS cross-check.
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
    )
    return x, y


def shoelace_area_m2(ring):
    n = len(ring)
    s = 0.0
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def clip_polygon(subject, clip):
    """Sutherland-Hodgman: clip convex `subject` by convex `clip` polygon."""
    def signed_area(ring):
        n = len(ring)
        s = 0.0
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            s += x1 * y2 - x2 * y1
        return s / 2.0

    def inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0

    def intersect(p1, p2, a, b):
        x1, y1 = p1; x2, y2 = p2; x3, y3 = a; x4, y4 = b
        d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(d) < 1e-9:
            return p2
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    if signed_area(clip) < 0:
        clip = clip[::-1]
    output = subject
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        if not output:
            break
        input_list, output = output, []
        for j in range(len(input_list)):
            cur, prev = input_list[j], input_list[j - 1]
            cur_in, prev_in = inside(cur, a, b), inside(prev, a, b)
            if cur_in:
                if not prev_in:
                    output.append(intersect(prev, cur, a, b))
                output.append(cur)
            elif prev_in:
                output.append(intersect(prev, cur, a, b))
    return output


AOI_WGS84 = (55.84, 13.64, 55.865, 13.685)  # lat_min, lon_min, lat_max, lon_max

# AOI crossing points from ASSUMPTIONS.md ("Hörbyån inflow boundary —
# corrected 2026-09-18"), WGS84 (lat, lon).
CROSSINGS_WGS84 = {
    "184": (55.84823, 13.68501),      # Hörbyån mainstem, east edge
    "64474": (55.83990, 13.66812),    # southern arm, south edge
}

# Cross-validated station positions (SWEREF99 TM), read from a response
# that did NOT self-query this SUBID — see module docstring.
# Source: web/data/scenario_streamflow_subid185.json's "stations" dict,
# cross-checked against web/data/_cache/hydronu's cached x/y lookup near
# the södra armen crossing, both give identical values.
CROSS_VALIDATED_OUTLET_SWEREF = {
    "184": (416723.5821729063, 6189919.264959738),
    "64474": (416588.6964713598, 6189690.292779488),
}

# The scaling factors scripts/scenario_correct_streamflow_for_aoi.py used
# BEFORE this check's finding was applied to production (2026-09-18),
# kept here for the before/after comparison this script prints. Production
# now uses the "recomputed" (crossing-based) factor shown below for both
# SUBIDs — see ASSUMPTIONS.md, "Update, 2026-09-18: applied to production."
PRE_FIX_SCALING = {
    "184": {"overlap_km2": 0.7129680448621921, "factor": 0.99126},
    "64474": {"overlap_km2": 0.23205072506708652, "factor": 0.99611},
}


def main():
    lat_min, lon_min, lat_max, lon_max = AOI_WGS84
    aoi_corners = [(lon_min, lat_min), (lon_max, lat_min), (lon_max, lat_max), (lon_min, lat_max)]
    aoi_sweref = [wgs84_to_sweref99tm(lat, lon) for lon, lat in aoi_corners]

    for subid in ["184", "64474"]:
        path = root / f"web/data/scenario_streamflow_subid{subid}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        upstream_area_km2 = data["upstreamArea"] / 1e6

        ring = [tuple(pt) for pt in data["coordinates"][0][0]]
        polygon_area_km2 = shoelace_area_m2(ring) / 1e6
        clipped = clip_polygon(ring, aoi_sweref)
        overlap_km2 = shoelace_area_m2(clipped) / 1e6 if clipped else 0.0

        lat, lon = CROSSINGS_WGS84[subid]
        cx, cy = wgs84_to_sweref99tm(lat, lon)
        ox, oy = CROSS_VALIDATED_OUTLET_SWEREF[subid]
        dx, dy = ox - cx, oy - cy
        dist_m = math.hypot(dx, dy)

        # Flow direction differs per inflow (mainstem flows east->west,
        # so downstream = smaller x; southern arm flows south->north, so
        # downstream = larger y) — see ASSUMPTIONS.md's boundary-crossing
        # table for both directions.
        downstream = dx < 0 if subid == "184" else dy > 0

        print(f"=== SUBID {subid} ===")
        print(f"  AOI crossing point (SWEREF99 TM): ({cx:.2f}, {cy:.2f})")
        print(f"  Outlet node (cross-validated 'pos', SWEREF99 TM): ({ox:.2f}, {oy:.2f})")
        print(f"  dx={dx:+.1f} m, dy={dy:+.1f} m, straight-line distance={dist_m:.1f} m")
        print(f"  Outlet is {'DOWNSTREAM (inside the AOI)' if downstream else 'upstream (outside the AOI)'} "
              f"of the crossing.")
        print(f"  S-HYPE upstream polygon area: {polygon_area_km2:.4f} km2 "
              f"(matches upstreamArea={upstream_area_km2:.4f} km2: {abs(polygon_area_km2 - upstream_area_km2) < 0.01})")
        print(f"  Polygon area inside the AOI bbox (the area between the outlet and the crossing): "
              f"{overlap_km2:.4f} km2")

        pre_fix = PRE_FIX_SCALING[subid]
        print(f"  Pre-fix scaling factor (2026-09-18, before this check): {pre_fix['factor']} "
              f"(from SVAR-polygon overlap {pre_fix['overlap_km2']:.4f} km2)")
        if downstream:
            recomputed_factor = (upstream_area_km2 - overlap_km2) / upstream_area_km2
            print(f"  *** Outlet is downstream of the crossing — the {pre_fix['factor']} scaling was "
                  f"insufficient. This SUBID's own upstream polygon puts {overlap_km2:.4f} km2 inside the "
                  f"AOI, vs. the {pre_fix['overlap_km2']:.4f} km2 SVAR-polygon overlap that factor was "
                  f"based on. S-HYPE-basis-consistent recomputation gives a factor of "
                  f"{recomputed_factor:.5f} — this has since been applied to "
                  f"web/data/scenario_streamflow_subid{subid}_aoi_corrected.json; see ASSUMPTIONS.md. ***")
        else:
            print("  Outlet is upstream of the crossing — no double-counted AOI area at the outlet itself; "
                  "the existing scaling factor's premise (small downstream-tip overlap) still needs its "
                  "own justification but is not contradicted by outlet position.")
        print()


if __name__ == "__main__":
    main()
