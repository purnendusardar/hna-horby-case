"""Build the SCS Curve Number (CN) grid for the Hörby AOI — the last
outstanding Phase 1 item (brief §4.3: "Assign CN from the NMD class
combined with the soil group derived from SGU soils").

Inputs (both already fetched, nothing new hits the network here):
- web/data/scenario_landcover.tif — NMD2023 land cover, clipped to the
  AOI, 287x273 pixels, ~10 m (scripts/scenario_process_landcover.py).
- web/data/scenario_landcover_classes.json — the same raster's per-class
  sealed/pervious/water classification, reused here rather than
  duplicating scripts/scenario_process_landcover.py's NMD_CLASS_LEGEND.
- web/data/scenario_soils.geojson — SGU soil polygons with an assumed
  SCS hydrologic group (A/B/C/D) per polygon
  (scripts/scenario_fetch_soils.py).

Why this doesn't use GDAL/QGIS (unlike scripts/scenario_process_landcover.py
and scripts/scenario_compute_aoi_drainage_area.py): those needed GDAL for a
genuine reprojection/clip of a 2.7 GB national dataset. Here both inputs are
already small, already in the AOI, and the only remaining operations are (a)
reading an uncompressed, striped, single-band 16-bit GeoTIFF — a ~30-line
stdlib parse, not worth a GDAL round-trip for — and (b) rasterizing 43
polygons onto a 287x273 grid, done with a plain scanline/even-odd fill
(handles holes automatically: a feature's exterior ring and its hole rings
are just fed to the same crossing-count test together, standard even-odd
polygon-fill semantics, no separate exterior/hole logic needed). Kept
stdlib-only, matching this repo's convention, and reuses the WGS84->SWEREF99
TM transverse Mercator already used and cross-checked in
scripts/scenario_lookup_subid.py.

Curve Number source: USDA NRCS (1986), TR-55 "Urban Hydrology for Small
Watersheds" — the same citation the brief itself gives for Manning's n and
Curve Numbers. Only the table rows actually needed for classes present in
this AOI are reproduced below (NMD_TO_TR55 / CN_TABLE), not the full table.

Documented assumption, stated once and applied uniformly rather than
guessed per class: NMD has no ground-cover-DENSITY attribute (TR-55's
"hydrologic condition" — poor/fair/good — describes canopy/cover density,
which NMD's class names don't encode; NMD's dry/fresh/moist qualifiers
describe soil MOISTURE regime, a different axis, already captured
separately by the SGU hydrologic-group lookup). Rather than inventing a
condition from an unrelated attribute, every class here is assigned TR-55's
POOR hydrologic condition — the conservative (higher-CN, more-runoff)
choice, appropriate for a flood-hazard tool with no cover-density data to
justify anything better. This is a single, uniform, and reversible
assumption, not a per-class guess.

On pervious cells only (per brief §4.3 — sealed and water cells are
excluded, not given a CN of 0). A cell gets no CN, and is reported
separately, if: it is sealed or water; its class is not in NMD_TO_TR55; or
no SGU soil polygon resolves a hydrologic group at that cell's centre
(possible at the AOI edge or under a "Vatten"/water soil polygon, which
carries hydrologic_group=None by design — see
scripts/scenario_fetch_soils.py).

Fallback for the genuine data gap (2026-09-18 follow-up): of the 29.4% of
the AOI with no CN, 98.9% (sealed+water) is a deliberate exclusion per
brief §4.3, not a gap — see scripts/scenario_diagnose_curve_number_gaps.py
for the full breakdown and map. The remaining slice (pervious land, class
resolved, but no soil-group match — "no_soil_group" below) is a real gap
and gets a documented fallback: hydrologic group B, the dominant/modal
group actually observed among this AOI's resolved cells and the
middle-of-the-road choice on the A(best)-D(worst) infiltration spectrum —
conservative without reaching for the worst case. The cell's own already-
resolved TR-55 category is kept; only the missing soil-group axis is
filled. Tracked separately as "fallback_filled", never merged silently
into "ok".

Usage:
    python scripts/scenario_compute_curve_number.py
"""
import json
import math
import pathlib
import struct

root = pathlib.Path(__file__).resolve().parents[1]
LANDCOVER_TIF = root / "web/data/scenario_landcover.tif"
LANDCOVER_CLASSES_JSON = root / "web/data/scenario_landcover_classes.json"
SOILS_GEOJSON = root / "web/data/scenario_soils.geojson"
OUTPUT_ASC = root / "web/data/scenario_curve_number.asc"
OUTPUT_SUMMARY = root / "web/data/scenario_curve_number_summary.json"

