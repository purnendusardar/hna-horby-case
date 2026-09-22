# HNA Hörby event explorer

First data-backed case: Hörbyån flooding, 17–19 November 2023. Built for a short municipality demonstration focused on roads and access.

## What works

- Actual CesiumJS globe, streamed elevation and bundled OpenStreetMap reference geometry; optional online OSM tile basemap; zoom, tilt, top-down and reset controls.
- Clickable Ågatan and Tvärgatan reference locations linked to the official flood notice.
- 843 current OSM road/watercourse features in the initial snapshot.
- 21 daily SMHI Hörby A rainfall observations, 1–21 November 2023, with UTC measurement intervals and quality flags; CSV download.
- Three official event updates, source links, evidence gaps and printable decision brief.
- Local data snapshots for event records and rainfall: no live SMHI/Overpass dependency during the presentation.

## Run the included built version

Python 3 is sufficient; no npm installation is needed to view the included `dist` folder:

```sh
python3 -m http.server 8080 --directory dist
```

Open http://localhost:8080. Do not double-click index.html: browser fetch requests require HTTP. WebGL2/hardware acceleration is needed for the map; internet is needed for elevation and optional online tiles. The bundled Cesium library and OSM reference geometry are served locally. The default map uses these reference vectors because shared preview networks may be blocked by the OSM tile service. The optional online basemap is off initially; enable it only in a normal browser deployment that complies with the provider's tile policy. Terrain can take time to stream on a slow connection. The evidence panels remain available during loading.

## Deploy to GitHub Pages

1. Create a public GitHub repository, or use the intended demo repository.
2. Upload this project's contents to the repository root, including `.github/workflows/pages.yml`, `package.json`, `package-lock.json`, `scripts` and `web`. Preserve the dot-prefixed `.github` folder (GitHub Desktop or git is simplest).
3. In repository Settings → Pages → Build and deployment, choose **GitHub Actions**.
4. Push to `main`, or run the **Deploy Hörby demo to GitHub Pages** workflow manually in Actions.
5. Open the URL shown by the deployment. All application paths are relative, including Cesium workers, so repository subpaths are supported.

The included workflow builds `dist` automatically. You do not need to commit `node_modules` or the bundled `dist` when using Actions. No deployment has been made on your behalf.

## Edit and rebuild

Requires Node.js 22 or newer:

```sh
npm ci
npm run build
npm run serve
```

`web/app.js` contains interactions, `web/style.css` the styling, and `web/data` the public snapshots. `scripts/build.mjs` copies the application and pinned Cesium distribution into `dist`.

## Refresh the source data

```sh
python3 scripts/fetch_geography.py
python3 scripts/fetch_rainfall.py
npm run build
```

Python uses only the standard library. Review diffs before accepting refreshed data. OSM identifiers/geometry may change; update and verify the event's street matching if necessary. This is API-sourced data with stored snapshots, not a live backend or a hydraulic modelling service.

## Reproducing model runs (Phase 2)

The website build above needs nothing beyond what's already described — it stays dependency-light and is unaffected by any of this. Reproducing the actual LISFLOOD-FP hydraulic model runs is a separate, heavier requirement: **WSL2 with a Linux build of LISFLOOD-FP 8** (GPL v2; see `ASSUMPTIONS.md` for the exact source, commit, and toolchain versions used, and `scripts/model_build_lisflood.sh` to rebuild it). Preprocessing that produces model inputs runs on Windows Python, same as the rest of `scripts/`; only building and running LISFLOOD-FP itself happens inside WSL, via `scripts/model_stage_and_run.sh`.

## Scientific interpretation

This is an evidence explorer, not a hydraulic reconstruction. The official report names parts of two streets; their exact flooded sections, depths and closure durations are unknown. Map pins locate representative points on those streets. They do not locate verified flood limits. Reference road lines are not classified as inundated. The timeline changes narrative updates, not a simulated water surface. No HNI scores, damage estimates, safe routes, intervention effects or event probabilities are invented.

