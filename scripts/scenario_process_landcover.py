"""Clip Naturvårdsverket NMD2023 basskikt (national land-cover GeoTIFF) to the
Hörby scenario AOI, and classify each land-cover class as sealed/pervious/
water (brief §4.3 — "Used to separate sealed and pervious surfaces").

Why this script needs GDAL, and why it isn't a normal `pip install` on this
machine: NMD2023 basskikt has no clip-capable API (see ASSUMPTIONS.md) — the
only source is a ~2.7 GB national-extent GeoTIFF
(https://geodata.naturvardsverket.se/nedladdning/marktacke/NMD2023/Basskikt_v2_x/NMD2023_basskikt_v2_1.zip,
CC0), which needs GDAL to open and clip. `pip install gdal` fails on this
machine (confirmed 2026-09-17: no prebuilt Windows wheel for this Python,
and building from source fails immediately in setuptools). QGIS 3.40.4 is
already installed on this machine with a working GDAL 3.10.2 (via
`osgeo.gdal`/`osgeo.ogr`), reachable through the qgis-mcp bridge — so this
script is written to run inside QGIS's Python (via
`mcp__qgis-mcp__execute_code`, or QGIS's own Python console), NOT as a
standalone `python scripts/...py` invocation like the rest of this repo's
scripts. This is a deliberate, documented exception to the "Python stdlib
only" convention used elsewhere in this repo — recorded here and in
ASSUMPTIONS.md/scenarios.yaml, not silently different.

Class legend: the raster's GDAL band has no embedded RAT/category names, but
the zip includes a sidecar `NMD2023bas_v2_1.tif.vat.dbf` (a dBase value
attribute table, readable via OGR) with the real Value -> Klass (Swedish
class name) mapping — this is what NMD_CLASS_LEGEND below is sourced from
(read directly from that file, 2026-09-17), not guessed or OCR'd from the
product-description PDF (which did not extract cleanly — see git history of
this file for that attempt).
"""
import glob
import json
import os
import zipfile

RAW_DIR = r"C:\Purnendu\Aegir\scenario_raw\nmd"
ZIP_PATH = os.path.join(RAW_DIR, "NMD2023_basskikt_v2_1.zip")
CLIP_OUTPUT = r"C:\Purnendu\Aegir\web\data\scenario_landcover.tif"
CLASSES_OUTPUT = r"C:\Purnendu\Aegir\web\data\scenario_landcover_classes.json"

# WGS84 AOI, same bbox as scripts/fetch_geography.py: lat_min,lon_min,lat_max,lon_max
AOI_WGS84 = (55.84, 13.64, 55.865, 13.685)