NODATA = -9999

# --- TR-55 Curve Numbers (USDA NRCS 1986), POOR hydrologic condition,
# by SCS hydrologic soil group A/B/C/D. Only rows needed here. ---
CN_TABLE = {
    "fallow_bare": {"A": 77, "B": 86, "C": 91, "D": 94},          # Table 2-2c, "Fallow, Bare soil"
    "row_crops_sr_poor": {"A": 72, "B": 81, "C": 88, "D": 91},    # Table 2-2c, "Row crops, straight row, Poor"
    "woods_poor": {"A": 45, "B": 66, "C": 77, "D": 83},           # Table 2-2c, "Woods, Poor"
    "brush_poor": {"A": 48, "B": 67, "C": 77, "D": 83},           # Table 2-2c, "Brush-weed-grass mixture, Poor"
    "pasture_poor": {"A": 68, "B": 79, "C": 86, "D": 89},         # Table 2-2c, "Pasture/rangeland, Poor"
}

# NMD2023 class value -> TR-55 category, for every PERVIOUS class actually
# present in this AOI (scripts/scenario_process_landcover.py's classified
# output, web/data/scenario_landcover_classes.json). Grouped by vegetation
# TYPE (forest / shrub / grass-and-open-wetland / bare) — condition is
# always "poor" per the module docstring's uniform conservative assumption.
NMD_TO_TR55 = {
    3: "row_crops_sr_poor",       # Åkermark (arable)
    # Forest, dry land and wetland alike (wetness handled by soil group, not condition):
    111: "woods_poor", 112: "woods_poor", 113: "woods_poor", 114: "woods_poor",
    115: "woods_poor", 116: "woods_poor", 117: "woods_poor",
    121: "woods_poor", 123: "woods_poor", 124: "woods_poor", 125: "woods_poor",
    126: "woods_poor", 127: "woods_poor",
    # Temporarily unforested (recently felled) — transitional brush-like cover:
    118: "brush_poor", 128: "brush_poor",
    # Shrub-dominated (all moisture-regime variants treated alike — see docstring):
    211: "brush_poor", 221: "brush_poor",
    4211: "brush_poor", 4212: "brush_poor", 4213: "brush_poor",
    # Grass-dominated / open wetland-mire / moss-dominated (vegetated, ungrazed):
    200: "pasture_poor", 213: "pasture_poor", 214: "pasture_poor",
    216: "pasture_poor", 217: "pasture_poor",
    223: "pasture_poor", 224: "pasture_poor", 225: "pasture_poor", 226: "pasture_poor",
    4221: "pasture_poor", 4222: "pasture_poor", 4223: "pasture_poor",
    4231: "pasture_poor", 4232: "pasture_poor", 4233: "pasture_poor",
    # No vegetation cover at all:
    411: "fallow_bare", 227: "fallow_bare",
}

# Fallback hydrologic group for genuine gaps (pervious, class resolved, but
# no soil-group match) — see module docstring for why group B.
FALLBACK_GROUP = "B"

# --- WGS84 -> SWEREF99 TM (same transform as scripts/scenario_lookup_subid.py) ---
_A = 6378137.0
_F = 1 / 298.257222101
_K0 = 0.9996
_LON0 = 15.0 * math.pi / 180.0
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
    )
    return x, y


# --- Minimal stdlib TIFF reader, sufficient for this specific raster
# (uncompressed, striped, single band, 16-bit unsigned, little-endian —
# confirmed by inspection: Compression=1, BitsPerSample=16, SampleFormat=1,
# PlanarConfiguration=1). Not a general TIFF reader. ---
def read_landcover_tiff(path):
    data = path.read_bytes()
    endian = "<" if data[0:2] == b"II" else ">"
    assert struct.unpack(endian + "H", data[2:4])[0] == 42, "not a classic TIFF"
    ifd_offset = struct.unpack(endian + "I", data[4:8])[0]

    n_entries = struct.unpack(endian + "H", data[ifd_offset:ifd_offset + 2])[0]
    tags = {}
    p = ifd_offset + 2
    type_sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 11: 4, 12: 8}
    type_fmt = {1: "B", 3: "H", 4: "I", 11: "f", 12: "d"}
    for _ in range(n_entries):
        tag, typ, count, value_bytes = struct.unpack(endian + "HHI4s", data[p:p + 12])
        size = type_sizes.get(typ, 1) * count
        if size <= 4:
            raw = value_bytes[:size]
        else:
            off = struct.unpack(endian + "I", value_bytes)[0]
            raw = data[off:off + size]
        if typ in type_fmt:
            tags[tag] = struct.unpack(endian + type_fmt[typ] * count, raw)
        p += 12

    width = tags[256][0]
    height = tags[257][0]
    assert tags[259][0] == 1, f"expected uncompressed TIFF, got compression={tags[259][0]}"
    assert tags[258][0] == 16, f"expected 16-bit samples, got {tags[258][0]}"
    rows_per_strip = tags[278][0]
    strip_offsets = tags[273]
    strip_byte_counts = tags[279]

    pixels = bytearray()
    for off, nbytes in zip(strip_offsets, strip_byte_counts):
        pixels.extend(data[off:off + nbytes])
    n_pixels = width * height
    values = struct.unpack(endian + "H" * n_pixels, bytes(pixels[:n_pixels * 2]))
    grid = [values[r * width:(r + 1) * width] for r in range(height)]

    pixel_w, pixel_h = tags[33550][0], tags[33550][1]
    origin_x, origin_y = tags[33922][3], tags[33922][4]
    return {
        "grid": grid, "width": width, "height": height,
        "pixel_w": pixel_w, "pixel_h": pixel_h,
        "origin_x": origin_x, "origin_y": origin_y,
    }


