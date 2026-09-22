const $ = id => document.getElementById(id);
const STORMS = [40, 70, 100];
const RESULTS = '../data/results/';
let viewer, buildings, topDown = false, depthLayer = null, valleyFloorM = 0;
const scenarios = {};   // storm mm -> {key, meta, impacts} for runs that have finished and been post-processed
let currentIdx = 1, lastGoodIdx = 1;

const load = async path => { const r = await fetch(path); if (!r.ok) throw new Error(`${path}: ${r.status}`); return r.json(); };
function errorMap(message) { $('map-error').hidden = false; $('map-error').textContent = message; }
const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };

// Camera: pitch -35 degrees over the town, same target as Case 01 (web/app.js).
function fly(lon = 13.6547, lat = 55.8491, range = 1900) {
  if (!viewer) return;
  const C = Cesium;
  viewer.camera.cancelFlight();
  viewer.camera.flyToBoundingSphere(new C.BoundingSphere(C.Cartesian3.fromDegrees(lon, lat, 80), 10), {
    duration: 1.2,
    offset: new C.HeadingPitchRange(0, C.Math.toRadians(topDown ? -90 : -35), range),
  });
}

const HEIGHT_METHOD_COLOR = {
  osm_height_tag: '#087e83',
  osm_levels_tag: '#249ac5',
  default_by_building_type: '#8a9aa5',
};

function addBuildings() {
  const C = Cesium;
  for (const f of buildings.features) {
    const ring = f.geometry.coordinates[0];
    const flatRing = ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1] ? ring.slice(0, -1) : ring;
    const color = HEIGHT_METHOD_COLOR[f.properties.height_method] || HEIGHT_METHOD_COLOR.default_by_building_type;
    viewer.entities.add({
      id: `bldg-${f.properties.osm_id}`,
      polygon: {
        hierarchy: new C.PolygonHierarchy(C.Cartesian3.fromDegreesArray(flatRing.flat())),
        extrudedHeight: f.properties.height_m,
        height: 0,
        heightReference: C.HeightReference.CLAMP_TO_GROUND,
        extrudedHeightReference: C.HeightReference.RELATIVE_TO_GROUND,
        material: C.Color.fromCssColorString(color).withAlpha(0.85),
        outline: true,
        outlineColor: C.Color.fromCssColorString('#173f50').withAlpha(0.25),
      },
    });
  }
}

function updateExaggeration() {
  const v = +$('exaggeration').value;
  $('exaggeration-value').textContent = `${v.toFixed(1)}×`;
  if (viewer) {
    viewer.scene.verticalExaggeration = v;
    viewer.scene.verticalExaggerationRelativeHeight = valleyFloorM;  // exaggerate relative to the valley floor, not the ellipsoid
    viewer.scene.requestRender();
  }
}

// ---- scenario data ------------------------------------------------------------------------------------------
async function loadScenarios() {
  let manifest = { scenarios: [] };
  try { manifest = await load(`${RESULTS}manifest.json`); } catch (e) { console.warn('No results manifest; every scenario is shown as not yet available.', e.message); }
  for (const mm of STORMS) {
    const options = manifest.scenarios.filter(s => s.storm_mm === mm);
    const pick = options.find(s => s.key.startsWith('freeout_')) || options[0];  // prefer the run with a free downstream boundary
    if (!pick) continue;
    try {
      const [meta, impacts] = await Promise.all([load(`${RESULTS}${pick.key}/meta.json`), load(`${RESULTS}${pick.key}/impacts.json`)]);
      scenarios[mm] = { key: pick.key, meta, impacts };
    } catch (e) { console.warn(`Results for ${mm} mm are listed but could not be read:`, e.message); }
  }
  for (const li of document.querySelectorAll('#storm-ticks li')) {
    const s = scenarios[+li.dataset.mm];
    li.classList.toggle('na', !s);
    li.querySelector('small').textContent = s ? (s.impacts.summary.boundary.startsWith('free') ? 'ready · free outflow' : 'ready · closed boundary') : 'not yet available';
  }
}

