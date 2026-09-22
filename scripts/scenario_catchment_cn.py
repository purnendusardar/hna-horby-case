"""Area-weighted Curve Number for the two Hörbyån inflow catchments (east arm /
SUBID 184 / Ebbamölleån; south arm / SUBID 64474), area OUTSIDE the AOI only.

Same lookup as the AOI grid (scripts/scenario_compute_curve_number.py): NMD2023
class -> TR-55 category (POOR condition) x SGU hydrologic group -> CN(II), sealed
cells counted as CN=98, water excluded, group-B fallback where no soil polygon
resolves — i.e. the same convention as "mean_cn_over_whole_aoi_excl_water_sealed_as_98"
in scenario_curve_number_summary.json, so the two figures are comparable.

Catchment geometry: union of the SVAR subcatchment polygons (web/data/scenario_subcatchments.geojson)
whose MAINDOWN drainage-topology chain reaches the arm's own anchor catchment (inclusive), minus the
AOI bounding box. Requires shapely (added to requirements-dataprep.txt for this step).

Runs in the data-prep venv:
    .venv\\Scripts\\python.exe scripts\\scenario_catchment_cn.py
"""
import json
import os
import pathlib
import urllib.parse
import urllib.request

for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio import features
from rasterio.mask import mask
from shapely.geometry import box, shape, mapping
from shapely.ops import unary_union

ROOT = pathlib.Path(__file__).resolve().parent.parent
NMD_TIF = ROOT / "scenario_raw/nmd/extracted/NMD2023_basskikt_v2_1/NMD2023bas_v2_1.tif"
SUBCATCH = ROOT / "web/data/scenario_subcatchments.geojson"
OUT_DIR = ROOT / "data/scenario/derived"
AOI_WGS84 = (13.64, 55.84, 13.685, 55.865)
TO3006 = Transformer.from_crs(4326, 3006, always_xy=True)

# ARO_UUID anchors, read from web/data/scenario_subcatchments.geojson and cross-checked against
# scenarios.yaml's AREA_UPSTREAM figures (77.6095 / 62.2171 km2, exact match) — NOT the UUIDs guessed
# from a misread earlier printout; corrected 2026-09-22 after AREA_UPSTREAM cross-checks caught the mixup.
EAST_ANCHOR = "8C58B808-B9F8-4E9F-8F34-448E17CFF50F"     # NAME='Ebbamölleån' (SUBID 184 proxy)
SOUTH_ANCHOR = "1A0D99F7-F82A-4AC7-94F2-2A86E2E4B295"    # NAME='Vid mätstation Hörbyån, södra armen' (SUBID 64474)
STOP_UUIDS = {"A5BE7041-2F1C-4F41-B7AA-7ED73F0659FE", "1D0DC07B-F547-41F3-9EEB-C1EDF1461A55", "FACEA6F7-59C5-413A-97F1-AEAE1D9C4585"}  # HEÅKRA, overall anchor, further downstream

# --- same TR-55 table as scripts/scenario_compute_curve_number.py (kept identical, not re-derived) ---
CN_TABLE = {
    "fallow_bare": {"A": 77, "B": 86, "C": 91, "D": 94},
    "row_crops_sr_poor": {"A": 72, "B": 81, "C": 88, "D": 91},
    "woods_poor": {"A": 45, "B": 66, "C": 77, "D": 83},
    "brush_poor": {"A": 48, "B": 67, "C": 77, "D": 83},
    "pasture_poor": {"A": 68, "B": 79, "C": 86, "D": 89},
}
NMD_TO_TR55 = {
    3: "row_crops_sr_poor",
    111: "woods_poor", 112: "woods_poor", 113: "woods_poor", 114: "woods_poor",
    115: "woods_poor", 116: "woods_poor", 117: "woods_poor",
    121: "woods_poor", 122: "woods_poor", 123: "woods_poor", 124: "woods_poor", 125: "woods_poor",
    126: "woods_poor", 127: "woods_poor",
    118: "brush_poor", 128: "brush_poor",
    211: "brush_poor", 221: "brush_poor", 4211: "brush_poor", 4212: "brush_poor", 4213: "brush_poor",
    200: "pasture_poor", 213: "pasture_poor", 214: "pasture_poor", 215: "pasture_poor",
    216: "pasture_poor", 217: "pasture_poor", 218: "pasture_poor",
    222: "pasture_poor", 223: "pasture_poor", 224: "pasture_poor", 225: "pasture_poor", 226: "pasture_poor",
    4221: "pasture_poor", 4222: "pasture_poor", 4223: "pasture_poor",
    4231: "pasture_poor", 4232: "pasture_poor", 4233: "pasture_poor",
    411: "fallow_bare", 227: "fallow_bare",
}
SEALED_VALUES = {51, 52, 53}   # NMD sealed classes (scenario_landcover_classes.json "kind": "sealed")
WATER_VALUES = {61, 62}
FALLBACK_GROUP = "B"
SEALED_CN = 98