def load_landcover_kind_lookup():
    classes = json.loads(LANDCOVER_CLASSES_JSON.read_text(encoding="utf-8"))["classes"]
    return {c["value"]: c["kind"] for c in classes}


def load_soil_polygons_sweref():
    data = json.loads(SOILS_GEOJSON.read_text(encoding="utf-8"))
    polygons = []
    for f in data["features"]:
        group = f["properties"]["hydrologic_group"]
        soil_class = f["properties"].get("jg2_tx")
        rings = []
        for ring in f["geometry"]["coordinates"]:
            sweref_ring = [wgs84_to_sweref99tm(lat, lon) for lon, lat in ring]
            rings.append(sweref_ring)
        xs = [x for ring in rings for x, y in ring]
        ys = [y for ring in rings for x, y in ring]
        polygons.append({
            "group": group,
            "soil_class": soil_class,
            "rings": rings,
            "bbox": (min(xs), min(ys), max(xs), max(ys)),
        })
    return polygons


def rasterize_soil_polygons(polygons, width, height, origin_x, origin_y, pixel_w, pixel_h):
    """Even-odd scanline fill, one raster row at a time. A feature's holes
    are just extra rings fed into the same crossing count — even-odd rule
    handles them without separate exterior/hole logic. Returns a grid of
    polygon INDEX (not group directly), so a pixel with no polygon match
    at all (index None) can be told apart from one matched to a polygon
    whose own hydrologic_group is None (e.g. "Vatten")."""
    poly_index_grid = [[None] * width for _ in range(height)]
    abs_pixel_h = abs(pixel_h)

    for row in range(height):
        y = origin_y - (row + 0.5) * abs_pixel_h
        for idx, poly in enumerate(polygons):
            bx0, by0, bx1, by1 = poly["bbox"]
            if y < by0 or y > by1:
                continue
            crossings = []
            for ring in poly["rings"]:
                n = len(ring)
                for i in range(n):
                    x1, y1 = ring[i]
                    x2, y2 = ring[(i + 1) % n]
                    if y1 == y2:
                        continue
                    if (y1 <= y < y2) or (y2 <= y < y1):
                        t = (y - y1) / (y2 - y1)
                        crossings.append(x1 + t * (x2 - x1))
            if not crossings:
                continue
            crossings.sort()
            for k in range(0, len(crossings) - 1, 2):
                x_start, x_end = crossings[k], crossings[k + 1]
                col_start = max(0, math.ceil((x_start - origin_x) / pixel_w - 0.5))
                col_end = min(width - 1, math.floor((x_end - origin_x) / pixel_w - 0.5))
                for col in range(col_start, col_end + 1):
                    poly_index_grid[row][col] = idx
    return poly_index_grid


SEALED_CN = 98  # TR-55 Table 2-2b, "Impervious areas" — used only for the
# whole-AOI mean below, never written into the per-cell CN grid itself
# (brief §4.3: CN applies to pervious cells; sealed cells are excluded from
# the grid, not given a CN of 0 or any other value there).

# Single-character codes for web/data/scenario_curve_number_reason_grid.txt
# — one row of ncols characters per raster row, for
# scripts/scenario_diagnose_curve_number_gaps.py to map without re-deriving
# any of this logic.
REASON_CODE = {
    "ok": "K", "sealed": "S", "water": "W", "unmapped_nmd_class": "U",
    "no_soil_group_no_polygon": "N", "no_soil_group_vatten": "V",
    "fallback_filled": "F",
}