const fmtH = h => `${(+h).toFixed(1)} h`;
function boundaryNote(s) {
  return s.impacts.summary.boundary.startsWith('free')
    ? 'The downstream (west) edge is a free outflow, as the brief specifies.'
    : 'Downstream boundary is CLOSED in this run: water cannot leave the model, so depths, especially in the western valley, are overstated.';
}

function renderHeadline(s) {
  const sm = s.impacts.summary, locs = s.impacts.locations.filter(l => l.resolvable !== false);
  const places = new Map();   // the four reporting places; Skattkistans förskola counts as wet if any candidate kindergarten is
  for (const l of locs) places.set(l.group || l.location, places.get(l.group || l.location) || l.exceeds_0p05_m);
  const wet = [...places.values()].filter(Boolean).length;
  const deepest = locs.reduce((a, b) => (b.street_surface_p90_m > a.street_surface_p90_m ? b : a));
  const box = $('headline');
  box.replaceChildren(
    el('span', { className: 'eyebrow', textContent: `${sm.storm_mm} MM DESIGN STORM` }),
    el('p', { className: 'big', textContent: `${wet} of ${places.size} reporting places exceed 0.05 m` }),
    el('p', { textContent: `Highest street-surface depth: ${deepest.location.replace(/^Skattkistans förskola \(candidate: (unnamed kindergarten )?/, 'Skattkistans förskola candidate (').replace(/\)$/, ')') } — 90th-percentile depth ${deepest.street_surface_p90_m.toFixed(2)} m · ${Math.round(deepest.wetted_fraction * 100)}% of footprint deeper than 0.05 m.` }),
    el('p', { textContent: `Water deeper than 0.3 m covers ${sm.area_gt_0p3_km2.toFixed(2)} km² of the ${sm.domain_km2.toFixed(1)} km² model domain (street-surface basis, channel and buildings excluded).` }),
    el('p', { className: 'warn', textContent: boundaryNote(s) }),
    el('p', { className: 'fine', textContent: sm.inflow.type.startsWith('constant')
      ? 'River inflows are constant placeholders and rain loss uses one uniform Curve Number — a numerical demonstration, not a forecast.'
      : 'River inflows are computed event hydrographs (checked against the Nov 2023 gauge record) but rain loss still uses one uniform Curve Number — a numerical demonstration, not a forecast.' }),
  );
}

function renderLegend(s) {
  const list = $('legend-list');
  list.replaceChildren(...s.meta.classes.map(c => el('li', {}, el('i', { style: `background:rgba(${c.rgba[0]},${c.rgba[1]},${c.rgba[2]},${Math.max(c.rgba[3] / 255, .85)})` }), c.label)));
  if (s.meta.river_layer) {
    const rc = s.meta.river_layer.rgba, oc = s.meta.river_layer.outline_rgba || [4, 61, 64, 255];
    list.append(el('li', {}, el('i', { style: `background:rgba(${rc[0]},${rc[1]},${rc[2]},${Math.max(rc[3] / 255, .85)});border:1.5px solid rgb(${oc[0]},${oc[1]},${oc[2]})` }), s.meta.river_layer.label));
  }
}