SOIL_TO_HYDROLOGIC_GROUP = {
    "Isälvssediment, sand": "A", "Isälvssediment": "A", "Postglacial sand": "A",
    "Postglacial finsand": "B", "Svämsediment, sand": "B", "Sandig morän": "B",
    "Glacial silt": "C", "Svämsediment, ler--silt": "D", "Kärrtorv": "D",
    "Sedimentärt berg": "D", "Fyllning": "C", "Vatten": None,
}


def aoi_box_3006():
    w, s, e, n = AOI_WGS84
    xs, ys = zip(*[TO3006.transform(x, y) for x, y in [(w, s), (w, n), (e, s), (e, n)]])
    return box(min(xs), min(ys), max(xs), max(ys))


def branch_geometry(anchor_uuid):
    d = json.loads(SUBCATCH.read_text(encoding="utf8"))
    by_uuid = {f["properties"]["ARO_UUID"]: f for f in d["features"]}
    members = []
    for f in d["features"]:
        cur = f["properties"]["ARO_UUID"]
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            if cur == anchor_uuid:
                members.append(f)
                break
            if cur in STOP_UUIDS or cur not in by_uuid:
                break
            cur = by_uuid[cur]["properties"]["MAINDOWN"]
    geoms = [shape(f["geometry"]) for f in members]
    union = unary_union(geoms)
    aoi = aoi_box_3006()
    outside = union.difference(aoi)
    return outside, union, [f["properties"]["NAME"] for f in members]


def fetch_soils_bbox(bbox_wgs84):
    url = ("https://api.sgu.se/oppnadata/jordarter25k-100k/ogc/features/v1/collections/grundlager/items?"
           + urllib.parse.urlencode({"bbox": ",".join(f"{v:.5f}" for v in bbox_wgs84), "f": "json", "limit": 10000}))
    req = urllib.request.Request(url, headers={"User-Agent": "HNA-research-demo/0.1", "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8")), url


def soils_to_3006_shapes(geojson):
    shapes = []
    for f in geojson["features"]:
        name = f["properties"].get("jg2_tx")
        group = SOIL_TO_HYDROLOGIC_GROUP.get(name)
        rings = []
        for ring in f["geometry"]["coordinates"]:
            rings.append([TO3006.transform(lon, lat) for lon, lat in ring])
        shapes.append((dict(type="Polygon", coordinates=rings), group, name))
    return shapes