# Source: NMD2023bas_v2_1.tif.vat.dbf, read via OGR 2026-09-17 (53 classes + 0=nodata).
# Value: (Swedish class name, sealed|pervious|water|nodata, rationale)
#
# "sealed" vs "pervious" is a documented ASSUMPTION for two ambiguous classes,
# not something NMD itself labels:
#   - 52 "Anlagd mark, ej byggnad eller väg/järnväg" (developed land, not
#     building/road) can mean gravel yards, sports pitches, etc. — mixed
#     runoff behaviour. Assigned "sealed" here as the conservative default
#     for anthropogenic non-vegetated ground; revisit if this fraction turns
#     out to matter in the Hörby AOI.
#   - 411 "Öppen fastmark utan vegetation" (bare open ground, not
#     glacier/snow) could be bare soil (infiltrates) or exposed bedrock
#     (near-impervious). Assigned "pervious" here (soil assumed more common
#     than bare rock in this lowland AOI) — also a documented guess, not
#     a source-backed classification.
NMD_CLASS_LEGEND = {
    0: ("(nodata / outside classified area)", "nodata", "No class assigned"),
    3: ("Åkermark", "pervious", "Arable land"),
    23: ("Låg fjällskog på våtmark", "pervious", "Alpine forest on wetland — not expected in this lowland AOI"),
    43: ("Låg fjällskog på fastmark", "pervious", "Alpine forest on dry land — not expected in this lowland AOI"),
    51: ("Byggnad", "sealed", "Building footprint"),
    52: ("Anlagd mark, ej byggnad eller väg/järnväg", "sealed", "ASSUMED sealed — see module docstring, genuinely mixed (gravel/sports pitch/etc.)"),
    53: ("Väg eller järnväg", "sealed", "Road or railway"),
    54: ("Torvtäkt", "pervious", "Peat extraction site — disturbed but not sealed"),
    61: ("Inlandsvatten", "water", "Inland water — excluded from sealed/pervious split"),
    62: ("Hav", "water", "Sea — not expected in this inland AOI"),
    111: ("Tallskog på fastmark", "pervious", "Pine forest, dry land"),
    112: ("Granskog på fastmark", "pervious", "Spruce forest, dry land"),
    113: ("Barrblandskog på fastmark", "pervious", "Mixed conifer forest, dry land"),
    114: ("Lövblandad barrskog på fastmark", "pervious", "Broadleaf-mixed conifer forest, dry land"),
    115: ("Triviallövskog på fastmark", "pervious", "Common broadleaf forest, dry land"),
    116: ("Ädellövskog på fastmark", "pervious", "Noble broadleaf forest, dry land"),
    117: ("Triviallövskog med ädellövinslag på fastmark", "pervious", "Common broadleaf forest with noble broadleaf, dry land"),
    118: ("Temporärt ej skog på fastmark", "pervious", "Temporarily unforested, dry land (e.g. recently felled)"),
    121: ("Tallskog på våtmark", "pervious", "Pine forest, wetland"),
    122: ("Granskog på våtmark", "pervious", "Spruce forest, wetland"),
    123: ("Barrblandskog på våtmark", "pervious", "Mixed conifer forest, wetland"),
    124: ("Lövblandad barrskog på våtmark", "pervious", "Broadleaf-mixed conifer forest, wetland"),
    125: ("Triviallövskog på våtmark", "pervious", "Common broadleaf forest, wetland"),
    126: ("Ädellövskog på våtmark", "pervious", "Noble broadleaf forest, wetland"),
    127: ("Triviallövskog med ädellövinslag på våtmark", "pervious", "Common broadleaf forest with noble broadleaf, wetland"),
    128: ("Temporärt ej skog på våtmark", "pervious", "Temporarily unforested, wetland"),
    200: ("Öppen våtmark (underindelning saknas)", "pervious", "Open wetland, unsubdivided"),
    211: ("Buskmyr", "pervious", "Shrub-dominated mire"),
    212: ("Ristuvemyr", "pervious", "Dwarf-shrub hummock mire"),
    213: ("Fastmattemyr, mager", "pervious", "Firm-carpet mire, nutrient-poor"),
    214: ("Fastmattemyr, frodig", "pervious", "Firm-carpet mire, lush"),
    215: ("Sumpkärr", "pervious", "Swamp fen"),
    216: ("Mjukmattemyr", "pervious", "Soft-carpet mire"),
    217: ("Lösbottenmyr", "pervious", "Loose-bottom mire"),
    218: ("Övrig öppen myr", "pervious", "Other open mire"),
    221: ("Våtmark med buskar", "pervious", "Wetland with shrubs"),
    222: ("Risdominerad våtmark", "pervious", "Dwarf-shrub dominated wetland"),
    223: ("Gräsdominerad våtmark, mager", "pervious", "Grass-dominated wetland, nutrient-poor"),
    224: ("Gräsdominerad våtmark, frodvuxen", "pervious", "Grass-dominated wetland, lush"),
    225: ("Gräsdominerad våtmark, högvuxen", "pervious", "Grass-dominated wetland, tall-growing"),
    226: ("Mossdominerad våtmark", "pervious", "Moss-dominated wetland"),
    227: ("Våtmark utan växttäcke", "pervious", "Wetland without vegetation cover"),
    228: ("Övrig öppen våtmark", "pervious", "Other open wetland"),
    411: ("Öppen fastmark utan vegetation (ej glaciär eller varaktigt snöfält)", "pervious", "ASSUMED pervious (bare soil vs. exposed bedrock ambiguous) — see module docstring"),
    4211: ("Torr buskdominerad mark", "pervious", "Dry shrub-dominated land"),
    4212: ("Frisk buskdominerad mark", "pervious", "Fresh (mesic) shrub-dominated land"),
    4213: ("Frisk-fuktig buskdominerad mark", "pervious", "Fresh-moist shrub-dominated land"),
    4221: ("Torr risdominerad mark", "pervious", "Dry dwarf-shrub dominated land"),
    4222: ("Frisk risdominerad mark", "pervious", "Fresh dwarf-shrub dominated land"),
    4223: ("Frisk-fuktig risdominerad mark", "pervious", "Fresh-moist dwarf-shrub dominated land"),
    4231: ("Torr gräsdominerad mark", "pervious", "Dry grass-dominated land"),
    4232: ("Frisk gräsdominerad mark", "pervious", "Fresh grass-dominated land"),
    4233: ("Frisk-fuktig gräsdominerad mark", "pervious", "Fresh-moist grass-dominated land"),
}