function renderLocations(s) {
  const ul = $('locations');
  ul.replaceChildren();
  const groups = new Map();
  for (const l of s.impacts.locations) {
    const g = l.group || l.location;
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(l);
  }
  for (const [g, rows] of groups) {
    const li = el('li', { className: 'loc-group' });
    if (rows.length > 1) li.append(el('span', { className: 'loc-head', textContent: `${g} — which one is it? Candidates:` }));
    for (const l of rows) {
      const label = rows.length > 1 ? l.location.replace(/^.*\(candidate: /, '').replace(/\)$/, '').replace(/^unnamed kindergarten (way\/\d+)$/, 'Unnamed kindergarten (OSM $1)') : l.location;
      const b = el('button', { className: 'loc' + (l.exceeds_0p05_m ? ' wet' : ''), type: 'button' },
        el('strong', { textContent: label }),
        el('span', { className: 'depth', textContent: l.resolvable === false ? 'n/a' : `${l.street_surface_p90_m.toFixed(2)} m` }),
        el('small', { textContent: l.resolvable === false ? 'outside model' : `90th-percentile depth · ${Math.round(l.wetted_fraction * 100)}% of footprint deeper than 0.05 m · peak at ${fmtH(l.time_of_max_h)}` }));
      b.onclick = () => { if (l.fly_to_lonlat) fly(l.fly_to_lonlat[0], l.fly_to_lonlat[1], 650); };
      li.append(b);
    }
    ul.append(li);
  }
}

function renderAssumptions(s) {
  const sm = s.impacts.summary;
  const inflowRow = sm.inflow.type.startsWith('constant')
    ? ['River inflow', `Constant ${sm.inflow.m3s['east inflow (Hörbyån mainstem)']} m³/s (Hörbyån) and ${sm.inflow.m3s['south inflow (southern arm)']} m³/s (southern arm) for the whole run`,
       'SMHI S-HYPE mean high flow used as a placeholder, not a storm hydrograph']
    : ['River inflow', `Computed event hydrographs, peaking at ${sm.inflow.peak_m3s['east inflow (Hörbyån mainstem)'].toFixed(1)} m³/s (Hörbyån) and ${sm.inflow.peak_m3s['south inflow (southern arm)'].toFixed(1)} m³/s (southern arm)`,
       'SCS-CN effective rainfall + SCS unit hydrograph + station-2128 baseflow, checked (not calibrated) against the Nov 2023 gauge record; NRCS lag equation used well outside its usual small-catchment range'];
  const rows = [
    ['Design storm', `${sm.storm_mm} mm in 24 h, alternating-block shape, peak at 40 % of the storm`, 'Rainfall totals from the brief; shape assumed'],
    ['Rain lost to the ground', `Curve Number 81.12 everywhere (sealed = 98): ${sm.effective_rain_mm} mm of ${sm.storm_mm} mm runs off`, 'One area-mean value instead of a map of CNs; assumed'],
    inflowRow,
    ['Downstream boundary', sm.boundary.startsWith('free') ? 'Free outflow along the west edge' : 'Closed — no outflow (depths overstated)', 'Model set-up choice'],
    ['River channel', 'Hörbyån arms 6 m wide, bankfull depth 0.585 m (east) / 0.571 m (south) / 1.404 m (below confluence); every other waterway 1.5 m wide × 0.5 m deep, banks 1:2', 'Bankfull depths solved from Manning’s equation to match each reach’s mean annual flood; not measured'],
    ['Culvert cuts', '2 of 25 candidate blockages cut through road embankments where a mapped waterway sits within 25 m of the pond; 23 left as genuine depressions', 'Project-defined 25 m rule, applied case by case — not a survey'],
    ['Reported location statistics', 'The 90th percentile of street-surface depth, and the wetted fraction of the footprint (share of cells > 0.05 m) — never a single-cell maximum', 'Project-defined: a maximum is set by one cell, often inside the river channel itself; these two exclude the channel and building-raised cells'],
    ['Storm drains', 'Not modelled (24.66 mm/h default capacity computed but not applied)', 'Assumed'],
    ['Buildings', 'Buildings are represented as impermeable blocks raised 10 m above the ground. At the 5 m model resolution, gaps between buildings narrower than one cell are closed, so rows of buildings can block flow more than they do in reality, and water can pond against them. Extruded heights on the map come from OSM tags or type defaults.', 'Assumed'],
    ['Surface roughness (Manning n)', 'Grass/agricultural and channel 0.035; sealed 0.015; forest 0.10', 'Literature values, copied as given'],
    ['Terrain', 'Lantmäteriet 1 m lidar, scanned 2025-02-18, RH 2000 heights, resampled to 5 m', 'Real data, processed; scan is later than the Nov 2023 event'],
    ['Model', `LISFLOOD-FP acceleration solver, ${sm.cell_m} m cells, ${sm.sim_hours} h`, 'Configuration'],
    ['Depth classes', '0.05–0.10, 0.10–0.30, 0.30–0.50, > 0.50 m', 'Project-defined display intervals, not standards'],
  ];
  $('assumed-list').replaceChildren(...rows.map(([k, v, why]) => el('li', {}, el('strong', { textContent: k }), ` — ${v}. `, el('em', { textContent: why }))));
}

