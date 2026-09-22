"""Fetch the 1 m Lantmäteriet DEM for the Hörby scenario explorer (brief section 3).

NOT RUN in this environment: Lantmäteriet Markhöjdmodell Nedladdning, grid 1+
requires an authenticated Lantmäteriet account (CC BY 4.0, account required —
see the brief's data table). This script is scaffolding for when that account
exists; it is not a working substitute for one.

Until this has been run and its output converted to self-hosted quantized-mesh
tiles, web/scenarios/app.js uses Esri World Elevation as a placeholder terrain
provider — the same service Case 01 already streams, and explicitly labelled
as visualization context, not an engineering DEM (see README.md's "Scientific
interpretation" section). scenarios.yaml records this as an open Phase 0 item.

Planned steps once credentials are available:

1. STAC search against https://api.lantmateriet.se/stac-hojd/v1 for grid-1+
   DEM tiles intersecting the Hörby AOI (same bbox as fetch_geography.py:
   55.84,13.64,55.865,13.685, plus the buffer the brief specifies for the
   hydraulic grid in Phase 2 — confirm the exact buffer before that phase).
2. Download the matched GeoTIFF(s) to data/scenario/raw/ (not created yet).
3. Heights are RH 2000 (normal heights). Convert to ellipsoidal heights with
   the SWEN17_RH2000 geoid model before use in Cesium, which expects
   ellipsoidal heights — the brief calls this out explicitly (section 5) and
   the water mesh in a later phase must use the same conversion, or the water
   surface and terrain will not align.
4. Tile the converted DEM as quantized-mesh (e.g. with cesium-terrain-builder
   or the quantized-mesh-tile Python package — neither is installed; pick one
   and add it to a scenario-specific requirements file, keeping the existing
   "Python standard library only" rule for the rest of the repo's scripts).
5. Self-host the tile set (GitHub Pages, brief section 5 hosting limits:
   ~1 GB/site, 100 MB/file, target <150 MB total scenario assets) and point
   Cesium's terrainProvider at it instead of ArcGISTiledElevationTerrainProvider.

This script intentionally raises rather than silently doing nothing, so it
cannot be mistaken for a working fetch if run by accident.
"""
import os
import sys

if __name__ == "__main__":
    if not os.environ.get("LANTMATERIET_API_KEY"):
        sys.exit(
            "scenario_fetch_terrain.py is not implemented yet: it needs a "
            "Lantmäteriet account/API key (LANTMATERIET_API_KEY) and a STAC "
            "client. See this file's module docstring for the planned steps. "
            "Phase 0 currently renders with Esri World Elevation as a "
            "placeholder terrain provider instead."
        )
    raise NotImplementedError(
        "LANTMATERIET_API_KEY is set, but the STAC search/download/geoid "
        "conversion/tiling steps below are not implemented yet — see the "
        "module docstring for the plan."
    )