def find_tif(extract_dir):
    tifs = glob.glob(os.path.join(extract_dir, "**", "*.tif"), recursive=True)
    if not tifs:
        raise FileNotFoundError(f"No .tif found under {extract_dir} after extraction")
    if len(tifs) > 1:
        tifs.sort(key=os.path.getsize, reverse=True)
    return tifs[0]


def extract():
    extract_dir = os.path.join(RAW_DIR, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    if not glob.glob(os.path.join(extract_dir, "**", "*.tif"), recursive=True):
        print(f"Extracting {ZIP_PATH} ...")
        with zipfile.ZipFile(ZIP_PATH) as z:
            z.extractall(extract_dir)
    return find_tif(extract_dir)


def clip_and_classify(tif_path):
    from osgeo import gdal, osr
    import numpy as np

    gdal.UseExceptions()
    src = gdal.Open(tif_path)
    src_srs = osr.SpatialReference()
    src_srs.ImportFromWkt(src.GetProjection())
    src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    wgs84 = osr.SpatialReference()
    wgs84.ImportFromEPSG(4326)
    wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_src = osr.CoordinateTransformation(wgs84, src_srs)

    lat_min, lon_min, lat_max, lon_max = AOI_WGS84
    x0, y0, _ = to_src.TransformPoint(lon_min, lat_min)
    x1, y1, _ = to_src.TransformPoint(lon_max, lat_max)
    te = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    gdal.Warp(
        CLIP_OUTPUT, src,
        outputBounds=te,
        outputBoundsSRS=src_srs,
        dstSRS=src_srs,
        resampleAlg="near",  # categorical data — never interpolate
        format="GTiff",
    )
    print(f"Wrote clipped AOI raster to {CLIP_OUTPUT}")

    clip = gdal.Open(CLIP_OUTPUT)
    gt = clip.GetGeoTransform()
    px_area_m2 = abs(gt[1] * gt[5])
    arr = clip.GetRasterBand(1).ReadAsArray()
    values, counts = np.unique(arr, return_counts=True)

    classes = []
    sealed_area = pervious_area = water_area = nodata_area = 0.0
    for v, c in sorted(zip(values, counts), key=lambda vc: -vc[1]):
        v = int(v)
        area_m2 = float(c) * px_area_m2
        name, kind, rationale = NMD_CLASS_LEGEND.get(v, (f"UNKNOWN CLASS {v}", "unknown", "Not in NMD_CLASS_LEGEND — investigate before use"))
        classes.append({"value": v, "name": name, "kind": kind, "rationale": rationale, "pixel_count": int(c), "area_m2": round(area_m2, 1)})
        if kind == "sealed":
            sealed_area += area_m2
        elif kind == "pervious":
            pervious_area += area_m2
        elif kind == "water":
            water_area += area_m2
        else:
            nodata_area += area_m2

    total = sealed_area + pervious_area + water_area + nodata_area
    summary = {
        "source": "Naturvårdsverket NMD2023 basskikt v2.1",
        "source_url": "https://geodata.naturvardsverket.se/nedladdning/marktacke/NMD2023/Basskikt_v2_x/NMD2023_basskikt_v2_1.zip",
        "class_legend_source": "NMD2023bas_v2_1.tif.vat.dbf, read via OGR 2026-09-17",
        "license": "CC0",
        "pixel_size_m2": px_area_m2,
        "sealed_pct": round(100 * sealed_area / total, 1) if total else None,
        "pervious_pct": round(100 * pervious_area / total, 1) if total else None,
        "water_pct": round(100 * water_area / total, 1) if total else None,
        "nodata_pct": round(100 * nodata_area / total, 1) if total else None,
        "classes": classes,
    }
    with open(CLASSES_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Wrote classification summary to {CLASSES_OUTPUT}")
    print(f"Sealed {summary['sealed_pct']}% / Pervious {summary['pervious_pct']}% / "
          f"Water {summary['water_pct']}% / Nodata {summary['nodata_pct']}%")
    unknown = [c for c in classes if c["kind"] == "unknown"]
    if unknown:
        print(f"WARNING: {len(unknown)} class value(s) present in the AOI are not in NMD_CLASS_LEGEND: {unknown}")
    return summary


if __name__ == "__main__":
    tif = extract()
    clip_and_classify(tif)