Daily rainfall uses SMHI representative dates; the observation typically ends at 06:00 UTC the following day. For example, the value assigned to 16 November is 36.9 mm, measured from 16 November 06:00:01 to 17 November 06:00:00 UTC. It is neither an hourly intensity nor a flood depth. Station observations are not catchment-average precipitation.

Esri terrain is visualization context, not an acquired Copernicus GLO-30 DEM or an engineering-grade local terrain dataset. Provider resolution and vertical reference must be checked before any analytical use. Modern terrain/OSM data do not reconstruct the 2023 physical landscape. If terrain fails, the app explicitly identifies its flat ellipsoid fallback.

## Sources and reuse

- Official event notice: https://www.krisinformation.se/nyheter/2023/november/oversvamning-i-horby/ (published 17 November 2023; includes updates for 18 and 19 November). The app contains short factual paraphrases and a source link; no news images or full articles are redistributed.
- SMHI data: https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/5/station/53530/period/corrected-archive/data.csv. Subset/reformatted by HNA, values and quality flags retained. Attribution: SMHI, CC BY 4.0; terms: https://www.smhi.se/data/om-smhis-data/villkor-for-anvandning.
- Cached SMHI-derived responses under `web/data/_cache/` — the station 2128 (HEÅKRA) discharge archive and the S-HYPE/HydroNu `data/point` JSON responses (see `ASSUMPTIONS.md` for what each one is). This directory is tracked in the repository, so these are **redistributed copies of SMHI data, not just local scratch files** — the same SMHI attribution and CC BY 4.0 terms above apply to them. Attribution: SMHI, CC BY 4.0; terms: https://www.smhi.se/data/om-smhis-data/villkor-for-anvandning. Size: ~1.0 MB across 6 files as of 2026-09-18. To regenerate instead of relying on the committed copies, delete `web/data/_cache/` and re-run the fetch scripts that populate it (`scripts/scenario_plausibility_check_station2128.py`, `scripts/scenario_fetch_streamflow.py SUBID`, `scripts/scenario_lookup_subid.py LAT LON`); each re-fetches and re-caches on a cache miss, subject to the 2-second rate limit in `scripts/_hydronu_cache.py`.
- OpenStreetMap contributors: https://www.openstreetmap.org/copyright, ODbL 1.0. The extracted reference database and query are included in `geography.geojson`. Current extraction date is recorded there. Standard tiles are loaded on demand; no bulk tile download or offline tile cache is included. Tile use policy: https://operations.osmfoundation.org/policies/tiles/.
- `web/data/scenario_buildings.geojson` (2,740 building footprints, extruded on the scenario explorer map) is likewise derived from OpenStreetMap: © OpenStreetMap contributors, ODbL 1.0. Building heights in it are assumed (OSM `height`/`building:levels` tags where present, otherwise a default by building type), not measured — see `ASSUMPTIONS.md`.
- Terrain: Esri World Elevation, streamed from https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer. Source attribution is rendered by Cesium; service availability and usage terms apply. No terrain tiles are redistributed.
- CesiumJS 1.133.0: Apache-2.0. Its bundled license/third-party notices are retained in `dist/vendor/cesium`.

## Three-minute Hörby walkthrough

1. Explain the 17 November incident and the two named streets.
2. Tilt/zoom the map and click each street; distinguish location evidence from precise inundation mapping.
3. Inspect the 16 November rainfall bar and its UTC interval.
4. Select 18 and 19 November updates; show the recovery warnings.
5. Print the brief, then ask which local datasets would resolve the listed evidence gaps.

## Next data required

Observed flood footprint/depths; river observations for the event; exact closures; road elevation and underpass/drainage geometry; verified access dependencies. These determine whether a scientifically defensible hydraulic model and asset exposure analysis can be added.
