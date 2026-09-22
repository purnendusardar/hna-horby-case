"""Phase 0 fallback building footprints for the scenario explorer.

Brief section 3 specifies Lantmäteriet Byggnad Nedladdning (vector footprints)
plus lidar-derived heights (90th percentile of class-1 points per footprint,
minus ground height). That pipeline needs an authenticated Lantmäteriet
account and lidar tooling — see scripts/scenario_fetch_terrain.py, not yet run
in this environment.

Until that access exists, this script fetches current OpenStreetMap building
footprints (same Overpass source and bbox as fetch_geography.py) and assigns
an ASSUMED height from OSM tags, so Phase 0 has real footprints to extrude in
CesiumJS today. Every assumed constant here must match the `buildings`
section of scenarios.yaml (kept in sync by hand; there is no shared loader
yet). Record any change to these numbers in ASSUMPTIONS.md.

Known limitation: only closed ways tagged building=* are fetched. Multipolygon
building relations (buildings with courtyards, mapped as OSM relations) are
skipped; there are typically very few of these in a town the size of Hörby,
but a Phase-1 pass should check the printed count against a manual look at
the data before treating this as complete.
"""
import json, pathlib, urllib.request, urllib.parse, datetime

root = pathlib.Path(__file__).resolve().parents[1]

# Same bounding box as scripts/fetch_geography.py, for the same Hörby tätort core.
BBOX = (55.84, 13.64, 55.865, 13.685)

# Must match scenarios.yaml -> buildings.height_fallback. Metres per storey,
# and assumed storey count by OSM building tag when neither height= nor
# building:levels= is present on the feature.
LEVEL_HEIGHT_M = 3.0
DEFAULT_LEVELS_BY_BUILDING_TAG = {
    "house": 2, "detached": 2, "semidetached_house": 2, "terrace": 2,
    "residential": 2, "apartments": 4, "commercial": 2, "retail": 2,
    "industrial": 1, "warehouse": 1, "school": 2, "kindergarten": 1,
    "church": 8,  # nave height, not eave height; flagged in ASSUMPTIONS.md
    "garage": 1, "garages": 1, "shed": 1, "hut": 1, "roof": 1,
}
DEFAULT_LEVELS = 2

query = f'''[out:json][timeout:60];(way["building"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]}););out geom;'''
url = "https://overpass-api.de/api/interpreter?" + urllib.parse.urlencode({"data": query})
req = urllib.request.Request(url, headers={"User-Agent": "HNA-research-demo/0.1"})
with urllib.request.urlopen(req, timeout=90) as response:
    raw = json.load(response)


def parse_height_metres(value):
    """Parse an OSM height=* value ('8', '8 m', '8m') to a float, or None."""
    if value is None:
        return None
    text = str(value).strip().lower().replace("m", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


features = []
method_counts = {}
for element in raw["elements"]:
    coords = [[p["lon"], p["lat"]] for p in element.get("geometry", []) if "lon" in p]
    if len(coords) < 4 or coords[0] != coords[-1]:
        continue  # not a closed way; skip rather than guess a polygon
    tags = element.get("tags", {})

    height_m = parse_height_metres(tags.get("height"))
    method = "osm_height_tag"
    if height_m is None:
        levels = tags.get("building:levels")
        try:
            levels = float(levels) if levels is not None else None
        except ValueError:
            levels = None
        if levels is not None:
            height_m = levels * LEVEL_HEIGHT_M
            method = "osm_levels_tag"
        else:
            building_tag = tags.get("building", "yes")
            levels = DEFAULT_LEVELS_BY_BUILDING_TAG.get(building_tag, DEFAULT_LEVELS)
            height_m = levels * LEVEL_HEIGHT_M
            method = "default_by_building_type"
    method_counts[method] = method_counts.get(method, 0) + 1

    features.append({
        "type": "Feature",
        "id": str(element["id"]),
        "properties": {
            "osm_id": element["id"],
            "building": tags.get("building", "yes"),
            "name": tags.get("name"),
            "height_m": round(height_m, 1),
            "height_method": method,
        },
        "geometry": {"type": "Polygon", "coordinates": [coords]},
    })

out = {
    "type": "FeatureCollection",
    "metadata": {
        "source": "OpenStreetMap contributors",
        "license": "ODbL 1.0",
        "source_url": "https://www.openstreetmap.org/copyright",
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "query": query,
        "status": "Phase 0 placeholder footprints and heights. Target source is "
                   "Lantmäteriet Byggnad Nedladdning + lidar-derived heights "
                   "(brief section 3); not yet fetched. height_method on each "
                   "feature records how its height was estimated; none are "
                   "measured lidar heights.",
    },
    "features": features,
}
target = root / "web/data/scenario_buildings.geojson"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(f"Saved {len(features)} building footprints to {target}")
print("Height method breakdown:", method_counts)
