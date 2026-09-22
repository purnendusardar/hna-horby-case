"""Compute the AOI area that actually drains to the west outflow point —
NOT the AOI bounding-box area — and report both, clearly labeled as
different quantities, alongside SVAR's own 147.49-139.83=7.66 km2 figure.

Why this needs GDAL/QGIS, and why it's not a standalone `python scripts/
...py` invocation: same reason as scripts/scenario_process_landcover.py —
written to run inside QGIS's Python (via `mcp__qgis-mcp__execute_code` or
QGIS's own console), a documented exception to this repo's stdlib-only
convention.

Method: the AOI bbox rectangle does not equal "the area draining to the
outflow" — some of the bbox may drain elsewhere (this is a Rain-on-grid
model over a rectangular clip of terrain, not a delineated watershed).
What SVAR's own topology says actually drains to/through the west outflow
point ("Vid mätstation HEÅKRA") is exactly the seven subcatchments that are
upstream of or at it (walked via MAINDOWN from
scripts/scenario_fetch_subcatchments.py's output, excluding the downstream
"Vid mätstation Hörbyån" anchor, which HEÅKRA drains INTO, not the reverse):
Ebbamölleån, Mynnar i Ebbamölleån, the two unnamed catchments feeding södra
armen, södra armen itself, the tiny unnamed catchment between södra armen
and HEÅKRA, and HEÅKRA's own local piece. Intersecting each of those seven
polygons with the AOI bbox and summing the overlaps gives the actual AOI
area that drains to the outflow — some of those catchments (the two large,
far-upstream headwater pieces) turn out to have zero overlap, which this
script reports rather than assumes.
"""
from qgis.core import (QgsVectorLayer, QgsGeometry, QgsCoordinateReferenceSystem,
                        QgsCoordinateTransform, QgsProject, QgsRectangle)

SUBCATCHMENTS_PATH = r"C:\Purnendu\Aegir\web\data\scenario_subcatchments.geojson"
AOI_WGS84 = (55.84, 13.64, 55.865, 13.685)  # lat_min, lon_min, lat_max, lon_max

# UUIDs of every SVAR subcatchment that is upstream of, or the same point
# as, the west outflow (Vid mätstation HEÅKRA) — excludes the further-
# downstream anchor, which HEÅKRA drains INTO. See ASSUMPTIONS.md for the
# full MAINDOWN topology walk that established this set.
UUIDS_DRAINING_TO_OUTFLOW = {
    "8C58B808-B9F8-4E9F-8F34-448E17CFF50F": "Ebbamölleån",
    "0B588941-ED4C-4F1B-B334-99AC365E4855": "Mynnar i Ebbamölleån",
    "D6C2D5CE-1DD4-4E38-99E0-5C94DB63DEC1": "(unnamed, feeds södra armen)",
    "3EDCA0B8-12CB-4593-A8F9-76E9E2159011": "(unnamed, feeds södra armen)",
    "1A0D99F7-F82A-4AC7-94F2-2A86E2E4B295": "södra armen",
    "C7BAA5D7-CBC0-47F6-9FDA-9C5790EF2BD9": "(unnamed, feeds HEÅKRA)",
    "A5BE7041-2F1C-4F41-B7AA-7ED73F0659FE": "Vid mätstation HEÅKRA (own local piece)",
}

# = 7.66, using UNCORRECTED inflow areas — a different quantity, see module
# docstring. RETIRED as a local-area check (2026-09-18): recomputed with the
# CORRECTED inflow areas instead, this arithmetic gives 8.61 km2, larger than
# the AOI bbox itself — not a coherent local-area figure either way. See
# scripts/scenario_check_shype_area_closure.py for the retirement and its
# S-HYPE-terms replacement. Left here unchanged as a record of what was
# originally computed, not as a check to still rely on.
SVAR_ARITHMETIC_FIGURE_KM2 = 147.49 - 139.83


def main():
    layer = QgsVectorLayer(SUBCATCHMENTS_PATH, "svar", "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Could not load {SUBCATCHMENTS_PATH}")

    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    sweref = QgsCoordinateReferenceSystem("EPSG:3006")
    tr = QgsCoordinateTransform(wgs84, sweref, QgsProject.instance())

    lat_min, lon_min, lat_max, lon_max = AOI_WGS84
    aoi_geom = QgsGeometry.fromRect(QgsRectangle(lon_min, lat_min, lon_max, lat_max))
    aoi_geom.transform(tr)
    aoi_bbox_area_km2 = aoi_geom.area() / 1e6

    total_drainage_overlap_km2 = 0.0
    print("Per-catchment overlap with the AOI bbox:")
    for feat in layer.getFeatures():
        uuid = feat["ARO_UUID"]
        if uuid in UUIDS_DRAINING_TO_OUTFLOW:
            g = QgsGeometry(feat.geometry())
            inter = g.intersection(aoi_geom)
            overlap_km2 = inter.area() / 1e6 if not inter.isEmpty() else 0.0
            total_drainage_overlap_km2 += overlap_km2
            print(f"  {UUIDS_DRAINING_TO_OUTFLOW[uuid]:45s} own_area_km2={g.area()/1e6:8.3f}  "
                  f"overlap_with_AOI_km2={overlap_km2:.4f}")

    print()
    print(f"AOI bounding-box area (the modelled rain-on-grid domain extent): {aoi_bbox_area_km2:.4f} km2")
    print(f"AOI area that actually drains to the west outflow (SVAR-delineated, a DIFFERENT, smaller "
          f"quantity): {total_drainage_overlap_km2:.4f} km2 "
          f"({total_drainage_overlap_km2/aoi_bbox_area_km2*100:.1f}% of the bbox)")
    print(f"SVAR arithmetic figure (147.49 - 139.83, a THIRD, independently-derived quantity, not "
          f"clipped to the AOI bbox shape at all): {SVAR_ARITHMETIC_FIGURE_KM2:.2f} km2")
    print()
    print("These three numbers are reported separately, not reconciled to agree with each other.")


if __name__ == "__main__":
    main()
