"""Fetch SGU Jordarter 25k-100k soil types for the Hörby scenario AOI (brief §4.3),
and assign an assumed SCS hydrologic soil group (A/B/C/D) to each polygon — the
lookup the infiltration model needs (Curve Number method, TR-55).

Endpoint: SGU's OGC API Features, collection "grundlager" ("Jordart,
grundlager" — the base/primary 1:25,000-1:100,000 soil-type layer). No
account or API key required — confirmed by a live 200 OK request during
research for this script (2026-09-17). Storage CRS is SWEREF99 TM (EPSG:3006)
but the API accepts/returns CRS84 (WGS84 lon,lat) bbox queries directly; no
bbox-crs parameter needed.

License: CC0 (SGU made its geological data CC0 in 2024, per sgu.se's own
licence terms page).

Known limitation: this is a bbox filter, not a true clip — a feature is
returned if its bounding box intersects the query bbox, even if its actual
geometry mostly lies elsewhere. Observed directly in this AOI: one "Vatten"
(open water) feature came back that is a large regional polygon, not a
water body actually in Hörby. Every feature keeps its full original geometry;
downstream code must clip to the exact AOI polygon before treating this as
per-cell input, not just trust bbox inclusion. Flagged here and in
ASSUMPTIONS.md rather than silently clipped, since this script has no
geometry-processing library available (stdlib only, like the rest of this
repo's Python) to do a real polygon clip.
"""
import json
import pathlib
import urllib.request
import urllib.parse
import datetime

root = pathlib.Path(__file__).resolve().parents[1]

BASE_URL = "https://api.sgu.se/oppnadata/jordarter25k-100k/ogc/features/v1"
COLLECTION = "grundlager"
# lon_min,lat_min,lon_max,lat_max (CRS84) — same AOI as fetch_geography.py's
# lat_min,lon_min,lat_max,lon_max=55.84,13.64,55.865,13.685, reordered for this API.
BBOX = "13.64,55.84,13.685,55.865"

# Assumed SCS hydrologic soil group per SGU jg2_tx class — a documented
# assumption (brief section 4.3/4.4: "Assign CN from the NMD class combined
# with the soil group derived from SGU soils"), not a measured infiltration
# rate. Based on typical grain-size/drainage character of each class:
# A = high infiltration (coarse sand/gravel), B = moderate (till, fine sand),
# C = moderate-low (silt), D = low (clay, peat/high water table, bedrock).
# Verify before Phase 2 relies on it — these are generic texture-based
# assignments, not a site calibration.
SOIL_TO_HYDROLOGIC_GROUP = {
    "Isälvssediment, sand": "A",
    "Isälvssediment": "A",
    "Postglacial sand": "A",
    "Postglacial finsand": "B",
    "Svämsediment, sand": "B",
    "Sandig morän": "B",
    "Glacial silt": "C",
    "Svämsediment, ler--silt": "D",
    "Kärrtorv": "D",
    "Sedimentärt berg": "D",
    "Fyllning": "C",  # anthropogenic fill: variable and unassessed here — conservative mid-range default
    "Vatten": None,  # open water — not a soil infiltration class; excluded from CN assignment
}
HYDROLOGIC_GROUP_NOTE = (
    "Assumed mapping from SGU jordart class to SCS hydrologic soil group "
    "(A/B/C/D), by typical grain size and drainage character. Not a measured "
    "infiltration rate or a site-specific calibration. A jg2_tx value not "
    "found in this table (soil classes outside those observed in the Hörby "
    "AOI on 2026-09-17) has hydrologic_group=null and must be classified "
    "before it's used in a Curve Number calculation."
)


def fetch_features():
    url = f"{BASE_URL}/collections/{COLLECTION}/items?" + urllib.parse.urlencode({"bbox": BBOX, "f": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": "HNA-research-demo/0.1", "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8")), url


def main():
    data, request_url = fetch_features()
    features = data.get("features", [])
    unmapped = set()
    for f in features:
        soil_name = f["properties"].get("jg2_tx")
        group = SOIL_TO_HYDROLOGIC_GROUP.get(soil_name, "UNMAPPED")
        if group == "UNMAPPED":
            unmapped.add(soil_name)
            group = None
        f["properties"]["hydrologic_group"] = group

    data["metadata"] = {
        "source": "SGU (Sveriges geologiska undersökning) — Jordarter 25k-100k, collection 'grundlager'",
        "source_url": request_url,
        "collection_landing_page": f"{BASE_URL}/collections/{COLLECTION}",
        "license": "CC0",
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bbox_crs84": BBOX,
        "warning": (
            "Bbox-filtered, not clipped — feature geometries may extend well "
            "beyond the query bbox (observed for at least one 'Vatten' "
            "feature in this AOI). Clip to the exact AOI polygon before use. "
            "hydrologic_group is an assumed lookup, not a measurement — see "
            "SOIL_TO_HYDROLOGIC_GROUP in this script and ASSUMPTIONS.md."
        ),
        "hydrologic_group_note": HYDROLOGIC_GROUP_NOTE,
    }

    target = root / "web/data/scenario_soils.geojson"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    classes = sorted({f["properties"].get("jg2_tx") for f in features})
    print(f"Saved {len(features)} soil polygons to {target}")
    print(f"Classes present: {classes}")
    if unmapped:
        print(f"UNMAPPED classes (hydrologic_group=null, need adding to SOIL_TO_HYDROLOGIC_GROUP): {sorted(unmapped)}")


if __name__ == "__main__":
    main()