def main():
    lc = read_landcover_tiff(LANDCOVER_TIF)
    kind_by_value = load_landcover_kind_lookup()
    polygons = load_soil_polygons_sweref()

    poly_index_grid = rasterize_soil_polygons(
        polygons, lc["width"], lc["height"], lc["origin_x"], lc["origin_y"], lc["pixel_w"], lc["pixel_h"]
    )

    cn_grid = [[NODATA] * lc["width"] for _ in range(lc["height"])]
    reason_grid = [[""] * lc["width"] for _ in range(lc["height"])]
    reason_counts = {
        "ok": 0, "sealed": 0, "water": 0, "unmapped_nmd_class": 0,
        "no_soil_group_no_polygon": 0, "no_soil_group_vatten": 0, "fallback_filled": 0,
    }
    cn_area_sum = 0.0
    cn_pixel_count = 0
    fallback_cn_area_sum = 0.0
    category_counts = {}
    unmapped_values = set()

    for row in range(lc["height"]):
        for col in range(lc["width"]):
            value = lc["grid"][row][col]
            kind = kind_by_value.get(value)
            if kind == "sealed":
                reason_counts["sealed"] += 1
                reason_grid[row][col] = REASON_CODE["sealed"]
                continue
            if kind == "water":
                reason_counts["water"] += 1
                reason_grid[row][col] = REASON_CODE["water"]
                continue
            category = NMD_TO_TR55.get(value)
            if category is None:
                reason_counts["unmapped_nmd_class"] += 1
                unmapped_values.add(value)
                reason_grid[row][col] = REASON_CODE["unmapped_nmd_class"]
                continue
            poly_idx = poly_index_grid[row][col]
            group = polygons[poly_idx]["group"] if poly_idx is not None else None
            if group not in ("A", "B", "C", "D"):
                # Genuine gap: tell "no polygon covers this point at all"
                # (AOI-edge / SGU coverage gap) apart from "matched a
                # polygon, but its own class has no hydrologic group"
                # (e.g. an SGU "Vatten" polygon under NMD-pervious land —
                # a real dataset disagreement, not a coverage hole).
                if poly_idx is None:
                    reason_counts["no_soil_group_no_polygon"] += 1
                    reason_grid[row][col] = REASON_CODE["no_soil_group_no_polygon"]
                else:
                    reason_counts["no_soil_group_vatten"] += 1
                    reason_grid[row][col] = REASON_CODE["no_soil_group_vatten"]
                # Fallback: keep the already-resolved TR-55 category, fill
                # only the missing soil-group axis with FALLBACK_GROUP.
                # See module docstring for why group B.
                cn = CN_TABLE[category][FALLBACK_GROUP]
                cn_grid[row][col] = cn
                reason_counts["fallback_filled"] += 1
                fallback_cn_area_sum += cn
                continue
            cn = CN_TABLE[category][group]
            cn_grid[row][col] = cn
            reason_counts["ok"] += 1
            reason_grid[row][col] = REASON_CODE["ok"]
            cn_area_sum += cn
            cn_pixel_count += 1
            key = f"{category}/{group}"
            category_counts[key] = category_counts.get(key, 0) + 1

    # --- Write ESRI ASCII grid (LISFLOOD-FP-native format; no GDAL needed
    # to read it back either). Cell is treated as square at ~10 m — the
    # source raster's pixel is very slightly non-square (10.0025 x
    # 9.9914 m, 0.11% apart), negligible for this use.
    cellsize = (lc["pixel_w"] + abs(lc["pixel_h"])) / 2
    xllcorner = lc["origin_x"]
    yllcorner = lc["origin_y"] - lc["height"] * abs(lc["pixel_h"])
    with OUTPUT_ASC.open("w", encoding="ascii") as f:
        f.write(f"ncols {lc['width']}\n")
        f.write(f"nrows {lc['height']}\n")
        f.write(f"xllcorner {xllcorner:.6f}\n")
        f.write(f"yllcorner {yllcorner:.6f}\n")
        f.write(f"cellsize {cellsize:.6f}\n")
        f.write(f"NODATA_value {NODATA}\n")
        for row in cn_grid:
            f.write(" ".join(str(v) for v in row) + "\n")

    reason_grid_path = root / "web/data/scenario_curve_number_reason_grid.txt"
    with reason_grid_path.open("w", encoding="ascii") as f:
        for row in reason_grid:
            f.write("".join(row) + "\n")

    total_pixels = lc["width"] * lc["height"]
    no_soil_group_total = reason_counts["no_soil_group_no_polygon"] + reason_counts["no_soil_group_vatten"]
    no_cn_total = reason_counts["sealed"] + reason_counts["water"] + reason_counts["unmapped_nmd_class"] + no_soil_group_total

    # Two mean-CN figures, deliberately kept separate — see
    # ASSUMPTIONS.md "How mean CN is computed" for which one is used where.
    mean_cn_resolved_only = cn_area_sum / cn_pixel_count if cn_pixel_count else None
    resolved_incl_fallback_count = cn_pixel_count + reason_counts["fallback_filled"]
    mean_cn_incl_fallback = (
        (cn_area_sum + fallback_cn_area_sum) / resolved_incl_fallback_count
        if resolved_incl_fallback_count else None
    )
    non_water_pixels = total_pixels - reason_counts["water"]
    # Whole-AOI figure: sealed cells contribute TR-55's standard impervious
    # CN (98) here ONLY, for this one summary statistic — never written
    # into the per-cell grid itself (brief §4.3 excludes sealed cells from
    # the grid). Water is excluded from both numerator and denominator
    # (no runoff-CN concept applies to open water); unmapped classes (0
    # pixels here) would also be excluded if any existed.
    mean_cn_whole_aoi = (
        (cn_area_sum + fallback_cn_area_sum + reason_counts["sealed"] * SEALED_CN) / non_water_pixels
        if non_water_pixels else None
    )

    summary = {
        "source_landcover": "web/data/scenario_landcover.tif",
        "source_soils": "web/data/scenario_soils.geojson",
        "cn_table_source": "USDA NRCS (1986), TR-55 Table 2-2c, POOR hydrologic condition throughout — see this script's module docstring for why 'poor' was chosen uniformly.",
        "grid": {"width": lc["width"], "height": lc["height"], "cellsize_m": cellsize,
                 "xllcorner": xllcorner, "yllcorner": yllcorner, "crs": "EPSG:3006 (SWEREF99 TM)"},
        "output_ascii_grid": "web/data/scenario_curve_number.asc",
        "output_reason_grid": "web/data/scenario_curve_number_reason_grid.txt",
        "pixel_counts_by_reason": reason_counts,
        "total_pixels": total_pixels,
        "no_cn_total_pixels": no_cn_total,
        "no_cn_pct_of_aoi": round(100 * no_cn_total / total_pixels, 1),
        "resolved_pct": round(100 * reason_counts["ok"] / total_pixels, 1),
        "fallback_pct_of_aoi": round(100 * reason_counts["fallback_filled"] / total_pixels, 3),
        "mean_cn_over_resolved_pervious_pixels_only": round(mean_cn_resolved_only, 2) if mean_cn_resolved_only else None,
        "mean_cn_over_resolved_plus_fallback_pixels": round(mean_cn_incl_fallback, 2) if mean_cn_incl_fallback else None,
        "mean_cn_over_whole_aoi_excl_water_sealed_as_98": round(mean_cn_whole_aoi, 2) if mean_cn_whole_aoi else None,
        "fallback_group_used": FALLBACK_GROUP,
        "pixel_counts_by_category_and_group": category_counts,
        "unmapped_nmd_class_values": sorted(unmapped_values),
    }
    OUTPUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Grid: {lc['width']}x{lc['height']} @ ~{cellsize:.3f} m, EPSG:3006")
    print(f"Pixel counts by reason: {reason_counts} (total {total_pixels})")
    if unmapped_values:
        print(f"WARNING: unmapped NMD class values present: {sorted(unmapped_values)} — add to NMD_TO_TR55.")
    print(f"No CN at all: {no_cn_total} px ({summary['no_cn_pct_of_aoi']}% of AOI) — "
          f"{reason_counts['sealed']} sealed + {reason_counts['water']} water (both deliberate exclusions, "
          f"{round(100*(reason_counts['sealed']+reason_counts['water'])/no_cn_total,1) if no_cn_total else 0}% "
          f"of the gap) + {no_soil_group_total} genuine gap (now fallback-filled, see below)")
    print(f"Mean CN, resolved-only: {summary['mean_cn_over_resolved_pervious_pixels_only']}")
    print(f"Mean CN, resolved+fallback: {summary['mean_cn_over_resolved_plus_fallback_pixels']}")
    print(f"Mean CN, whole AOI (excl. water, sealed=98): {summary['mean_cn_over_whole_aoi_excl_water_sealed_as_98']}")
    print(f"Wrote {OUTPUT_ASC}")
    print(f"Wrote {reason_grid_path}")
    print(f"Wrote {OUTPUT_SUMMARY}")


if __name__ == "__main__":
    main()
