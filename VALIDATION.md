# Validation of the first Hörby case

## Completed

- Node build succeeds and produces a self-contained application distribution with local Cesium scripts, workers, assets and notices.
- Event geometry references match the named OSM streets.
- The rainfall snapshot has 21 records, each with SMHI's G (checked and approved) flag; the maximum is 36.9 mm on representative day 2023-11-16.
- Browser interaction checks cover both street selections, layer visibility, transparency, the three event updates, top-down/3D controls and generated print-brief content.
- The app loads from a nested `/demo/` path, as used by GitHub project pages.
- A 390-pixel viewport check found no horizontal document overflow.
- No JavaScript page errors in the checked browser flow.

## Service behaviour and limits

- OSM tile servers returned an access-blocked image on this shared test network. The online tile layer is optional and off by default. Bundled, attributed OSM vector geometry is the default reference map. Do not bypass provider restrictions.
- Esri World Elevation metadata and terrain tiles responded during testing. Terrain streaming may be slow and is not an offline dependency.
- The application is packaged for GitHub Pages but has not been deployed to the user's GitHub account. Test the published URL on the presentation computer before the meeting.
- Testing validates software behaviour and the source-to-display data transformation, not a flood model. No hydraulic model is implemented or claimed.

## Scientific gaps retained in the interface

The official notice describes parts of Ågatan and Tvärgatan as submerged without boundaries, depths or reopening times. Map markers are representative street locations. The 18 November peak in the initial notice was expected, not a measured maximum. Current map geometry and terrain do not establish the 2023 configuration. Exact flood footprints, closure records and river measurements are still required for a quantitative reconstruction.