function showDepthLayer(s) {
  if (!viewer) return;
  const C = Cesium;
  if (depthLayer) { viewer.imageryLayers.remove(depthLayer, true); depthLayer = null; }
  const [w, so, e, n] = s.meta.bounds_west_south_east_north;
  C.SingleTileImageryProvider.fromUrl(`${RESULTS}${s.key}/maxdepth.png`, { rectangle: C.Rectangle.fromDegrees(w, so, e, n) })
    .then(p => { depthLayer = viewer.imageryLayers.addImageryProvider(p); depthLayer.show = $('toggle-depth').checked; viewer.scene.requestRender(); })
    .catch(err => { console.error('Depth layer failed', err); $('data-status').textContent = 'The depth layer could not be drawn.'; });
}

function selectScenario(mm) {
  const s = scenarios[mm];
  if (!s) return;
  $('storm-value').textContent = `${mm} mm`;
  $('storm').setAttribute('aria-valuetext', `${mm} millimetres`);
  $('storm-note').textContent = `Showing the finished ${mm} mm run (${s.impacts.summary.boundary.startsWith('free') ? 'free downstream outflow' : 'closed downstream boundary'}).`;
  renderHeadline(s); renderLegend(s); renderLocations(s); renderAssumptions(s); showDepthLayer(s);
}

function onStorm() {
  const idx = +$('storm').value, mm = STORMS[idx];
  if (!scenarios[mm]) {
    $('storm').value = lastGoodIdx;
    $('storm-note').textContent = `${mm} mm: not yet available — its model run has not finished.`;
    return;
  }
  lastGoodIdx = currentIdx = idx;
  selectScenario(mm);
}

