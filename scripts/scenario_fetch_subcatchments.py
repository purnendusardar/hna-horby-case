"""Fetch SMHI SVAR 2022 Delavrinningsområden (subcatchments) and trace which
ones drain into Hörbyån at Hörby (brief §4.4 — needed for the upstream
inflow boundary condition).

Endpoint: SMHI's open WFS at https://opendata-view.smhi.se/SMHI_vatten/wfs
(WFS 2.0.0, GeoServer), layer SMHI_vatten:Delavrinningsomraden_2022. No
account or API key required — confirmed by a live request during research
for this script (2026-09-17). Storage/default CRS is SWEREF99 TM (EPSG:3006);
this script queries with an explicit WGS84 (EPSG:4326) bbox instead, where
the axis order is lat,lon (not lon,lat) for this CRS URN form — verified by
a real request, not assumed from the spec.

License: SMHI's general open-data terms (CC BY 4.0, per
smhi.se/data/om-smhis-data/villkor-for-anvandning) are the standing
assumption for this dataset; not independently re-confirmed for SVAR
specifically in this session — flagged in ASSUMPTIONS.md.

Method: fetch every subcatchment in a bbox generously larger than Hörby's
own small AOI (the upstream watershed extends well beyond the town), then
walk the MAINDOWN attribute (SVAR's real drainage-topology link: each
catchment names the ARO_UUID of the catchment immediately downstream of it)
upstream from Hörby's own gauging-station catchment. This is a real
breadth-first search over the dataset's own topology, not an inferred
guess from geometry position, and it isn't hardcoded to a fixed catchment
list beyond the single anchor ID below.
"""
import json
import pathlib
import urllib.request
import urllib.parse
import datetime
from collections import defaultdict

root = pathlib.Path(__file__).resolve().parents[1]

WFS_BASE = "https://opendata-view.smhi.se/SMHI_vatten/wfs"
LAYER = "SMHI_vatten:Delavrinningsomraden_2022"
# Generous bbox around Hörby (lat_min,lon_min,lat_max,lon_max) — wide enough
# to contain the whole traced upstream watershed (~62 km^2 total, found to
# extend north/west of the town during Phase 1 research), not just the tight
# Hörby-tätort AOI used elsewhere in this repo.
WIDE_BBOX = (55.75, 13.45, 55.95, 13.85)
# Hörby's own gauging-station catchment on Hörbyån — identified 2026-09-17 by
# name ("Vid mätstation Hörbyån") within the tight Hörby AOI bbox. Treated as
# a stable dataset identifier (SVAR's ARO_UUID), not re-derived by name
# matching on every run, since name matching is fragile (multiple
# Hörbyån-named catchments exist along the river).
HORBY_ANCHOR_ARO_UUID = "1D0DC07B-F547-41F3-9EEB-C1EDF1461A55"


def fetch_features():
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typenames": LAYER,
        "bbox": f"{WIDE_BBOX[0]},{WIDE_BBOX[1]},{WIDE_BBOX[2]},{WIDE_BBOX[3]},urn:ogc:def:crs:EPSG::4326",
        "outputFormat": "application/json",
        "count": "500",
    }
    url = WFS_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "HNA-research-demo/0.1"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode("utf-8")), url


def upstream_of(anchor_uuid, features):
    by_id = {f["properties"]["ARO_UUID"]: f for f in features}
    downstream_of = defaultdict(list)  # MAINDOWN -> [ARO_UUID, ...]
    for f in features:
        p = f["properties"]
        if p.get("MAINDOWN"):
            downstream_of[p["MAINDOWN"]].append(p["ARO_UUID"])

    if anchor_uuid not in by_id:
        raise RuntimeError(
            f"Anchor {anchor_uuid} not found in the {len(features)} features returned for "
            f"WIDE_BBOX={WIDE_BBOX} — widen the bbox or re-check the anchor ID against a fresh "
            f"query of the tight Hörby AOI."
        )

    visited, frontier = set(), [anchor_uuid]
    while frontier:
        node = frontier.pop()
        if node in visited:
            continue
        visited.add(node)
        frontier.extend(u for u in downstream_of.get(node, []) if u not in visited)
    return by_id, visited


def main():
    data, request_url = fetch_features()
    features = data.get("features", [])
    by_id, upstream_set = upstream_of(HORBY_ANCHOR_ARO_UUID, features)

    for f in features:
        uuid = f["properties"]["ARO_UUID"]
        f["properties"]["is_horby_anchor"] = uuid == HORBY_ANCHOR_ARO_UUID
        f["properties"]["is_upstream_of_horby"] = uuid in upstream_set

    data["metadata"] = {
        "source": "SMHI SVAR 2022 (Svenskt VattenArkiv), Delavrinningsområden",
        "source_url": request_url,
        "layer": LAYER,
        "license": "CC BY 4.0 (SMHI general open-data terms — not independently re-confirmed for this specific WFS/dataset; see ASSUMPTIONS.md)",
        "license_terms_url": "https://www.smhi.se/data/om-smhis-data/villkor-for-anvandning",
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "horby_anchor_aro_uuid": HORBY_ANCHOR_ARO_UUID,
        "warning": (
            "is_upstream_of_horby is a real breadth-first walk of the MAINDOWN "
            "attribute from the Hörby anchor catchment, over features returned "
            "for WIDE_BBOX — not a guess from geometry position. If the true "
            "watershed extends beyond WIDE_BBOX, this will silently under-count "
            "upstream catchments; the upstream_of() RuntimeError only catches "
            "a missing anchor, not a truncated watershed. Total upstream area "
            "printed below should be sanity-checked against AREA_UPSTREAM on "
            "the anchor feature itself, which SVAR computes independently."
        ),
    }

    target = root / "web/data/scenario_subcatchments.geojson"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    upstream_features = [f for f in features if f["properties"]["ARO_UUID"] in upstream_set]
    total_area_km2 = sum(f["properties"].get("AREA", 0) for f in upstream_features) / 1e6
    anchor = by_id[HORBY_ANCHOR_ARO_UUID]
    print(f"Saved {len(features)} subcatchments ({len(upstream_set)} upstream of/at Hörby) to {target}")
    print(f"Anchor: {anchor['properties'].get('NAME')} ({HORBY_ANCHOR_ARO_UUID}), "
          f"AREA_UPSTREAM (SVAR's own figure) = {anchor['properties'].get('AREA_UPSTREAM', 0) / 1e6:.2f} km^2")
    print(f"Sum of local AREA over the {len(upstream_set)} catchments this BFS found = {total_area_km2:.2f} km^2 "
          f"(sanity-check against the SVAR figure above; a large gap means WIDE_BBOX likely truncated the watershed)")
    for f in sorted(upstream_features, key=lambda f: -f["properties"].get("AREA", 0)):
        p = f["properties"]
        print(f"  {p.get('NAME') or '(unnamed)'} — {p['ARO_UUID']} — {p.get('AREA', 0)/1e6:.2f} km^2 -> MAINDOWN {p.get('MAINDOWN')}")


if __name__ == "__main__":
    main()