def catchment_cn(geom, soils_geojson):
    with rasterio.open(NMD_TIF, crs="EPSG:3006") as src:
        arr, tf = mask(src, [mapping(geom)], crop=True, filled=True, nodata=0)
    arr = arr[0]
    shape_ = arr.shape

    soil_shapes = soils_to_3006_shapes(soils_geojson)
    group_code = {"A": 1, "B": 2, "C": 3, "D": 4}
    burn = [(geom_, group_code[g]) for geom_, g, _ in soil_shapes if g in group_code]
    group_grid = features.rasterize(burn, out_shape=shape_, transform=tf, fill=0, dtype="uint8") if burn else np.zeros(shape_, "uint8")
    code_group = {v: k for k, v in group_code.items()}

    inside = features.rasterize([(mapping(geom), 1)], out_shape=shape_, transform=tf, fill=0, dtype="uint8").astype(bool)
    cn_sum, cn_n, fallback_n = 0.0, 0, 0
    sealed_n = water_n = unmapped_n = nodata_n = 0
    for val in np.unique(arr[inside]):
        m = inside & (arr == val)
        n = int(m.sum())
        if val == 0:
            nodata_n += n
            continue
        if val in WATER_VALUES:
            water_n += n
            continue
        if val in SEALED_VALUES:
            sealed_n += n
            cn_sum += n * SEALED_CN
            continue
        cat = NMD_TO_TR55.get(int(val))
        if cat is None:
            unmapped_n += n
            continue
        gcodes, counts = np.unique(group_grid[m], return_counts=True)
        for gc, c in zip(gcodes, counts):
            group = code_group.get(int(gc), FALLBACK_GROUP)
            cn = CN_TABLE[cat][group]
            cn_sum += c * cn
            cn_n += c
            if gc == 0:
                fallback_n += c
    total_used = int(cn_n + sealed_n)
    cn2 = cn_sum / total_used if total_used else None
    px_area_km2 = abs(tf.a * tf.e) / 1e6
    return dict(cn2=round(cn2, 2) if cn2 else None, pixels_used=total_used, pixels_sealed=int(sealed_n),
                pixels_water_excluded=int(water_n), pixels_unmapped=int(unmapped_n), pixels_nodata_outside_raster=int(nodata_n),
                pixels_fallback_group_b=int(fallback_n), area_used_km2=round(total_used * px_area_km2, 3),
                area_geometry_km2=round(geom.area / 1e6, 3), pixel_size_m=round(abs(tf.a), 2))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    aoi = aoi_box_3006()
    results = {}
    combined_bounds = None
    geoms_3006 = {}
    for key, anchor in (("east_184", EAST_ANCHOR), ("south_64474", SOUTH_ANCHOR)):
        outside, full, names = branch_geometry(anchor)
        geoms_3006[key] = outside
        b = outside.bounds
        combined_bounds = b if combined_bounds is None else (
            min(combined_bounds[0], b[0]), min(combined_bounds[1], b[1]), max(combined_bounds[2], b[2]), max(combined_bounds[3], b[3]))
        results[key] = dict(member_catchment_names=names, area_outside_aoi_km2=round(outside.area / 1e6, 3),
                            area_incl_aoi_km2=round(full.area / 1e6, 3))

    to4326 = Transformer.from_crs(3006, 4326, always_xy=True)
    pad = 300  # metres, so soil polygons at the catchment edge aren't bbox-clipped away
    x0, y0, x1, y1 = combined_bounds[0] - pad, combined_bounds[1] - pad, combined_bounds[2] + pad, combined_bounds[3] + pad
    corners = [to4326.transform(x, y) for x in (x0, x1) for y in (y0, y1)]
    bbox_wgs84 = (min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners))
    soils_geojson, soils_url = fetch_soils_bbox(bbox_wgs84)
    (OUT_DIR / "catchment_soils_raw.geojson").write_text(json.dumps(soils_geojson, ensure_ascii=False), encoding="utf8")

    for key in results:
        cn = catchment_cn(geoms_3006[key], soils_geojson)
        cn3 = 23 * cn["cn2"] / (10 + 0.13 * cn["cn2"]) if cn["cn2"] else None
        results[key].update(cn2=cn["cn2"], cn3_amc3=round(cn3, 2) if cn3 else None, cn_detail=cn)
        (OUT_DIR / f"catchment_{key}.geojson").write_text(
            json.dumps(dict(type="Feature", properties=dict(key=key), geometry=mapping(geoms_3006[key])), ensure_ascii=False), encoding="utf8")

    out = dict(method="Area-weighted CN(II) over NMD2023 x SGU soils, same TR-55 POOR-condition lookup as the AOI grid "
               "(scripts/scenario_compute_curve_number.py); sealed=98, water excluded, group-B fallback where no soil polygon resolves. "
               "CN(III) = 23*CN(II)/(10+0.13*CN(II)) (Chow, Maidment & Mays, 1988), for the wet-November AMC III assumption.",
               soils_source_url=soils_url, soils_bbox_wgs84=list(bbox_wgs84), catchments=results)
    (OUT_DIR / "catchment_cn.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf8")
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