// ---- map ------------------------------------------------------------------------------------------------------
async function initMap() {
  if (!window.Cesium) { errorMap('The map library did not load. Check that the complete dist folder was deployed.'); return; }
  const C = Cesium;
  try {
    viewer = new C.Viewer('map', {
      baseLayer: false, baseLayerPicker: false, geocoder: false, homeButton: false,
      sceneModePicker: false, navigationHelpButton: false, animation: false, timeline: false,
      fullscreenButton: false, infoBox: false, selectionIndicator: false, requestRenderMode: true,
      msaaSamples: 1, contextOptions: { webgl: { alpha: false, preserveDrawingBuffer: true } },
      terrainProvider: new C.EllipsoidTerrainProvider(),
    });
    viewer.scene.highDynamicRange = false;
  } catch (e) {
    errorMap('3D graphics are unavailable in this browser. Enable hardware acceleration or try a browser with WebGL2.');
    console.error(e);
    return;
  }
  viewer.scene.globe.baseColor = C.Color.fromCssColorString('#d5e4e8');
  viewer.scene.backgroundColor = C.Color.fromCssColorString('#c4e4ee');
  viewer.scene.globe.enableLighting = false;
  const credit = html => viewer.scene.frameState.creditDisplay.addStaticCredit(new C.Credit(html, true));
  credit('Terrain data: Markhöjdmodell Nedladdning © <a href="https://www.lantmateriet.se/" target="_blank" rel="noopener">Lantmäteriet</a> (processed), CC BY 4.0');
  credit('© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a> · ODbL');

  addBuildings();
  updateExaggeration();
  $('exaggeration').oninput = updateExaggeration;
  $('toggle-buildings').onchange = () => { viewer.entities.show = $('toggle-buildings').checked; viewer.scene.requestRender(); };
  $('toggle-depth').onchange = () => { if (depthLayer) { depthLayer.show = $('toggle-depth').checked; viewer.scene.requestRender(); } };

  $('reset').onclick = () => fly();
  $('zoom-in').onclick = () => { viewer.camera.zoomIn(viewer.camera.positionCartographic.height * .35); viewer.scene.requestRender(); };
  $('zoom-out').onclick = () => { viewer.camera.zoomOut(viewer.camera.positionCartographic.height * .45); viewer.scene.requestRender(); };
  function mode(top) { topDown = top; $('view2d').setAttribute('aria-pressed', String(top)); $('view3d').setAttribute('aria-pressed', String(!top)); fly(); }
  $('view2d').onclick = () => mode(true); $('view3d').onclick = () => mode(false);
  fly();

  $('terrain-status').textContent = 'Buildings loaded · terrain loading';
  // Display terrain only (placeholder, not used by any model result): Esri World Elevation, as in Case 01.
  C.ArcGISTiledElevationTerrainProvider.fromUrl('https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer')
    .then(async provider => {
      viewer.terrainProvider = provider;
      $('terrain-status').textContent = '3D terrain · Esri World Elevation · display only, not the model DEM';
      provider.errorEvent.addEventListener(() => { $('terrain-status').textContent = 'Terrain service interrupted · detail may be incomplete'; });
      try {  // valley floor = terrain height where Hörbyån leaves the model at the west edge
        const [p] = await C.sampleTerrainMostDetailed(provider, [C.Cartographic.fromDegrees(13.6397, 55.8451)]);
        if (Number.isFinite(p.height)) valleyFloorM = p.height;
      } catch (e) { console.warn('Valley-floor height not sampled; exaggerating relative to the ellipsoid.', e); }
      updateExaggeration();
    })
    .catch(() => { $('terrain-status').textContent = 'Flat-earth surface · elevation service unavailable'; });

  window.hnaScenario = { viewer, buildings, scenarios, select: i => { $('storm').value = i; onStorm(); } };
}

async function main() {
  try {
    buildings = await load('../data/scenario_buildings.geojson');
    const counts = buildings.features.reduce((acc, f) => { acc[f.properties.height_method] = (acc[f.properties.height_method] || 0) + 1; return acc; }, {});
    await Promise.all([loadScenarios(), initMap()]);
    $('storm').oninput = onStorm;
    const first = [1, 0, 2].find(i => scenarios[STORMS[i]]);   // start on 70 mm if finished, else the first finished one
    if (first === undefined) {
      $('headline').replaceChildren(el('span', { className: 'eyebrow', textContent: 'NO FINISHED SCENARIO YET' }), el('p', { className: 'fine', textContent: 'The model runs have not produced results that can be shown here yet.' }));
      $('locations').replaceChildren(el('li', { className: 'fine', textContent: 'No results yet.' }));
      $('legend-list').replaceChildren();
    } else { $('storm').value = first; lastGoodIdx = currentIdx = first; selectScenario(STORMS[first]); }
    $('data-status').textContent = `${buildings.features.length} building footprints (OpenStreetMap): ${counts.osm_height_tag || 0} with OSM height tags, `
      + `${counts.osm_levels_tag || 0} from building:levels, ${counts.default_by_building_type || 0} from type defaults. Heights are assumed, not lidar.`;
  } catch (e) {
    errorMap('Scenario data could not load. Serve the complete dist directory over HTTP; opening index.html directly as a file is not supported.');
    $('data-status').textContent = e.message;
    console.error(e);
  }
}
main();
