# Scenario explorer — assumptions log

One row per assumed value shown in or driving the scenario explorer, per the
brief's Phase 1 deliverable ("`scenarios.yaml`, `ASSUMPTIONS.md` — one source
per value"). Covers what Phase 0 (terrain + buildings) uses, plus the storm
shape, default drainage capacity, and literature-constant sections of Phase 1
that are computable without external data access. Infiltration and inflow
are still open (see below).

| Value | Assumed as | Source | Status |
|---|---|---|---|
| Terrain provider | Esri World Elevation (streamed, same as Case 01) | https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer | **Placeholder.** Target is a self-hosted 1 m Lantmäteriet DEM (`scenarios.yaml` → `terrain.target_source`); blocked on a Lantmäteriet account. |
| Building footprints | Current OSM `building=*` ways in the Case 01 bbox | Overpass API, ODbL 1.0 | **Placeholder.** Target is Lantmäteriet Byggnad Nedladdning; blocked on account + legal-review ordering step. Multipolygon building relations are not fetched (ways only). |
| Building height | `height=*` tag if present, else `building:levels=*` × 3.0 m, else a default storey count per OSM `building` tag | Assumed; no measurement | **Placeholder.** Target is 90th-percentile lidar height per footprint minus DEM ground height (brief §3), or GlobalBuildingAtlas LoD1 as a documented fallback if lidar access is slow. 2740 buildings fetched 2026-09-17: 2 used `height`, 7 used `building:levels`, 2731 used the type default — i.e. almost all heights in the current view are unmeasured defaults, not lidar. |
| `church` default storeys | 2 (→ 6 m via level_height_m) | Assumed; deliberately low-confidence | Flagged in `scenarios.yaml` as a known-bad default (nave height, ignores spires). Low occurrence in the AOI. Revisit before any church appears in a Phase 3 "named places reached" result. |
| Storm hyetograph shape | `i(T_R,Å) = 190·Å^(1/3)·ln(T_R)/T_R^0.98 + 2` (T_R min, Å months), alternating-block method, 10-min blocks, peak at r=0.4 of 24 h, shaped at Å=24 months | Specified directly for this project, 2026-09-17 (supersedes an earlier "commonly cited Dahlström formula" used before) | **Formula confirmed against its worked example only.** `tests/test_scenario_generate_hyetographs.py::test_worked_example` checks the code reproduces Å=24,T_R=10 → ≈134 l/s·ha, so the implementation matches the formula as given — that is not the same as the formula being checked against a primary source (e.g. P104); no such citation exists for this exact form. Regenerated 2026-09-17 by `scripts/scenario_generate_hyetographs.py`; plots/CSVs in `docs/hyetographs/`. Method is still the alternating-block substitute for the brief's literal "Chicago Design Storm" — see `scenarios.yaml` → `storm.method_deviation_note`. |
| Default drainage capacity | 24.66 mm/h (68.51 l/s·ha), computed for a 24-month/30-min event from the corrected formula above | Same as above | **Mismatch flag cleared.** Falls inside the brief's own "roughly 20–25 mm/h" estimate (§4.2) — the previous formula's 15.95 mm/h did not, which is why the formula was corrected. Still only checked against its own worked example, not a primary source (see row above). |
| Half-blocked drainage multiplier | 0.5× capacity | Brief §4.2, stated directly | Not independently sourced; it's a scenario toggle value the brief specifies, not a measurement. |
| Submerged-outlet HAND threshold | 1.5 m | Brief §4.2, stated directly | Not independently sourced. Needs a DEM-derived HAND raster to actually apply — blocked behind the same Phase 0 terrain item as everything else needing the real DEM. |
| Manning's n (channel/sealed/grass/forest) | 0.035 / 0.015 / 0.035 / 0.10 | Chow, V.T. (1959), *Open-Channel Hydraulics*, as tabulated in brief §4.6 | Literature constants, copied as given. Not independently checked against Chow 1959 in this session. |
| Terrain conditioning (channel burn depth, bank slope, culvert widths, building obstruction height) | 1.0 m / 1:2 / 0.8–1.5 m / +10 m | Brief §4.5, stated directly | Not independently sourced. Cannot be applied yet — needs the real 1 m DEM (Phase 0 terrain blocker). |

## Phase 1 data sources fetched (brief §4.3/§4.4)

Every source below, its exact query, download date and licence — per the
brief's instruction to record all three.

| Dataset | Endpoint & query | Downloaded | Licence | Output | Notes |
|---|---|---|---|---|---|
| SGU Jordarter 25k–100k (soil types), collection `grundlager` | `https://api.sgu.se/oppnadata/jordarter25k-100k/ogc/features/v1/collections/grundlager/items?bbox=13.64,55.84,13.685,55.865&f=json` (CRS84 lon/lat bbox; storage CRS is SWEREF99 TM/EPSG:3006, API reprojects transparently) | 2026-09-17 | CC0 | `web/data/scenario_soils.geojson` (43 features) | No account needed. Bbox-filtered, not clipped — at least one returned "Vatten" (water) feature's real geometry extends well beyond this AOI; must be clipped to the exact AOI polygon before per-cell use, not just trusted from bbox inclusion (see script docstring). |
| SMHI SVAR 2022 Delavrinningsområden (subcatchments) | `https://opendata-view.smhi.se/SMHI_vatten/wfs?service=WFS&version=2.0.0&request=GetFeature&typenames=SMHI_vatten:Delavrinningsomraden_2022&bbox=55.75,13.45,55.95,13.85,urn:ogc:def:crs:EPSG::4326&outputFormat=application/json&count=500` (WFS 2.0.0/GeoServer; note this CRS URN form uses lat,lon axis order, not lon,lat) | 2026-09-17 | CC BY 4.0 — SMHI's general open-data terms, not independently re-confirmed for this specific WFS in this session (`smhi.se/data/om-smhis-data/villkor-for-anvandning`) | `web/data/scenario_subcatchments.geojson` (36 features, 8 flagged upstream of/at Hörby) | No account needed. Upstream set found by a real breadth-first walk of the `MAINDOWN` attribute (SVAR's own drainage topology) from the Hörby gauging-station catchment (ARO_UUID `1D0DC07B-F547-41F3-9EEB-C1EDF1461A55`), not inferred from geometry. Sum of local `AREA` over the 8 catchments found (151.78 km²) matches the anchor's own `AREA_UPSTREAM` figure exactly — confirms the query bbox wasn't truncating the watershed. |
| Naturvårdsverket NMD2023 basskikt (land cover) | Bulk download `https://geodata.naturvardsverket.se/nedladdning/marktacke/NMD2023/Basskikt_v2_x/NMD2023_basskikt_v2_1.zip` (2,705,971,730 bytes, no clip API exists — see below) | 2026-09-17 | CC0 | `web/data/scenario_landcover.tif` (clipped AOI raster, 537 KB), `web/data/scenario_landcover_classes.json` (classification summary) | **Resolved, by user decision.** Downloaded the full 2.7 GB national GeoTIFF to `scenario_raw/nmd/` (gitignored, not committed) and clipped it to the Hörby AOI. `pip install gdal` failed on this machine (no prebuilt Windows wheel; source build fails in setuptools immediately) — processed instead through the QGIS 3.40.4 installation already on this machine (GDAL 3.10.2 via `osgeo.gdal`/`osgeo.ogr`, reached through the qgis-mcp bridge), a deliberate, documented exception to this repo's stdlib-only Python convention. See `scripts/scenario_process_landcover.py`. |
| SMHI S-HYPE flow (Vattenwebb HydroNu) | `https://vattenwebb.smhi.se/hydronu/data/point?subid={SUBID}` | Endpoint confirmed 2026-09-17; a real Hörbyån SUBID not yet obtained | CC BY 4.0 (SMHI general terms, not independently re-confirmed for this endpoint) | `scripts/scenario_fetch_streamflow.py` (ready to run) | **Endpoint works, no account — but the SUBID has no scriptable lookup.** SVAR's WFS (used above) keys catchments by ARO_UUID, not SUBID, and no crosswalk or spatial-lookup API was found (three plausible REST endpoints all 404'd; the `nadia` SPA's JS bundle has no lookup URL; even a third-party open-source client for this API documents finding the SUBID by hand from the HydroNu map UI). **Needs a human to open https://vattenwebb.smhi.se/hydronu/, find Hörbyån at/near Hörby (≈55.849, 13.655), click the reach, and read the SUBID off the popup.** Separately: this endpoint's flow data (`chartData.coutHindcast`) is only a rolling ~30-day window ending at fetch time, not a queryable archive — it cannot return the actual November 2023 flow. `chartData.mq`/`mlq`/`mhq` (long-run mean/low/high, m³/s) are usable as a general baseflow reference once a SUBID is known; the historical event figure would need SMHI's separate `nadia` bulk-download portal, untested here for login requirements. |

## Soil-type → SCS hydrologic soil group (documented assumption)

`scripts/scenario_fetch_soils.py`'s `SOIL_TO_HYDROLOGIC_GROUP` table, assigning each SGU `jg2_tx` soil class an assumed SCS group (A=high infiltration … D=low), by typical grain size/drainage character — **not a measured infiltration rate or a site calibration**:

| SGU class (`jg2_tx`) | Assumed group | Rationale |
|---|---|---|
| Isälvssediment, Isälvssediment sand | A | Glaciofluvial sand/gravel — coarse, well-drained |
| Postglacial sand | A | Coarse, well-drained |
| Postglacial finsand, Svämsediment sand | B | Finer sand — moderate infiltration |
| Sandig morän | B | Sandy till — moderate |
| Glacial silt | C | Silt — moderate-low |
| Fyllning | C | Anthropogenic fill — variable and unassessed here; conservative mid-range default, not a real classification |
| Svämsediment ler–silt, Kärrtorv (fen peat), Sedimentärt berg | D | Clay, organic/high-water-table peat, and bedrock all treated as low-infiltration for runoff purposes |
| Vatten (open water) | *(excluded)* | Not a soil class; excluded from Curve Number assignment rather than guessed |

Every one of the 12 soil classes actually present in the Hörby AOI (fetched 2026-09-17) has an assignment; a class outside this set gets `hydrologic_group: null` and must be classified before use, rather than silently defaulted.

## NMD land cover → sealed/pervious/water (documented assumption)

`scripts/scenario_process_landcover.py`'s `NMD_CLASS_LEGEND` classifies every one of NMD2023's 53 land-cover classes (names sourced directly from the dataset's own `NMD2023bas_v2_1.tif.vat.dbf` sidecar file, not guessed) as `sealed`, `pervious`, or `water`. Two classes needed a real judgement call rather than a clean read of the class name:

| NMD class (code) | Assigned as | Why it's a judgement call |
|---|---|---|
| Anlagd mark, ej byggnad eller väg/järnväg (52) | sealed | "Developed land, not building or road/rail" covers genuinely mixed surfaces (gravel yards, sports pitches, etc.) with different real runoff behaviour. Assigned sealed as the conservative default for anthropogenic non-vegetated ground — not source-backed, revisit if this fraction matters in the Hörby AOI. |
| Öppen fastmark utan vegetation (411) | pervious | "Bare open ground, not glacier/snow" could be bare soil (infiltrates) or exposed bedrock (near-impervious); assigned pervious on the assumption soil is more common than bare rock in this lowland AOI — not source-backed. |

**Result for the Hörby AOI (fetched 2026-09-17, 10 m pixels):** 28.6% sealed, 70.7% pervious, 0.7% water. Full per-class breakdown in `web/data/scenario_landcover_classes.json`.

## Hörbyån inflow boundary — corrected 2026-09-18

The upstream-catchment anchor recorded above (`1D0DC07B`, "Vid mätstation Hörbyån", 151.78 km²) is a valid catchment delineation but **the wrong point for the brief's §4.4 upstream boundary hydrograph** — it sits downstream of the town, mostly outside the model AOI. Checked against the OSM river geometry after a prompt to eyeball it; map: `docs/horby_inflow_point_check.png`.

What the geometry actually shows (flow is **east → west**; the anchor drains to "Mynnar i Östra Ringsjön"):

| Boundary crossing | Coordinates | OSM way | SVAR catchment | Upstream area |
|---|---|---|---|---|
| **Inflow** — Hörbyån mainstem, east edge | 55.84823, 13.68501 | 77387390 (`name=Hörbyån`) | Ebbamölleån | 77.61 km² |
| **Inflow** — southern arm, south edge | 55.83990, 13.66812 | 77387397 (unnamed, `waterway=river`) | Vid mätstation Hörbyån, södra armen | 62.22 km² |
| Outflow — Hörbyån leaves AOI, west edge | 55.84508, 13.63971 | 77387390 | Vid mätstation HEÅKRA | 147.49 km² at this point |

Three consequences, all of which would have been silent errors:

1. **Two inflows, not one.** They join at 55.84725, 13.66771, ~1 km east of the town centre. A single upstream hydrograph would misrepresent the system.
2. **Double-counting risk.** The brief's method rains on the whole 2D grid *and* adds boundary hydrographs. Each hydrograph must therefore carry only area *outside* the domain (77.61 + 62.22 = 139.83 km²), not the 151.78 km² anchor figure, which includes local area the rain-on-grid already produces.
3. **Naming mismatch worth knowing.** OSM tags the *eastern* inflow `name=Hörbyån`, while SVAR calls the catchment it drains *Ebbamölleån*; the southern arm is unnamed in OSM but named in SVAR. Don't match these two datasets by name.

Separately, the point previously suggested for the manual HydroNu SUBID lookup (55.849, 13.655) is **116 m off-stream**. On-stream equivalent: **55.85001, 13.65548** — verified on Hörbyån's mainstem, 492 m from the nearest other watercourse, and downstream of the confluence so it carries combined flow.

## Open items carried from the brief, not yet started

Once land cover and soils are combined into an actual Curve Number grid
(brief §4.3), infiltration will have every input it needs. Engine choice
and the run matrix (§4.7) are Phase 2 work. Do not treat any of this as
"assumed to be zero"; it simply hasn't been decided or found yet.

## Four follow-ups on the inflow work — resolved 2026-09-18

### 1. Real gauge for "Vid mätstation Hörbyån" — HEÅKRA, not a "Hörby" station

Searched SMHI's open Hydrological Observations API (parameter 1,
Vattenföring/Dygn — daily discharge; 720 stations nationally, fetched
2026-09-18) for any station named Hörby/Hörbyån. **None exists.** The SVAR
subcatchment named "Vid mätstation Hörbyån" (ARO_UUID 1D0DC07B, the original
anchor) is a different, further-downstream catchment with no coincident
open-data gauge nearby either.

What does exist: station **HEÅKRA (id 2128)**, 55.8449 N / 13.6350 E, owner
SMHI, **active, period of record 1973-05-23 to present** (fetched archive's
own first/last rows). It sits **0.31 km from the model's already-identified
west outflow boundary point** (55.84508, 13.63971), and its own
`catchmentSize` (146.8 km²) is close to SVAR's AREA_UPSTREAM for the "Vid
mätstation HEÅKRA" polygon (147.494 km², i.e. the 147.49 km² used in
`scenarios.yaml`) — ~0.5% apart. `region`/`catchmentName` = 96/"RÖNNE Å",
the larger system Hörbyån feeds. Treated as the real-world counterpart of
the model's west outflow, not of the "Vid mätstation Hörbyån" anchor by
name.

Fetched daily discharge for Nov 2023 (30/30 days) and Jan 2024 (31/31 days),
all flagged **G** ("kontrollerade och godkända" — checked/approved). Script:
`scripts/scenario_fetch_observed_discharge.py`. Output:
`web/data/scenario_observed_discharge_heakra.json` /
`.csv`.

- **November 2023 mean discharge: 7.171 m³/s.** This is the whole-month
  mean requested — it is *not* a dry-antecedent baseflow figure, since it
  includes the flood peak itself (daily discharge rises from ~3.7 m³/s on
  15 Nov to 24.1 m³/s on 17 Nov, matching the reported 17–19 November flood
  event almost exactly). Recorded here as-is, per the instruction to use
  the observed November mean in place of an assumed value.
- **January 2024 mean discharge: 8.295 m³/s** (fetched for reference/period
  comparison, not itself substituted for anything).

This observed 7.171 m³/s is a different quantity from S-HYPE's long-run
`mq` statistics recorded elsewhere (e.g. SUBID 185's mq = 1.819 m³/s) —
S-HYPE's `mq` is a *modelled long-term mean*, while 7.171 m³/s is the
*real, single-month, flood-inclusive* observed mean. Both are kept, not
merged.

### 2. AOI area vs. the 147.49 − 139.83 = 7.66 km² implied "local" area

The model AOI is the bbox used throughout Phase 1
(`scripts/scenario_fetch_buildings.py` `BBOX`,
`scripts/scenario_process_landcover.py` `AOI_WGS84`): lat 55.84–55.865 N,
lon 13.64–13.685 E.

Computed precisely in QGIS (EPSG:4326 rectangle transformed to EPSG:3006,
SVAR's own projected CRS, then `.area()`):

- **AOI bbox area: 7.8399 km².**
- **147.49 − 139.83 = 7.66 km²** (SVAR's outflow upstream area minus the
  uncorrected sum of the two inflow upstream areas).

These are two independently computed numbers from two different methods
(a geodetic bbox area vs. a SVAR catchment-area subtraction) that happen to
be close (~2.3% apart, 0.18 km²) — **not reconciled to force agreement.**
Both are recorded in `scenarios.yaml` (`inflow.boundary_note`). The AOI bbox
is the actual rain-on-grid domain; the 7.66 km² figure is what SVAR's own
delineation implies is "local to the outflow's own subcatchment" — they are
conceptually related but not guaranteed to be the same polygon, and this
session did not attempt to prove they are.

### 3. Inflow catchment polygons DO overlap the AOI — corrected areas

Checked both boundary-inflow SVAR polygons (Ebbamölleån, "Vid mätstation
Hörbyån, södra armen") against the AOI bbox for overlap, in QGIS
(EPSG:3006, `QgsGeometry.intersection`):

| Catchment | SVAR AREA_UPSTREAM (km²) | Overlap with AOI (km²) | Corrected (outside-AOI) area (km²) |
|---|---|---|---|
| Ebbamölleån | 77.609 | 0.713 | **76.896** |
| Södra armen | 62.217 | 0.232 | **61.985** |
| **Sum** | 139.826 | 0.945 | **138.881** |

Both catchments overlap the AOI by a real, non-trivial amount (their
downstream tips extend slightly into the modelled domain before crossing
the boundary). **Using the uncorrected SVAR AREA_UPSTREAM figures as each
boundary hydrograph's contributing area would double-count 0.945 km² of
land that the rain-on-grid domain already covers.** The corrected areas
above (76.90 and 61.98 km²) are what each hydrograph should represent if
it is to carry only area *outside* the AOI, per the brief's own
double-counting caveat. Recorded in `scenarios.yaml` under each
`boundary_inflows` entry (`aoi_overlap_km2`, `aoi_overlap_corrected_km2_svar`).

This is an area correction only — it does not change which SUBID/catchment
is used, just what upstream area that inflow's hydrograph should be
understood to represent once rain-on-grid is added on top.

### 4. S-HYPE SUBIDs for each inflow, found and fetched separately

The 2026-09-17 blocker ("no scriptable SUBID lookup exists") is
**superseded**. Reading HydroNu's own client code
(`https://vattenwebb.smhi.se/hydronu/9b203093c2f5d9e820dd2f86d1eec9ab.js`,
the requirejs `data-main` bundle) shows its map click handler calls
`data/point?x={SWEREF99TM_x}&y={SWEREF99TM_y}` — the same `data/point`
endpoint already used by `scripts/scenario_fetch_streamflow.py`, just
keyed by coordinate instead of SUBID.

**Important finding, not obvious from the endpoint alone:** querying
`x,y` near the Hörbyån headwaters does *not* return the nearest SUBID's own
data — several points 1–9 km apart all returned the same distant fallback
point (~55.86 N, 13.575 E, near Ringsjön/Höör, upstreamArea 356 km²). What
actually works: the query response's own `stations` dict lists *every*
nearby SUBID used to build that response's network diagram (positions in
EPSG:3006, plus `upstream`/`downstream` SUBID links) — the real target
SUBID is found by searching *that* dict, not by trusting the top-level
`poiCenter`/`subid` of the initial query. Script:
`scripts/scenario_lookup_subid.py LAT LON` (stdlib-only; implements its own
WGS84→SWEREF99 TM transverse Mercator to avoid a pyproj/GDAL dependency,
checked against QGIS's own transform to <0.01 m agreement).

**Nearest-distance alone is also not sufficient** to pick the right SUBID:
for the södra armen boundary point, the single nearest node (SUBID 64473,
108 m away) is a small headwater sub-piece, not the aggregation point for
the whole named catchment. Disambiguated instead by comparing each
candidate's own `upstreamArea` (from `scripts/scenario_fetch_streamflow.py
SUBID`) against the independent SVAR AREA_UPSTREAM figure for the same
named catchment:

| Inflow | SUBID | S-HYPE upstreamArea (km²) | SVAR AREA_UPSTREAM (km²) | Agreement |
|---|---|---|---|---|
| Hörbyån mainstem (east edge, "Ebbamölleån") | **184** | 81.60 | 77.61 | ~5% apart |
| Southern arm (south edge, "södra armen") | **64474** | 59.65 | 62.22 | ~4% apart |
| *(cross-check only)* west outflow, "Vid mätstation HEÅKRA" | *185* | *146.67* | *147.49* | *~0.6% apart* |

The two inflow SUBIDs' upstream areas are close to but not identical to
SVAR's — expected for two independent delineations/vintages (S-HYPE
subbasins vs. SVAR Delavrinningsområden), not forced to match. SUBID 185's
much tighter agreement (0.6%) for the already-independently-identified west
outflow point is a useful cross-check that this coordinate→SUBID method is
sound, and separately corroborates the HEÅKRA gauge identification in
finding 1 above.

**Fetched each inflow's full S-HYPE record separately, as two distinct
files — never merged, never area-split from a single series:**

- `web/data/scenario_streamflow_subid184.json` (Ebbamölleån/east mainstem):
  mq=0.943, mlq=0.062, mhq=6.432 m³/s.
- `web/data/scenario_streamflow_subid64474.json` (södra armen):
  mq=0.667, mlq=0.035, mhq=4.787 m³/s.

Both fetched with `scripts/scenario_fetch_streamflow.py SUBID`, run once
per SUBID (unchanged from its original design — it always took one SUBID
per invocation, per file). The existing endpoint limitation still applies
unchanged: `coutHindcast`/`psimHindcast` in each file are a rolling ~30-day
window ending at fetch time, not the November 2023 event; `mq`/`mlq`/`mhq`
are the usable long-run references from S-HYPE specifically. For the real
November 2023 event flow, use finding 1's HEÅKRA gauge observation instead
— it is a different, better-suited data source for that specific need, not
a replacement for having two separate S-HYPE inflow records.

**All joins in this section are on SUBID (184, 64474, 185) or on SVAR
ARO_UUID, never on name** — "Hörbyån" alone is ambiguous across at least
four distinct SVAR features in this dataset (the mainstem OSM way, the
anchor catchment, the södra armen catchment, and the town itself).

## Five more follow-ups — resolved 2026-09-18 (round 2)

### 1. Baseflow: pre-event value, not the flood-inclusive monthly mean

The Nov 2023 and Jan 2024 monthly means recorded above (7.171 and
8.295 m³/s) **both include their month's flood event** and are not usable
as a wet-antecedent *initial condition* — they are now recorded as context
only, not model input. Script: `scripts/scenario_compute_baseflow.py`
(reads the already-fetched `scenario_observed_discharge_heakra.json`, no
new fetch).

**November 2023** (event: 17–19 Nov, **peak 24.1 m³/s on 17 Nov**). The
daily series is flat/declining through 15 Nov, then **16 Nov (11.1 m³/s)
is already the rising limb** ahead of the reported flood — not a
pre-event day, contrary to treating "15–16 Nov" as a clean two-day
window.

| Candidate | Value (m³/s) |
|---|---|
| Day 15 alone (last clean day) | 3.65 |
| Day 16 alone (**contaminated — event onset**) | 11.1 |
| Median(1–15 Nov) | **4.47** |
| Monthly mean (context only, event-inclusive) | 7.171 |

**Used median(1–15 Nov) = 4.47 m³/s** as the wet-antecedent baseflow input
— more robust than a single day, and cleanly excludes the contaminated
16th.

**January 2024** (event: 22–27 Jan, peak 27.8 m³/s on 24 Jan). Mirroring
Nov's "1–15" window literally is misleading here: **days 1–3 (9.9, 10.8,
7.65 m³/s) are the recession tail of a different, earlier event**, not
part of the buildup to the 22–27 Jan flood — flow actually stabilises
4–20 Jan, then **21 Jan (4.74 m³/s) is already rising** ahead of that
event.

| Candidate | Value (m³/s) |
|---|---|
| Day 20 alone (last clean day before the 22–27 Jan event) | 3.16 |
| Day 21 alone (**contaminated — event onset**) | 4.74 |
| Median(1–15 Jan) (literal mirror of Nov's window — **includes 3 contaminated days from the unrelated earlier event**) | 3.62 |
| Median(4–20 Jan) (stable window, excludes both the unrelated earlier recession and this event's own onset) | **3.19** |
| Monthly mean (context only, event-inclusive) | 8.295 |

**Used median(4–20 Jan) = 3.19 m³/s**, not median(1–15 Jan), because the
first three January days are contaminated by an unrelated prior event, not
by the event this figure is meant to sit ahead of — using 1–15 verbatim
would silently fold a different flood's recession into a "baseflow"
figure. Both are recorded so this choice is visible, not hidden.

**Window-end check, done programmatically, not just asserted (2026-09-18
follow-up):** a plain day-over-day ratio threshold is too blunt for this
series — the "stable" 4–20 window itself contains ~30–50% single-day
wiggles (e.g. 13 Jan 2.67 → 14 Jan 4.1 m³/s) that a fixed ratio would
misflag as a rise. Instead `scripts/scenario_compute_baseflow.py`'s
`check_window_ends_before_rise()` requires a day to be a **new running
maximum relative to the whole window so far** to count as the rise's
onset — a genuine breakout above the established range, not a wiggle
inside it. Result: **20 Jan (3.16 m³/s) stays within the 4–20 range (max
4.27 m³/s); 21 Jan (4.74 m³/s) is the first day to break above that range
— confirmed rising-limb onset at 21 Jan.** The window ending at 20 Jan is
therefore confirmed to sit before the rise; **no shift was needed**, and
the 3.19 m³/s figure above is unchanged. (Had the check failed, the
window end would have been walked backward a day at a time and the median
recomputed — the script does this automatically rather than assuming the
literal date is always right.)

**Event peaks, recorded together for comparison:**

| Event | Peak discharge | Peak date |
|---|---|---|
| November 2023 | **24.1 m³/s** | **17 Nov 2023** |
| January 2024 | **27.8 m³/s** | **24 Jan 2024** |

### 2. Plausibility check on station 2128 — passes, not flagged

Script: `scripts/scenario_plausibility_check_station2128.py`. Fetches (or
reuses a cached copy of) the full 1973-05-23–2026-09-16 archive (19,475
daily records — cached at
`web/data/_cache/smhi_hydroobs_station2128_corrected_archive.csv`).

- **Long-term mean flow: 1.8349 m³/s** (long-term median: 0.907 m³/s — the
  large mean/median gap itself reflects the network's typically flashy,
  right-skewed daily-flow distribution, not a data error).
- **SMHI's own stated drainage area for station 2128: 146.8 km².**
  - vs. SVAR `AREA_UPSTREAM` for the *same point* ("Vid mätstation
    HEÅKRA"): 147.494 km² (+0.47%) — a tight match, as expected for the
    same physical point measured two ways.
  - vs. SVAR `AREA_UPSTREAM` for the anchor ("Vid mätstation Hörbyån"):
    151.783 km² (+3.39%) — **this is a different, further-downstream
    catchment** (see the "corrected 2026-09-18" section above), so a gap
    here is expected and is not a station-identity problem.
- **Long-term mean specific runoff:** 1.8349 m³/s × 1000 / 146.8 km² =
  **12.499 l/s/km²**.
- **Nov 2023 specific runoff (using the flood-inclusive monthly mean,
  7.171 m³/s, for this specific sanity check — not the pre-event baseflow
  above):** 7.171 × 1000 / 146.8 = **48.851 l/s/km²**.
- **Ratio: 3.908×.** Below the 5× flag threshold —
  **no flag; station 2128's Nov 2023 reading is plausible and was safe to
  use.** (Had this exceeded 5×, this session would have stopped before
  using the station's data in finding 1 or anywhere downstream of it.)

### 3. AOI area draining to the west outflow — NOT the bbox area

Corrected the earlier "AOI area" figure, which was just the AOI bounding
box (7.8399 km²) — that is the size of the rain-on-grid **domain**, not
necessarily the area that actually **drains to** the west outflow point.
Script: `scripts/scenario_compute_aoi_drainage_area.py` (run via the
qgis-mcp bridge, same documented GDAL exception as
`scripts/scenario_process_landcover.py`).

Method: walked SVAR's own `MAINDOWN` topology to find every subcatchment
upstream of, or equal to, the west outflow point ("Vid mätstation
HEÅKRA") — seven catchments in total (Ebbamölleån, "Mynnar i Ebbamölleån",
two unnamed catchments feeding södra armen, södra armen itself, a tiny
unnamed catchment between södra armen and HEÅKRA, and HEÅKRA's own local
piece) — then intersected each with the AOI bbox in EPSG:3006 and summed
the overlaps:

| Catchment | Own area (km²) | Overlap with AOI (km²) |
|---|---|---|
| Ebbamölleån | 49.028 | 0.713 |
| Mynnar i Ebbamölleån | 28.582 | 0.000 |
| (unnamed, feeds södra armen) | 16.533 | 0.000 |
| (unnamed, feeds södra armen) | 16.149 | 0.000 |
| Södra armen | 29.535 | 0.232 |
| (unnamed, feeds HEÅKRA) | 0.102 | 0.102 |
| Vid mätstation HEÅKRA (own local piece) | 7.565 | 4.915 |
| **Sum (= AOI area draining to the outflow)** | | **5.962** |

**Three separately labelled quantities, not reconciled to agree:**

1. **AOI bounding-box area (the modelled domain's own size): 7.8399 km².**
2. **AOI area that actually drains to the west outflow (SVAR-delineated):
   5.962 km²** — 76.0% of the bbox; the remaining ~1.88 km² of the AOI
   rectangle drains elsewhere per SVAR's delineation (two of the far
   upstream headwater catchments have zero overlap with the AOI at all,
   which the script reports rather than assumes).
3. **147.49 − 139.83 = 7.66 km²** — SVAR's own arithmetic (outflow's total
   upstream area minus the two boundary inflows' upstream areas). This is
   *not* clipped to the AOI bbox shape in any way; it happens to be close
   to figure 1 (bbox area) but is a genuinely different computation from
   figure 2, and the three are not the same quantity despite two of them
   being numerically close.

### 4. Inflow hydrographs: S-HYPE areas paired with S-HYPE flows, AOI-overlap applied as a scaling factor

Re-paired each inflow's flow series with its **own S-HYPE upstreamArea**
(not SVAR's), since mixing a SVAR area with an S-HYPE-derived flow series
would itself be a basis mismatch:

| Inflow | SUBID | S-HYPE upstreamArea (km²) | SVAR AREA_UPSTREAM (km²) | Divergence |
|---|---|---|---|---|
| Ebbamölleån/east mainstem | 184 | 81.599 | 77.609 | +5.1% |
| Södra armen | 64474 | 59.647 | 62.217 | −4.1% |

Recorded as a divergence, not reconciled — two different delineations
(S-HYPE subbasins vs. SVAR Delavrinningsområden) are not expected to agree
exactly.

**AOI-overlap correction is now applied as an actual scaling factor on
each flow series**, not just recorded as a corrected area. Script:
`scripts/scenario_correct_streamflow_for_aoi.py`.

- SUBID 184: overlap 0.713 km² (from the SVAR Ebbamölleån polygon ∩ AOI
  bbox — S-HYPE's own upstream-basin polygon is not available from
  HydroNu for aggregated points, only a local-subbasin polygon; see
  finding 5) → corrected area 80.886 km² → **scaling factor 0.99126**.
- SUBID 64474: overlap 0.232 km² → corrected area 59.415 km² → **scaling
  factor 0.99611**.

**Assumption stated plainly** (not a measurement): flow scales linearly
with contributing area (uniform specific-runoff assumption). The scaling
factor is applied to `mq`, `mlq`, `mhq`, and every value in
`chartData.coutHindcast`/`coutForecast` (all m³/s — flow). It is **not**
applied to `psimHindcast`/`psimForecast` (mm — precipitation intensity,
which does not change because less downstream area is being counted).

Outputs, kept as two separate files alongside the unscaled originals
(nothing merged):

- `web/data/scenario_streamflow_subid184_aoi_corrected.json` (mq
  0.9428 → 0.9346 m³/s)
- `web/data/scenario_streamflow_subid64474_aoi_corrected.json` (mq
  0.6675 → 0.6649 m³/s)

Each carries an `_aoi_correction` block recording the exact area, overlap,
factor, and method, so the correction is traceable back to its inputs
rather than a silent multiply.

### 5. HydroNu `data/point` is undocumented, unsupported, and may change

This is not a published, versioned SMHI API — it was found by reading
HydroNu's own client JavaScript (see `scripts/scenario_lookup_subid.py`'s
module docstring), not from any API reference. Treat everything sourced
from it (SUBIDs 184/64474/185 and their flow series) as **reverse-engineered
and liable to break or change silently** if SMHI updates that page.

Mitigations added, in `scripts/_hydronu_cache.py`, used by both
`scripts/scenario_fetch_streamflow.py` and `scripts/scenario_lookup_subid.py`:

- **Caching.** Every raw response is cached under
  `web/data/_cache/hydronu/`, keyed by request URL. Re-running either
  script reads the cache instead of re-hitting the endpoint; pass
  `--force` to bypass it and re-fetch.
- **Rate limiting.** At most one request per 2 seconds, enforced via a
  shared timestamp file in the same cache directory (works across separate
  process invocations, not just within one run) — a courtesy limit, since
  this endpoint has no published usage terms to follow.

If this endpoint stops working in a future session, the values already
recorded here (SUBIDs, areas, mq/mlq/mhq, the cached JSON responses
themselves) remain usable as a frozen snapshot; only *refreshing* them
would be blocked.

## Two more follow-ups — resolved 2026-09-18 (round 3)

### 1. SVAR subtraction retired as a local-area check; closed in S-HYPE terms instead

Section "AOI area vs. the 147.49 − 139.83 = 7.66 km²..." above (round 1,
finding 2) used the **uncorrected** SVAR inflow areas (139.83 =
77.61 + 62.22). Recomputed instead with the **corrected** (outside-AOI)
inflow areas from round 1 finding 3 (76.896 + 61.985 = 138.881):

**147.494 − 138.881 = 8.613 km²** — **larger than the AOI bounding box
itself (7.8399 km²).** A "local area" figure that exceeds the box it is
supposed to be local to is not a coherent local-area check (subtracting a
corrected, smaller pair of inflow areas from an uncorrected, larger
outflow area double-removes area both delineations already share near the
boundary). **This arithmetic is retired as a local-area cross-check.**
Script: `scripts/scenario_check_shype_area_closure.py`.

Replacement: close the same balance entirely in **S-HYPE terms** (no SVAR
figures mixed in), using each SUBID's own `upstreamArea`:

| Quantity | Value (km²) |
|---|---|
| SUBID 185 (west outflow) S-HYPE upstreamArea | 146.672627 |
| SUBID 184 (Ebbamölleån) S-HYPE upstreamArea | 81.598542 |
| SUBID 64474 (södra armen) S-HYPE upstreamArea | 59.647034 |
| **S-HYPE closure: 185 − (184 + 64474)** | **5.427051** |
| Computed AOI-draining area (round 2 finding 3, SVAR MAINDOWN walk ∩ AOI bbox) | 5.962 |
| **Residual (computed − S-HYPE closure)** | **0.534949 (≈8.97% of the computed figure)** |

Both figures are reported, not reconciled: the S-HYPE closure is subbasin
arithmetic on one delineation/vintage; the computed 5.962 km² is a
topology walk on a different one (SVAR Delavrinningsområden) intersected
with the AOI bbox. A residual of this size is consistent with two
independent delineations, not evidence either is wrong.

### 2. Inflow outlets are downstream of their AOI crossings — the ~0.99 scaling is flagged as insufficient

For each inflow SUBID, measured the distance from its S-HYPE outlet node
to the AOI crossing point used to identify it (round 1 finding "Hörbyån
inflow boundary"), and the area of that SUBID's own upstream polygon
lying inside the AOI. Script:
`scripts/scenario_check_inflow_outlet_position.py`.

**Outlet-position caveat found while building this check:** a per-SUBID
`data/point?subid=X` response's own top-level `poiCenter` is **not**
reliable as that SUBID's true position (confirmed for SUBID 184:
`poiCenter` sits 6.3 km from the true node). Nor is a response's
self-referential `stations[subid]` entry (`subid184.json`'s own
`stations["184"]["pos"]` is the exact same coordinate pair as
`subid64474.json`'s own `stations["64474"]["pos"]` — the same value for
two different reaches, clearly a placeholder). What **is** reliable: a
station's `pos` in the `stations` dict of a query that did **not**
self-query it — identical across every independent response checked here
(3 responses per SUBID). Positions below use only cross-validated values.

**One-line warning for future use of this endpoint: a per-SUBID
`data/point?subid=X` response's own `poiCenter` and its self-referential
`stations[subid]` entry both return placeholder coordinates, not that
SUBID's real position — never trust either without cross-checking against
a `stations[subid]` entry from a *different* query.**

Separately: `scripts/scenario_correct_streamflow_for_aoi.py` states each
response's `coordinates` field is "only a LOCAL subbasin polygon, not the
full aggregated upstream one." Checked against SUBID 64474, whose
`subbasinArea` (0.374 km²) is tiny next to its `upstreamArea`
(59.647 km²): the `coordinates` polygon's own shoelace area is
**59.647 km², matching `upstreamArea`, not `subbasinArea`.** So
`coordinates` is in fact the full upstream polygon, at least for this
SUBID — corrected here rather than left standing.

| Inflow | Distance, outlet → crossing | Outlet position relative to crossing | Own upstream polygon area inside AOI |
|---|---|---|---|
| SUBID 184 (Ebbamölleån, east edge) | 946.3 m | **downstream** (dx −944.9 m, i.e. inside the AOI) | **2.2481 km²** |
| SUBID 64474 (södra armen, south edge) | 627.0 m | **downstream** (dy +626.9 m, i.e. inside the AOI) | **0.2804 km²** |

Both outlets sit **downstream of the crossing** — i.e. already on the AOI
side of the boundary, matching the qualitative "downstream tips extend
slightly into the domain" description in round 1 finding 3, but the
quantities disagree substantially with what that finding used:

- **SUBID 184: the 0.99126 scaling factor is flagged as insufficient.**
  Its own upstream polygon puts 2.2481 km² inside the AOI — over 3× the
  0.7130 km² SVAR-polygon overlap the current factor is based on. An
  S-HYPE-basis-consistent recomputation would give **0.97245**, not
  0.99126.
- **SUBID 64474: flagged, smaller effect.** 0.2804 km² inside the AOI vs.
  the 0.2321 km² used — an S-HYPE-basis-consistent factor would be
  **0.99530** vs. 0.99611.

**Update, 2026-09-18 (same day): applied to production.** The recomputed,
S-HYPE-basis-consistent factors are now live in
`web/data/scenario_streamflow_subid184_aoi_corrected.json` (0.97245) and
`..._subid64474_aoi_corrected.json` (0.99530) — `scripts/
scenario_correct_streamflow_for_aoi.py`'s `INFLOWS` overlap constants were
updated to each SUBID's own upstream-polygon-∩-AOI-bbox area
(2.24809033984375 / 0.2803689753417969 km²) and the script re-run, which
overwrote the two `*_aoi_corrected.json` files in place. No parallel
"v2" files were kept — git history is the record of the prior (0.99126 /
0.99611) correction.

**Why the crossing-based (polygon-∩-AOI) area is the correct basis, not
the outlet position itself:** the outlet is just a node in S-HYPE's
network graph — its `upstreamArea` is a flow accounting figure for
everything upstream of that node, including whatever slice of that
upstream polygon happens to fall inside the AOI. Since the outlet sits
*downstream* of the AOI crossing (previous finding), that slice is real:
the rain-on-grid model already generates its own runoff for that same
ground inside the AOI. Scaling by outlet-to-crossing *distance* would say
nothing about how much of the SUBID's actual drainage area lies in that
gap; scaling by the polygon area actually inside the AOI (2.2481 /
0.2804 km²) directly removes the ground the boundary hydrograph and the
rain-on-grid model would otherwise both claim.

**S-HYPE closure re-run with these same crossing-based (AOI-corrected)
inflow areas:** 146.672627 − (79.35045 + 59.36667) = **7.9555 km²**, vs.
the computed 5.962 km² → residual **−1.9935 km² (≈−33.4%)**. The residual
does **not** shrink — it grows roughly 4× in magnitude and flips sign.
Why: **SUBID 185 (the west outflow) has the same outlet-vs-crossing
geometry issue as the two inflows** — its own S-HYPE outlet node sits
~267 m *downstream of* the AOI's west boundary crossing, i.e. already
past the west edge, outside the AOI. Its `upstreamArea` (146.673 km²) was
left uncorrected in this re-run (only the two inflows were corrected), so
it still carries an extra strip of area between the west edge and 185's
own outlet (**~2 km²**, matching the residual's growth almost exactly)
that this subtraction never removes. The result is left holding both the
true local area and that uncorrected strip, rather than closing. (Not
investigated further, per instruction — the round-3 finding-1 closure
above, using each SUBID's plain `upstreamArea` for all three points
consistently, remains the reported S-HYPE closure.)

## Curve Number grid — built 2026-09-18 (last outstanding Phase 1 item)

Combines `web/data/scenario_landcover.tif` (NMD2023, sealed/pervious/water)
with `web/data/scenario_soils.geojson` (SGU hydrologic groups) into a
per-cell SCS Curve Number, per brief §4.3. Script:
`scripts/scenario_compute_curve_number.py`. Kept stdlib-only like the rest
of this repo (a ~30-line parser for this specific uncompressed/striped/
16-bit GeoTIFF, and a plain scanline/even-odd polygon fill for the soil
polygons — handles holes automatically, no separate exterior/hole logic)
rather than another GDAL/QGIS round-trip, since both inputs are already
AOI-sized and the only remaining step is combining two rasters/vectors
already in hand.

**CN table source:** USDA NRCS (1986), TR-55 Table 2-2c — the same
citation the brief already gives for Curve Numbers. Only the rows needed
for classes present in this AOI are reproduced in the script, not the
full table.

**Documented assumption, applied once and uniformly, not guessed per
class:** NMD carries no ground-cover-*density* attribute — TR-55's
"hydrologic condition" (poor/fair/good) describes canopy/cover density,
which NMD's class names don't encode. NMD's dry/fresh/moist qualifiers
describe soil *moisture regime* instead, a different axis already
captured separately by the SGU hydrologic-group lookup — using it as a
proxy for cover density would be inventing a correlation, not reading
one. Every pervious class is therefore assigned TR-55's **POOR**
condition uniformly: the conservative (higher-CN, more-runoff) choice,
appropriate for a flood-hazard tool with no real cover-density data to
justify anything better.

Each NMD class present in the AOI is mapped to one of five TR-55
categories by vegetation type — arable → row crops (straight row);
forest (dry-land and wetland alike) → woods; shrub-dominated → brush;
grass-dominated/open wetland-mire/moss → pasture/rangeland; classes with
no vegetation cover at all → fallow, bare soil. Full mapping in
`NMD_TO_TR55` in the script.

**On pervious cells only** (brief §4.3) — sealed and water cells get no
CN (not a CN of 0). A cell is also left without a CN, and counted
separately, if its class isn't in the mapping (0 occurred) or no SGU soil
polygon resolves a hydrologic group at its centre (61 cells — see "Curve
Number gaps" below for exactly why, not just "AOI edge" as originally
guessed here).

**Result** (`web/data/scenario_curve_number_summary.json`,
`web/data/scenario_curve_number.asc` — ESRI ASCII grid, LISFLOOD-FP-native
format, 287×273 cells at ~10 m, EPSG:3006):

| | |
|---|---|
| Resolved (CN assigned) | 55,306 / 78,351 cells = **70.6%** of the AOI |
| Excluded — sealed | 22,446 cells |
| Excluded — water | 538 cells |
| Genuine gap — no soil group (now fallback-filled, see below) | 61 cells |
| Unmapped NMD classes | 0 |
| **Mean CN, resolved cells only** | **74.28** |

Soil group B dominates the resolved cells (woods_poor/B 17,509;
pasture_poor/B 18,796; row_crops_sr_poor/B 9,995; brush_poor/B 4,248 —
all four groups A–D appear, but B is by far the largest). Not reconciled
against any other source — this is the first time a CN grid has existed
for this AOI, so there is nothing yet to cross-check it against.

## Curve Number gaps — mapped and broken down — 2026-09-18

The 29.4% of the AOI with no CN (23,045 of 78,351 cells) was mapped and
its reasons broken down, rather than left as one aggregate percentage.
Script: `scripts/scenario_diagnose_curve_number_gaps.py`, reading
`scripts/scenario_compute_curve_number.py`'s new per-cell reason grid
(`web/data/scenario_curve_number_reason_grid.txt`). Map:
`docs/curve_number_gaps.png` (gray = sealed, blue = water, orange = the
genuine gap; pale = resolved).

### Top reasons, ranked

| Reason | Cells | % of the 29.4% gap | % of whole AOI | Deliberate exclusion, or a real gap? |
|---|---|---|---|---|
| Sealed (buildings/roads) | 22,446 | 97.4% | 28.6% | **Deliberate** — brief §4.3 excludes sealed cells from CN outright |
| Water | 538 | 2.3% | 0.7% | **Deliberate** — same reason |
| No soil-group match | 61 | 0.26% | 0.078% | **Real gap** — see below |
| Unmapped NMD class | 0 | 0% | 0% | n/a — none occurred |

**The overwhelming majority of the 29.4% (99.7%) is not missing data at
all** — it's sealed and water cells correctly excluded per the brief.
Only 61 cells (0.078% of the AOI) are an actual gap.

### What causes the 61-cell gap, exactly

Not a coverage hole: **all 61 cells DO fall inside an SGU soil polygon**
(`no_soil_group_no_polygon` = 0, `no_soil_group_vatten` = 61). Every one
of them lands inside an SGU polygon whose own soil class is **"Vatten"**
(open water — `hydrologic_group=None` by design, scripts/
scenario_fetch_soils.py), while NMD's land cover classifies the same
10 m pixel as pervious (mostly grass/wetland/forest). **This is a dataset
disagreement over where water's edge sits, not missing coverage**, and the
map confirms it visually: the orange gap cells sit as thin scattered
speckles hugging the exact boundaries of the river corridor through town
and two ponds — classic raster/vector edge-alignment mismatch, where a
10 m pixel's centre falls just inside SGU's water polygon while NMD's
independently-drawn landcover boundary puts the same ground as bank
vegetation.

The NMD classes actually under these 61 cells confirm this: mostly
grass/wetland classes right at a water's edge (4233 "Frisk-fuktig
gräsdominerad mark" ×11, 225 "Gräsdominerad våtmark, högvuxen" ×11) but
also streamside forest (115/116/111/117/114, all "på fastmark"/dry-land
forest types, ×26 combined) and even 2 cells of arable land — consistent
with a real, narrow riparian edge, not a systematic classification error
affecting one land-cover type.

### Cluster or scatter — by reason, via connected-component labelling

| Reason | Components | Largest component | % of cells in largest | Pattern |
|---|---|---|---|---|
| Sealed | 628 | 20,758 cells | 92.5% | **Clustered** — one contiguous urban mass (Hörby's built-up core) plus scattered single-building outliers |
| Water | 79 | 195 cells | 36.2% | **Mixed** — the river corridor is one larger component, plus many small isolated ponds/ditches |
| No-soil-group gap | 29 | 9 cells | 14.8% (65.5% of components are lone single cells) | **Scattered** — thin speckles along water edges, not one systemic hole |

The gap **scatters** — thin edge-speckles distributed along multiple
water features across the AOI, not concentrated in one place (e.g. not
all at the AOI boundary, which would indicate a coverage-extent problem
instead).

### Fallback CN for the 61-cell gap — group B, not the worst case

**Applied:** for each of the 61 gap cells, the already-resolved TR-55
vegetation category is kept (the gap is only in the soil-*group* axis);
the missing group is filled with **hydrologic group B**.

**Justification:** the instruction was to use a conservative mid-range
CN if the gap falls mainly on pervious land — it does, by construction
(100% of these 61 cells are pervious; a gap can only occur after a
pervious classification succeeds). Group B, not C or D, was chosen
because:
1. It is the **empirically dominant/modal group** for this exact AOI (see
   the resolved-cell breakdown above — B outnumbers every other group by
   a wide margin), so it's the locally-representative default, not an
   arbitrary pick.
2. It sits **second from the best** on the A(highest infiltration)→D(lowest)
   spectrum — moderate, not reaching for the punitive D-group worst case
   the way defaulting to D would, matching "mid-range... rather than
   anything high."

This changes 61 of 78,351 cells (0.078% of the AOI) — negligible effect
on the area-weighted mean CN (74.28 → 74.28 at 2 d.p.), tracked separately
as `fallback_filled` in the summary JSON rather than silently merged into
`ok`.

### How "mean CN 74.28" is computed — both figures, not one

**74.28 is area-weighted over resolved cells only** (55,306 of 78,351;
sealed and water cells contribute nothing to it, per brief §4.3 — CN
doesn't apply to them at all, not that they're assumed to be 0). Cell
size is ~10.00 m × ~10.00 m throughout (0.11% non-square, negligible), so
pixel-count-weighted and area-weighted are the same figure here.

Three figures are now reported, each answering a different question
(`web/data/scenario_curve_number_summary.json`):

| Figure | Value | What's included |
|---|---|---|
| Resolved cells only | **74.28** | The 55,306 cells with a real soil-group match |
| Resolved + fallback | **74.28** | Adds the 61 fallback-filled cells (unchanged at 2 d.p. — too small a share to move it) |
| Whole AOI, sealed=98 | **81.12** | All 78,351 cells except water (excluded — no runoff-CN concept applies to open water); sealed cells contribute TR-55's standard impervious value (98, Table 2-2b) **for this one summary statistic only** — never written into the per-cell grid itself |

**74.28 is the right figure for anything about pervious-land infiltration
behaviour specifically** (it's what the CN grid itself represents).
**81.12 is the right figure for a single "how runoff-prone is this AOI
overall" number**, since it accounts for the fact that 28.6% of the AOI
is impervious and contributes far more runoff than any pervious CN alone
would suggest.

## Phase 1 complete — 2026-09-18

**Derived from data this phase** (fetched, computed, or verified — not a
brief-stated default or literature constant copied as given):

- **Storm hyetograph shape & default drainage capacity.** Corrected
  formula, checked against its own worked example; 24.66 mm/h falls
  inside the brief's own ~20–25 mm/h estimate (§4.2).
- **Land cover.** NMD2023 basskikt, clipped to the AOI: 28.6% sealed /
  70.7% pervious / 0.7% water at 10 m pixels.
- **Soils.** SGU Jordarter 25k–100k: all 12 classes present in the AOI
  assigned an SCS hydrologic group.
- **Baseflow.** Observed HEÅKRA (station 2128) discharge, pre-event
  windows verified programmatically against the rising limb (not just
  asserted): Nov 2023 median(1–15) = 4.47 m³/s (peak **24.1 m³/s, 17
  Nov**); Jan 2024 median(4–20) = 3.19 m³/s (peak **27.8 m³/s, 24 Jan**).
- **Inflow areas and hydrographs.** S-HYPE SUBIDs 184 (Ebbamölleån) and
  64474 (södra armen) fetched and AOI-overlap-corrected using each
  SUBID's own upstream polygon intersected with the AOI bbox (scaling
  factors **0.97245** / **0.99530**, applied to `mq`/`mlq`/`mhq` and the
  full flow series in the production `*_aoi_corrected.json` files).
- **AOI drainage-area closure.** 5.962 km² (SVAR MAINDOWN topology walk ∩
  AOI bbox), cross-checked independently in S-HYPE terms (5.427 km²,
  residual 0.535 km² / 8.97%) — two different delineations landing within
  ~9% of each other, not reconciled further.
- **Curve Number grid.** Land cover and soils combined per-cell into an
  actual CN grid (`web/data/scenario_curve_number.asc`): 70.6% of the AOI
  resolved, mean CN 74.28 over resolved pervious cells; 81.12 over the
  whole AOI excluding water (sealed cells contribute TR-55's standard 98
  for this one summary figure only). The 29.4% gap was mapped and broken
  down (see "Curve Number gaps" section above): 99.7% of it is sealed/
  water, deliberately excluded per brief §4.3, not missing data — only
  61 cells (0.078% of the AOI) are a real gap, traced to an SGU/NMD
  disagreement at water-body edges and fallback-filled with hydrologic
  group B. The CN *values themselves* are still TR-55 literature
  constants under a uniform "poor condition" assumption, same caveat as
  Manning's n below — what's newly derived is the grid, i.e. which cell
  gets which combination of class and soil group.

**Still assumed, not yet built from data:**

- **Culvert widths (0.8–1.5 m), channel burn depth (1.0 m), bank slope
  (1:2), building obstruction height (+10 m).** Brief-stated (§4.5), not
  independently sourced, and cannot be applied yet — blocked on the real
  1 m Lantmäteriet DEM (terrain is still the Esri World Elevation
  placeholder).
- **Manning's n (0.035 / 0.015 / 0.035 / 0.10).** Literature constants
  (Chow, 1959), copied as given; not independently checked against the
  source this session.
- **Soil → SCS hydrologic-group lookup.** A documented judgement-call
  mapping (grain size/drainage character), not a measured infiltration
  rate or a site calibration.

## Phase 2 kickoff — LISFLOOD-FP 8 obtained, built, and validated — 2026-09-18

**Engine decision:** LISFLOOD-FP 8, per the brief's own §4.7 preference
(CLI-scriptable, matching how this whole project has been built).

### Licence

The actual repository `LICENSE` file is **GPL v2** (plain, no
non-commercial restriction), matching the Zenodo record's own metadata
(`GNU General Public License v2.0 only`). **Discrepancy noted:**
seamlesswave.com's own webpage text describes it as "GPL v3.0 for any
non-commercial use" — that page's wording is stale/inconsistent with the
actual LICENSE file and Zenodo metadata, which are treated as
authoritative here (they are the operative legal text, not a marketing
page). GPL v2 permits this project's use.

**What GPL v2 actually obligates here (2026-09-18 follow-up):** LISFLOOD-FP
runs as a standalone external binary, invoked as a subprocess
(`scripts/model_stage_and_run.sh`) — it is not linked into, compiled
with, or distributed alongside this project's own code. Model *outputs*
(depth grids, `.mass` files, anything this project's own preprocessing or
web front-end does with them) are this project's own work product, not a
derivative work of LISFLOOD-FP's source under GPL — running a GPL tool
and using its output data doesn't extend GPL to the output or to unrelated
programs that merely invoke it. **No copyleft obligation attaches to the
website or to this repo's own preprocessing/staging scripts.** The one
thing that WOULD trigger GPL v2's terms is redistributing the LISFLOOD-FP
*binary itself* (or a modified version of its source) — if that ever
happens, GPL v2's terms (source availability, licence notice, etc.) apply
to that binary/source, not retroactively to this project.

### Documentation capability check (all four confirmed, none missing)

Checked against the v8-specific case-study pages (not older-version
docs), before any build was attempted:

| Requirement | Confirmed via | File / keyword |
|---|---|---|
| Time-varying spatially distributed rainfall | Merewether case study (v8) | `.nc` rainfall file — "spatially- and temporally-varying" |
| Point/line inflow boundaries with time series | `.bci`/`.bdy` docs | QVAR applicable "at either a boundary segment (an edge) or a point source", backed by a `.bdy` time series |
| Spatially varying Manning's n grid | Merewether case study (v8) | `.n` file — "floodplain friction coefficient Manning's file" |
| Mass-balance output file | Merewether case study (v8), "Running the code, outputs" | `.mass` file, interval set by `massint` |

Nothing missing — no redesign needed.

### Build — WSL2, not native Windows

**Decision: WSL2/Linux build, not native MSVC.** This machine had no
Visual Studio, MSVC, or CMake installed (`Program Files\Microsoft Visual
Studio\18` existed as an empty folder — not a real install). LISFLOOD-FP's
Windows build docs target VS2019 specifically and don't list
dependencies; its Linux build docs are precise (`libnuma-dev`,
`libnetcdf-dev`, CMake ≥3.13) and this machine already had WSL2 Ubuntu
24.04 installed. Lower friction, better-documented path — chosen over
installing a multi-GB toolchain from scratch for a less-certain result.

**Exact reproducible build record** (also captured in
`scripts/model_build_lisflood.sh`, which re-derives this from scratch —
download, MD5 check, commit check, build):

| | |
|---|---|
| Source | Zenodo DOI [10.5281/zenodo.13121102](https://zenodo.org/records/13121102), `LISFLOOD-FP-v8.2.zip` |
| MD5 (verified against Zenodo's own checksum) | `a0a607cf68078b56a9c50c7013cafa95` |
| Git commit (embedded in the release archive) | `79ba7d380650ed9eec93656704e931ec2b89da6d` (2024-03-05; 217 commits past the `v8.1.0` tag — no `v8.2` git tag exists in the source tree itself) |
| Binary's own self-reported version | `8.1.0` (VersionHistory.h wasn't bumped for the v8.2 packaging — noted, not corrected) |
| OS | Ubuntu 24.04.4 LTS, kernel `6.18.33.2-microsoft-standard-WSL2` (WSL2) |
| Compiler | GCC/G++ 13.3.0 (`13.3.0-6ubuntu2~24.04.1`) |
| CMake | 3.28.3 |
| apt packages | `libnuma-dev` 2.0.18-1ubuntu0.24.04.1, `libnetcdf-dev` 1:4.9.2-5ubuntu4, `libnetcdf-c++4-dev` 4.3.1-4build2 |
| Build config | `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` (default `config.default.cmake`: `_NETCDF=1`; no CUDA toolkit present, so CPU-only) |

Build succeeded first attempt — no errors, only pre-existing compiler
warnings in LISFLOOD-FP's own source (unused `fscanf` return values,
one `sprintf` format-overflow warning) that are not this project's to fix.

### Toy 2-cell case — validated, not just "compiles"

Ran a genuine 1×2-cell domain (`model/inputs/toy2cell/`: a 2-column,
1-row DEM sloping 10 m → 9 m, west-edge `QFIX 0.05` inflow, east-edge
`FREE` outflow, `fpfric 0.03`, 60 s sim). Result
(`model/outputs/toy2cell/toy2cell.mass`): `Qin` ramps to a steady
0.500 m³/s, `Qout` converges to match it by t=60 s, **`Qerror`/`Verror` ≈
0.0000 throughout** — a real, mass-conserving simulation, not just a
successful compile. Both cells reach 0.040 m depth at steady state, as
expected for a flat two-cell channel.

### Environment split — Windows Python for preprocessing, WSL for execution only

**Decision, applied consistently, no mixed-environment path handling:**
every existing preprocessing script (`scripts/scenario_*.py`) stays on
Windows Python, using Windows paths, exactly as before — these also
produce `web/data/*` for the website and that must stay untouched. WSL is
used **only** to build and run LISFLOOD-FP itself. The Windows/WSL
boundary is crossed in exactly one place:
`scripts/model_stage_and_run.sh <run_name>`, run from WSL, which:

1. Copies `model/inputs/<run_name>/` (prepared by the Windows-side
   preprocessing scripts) into `~/lisflood-runs/<run_name>/` — the WSL
   (ext4) filesystem, never `/mnt/c/`.
2. Runs `lisflood` entirely under `~/lisflood-runs/<run_name>/` — every
   per-timestep `.wd`/`.elev` file LISFLOOD-FP writes stays on the WSL
   filesystem during the run, not on the `/mnt/c/` 9p-style mount, which
   is measurably slower for many-small-file I/O.
3. Copies the finished `results/` back to `model/outputs/<run_name>/` in
   the Windows repo.

No script other than `model_stage_and_run.sh` ever references `/mnt/c/`
or a WSL path — each script lives in exactly one environment. `model/`
(new top-level directory): `inputs/` is tracked (small, versioned model
configuration, same precedent as `web/data/*.tif`); `outputs/` is
gitignored (regenerable simulation results).

### Infiltration and drainage capacity: applied in preprocessing, not in LISFLOOD-FP

**Design decision:** all hydrology (infiltration via the Curve Number
grid above, and the brief's drainage-capacity/submerged-outlet logic)
stays in this project's own Python preprocessing, which will produce a
**net effective-rainfall grid** (gross rainfall minus losses, per cell,
per timestep) as LISFLOOD-FP's `.nc` rainfall input. LISFLOOD-FP's own
infiltration options are confirmed (from `pars.cpp`) to be the `.par`
keywords **`infiltration`/`inf`** (constant rate) and **`infilfile`**
(spatially distributed grid) — **neither is ever set** in any `.par` file
this project generates. Leaving both unset keeps
`Statesptr->calc_infiltration` at its default OFF, so LISFLOOD-FP applies
zero internal infiltration loss of its own. This avoids double-applying
losses (once in preprocessing, again inside the solver) and keeps every
hydrological assumption in one auditable place (this repo's own scripts
and ASSUMPTIONS.md) rather than split across a Python preprocessing step
and an opaque solver flag.

## DEM: FABDEM rejected, Copernicus GLO-30 used as a pipeline-validation placeholder — 2026-09-18

**FABDEM rejected — do not reconsider it.** FABDEM removes forest/building
bias from Copernicus GLO-30 (closer to bare-earth than GLO-30 itself), but
its licence is **CC BY-NC-SA 4.0**: non-commercial *and* share-alike. Both
clauses are incompatible with this project as scoped (a municipal
demonstration tool with no restriction on reuse or on future commercial
paths) — share-alike would force any derivative data product this project
publishes under the same restrictive licence, and non-commercial forecloses
options with no offsetting benefit over other candidate sources. **Not
used, and not to be revisited unless the project's own licensing scope
changes first** (that would be a project-level decision, not a data
availability question — the licence, not the data quality, is why this was
rejected).

**Copernicus GLO-30 used instead, explicitly as a placeholder for pipeline
validation only** — not a step toward a usable flood result. Fetched the
single 1°×1° tile covering the AOI (55.84–55.865°N, 13.64–13.685°E falls
entirely inside tile N55/E013) from the public AWS Open Data bucket, no
account or credentials needed:

```
curl -sI 'https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N55_00_E013_00_DEM/Copernicus_DSM_COG_10_N55_00_E013_00_DEM.tif'
-> HTTP/1.1 200 OK (public, unsigned GET; no --no-sign-request/AWS CLI
   needed for a plain read of this bucket — confirmed by a live HEAD
   request, 2026-09-18)
```

Reprojected and resampled to the model grid in WSL2 via GDAL 3.8.4
(`gdalwarp`/`gdal_translate` — installed via `apt`; see "Phase 2 kickoff"
above for why WSL, not native Windows GDAL): EPSG:4326 → EPSG:3006,
bilinear resampling (continuous elevation data — never nearest-neighbour,
unlike the categorical land-cover raster), forced onto the *exact same*
287×273 grid as `web/data/scenario_landcover.tif` and the Curve Number
grid (`-te`/`-ts` pinned to that grid's own corners and cell count) so
every input in the pilot run is co-registered. Output:
`model/inputs/pipelinetest_horby_pilot/pipelinetest_horby_pilot.dem.asc`.

**Marking, per instruction:** the filename carries the `pipelinetest_`
prefix, and `model/inputs/pipelinetest_horby_pilot/run_metadata.json`
records `"placeholder_dem": true` and `"usable_for_flood_analysis": false`
explicitly — this is not a convention to remember to apply consistently
by hand later, it's checked into the run's own metadata.

**Why no result from this DEM is usable for flood analysis, stated
plainly:**
1. **GLO-30 is a Digital *Surface* Model, not a bare-earth DTM.** Its
   elevations include vegetation canopy and building heights. In a
   built-up river town like Hörby, this means the "ground" the solver sees
   is in places tree canopy or rooftop height — a flood model built on it
   will place high ground where there's actually a permeable gap between
   buildings, and vice versa. The brief's own target (a real 1 m
   Lantmäteriet bare-earth DEM) exists precisely to avoid this.
2. **Hörbyån is sub-cell at 30 m.** The river that drives this whole
   project's flood event is narrower than one GLO-30 pixel throughout the
   AOI — it isn't resolved as a channel at all, just smeared into
   whatever elevation the 30 m footprint averages to. No channel
   conveyance, no realistic river stage — there is no version of "the
   river" in this DEM to route flow through.
3. Consequence of both: any depth grid, mesh, or `.mass` figure this
   placeholder produces describes the *mechanics of the pipeline*, not
   the flood. Treat every output from a `pipelinetest_` run as exactly
   that and nothing else.

**Required attribution** (Article 6(b) of the COP-DEM-GLO-30-F licence,
since the data is reprojected/resampled here — i.e. adapted, not
redistributed verbatim):

> produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus
> Defence and Space GmbH 2014-2018 provided under COPERNICUS by the
> European Union and ESA; all rights reserved

## Pilot pipeline run — input generation through output conversion — 2026-09-18

With the GLO-30 placeholder in place, ran the full intended chain once,
end to end, to find where it breaks before the real 1 m DEM exists.
Everything here uses run name `pipelinetest_horby_pilot` throughout.

### Where the pilot chain breaks (found before the solver even ran)

Two distinct, real bugs surfaced just from generating the DEM ASCII grid
— both from the same root cause: **LISFLOOD-FP's ASCII-grid readers
(`LoadDomainGeometry` in `input.cpp`, and `LoadManningsn`) are fixed
*positional* parsers.** They don't read header field names — they call
`fscanf` a fixed number of times and use whichever token comes second on
each line, assuming an exact 6-line shape: `ncols, nrows, xllcorner,
yllcorner, cellsize, NODATA_value`, in that order, always one cellsize
value applied to both axes (`Parptr->dy = Parptr->dx;` in
`LoadDomainGeometry`, line ~1487). Anything that changes the number of
header lines desyncs every `fscanf` after it — including the start of the
actual grid data.

1. **Non-square-pixel DEMs break the header shape.** The model grid's
   pixel is 10.0025 × 9.9914 m (0.11% non-square — same source as the
   Curve Number grid's own note on this). GDAL's `AAIGrid` driver refuses
   to write a single `cellsize` line for a non-square raster and instead
   writes a non-standard two-line `dx`/`dy` header. Fed to LISFLOOD-FP
   as-is, its 5th `fscanf` (expecting `cellsize`) would read the `dx`
   line correctly, but its 6th `fscanf` (expecting `NODATA_value`) would
   read the `dy` line instead — silently setting `NODATA_value` to
   ~9.99 and shifting every subsequent read (the entire DEM's elevation
   data) by one token. **Fix applied:** `gdal_translate -co
   FORCE_CELLSIZE=YES`, then the `cellsize` line's value overwritten to
   match the Curve Number grid's own declared cellsize
   (9.996932063502381) exactly — so every grid in this pipeline declares
   the identical cellsize, not just "a" square number.
2. **A DEM with no missing pixels breaks the header shape too, the other
   way.** This AOI clip has 100% valid pixels (no NODATA anywhere), so
   GDAL's `AAIGrid` writer omitted the `NODATA_value` line entirely
   (nothing to declare). LISFLOOD-FP's reader has no such conditional —
   it always does a 6th `fscanf` expecting that line. Without it, the
   *first real elevation value* would be consumed as `NODATA_value`,
   again shifting every subsequent DEM value by one. **Fix applied:**
   `gdal_translate -a_nodata -9999` forces GDAL to declare a NODATA value
   (even though nothing in this clip actually uses it), so the 6-line
   header is always present.

Both are exactly the kind of break "swap in the real DEM" would NOT
surface on its own if the real DEM happened to be square-pixel with a
NODATA border — worth fixing once in the DEM-generation step
(`gdalwarp`/`gdal_translate` invocation, documented above) rather than
per-run. `scripts/model_build_pilot_inputs.py`'s Manning's n grid writer
was built to emit the same fixed 6-line shape from the start, for the
same reason (`LoadManningsn` has the identical positional-parsing
pattern).

### Input generation

- **DEM:** placeholder GLO-30, as above.
- **Manning's n grid:** brief §4.6 values (forest 0.10, everything else
  pervious/water 0.035 — grass and channel share the same brief-given
  value, and there is no delineated channel mask in this project yet —
  sealed 0.015), assigned per NMD class over the same 287×273 grid.
  Script: `scripts/model_build_pilot_inputs.py`.
- **Rainfall:** LISFLOOD-FP's simpler `rainfall <file>` keyword —
  spatially UNIFORM, temporally-varying (mm/hr time series) — not the
  full spatially-varying `dynamicrainfile` NetCDF path confirmed earlier
  in the doc-capability check. **Deliberate pilot-run scoping, not a
  capability gap**: building the CN-grid-based per-cell effective-rainfall
  NetCDF is real follow-on work, scoped out here to get the rest of the
  chain (solver, mass balance, output conversion) validated first. Source
  data: `docs/hyetographs/hyetograph_40mm.csv` (already generated, nothing
  recomputed), 144×10-minute blocks over 24 hours.
- **Boundary conditions:** none set (`bcifile` omitted) — all four edges
  default closed. **Also a deliberate pilot simplification**: the two
  real S-HYPE inflow hydrographs (SUBIDs 184/64474) exist but weren't
  wired in for this pass, both because their real AOI-crossing points sit
  slightly outside this rectangular grid's exact edge (a pre-existing,
  already-documented nuance — see "Inflow outlets are downstream of the
  crossing" above) and because a closed-boundary, rainfall-only
  configuration gives the *cleanest possible* mass-balance check for
  validating the solver mechanics: with zero outflow, cumulative rain
  volume in should equal stored volume, almost exactly.

### Solver run

Ran via `scripts/model_stage_and_run.sh pipelinetest_horby_pilot` — the
same staged-into-WSL, run-under-`$HOME`, results-copied-back path
validated with the toy case. `sim_time 86400` (24 h, matching the
hyetograph), `massint 900`, `saveint 21600`.

### Where it actually broke: not a crash, a computational wall

The run did not crash and did not produce wrong output — it produced
**correct output too slowly to be practical**, which is its own real
finding. Watched via `ps`: at wall-clock 12 minutes in (14 CPU cores at
~1390% CPU, i.e. genuinely parallel, not stuck), the simulation had only
reached **8,100 s of the 86,400 s target (9.4%)**, and the adaptive
timestep had already collapsed from its initial 1.0 s down to **0.17 s**
(`.mass` file, `Tstep` column). Extrapolating linearly (itself optimistic,
since the timestep kept shrinking as more water accumulated) put full
completion over two hours away for one run of one scenario — impractical
for the brief's actual run matrix (6+ runs).

**Original attribution corrected, 2026-09-19: "DSM noise" was an
unverified guess, not a diagnosis — see "Timestep collapse, actually
diagnosed" below for what's really going on.** Killed the run at this
point (`kill -9`) rather than let it continue burning compute on a
placeholder that was never going to produce a usable result anyway.

**Re-ran a short version** (`pipelinetest_horby_pilot_short`, `sim_time
5400` — the portion of the storm before the timestep collapse) to
actually complete the rest of the chain end to end. Finished in 4.55
minutes.

### Timestep collapse, actually diagnosed (2026-09-19 follow-up)

The original write-up above blamed "GLO-30 DSM noise" without checking —
that was an assumption dressed as a finding. Diagnosed properly instead,
against `pipelinetest_horby_pilot_diag` (same inputs, `sim_time 8100`,
`saveint 900` — nine snapshots spanning the exact collapse window
6300–8100 s, re-run in 9.13 minutes; deterministic, `.mass` figures match
the original run exactly at every shared timestamp).

**1. Which solver was actually active.** Invocation:
`lisflood -v pipelinetest_horby_pilot_diag.par` — the only flag is `-v`
(verbose logging; no other command-line flags). The `.par` file set none
of `acceleration`, `dg2`, `fv1`, or `Roe`. Checked
`lisflood.cpp`'s own state initialisation: all four default **OFF**
(`SimStates.acceleration = OFF`, etc. — lines ~206–271); only
`adaptive_ts` defaults ON. With every named solver off, `FloodplainQ` in
`fp_flow.cpp` falls through to `CalcFPQx`/`CalcFPQy` — **the original
1996-vintage Bates & De Roo explicit diffusive storage-cell scheme**, not
LISFLOOD-FP 8's headline DG2 solver (the one the brief and the v8 paper
actually describe) or the newer `acceleration` formulation. **This
pilot never exercised DG2 at all** — a real, separate finding: getting a
representative performance/stability read on this model requires setting
`dg2` (or `acceleration`) explicitly, which this pilot's `.par` files
did not do.

**2. Depths and DEM, checked for spurious artefacts.** Max depth at the
diagnostic run's last snapshot (t=8100.012 s) is **0.397 m**, at row 125,
col 235 (SWEREF 417186.9, 6190583.3) — a genuine, if small, local
depression (ground 89.42 m vs. 89.78–90.07 m on its four neighbours, a
plausible ~0.4–0.6 m dip, not a sink). Checked the full DEM for
NODATA-read-as-elevation and pit artefacts: **0 NODATA cells** anywhere
in the grid (matches the earlier `-a_nodata` fix — no gaps to
misinterpret) and **0 cells more than 5 m below all four neighbours**
(i.e. no bilinear-resampling sinks or edge artefacts). Depths are sane —
this is not a data bug.

**3. Rainfall units and magnitude, checked independently of mass
balance.** Mass balance closing (`Qerror`/`Verror` ≈ 0) only proves the
model is internally consistent with whatever it was given — it says
nothing about whether that input's real-world magnitude is right (e.g. a
value fed as mm/hr that was actually in m/s would still close the mass
balance perfectly, just at the wrong scale). Checked instead by comparing
`pipelinetest_horby_pilot_diag.rain`'s literal values against
`docs/hyetographs/hyetograph_40mm.csv`, the source they were transcribed
from: identical figures (e.g. `0.842` at block 0, matching the CSV's
`intensity_mm_per_h` column exactly), time axis correctly labelled
`minutes` (matching the CSV's `t_start_min`, not seconds or hours), peak
**42.985 mm/h at t=570 min** (≈9.5 h in — matches the documented "peak at
r=0.4 of 24 h" ≈576 min design). `input.cpp` confirms LISFLOOD-FP expects
this keyword's values in mm/h and converts internally
(`/= (1000*3600)`, line 2158) — units and magnitude both check out; no
scale-factor bug. At the diagnosed collapse point (t=8100 s = 135 min
into the storm), the actual applied rain rate is still only ~0.9 mm/h —
**a physically modest rainfall was enough to trigger the collapse**, which
points at the numerics, not an inflated rainfall input.

**4. The actual dt-limiting cell (classic scheme, not acceleration — so
answering the literal "if acceleration is active" framing: it isn't, but
the same request applies to the scheme that IS active).** Replicated
`CalcFPQx`/`CalcFPQy`'s exact stability formula
(`alpha = hflow^(5/3)/(2·fn·Sf)`, or the linearised
`alpha = hflow^(5/3)·√dx/(fn·√dhlin)` when `dh < dhlin`; `dt = 0.25·dx²/alpha`)
against the t=8100 s snapshot, using the solver's own default constants
confirmed from `lisflood.cpp` (`DepthThresh=1e-3`, `MaxHflow=10.0`, and —
easy to get wrong — `dhlin = dx·0.0002 ≈ 0.002 m`, *not* the 0.01 default,
because that default only applies when `dhoverw=ON`, which it isn't
here). Computed minimum: **dt ≈ 0.195 s**, at the x-direction edge
between row 239/col 190–191 (SWEREF ≈ 416737.0, 6189443.6) — matching the
solver's own logged `Tstep` (0.1717 s) closely enough (same order of
magnitude, same collapse window) to trust the replication. That edge has
`hflow=0.115 m`, `dh=0.001 m` (below the 0.002 m linearisation threshold
— i.e. an almost perfectly flat water surface between the two cells) and
`n=0.015` — **a sealed/impervious Manning's-n cell**. **Mechanism: thin,
nearly-flat sheet flow over a low-Manning's-n (impervious) surface** is a
textbook trigger for this specific explicit scheme's `hflow^(5/3)`-scaled
instability (why the `acceleration` and `dg2` formulations exist in the
first place). Not a DSM artefact, not a rainfall bug — **a numerical
scheme limitation, triggered by ordinary shallow runoff over sealed
ground, that the classic scheme handles poorly and DG2/acceleration are
specifically built to handle better.** Next step, not done in this
session: re-run the same inputs with `dg2` (or `acceleration`) set in the
`.par` file and check whether the same rainfall produces a stable,
practical timestep.

### Mass balance check

`pipelinetest_horby_pilot_short.mass`: with all boundaries closed and no
infiltration active anywhere (LISFLOOD-FP's own infiltration is off, per
design; this pilot also didn't apply the CN-based preprocessing loss —
see rainfall note above), **`Vol` matches the `Rain-(Inf+Evap)` column
exactly at every single row** (e.g. both read 10094.5139 at t=5400 s),
and **`Qerror`/`Verror` stay at ≈0.0000 throughout** (largest deviation
`-0.0000`, i.e. below display precision). This is the cleanest possible
mass-balance check — a closed system where rain-in must equal volume
stored, and it does, to displayed precision. `Area` (wetted extent) stays
at 0 until t=4500 s, then grows to 61,862 m² (≈0.8% of the AOI) by
t=5400 s — consistent with a slow start to standing water at these early,
still-modest rainfall intensities (the alternating-block storm peaks at
40% through its duration, i.e. t≈34,560 s — this short run doesn't reach
anywhere near the peak).

### Output conversion — both stages completed, against real model output

- **Depth PNG:** `scripts/model_convert_depth_to_png.py` against the
  final snapshot (t=5400 s): 287×273 RGBA PNG, max depth 0.104 m, 29 cells
  ≥5 cm rendered opaque (everything else transparent, per the brief's
  spec). Verified correct at the byte level, not just "ran without
  erroring" — decoded the written PNG's raw pixel bytes back out and
  confirmed exact RGBA values against the colour-ramp formula for known
  test-case depths before running it on real output. Visually: scattered
  isolated speckles of standing water, not a coherent channel — a direct,
  visible illustration of finding #2 above (the river is sub-cell at
  30 m, so there's no channel for this DSM to route water into; it just
  ponds in whatever small depressions the noisy surface happens to have).
- **Water mesh:** `scripts/model_convert_depth_to_mesh.py` against the
  same snapshot: 29 wet cells → 116 vertices, 58 triangles, a valid
  uncompressed glTF 2.0 binary (`.glb`). Verified structurally correct by
  parsing the written file back — header/chunk lengths, JSON validity,
  accessor/bufferView offsets, and the actual decoded vertex positions
  and triangle indices all checked against a hand-computed synthetic test
  case before trusting it on real output.
- **Draco compression — not a wall, contrary to expectation.** Expected
  this to be the actual break (no Draco tooling installed, similar to the
  Visual-Studio-vs-WSL situation earlier), but this repo already has
  Node/npm for its own web build, and `npx --yes @gltf-transform/cli draco
  water_t5400.glb water_t5400_draco.glb` worked on the first try — no new
  install beyond what `npx` fetches on demand. Output: 4.98 KB → 1.47 KB,
  verified to genuinely carry the `KHR_draco_mesh_compression` glTF
  extension (not just copied through). **So the brief's exact
  "Draco-compressed .glb" spec is achievable with tooling already in this
  repo** — `scripts/model_convert_depth_to_mesh.py` itself does not call
  it (kept as a separate, explicit post-processing step, not silently
  baked into a Python script that would otherwise need to shell out to
  `npx`).

### Summary: what actually swaps in for the real DEM

Every non-DEM input generated above (`.n`, `.rain`, the `.par` structure)
and every script in the chain (`model_stage_and_run.sh`,
`model_convert_depth_to_png.py`, `model_convert_depth_to_mesh.py`) is
DEM-agnostic — none of them know or care that the DEM is a placeholder.
Swapping in the real 1 m Lantmäteriet DEM means: (1) re-running the
`gdalwarp`/`gdal_translate` steps above against the real DEM instead of
the GLO-30 tile (same target grid, same `FORCE_CELLSIZE`/`-a_nodata`
fixes, since those are LISFLOOD-FP parser quirks, not GLO-30-specific),
and (2) **not** expecting the timestep collapse to go away on its own —
per the corrected diagnosis above, it's a numerical-scheme limitation
(the default classic explicit solver, triggered by shallow flow over
low-Manning's-n ground), not primarily a DEM-roughness artefact. A
smoother real DEM may help marginally, but the actual fix is setting
`dg2` or `acceleration` in the `.par` file, independent of which DEM is
used. Separately, at 1 m resolution over the same AOI extent the grid
would also be ~100x larger in cell count (287×273 → far more cells),
which is its own performance question this pilot did not test. Nothing
else in the pipeline changes.

## Solver comparison, cost model, and a mandatory solver keyword — 2026-09-21

Direct follow-up to "Timestep collapse, actually diagnosed" above: rather
than take that diagnosis on faith, re-ran the same test three ways
(default/classic, `acceleration`, `dg2`), checked the acceleration
solver's own thin-film cutoff, built a resolution cost model from the
solvers' actual stability formulas, measured OpenMP thread scaling, and
closed the loop that let this happen at all — a build-level assertion
that now refuses to run without an explicit solver keyword.

### Three-way comparison — two different forcing mechanisms needed, and why

**First attempt (rainfall-driven, same as the original pilot) found a
second silent-default class of bug before any timing comparison was even
possible: DG2 does not read the simple `rainfall <file>` keyword at all.**
Grepped `swe/dg2*.cpp` for `Arrptr->rain` — zero matches; DG2 only
ingests rain via `dynamicrainfile` (NetCDF). Running the DG2 pilot `.par`
unmodified produced **exactly zero accumulated volume for 900+ seconds of
simulated time** (`Vol` and `Rain-(Inf+Evap)` both pinned at `0.0000e+00`)
— LISFLOOD-FP printed `Loading time varying rainfall / Done.` as if
nothing were wrong, no warning that the solver in use ignores that file.
**A third silent-default-shaped bug, same session, same failure mode as
the missing solver keyword — flagged for the same reason.** Killed that
run; NetCDF rainfall generation is out of scope for this pass (already
noted as deferred), so a rainfall-driven three-way comparison isn't
possible yet without that work.

**Second attempt, startfile-driven, worked for all three.** Uniform
0.02 m initial depth (`model/inputs/_dg2_startfiles/start.h`, +`.h1x`/
`.h1y` companions of zeros for DG2 — needed only because `startq2d` is
off, so the momentum-slope companions `Qx1x` etc. aren't read at all;
confirmed from `swe/dg2new.cpp`), no rainfall, no boundary inflow — a
pure "let the DEM redistribute a fixed volume of standing water" test,
`sim_time 300`. (An initial pass at 0.1 m uniform depth was abandoned
after 5+ minutes produced only one `massint` checkpoint — a genuinely
harsher stability test than needed to make the comparison; 0.02 m gives
the same qualitative answer in a practical run time.)

**DG2 needs its own DEM preprocessing step, undocumented on
seamlesswave.com, discovered from the abort message alone.** Running
`dg2` for the first time failed immediately: `ERROR: Loading DEM1x`.
`swe/dg2new.cpp` reads `<demfilename>1x` and `<demfilename>1y` — DG2's
per-cell linear reconstruction needs within-cell elevation *slope*
moments, not just the cell-mean elevation every other solver uses. These
are generated by a fourth build target this project hadn't used until
now, `build/generateDG2DEM`: point it at a `.par` file whose `DEMfile`
value has a `.raw` sibling (the plain elevation grid), and it writes the
base DEM plus the `1x`/`1y` companions. Workflow, now folded into
`scripts/model_stage_and_run.sh`'s prerequisites for any `dg2` run:
```
cp foo.dem.asc foo.dem.asc.raw
generateDG2DEM foo.par        # writes foo.dem.asc, foo.dem.asc1x, foo.dem.asc1y
lisflood foo.par               # dg2 keyword set — now finds all three
```

**Results** (`model/outputs/pipelinetest_horby_pilot_cmp2_{default,accel,dg2}`):

| Solver | Wall-clock (300 s sim) | Steps | Mean dt | Min dt (global) | Max depth @ t=300s | Mass balance |
|---|---|---|---|---|---|---|
| Default (classic) | **13.68 min** | 34,591 | 0.00867 s | 0.0060 s | 1.963 m | Exact (Vol = 156,605.8644 m³ throughout, Qerror ≈0.0000) |
| `acceleration` | **0.22 min (13 s)** | 300 | 1.000 s | 1.000 s (never dropped) | 1.904 m | Exact, same Vol |
| `dg2` | **7.32 min** | 1,755 | 0.171 s | 0.0340 s | **0.392 m** | Exact to ~1e-12 (tighter than the other two's displayed precision) |

Acceleration is **~62x faster** than the classic scheme here, and never
left its initial 1.0 s step — matching the "answering the literal
'if acceleration is active' framing" request directly: with acceleration
active, dt is NOT collapsing, so there is no dt-limiting cell to chase for
that solver on this test.

**Max depth diverges sharply for DG2 (0.392 m) vs. the other two
(≈1.9 m) — flagged, not explained away.** All three conserve the same
total volume exactly, so this is purely a *redistribution* difference.
Plausible reason, not confirmed: DG2 solves the full non-linear shallow
water equations (both local and convective acceleration terms), while
the classic scheme is a purely diffusive local-storage approximation and
`acceleration` is a local-inertial approximation that drops the
convective term — these are three different levels of physical
approximation, not three numerical schemes for the same equations, so
depth-field disagreement under identical mass and initial conditions is
not automatically a bug in any of them. This needs more investigation
before any of the three is treated as validated for this AOI's actual
terrain — noted here as an open item, not resolved.

### `depththresh` (acceleration's thin-film cutoff) — tested, not adopted

Checked for a `depthoff` keyword first, per the literal ask — it exists
but means something unrelated (`Statesptr->save_depth = OFF`, i.e. don't
write the `.wd` output file; nothing to do with a physical thin-film
cutoff). **The actual thin-film/dry-cell cutoff for every solver,
including acceleration, is `DepthThresh`** (`.par` keyword
`depththresh`, default `1e-3` = 1 mm, confirmed from `fp_acc.cpp`'s
`CalcT`/`CalcFPQxAcc` — acceleration has no separate threshold of its own
the way DG2 does with `dg2depththresh`). Confirmed unset (left at
default) in every `.par` this project has written.

Re-ran the acceleration startfile test with `depththresh 0.01` (1 cm, a
10x-more-aggressive dry-cell cutoff) alongside the default-threshold run:

| `depththresh` | Wall-clock | dt | Max depth @ t=300s | Wetted area @ t=300s |
|---|---|---|---|---|
| 0.001 (default) | 0.22 min | 1.0 s throughout | 1.904 m | 1,986,281 m² |
| 0.01 | 0.20 min | 1.0 s throughout (**no change**) | 1.629 m | 1,374,356 m² (**31% less**) |

**No dt or wall-clock benefit in this test** — acceleration's dt is set
by `cfl·dx/√(g·MaxH)` (global max depth), and MaxH here is already well
above 1 cm almost immediately, so raising the cutoff from 1 mm to 1 cm
never binds the dt formula. It **does** change the physical result
substantially (31% less wetted area, ~14% lower max depth) — real
puddles in the 1 mm–1 cm range that would otherwise slowly redistribute
are instead frozen in place as "dry" and never move. **Not adopted**:
it buys nothing here and measurably changes the answer. It remains a
candidate for the *classic scheme's* rainfall-driven collapse
specifically (that collapse's dt-limiting edge, from the earlier
diagnosis, had `hflow=0.115 m` — well above 1 cm, so this exact fix
wouldn't have helped that case either, but the general idea — that a
too-fine `DepthThresh` can be what's forcing tiny timesteps for actual
sheet flow, not just true stagnant puddles — is worth testing against
the classic scheme directly before it's ruled out). Not tested here.

### Cost model — Δx² (classic) vs. Δx (acceleration), by resolution and domain size

Stability formulas, read directly from source, not assumed:
- Classic: `dt = 0.25·dx²/α`, `α` independent of `dx` → **dt ∝ dx²**
  (`fp_flow.cpp::CalcFPQx`).
- Acceleration: `dt = cfl·dx/√(g·MaxH)` → **dt ∝ dx** (`fp_acc.cpp::CalcT`).

Total cost for a fixed simulated duration ∝ (cells) × (steps) =
(Area/dx²) × (T/dt):
- Classic: **cost ∝ Area / dx⁴**
- Acceleration: **cost ∝ Area / dx³**

Calibrated against this session's actual measured 10 m/full-AOI baseline
(Area = 7.8399 km², 300 s test: classic 13.68 min, acceleration 0.22 min)
— everything else is a **theoretical projection from that one measured
point**, not independently run at every resolution (a classic-scheme run
at 2 m would be projected to take days — see below — and wasn't
attempted). "Core domain" is this session's own illustrative example
(800 m × 800 m = 0.64 km², roughly the town-centre/river-corridor scale),
not a boundary defined anywhere else in this project.

| Resolution | Cells (full AOI, 7.84 km²) | Classic, full AOI | Accel, full AOI | Cells (core, 0.64 km²) | Classic, core | Accel, core |
|---|---|---|---|---|---|---|
| 30 m | ~8,736 | 0.17 min | 0.008 min | ~729 | 0.014 min | 0.0007 min |
| 10 m | 78,351 (measured) | **13.68 min (measured)** | **0.22 min (measured)** | 6,400 | 1.12 min | 0.018 min |
| 5 m | 313,404 | 218.9 min (3.65 h) | 1.73 min | 25,600 | 17.9 min | 0.14 min |
| 2 m | 1,958,775 | 8,550 min (**≈5.9 days**) | 27.1 min | 160,000 | 697.7 min (11.6 h) | 2.21 min |

**Reading this table:** at the brief's target resolutions, the classic
scheme is impractical below ~10 m over the full AOI (5.9 days at 2 m is
not a usable iteration loop for a 6-run matrix); acceleration stays
practical down to 2 m even over the full AOI (27 min/run). The core
domain doesn't rescue the classic scheme at 2 m either (11.6 h) — the
dx⁴ penalty dominates over the smaller cell count. This is the concrete,
quantified case for `acceleration` (or `dg2`, not modelled here since its
own CFL constant/behaviour wasn't isolated from this test) as the Phase 2
default, not just "it was faster in one test."

### OpenMP thread scaling — a real, reproducible cliff at 14 threads

Measured wall-clock for the `dg2` 60 s startfile test
(`OMP_NUM_THREADS` = 1/2/4/7/14, everything else identical):

| Threads | Wall-clock |
|---|---|
| 1 | 18.43 s |
| 2 | 9.11 s (1.98x) |
| 4 | 8.79 s (2.10x — barely better than 2) |
| **7** | **6.85 s (2.69x — best observed)** |
| 14 | 135.17 s (**7.3x SLOWER than 1 thread**) |

The 14-thread result was re-run twice more to rule out a one-off system
hiccup: 136.7 s and 138.3 s — **reproducible, not noise.**

**Root cause, reasonably confident but not exhaustively proven:**
`lscpu` shows this machine is an Intel Core Ultra 7 165U — **7 physical
cores, 2 threads/core (hybrid P-core/E-core architecture), 14 logical
CPUs.** `fp_flow.cpp`/`swe/dg2.cpp` issue a fresh `#pragma omp parallel
for` **every single timestep**, implying a thread-pool wake/join barrier
per step. On a hybrid CPU, OpenMP's default static scheduling assumes
uniform per-thread speed; splitting this project's small 287×273 grid
across 14 logical threads including slower E-cores means fast P-core
threads finish their slice and sit idle at the barrier waiting for slow
E-core threads, every single step, thousands of times per run — a known
failure mode for fine-grained per-step OpenMP parallelism on hybrid CPUs,
compounded here by WSL2's own virtualization scheduling overhead on top.
**Practical recommendation: cap `OMP_NUM_THREADS` at 7** (one thread per
physical core) for this machine, not the full logical count — 7 was
empirically the best of the five counts tested, matching physical core
count exactly. `scripts/model_stage_and_run.sh` does not currently set
`OMP_NUM_THREADS`; doing so is a follow-up (not applied yet — this is a
measurement, not a change to the run script).

### Mandatory solver keyword — closing the loop for good

**Patched LISFLOOD-FP itself**, not just this project's own `.par`
files, so a future session can't reintroduce the same silent default no
matter how a run gets launched. `pars.cpp::CheckParams` now aborts
immediately, before any DEM/data loads, if none of `acceleration`, `dg2`,
`mwdg2`, `fv1`, `fv2`, `Roe`, or `SGC` is set (by `.par` keyword or
command line):

```
ERROR: no solver keyword set in the parameter file or on the command
line (expected one of: acceleration, dg2, mwdg2, fv1, fv2, Roe, SGC).
Refusing to silently default to the classic explicit scheme. Aborting.
```

Verified both directions: a `.par` with no solver keyword now aborts
with this message before loading the DEM; every `.par` that already sets
a solver (toy2cell, all `_accel`/`_dg2` variants) still runs identically
to before the patch (re-checked `pipelinetest_horby_pilot_cmp2_accel`
byte-for-byte against its pre-patch `.mass` output). Patch saved at
`model/lisflood-patches/0001-require-explicit-solver.patch` (21 lines,
clean diff — CRLF line endings preserved, since a first attempt that
didn't preserve them produced a 2,300-line noise diff against the whole
file) and applied automatically, idempotently, by
`scripts/model_build_lisflood.sh` on every build.

**No new keyword was invented for "the classic scheme, but explicitly
requested."** LISFLOOD-FP has no such keyword — the classic scheme *is*
"nothing set," which the patch now forbids outright. The historical
`.par` files that deliberately tested classic-scheme behaviour in this
session (`pipelinetest_horby_pilot{,_short,_diag}`,
`pipelinetest_horby_pilot_cmp{,2}_default`) are left with no solver
keyword **on purpose**, each now carrying a `#`-comment explaining why
and noting they need the pre-patch binary to re-run — a visible,
documented exception, not a silent one. Every other `.par` in
`model/inputs/` now sets a solver explicitly. Going forward: **every new
`.par` file must set a solver keyword**; the build will refuse to run it
otherwise.


## Real 1 m DEM (Lantmäteriet) — acquired, mosaicked, clipped, conditioned — 2026-09-21

**Source collection: `mhm-61_4`** (STAC `api.lantmateriet.se/stac-hojd/v1`, "Markhöjdmodell 61_4",
1 m GeoTIFF/COG, EPSG:5845 = SWEREF99 TM + RH 2000, CC BY 4.0). A bbox search over the AOI returned
three collections: `mhm-61_4` (2.5 km tiles), `dtm-cog` (10 km tiles, ~262 MB each, two needed) and
`dsm-skoglig-copc` (point clouds — surface, not ground, so unusable). `mhm-61_4` was chosen because it
is the "grid 1+" product the brief names, six 2.5 km tiles cover the whole AOI+buffer for ~52 MB
instead of ~524 MB, and every tile ships its own `*_ursprung.json` scan-date record. Six items:
`619_41_0075`, `619_41_0050`, `619_41_0025`, `618_41_7575`, `618_41_7550`, `618_41_7525`.
All six file sizes match the STAC `file:size` exactly. Stored in the gitignored `data/scenario/raw/`.

**How the tiles were obtained (manual, not scripted).** The six GeoTIFFs were **downloaded by hand,
through a web browser**, from `dl1.lantmateriet.se`, using URLs the assistant read from the STAC
items. The scripted login **still fails**: `LANTMATERIET_SYSTEM_USER/PASSWORD` authenticate against
the STAC API (HTTP 200) but return **HTTP 401** (Basic realm "Authorization Server") on the download
host, tested 2026-09-21. **Account used for the browser download: the project Lantmäteriet system
account** (recorded as a role, not a login or e-mail address, since this file is published verbatim
to the public site — see `scripts/build.mjs`).
`scripts/scenario_fetch_terrain.py` remains an unimplemented stub; automating this is Post-launch
(docs/LAUNCH_CHECKLIST.md).

**Scan dates (Ursprung `matdatum`, per tile): all six = 2025-02-18**, method "Luftburen
laserskanning", stated vertical uncertainty 0.1 m, planar 0.3 m.

> **Note on scan date (downgraded from a flag).** A February 2025 scan is *fine for
> current-conditions scenarios*. It only matters for **comparisons against the November 2023 event**:
> anything built, demolished or re-graded between Nov 2023 and Feb 2025 will differ from the ground
> as it was during the event, and a February scan is leaf-off (fine for ground; snow/frozen-ground
> artefacts near water are the residual worry). Any event-comparison result must carry this caveat.
> Separately, `dtm-cog` tile `619_41` (modified 2026-09-14) includes a 2026-04-21 rescan patch
> (~200×160 m, EPSG:3006 417926–418128 E, 6191666–6191824 N) inside the 500 m buffer, outside the
> AOI, not in our tiles — tracked as Post-launch.

**Clip:** AOI bbox (55.84–55.865 N, 13.64–13.685 E) transformed to EPSG:3006, then a true 500 m
buffer applied *in EPSG:3006* metres, snapped outward to multiples of 10 m (so 2/5/10 m blocks align):
E 414330–418210, N 6188550–6192400 (3880×3850 cells at 1 m, no nodata). **Heights stay in RH 2000
exactly as delivered — no geoid conversion, no quantized-mesh tiles** (both are display-terrain
work, deferred to docs/LAUNCH_CHECKLIST.md "Post-launch"; display terrain stays Esri for launch).

**Sanity check vs GLO-30** (GLO-30 minus Lantmäteriet DTM, on the existing 287×273 land-cover grid,
1 m DTM block-averaged, GLO-30 bilinear). GLO-30 is a *surface* model (EGM2008), so positive
differences over vegetation/buildings are expected:

| Group (NMD) | n cells | mean | median | sd |
|---|---|---|---|---|
| Open land (3, 411, 42xx) | 35,195 | +1.10 m | **+0.47 m** | 2.46 |
| Built-up (51, 52) | 13,951 | +1.08 m | +0.86 m | 1.29 |
| Road/rail (53) | 8,495 | +1.18 m | +0.84 m | 1.68 |
| Forest (111–128) | 19,554 | +6.25 m | +4.94 m | 5.11 |
| All valid | 78,351 | +2.40 m | +1.00 m | 3.86 |

Reading: open-land median +0.5 m is the best estimate of the combined datum/vegetation offset — no
sign of tile misregistration or a gross vertical blunder. Forest +6 m is canopy in a 30 m surface
model, smoothed by bilinear resampling (a 2010s vintage tile from 2022 download, not 2025 canopy).
Built-up is low partly because class 52 ("anlagd mark") is mostly not roofs.

**Conditioning (brief 4.5) — `scripts/scenario_prep_dem.py`, done on the 1 m grid, then aggregated.**

**ASSUMPTION — channel dimensions (set by the project lead 2026-09-21, not measured, not in the
brief):**
- **Hörbyån's two arms — OSM ways 77387390 (mainstem) and 77387397 (southern arm), the two
  `boundary_inflows` ways — 6 m wide, 1.0 m deep.**
- **All other waterways (other river/stream/drain OSM lines, including the short Hörbyån pieces in
  the town-centre braids) — 1.5 m wide, 0.5 m deep.**
Width = trapezoid bottom width, banks 1:2. Depth = below the running-minimum ground level along the
line (the lidar is a ground model with no water surface, so this stands in for the brief's "lidar
water surface"). Both values live in `scripts/scenario_prep_dem.py` (`MAIN_ARM`, `OTHER_WATERWAY`)
and should move into `scenarios.yaml` with a source note (brief §1) once confirmed.

Other conditioning choices, all mine, all first-pass:
- Buildings: 2,740 OSM footprints raised **+10 m**; a model cell is raised when ≥50 % of its 1 m
  cells are inside a footprint.
- Channels aggregate to the model cell by **minimum** (not mean) wherever any 1 m channel cell falls
  in it, so the burned channel survives coarsening. Side effect at 5 m: a 1.5 m stream becomes a 5 m
  wide cell at bed level — conveyance is overstated for the small waterways.
- Flow direction of each waterway line is set by the DEM (the line is flipped so its start is the
  higher end; 5 of 23 lines flipped), not by trusting OSM way direction. Bed is forced non-increasing
  downstream.
- Culvert (`tunnel=culvert/yes`) segments are burned like any other channel (6 segments), and a
  ±15 m minimum filter carries the bed under road/rail embankments. So culverts and the main-river
  "bridges" (open channel) fall out of the same burn; only 3 of the 23 lines touch a road. **No
  separate culvert geometry is built and culvert widths are not checked against the brief's 0.8 m
  / 1.5 m** (Post-launch).
- Weirs are not modelled. Water bodies (NMD 61) are left as delivered.

**Environment (deviation from the earlier note).** No rasterio environment or requirements file
existed anywhere on this machine for Aegir (searched the repo, `C:\Purnendu`, the user profile and
WSL; WSL has GDAL 3.8.4 but no rasterio; the QGIS "hypercoast" plugin venv has rasterio 1.5.0 but is a
different tool's environment, so it was not reused). Created **`C:\Purnendu\Aegir\.venv`** from the new
`requirements-dataprep.txt` (`rasterio==1.5.0`, `numpy==2.4.6`, `pyproj==3.7.2`, pinned to the versions
already proven in the hypercoast venv; Python 3.14.5, bundled GDAL 3.12.1). Data-prep scripts only.
Machine-scope `GDAL_DATA` **and `PROJ_LIB`** both point at PostgreSQL 18's older copies (the PROJ one
caused `proj.db ... DATABASE.LAYOUT.VERSION.MINOR = 2` errors); the scripts unset `GDAL_DATA`,
`PROJ_LIB`, `PROJ_DATA` for their own process only.

## Model domain, core definition, and 5 m speed probes — 2026-09-21

**Decision rule (set by the project lead):** use 5 m over a core domain if a full run takes ≤ 2 h;
otherwise 10 m over the full AOI. A later instruction refined it: probe 5 m on both the core and the
full AOI, and if the *full AOI* meets ≤ 2 h, use the full AOI and drop the core. "Full run" = the
brief's 36 h simulation.

**Core domain definition (project lead, 2026-09-21 — never defined in the files before).** A
sub-area of the AOI that must contain: the three river boundary points (east inflow 55.84823 N
13.68501 E; south inflow 55.83990 N 13.66812 E; west outflow 55.84508 N 13.63971 E) on or inside its
edge, so the Phase 1 inflow hydrographs stay valid; the confluence (55.84725 N 13.66771 E); and
Ågatan, Tvärgatan, Skattkistans förskola and the ICA car park, each with a **200 m margin**. Trim
only areas that drain away from the core; if a trimmed area drains significantly toward the core,
keep it in.

How it was applied (`scripts/scenario_prep_dem.py`, geometry in `data/scenario/landmarks.json`):
- The three boundary points sit within ~20 m of the AOI's west, east and south edges (the west
  outflow point is 18 m *outside* the AOI bbox, the south inflow 11 m outside), so the core cannot
  trim on those sides. **Both domains are the AOI bbox extended by 15 m around each boundary point,
  snapped outward to the 5 m grid** (E 414810–417705, S 6189045), so every boundary point has a cell
  inside the domain. Only the north edge is free.
- **Skattkistans förskola is not named in OpenStreetMap.** OSM has three kindergartens in the town
  (Klurifax förskola; two unnamed ways at 55.8468 N 13.6669 E and 55.8512 N 13.6482 E). Which one is
  Skattkistans was not verified, so **all three are inside the core** (conservative). "ICA car park" =
  the two OSM parking ways adjoining ICA Kvantum Hörby (way 239481962/239481963); Ågatan and
  Tvärgatan = all OSM ways with those names.
- Northernmost landmark: the unnamed kindergarten at 55.85152 N. **Core north edge = that +200 m =
  6190585 N (≈55.8533 N).**
- **Core area 4.46 km² vs full AOI domain 8.25 km² (54 %)** — 579×308 vs 579×570 cells at 5 m.

**Drainage of the trimmed strip toward the core** (`scripts/scenario_core_drainage.py`, conditioned
5 m DEM, priority-flood fill + D8): the trimmed strip is 3.79 km²; **1.68 km² (44 %) drains toward
the core** — 83 % of the first 100 m band north of the core edge, still ~45–55 % between 100 m and 900 m
north, falling to ~0 % beyond ~1.3 km. That is significant, so by the rule above the trimmed strip
belongs *in* the model. (D8 on a 5 m DEM with buildings raised +10 m is an approximation; it ignores
storm drains.)

**5 m speed probes** (LISFLOOD-FP 8.1, `acceleration`, `OMP_NUM_THREADS=7` — the physical-core cap
measured earlier; 2 h simulated at the peak 2 h of the 70 mm storm, 29.2 mm; both domains, identical
settings, run sequentially):

| Domain | Cells | 2 h simulated, wall-clock | ms per step | min Δt |
|---|---|---|---|---|
| Core | 579×308 = 178k | 127 s (1.98 min compute) | 7.7 | 0.40 s |
| **Full AOI** | 579×570 = 330k | **194 s (3.22 min compute)** | 12.5 | 0.399 s |

Per-step cost scales with cell count, not wet area (core 30 % wet at the end, AOI 24 %). **Conservative
36 h extrapolation, full AOI:** steps = 129,600 s / Δt. Δt 0.40 s → 324k steps → **68 min**; Δt 0.30 s
→ 90 min; Δt 0.25 s → 108 min. Δt started at 1.0 s and was still falling slowly at 0.40 s, so 0.25 s is
a deliberately pessimistic floor (the probe's Δt is set by a single deep inflow cell — see below —
and real inflows are gentler). **All three are ≤ 2 h, so the rule picks the full AOI at 5 m and the
core is dropped.** The margin at the pessimistic floor is small (108 of 120 min); the measured wall
time of the 36 h pilot below is the check on this.

Earlier, superseded probe: 2 m over AOI + 500 m buffer (3.7 M cells) was stopped at 3,000 of 7,200
simulated seconds after 519 s wall-clock with Δt already 0.38 s — projected far beyond 2 h.

**Probe/pilot inflow caveats (important):**
- LISFLOOD-FP point-source `QFIX` in the `.bci` is **per unit width** (`iterateq.cpp` multiplies it by
  `dx`). The two 2 h probes therefore injected 30×5 + 20×5 = **250 m³/s, not the intended 50 m³/s**
  (the log's `Qin` = 250 shows it). That overstates depth in the inflow cells (max depth there ≈ 8 m)
  and so *lowers* Δt — the probe timings are conservative, but the probe *depths* mean nothing.
  `scripts/scenario_build_dem_probe.py` now divides by the cell size so `--q` is m³/s.
- The Phase 1 storm hydrographs are **not built** (`inflow.baseflow_shype` is still pending in
  `scenarios.yaml`). Probes use constant placeholder flows; the pilot uses S-HYPE's *mean high flow*
  (`mhq`: 6.25 m³/s at SUBID 184 east, 4.76 m³/s at SUBID 64474 south) held constant for 36 h —
  a placeholder far below what a 70 mm event on 77 km² would deliver.
- Rain in the pilot is spatially uniform SCS effective rain from the whole-AOI mean CN 81.12 (sealed
  cells as 98; from `web/data/scenario_curve_number_summary.json`) → 28.9 mm of 70 mm, peak 31 mm/h.
  No drainage-capacity removal. Manning's n from NMD class as in the earlier pilot; the 500 m buffer
  is not in the model domain, so no cells lack land cover except a ≤ 20 m fringe (default n 0.035).
- Result-quality: none of these runs is a flood-hazard result (`run_metadata.json` marks
  `inflow_is_placeholder: true`, `usable_for_flood_analysis: false`).

## Pilot success criteria — written before any depth output was opened — 2026-09-21 23:08:47 +02:00

Project-defined tolerances (not literature values), written 2026-09-21 by the assistant under the
overnight plan because ASSUMPTIONS.md contained no pilot success criteria (searched for "success
criteri*", "acceptance criteri*", "pass/fail"). **Timestamp of writing: 2026-09-21 23:08:47 +02:00.** State of knowledge at
that moment: the assistant had read only the .mass progress lines of the probes and of the 70 mm
run while it was running (time, timestep, wet area, volume, volume error) and the run's
"Total computation time"; it had **not** opened any .max, .wd, .elev or map. The 40 mm and
100 mm runs had not started outputs yet. Thresholds below were not tuned to any depth result.

Applied to every completed run (70 mm pilot = production run, then 40 mm, 100 mm):

| # | Criterion | Pass if |
|---|---|---|
| C1 | Completion | Run reaches the configured 36 h (sim_time 129,600 s), 
un.log contains "Total computation time", no abnormal exit |
| C2 | Mass balance | \|cumulative volume error\| (Verror, last .mass row) <= **1 %** of total inflow volume (boundary inflow + effective rain, both integrated over 36 h) |
| C3 | Wall-clock | Total wall-clock for the full run <= **2 h** (the 5 m-full-AOI rule) |
| C4 | No timestep collapse | Minimum timestep over the run >= **0.1 s** |
| C5 | Valid grids | .max has no NaN and no negative depths; grid size equals the DEM (579 x 570) |
| C6 | No inflow-cell pile-up | Maximum depth within 3 cells (15 m) of either inflow point <= **3 m** |
| C7 | Reporting locations resolvable | All four reporting locations (Ågatan, Tvärgatan, Skattkistans förskola, ICA car park) fall inside the domain, so impacts.json can be computed |

Not pass/fail (reported only): standing-water candidates for missing culverts (depth > 0.3 m with a
downstream edge on a road/rail embankment). Whole-run results are placeholders regardless of these
criteria: inflows are constant placeholders and rain uses one uniform CN (see the "Probe/pilot
inflow caveats" above), so a pass means *numerically sound*, not *hazard-representative*.

## 70 mm run (pilot = production run) — results against the success criteria — evaluated 2026-09-21 23:14:59 +02:00

Run pilot_aoi_5m_70mm: full AOI, 5 m (579 x 570), LISFLOOD-FP 8.1 cceleration, 7 threads, 36 h,
SCS effective rain 28.9 mm (CN 81.12), constant placeholder inflows 6.25 + 4.76 m3/s, **all four
edges closed**. Snapshots every 6 h only (this run predates the 2 h-grid request), so its
intermediate max grids are 6-hourly running maxima; the final .max is exact.

| # | Criterion | Result | Value |
|---|---|---|---|
| C1 | Completion | **pass** | reached t = 129,600 s; "Total computation time" present |
| C2 | Mass balance <= 1 % of inflow | **pass** | independent closure 0.022 % (-371 m3 of 1,665,343 m3); last-row Verror 0.0; max \|Verror\| in any row 0.0085 m3 |
| C3 | Wall-clock <= 2 h | **pass** | 2,177 s wall (36.3 min compute) — the pre-run conservative projection was 68-108 min |
| C4 | Min timestep >= 0.1 s | **pass** | min 0.4045 s (reached at the end of the run); mean 0.4606 s over 281,387 steps. LISFLOOD-FP reports the *time* of the minimum only, not its cell |
| C5 | Valid grids | **pass** | 570 x 579, no NaN, no negative depth, max 7.63 m |
| C6 | Inflow cells <= 3 m | **pass** | 0.95 m (east) and 0.39 m (south) within 15 m of the inflow points |
| C7 | Reporting locations resolvable | **pass** | all in the domain |

**Pass here means numerically sound, not physically representative.** The maximum-depth map
(model/outputs/pilot_aoi_5m_70mm/maxdepth_map.png) shows why: with every edge closed and the
west outflow not modelled (the brief requires free outflow at the downstream boundary), the
1.67 million m3 that enters over 36 h cannot leave, and the western valley floor fills like a
bathtub — 3-7 m deep through the western part of the town, still rising at 36 h. Depths at the
reporting locations are dominated by that artefact, not by rainfall or river behaviour:

| Location | Max depth | Time of max |
|---|---|---|
| Ågatan | 6.52 m | 36.0 h (end) |
| Tvärgatan | 3.58 m | 36.0 h (end) |
| ICA car park | 3.95 m | 36.0 h (end) |
| Skattkistans förskola — candidate Klurifax förskola | 0.65 m | 36.0 h |
| — candidate unnamed kindergarten way/300881149 | 1.72 m | 36.0 h |
| — candidate unnamed kindergarten way/300881151 | 0.09 m | 9.69 h |

**Not for publication as flood results.** Corrected supplementary variants with a free outflow
along the west edge (scen_aoi_5m_{70,40,100}mm_freeout) were queued after the required runs
(see docs/OVERNIGHT_REPORT.md).

**Artefact candidates (missing culverts), 70 mm run — no DEM changes made.** Six connected areas
deeper than 0.3 m have a downstream edge (lowest rim cells) on a road embankment; details, locations
in EPSG:3006 and *unapplied* proposed cuts are in model/outputs/pilot_aoi_5m_70mm/artefact_candidates.json
and proposed_corrections_UNAPPLIED.geojson. Downstream-edge rule (project-defined): rim cells within
0.25 m of the pond's lowest rim elevation, >= 50 % of them within 5 m of a road/rail centreline. The
big western lake is *not* one of them — it is the closed-boundary artefact above. OSM shows no railway in the fetched extract, but that extract was queried for `highway` and `waterway` only (`scripts/fetch_geography.py`), so **railway embankments were not checked at all** (Post-launch: fetch `railway=*`). Road ways tagged `bridge=yes` (16) are not treated as embankments (a bridge deck is not fill in a ground model), so the candidates are road embankments only.

## Run records (overnight queue)

Written automatically by `scripts/overnight_report.py` after each finished run. Thresholds (1 % volume error, criteria C1-C7) are project-defined tolerances, not literature values.

### Run record - `scen_aoi_5m_40mm` (40 mm, closed boundary)

- Recorded 2026-09-21 23:32:43 +0200. Wall-clock 1419 s (incl. staging), compute 23.53 min.
- Timestep: min 0.4082 s (first reached at t = 129600 s; LISFLOOD-FP reports the time only, not the cell), mean 0.4641 s over 279,239 steps.
- Cumulative volume error: independent closure -40.1 m3 = 0.0027 % of total inflow 1,501,978 m3 (outflow 0 m3); solver last-row Verror -0.0 m3. Within the 1 % tolerance.
- Criteria: 7/7 pass. Boundary: none (all edges closed; the west outflow is NOT modelled).

### Run record - `scen_aoi_5m_100mm` (100 mm, closed boundary)

- Recorded 2026-09-22 00:01:58 +0200. Wall-clock 1754 s (incl. staging), compute 29.13 min.
- Timestep: min 0.3998 s (first reached at t = 129600 s; LISFLOOD-FP reports the time only, not the cell), mean 0.4556 s over 284,463 steps.
- Cumulative volume error: independent closure 656.8 m3 = 0.0353 % of total inflow 1,862,536 m3 (outflow 0 m3); solver last-row Verror 0.0 m3. Within the 1 % tolerance.
- Criteria: 7/7 pass. Boundary: none (all edges closed; the west outflow is NOT modelled).

### Run record - `scen_aoi_5m_70mm_freeout` (70 mm, free west outflow (supplementary))

- Recorded 2026-09-22 00:16:11 +0200. Wall-clock 858 s (incl. staging), compute 14.2 min.
- Timestep: min 0.6515 s (first reached at t = 109200 s; LISFLOOD-FP reports the time only, not the cell), mean 0.7207 s over 179,817 steps.
- Cumulative volume error: independent closure -272.5 m3 = 0.0164 % of total inflow 1,665,343 m3 (outflow 1,491,753 m3); solver last-row Verror -0.0 m3. Within the 1 % tolerance.
- Criteria: 7/7 pass. Boundary: free outflow along the west edge (LISFLOOD FREE, local slope).

### Run record - `scen_aoi_5m_40mm_freeout` (40 mm, free west outflow (supplementary))

- Recorded 2026-09-22 00:25:23 +0200. Wall-clock 569 s (incl. staging), compute 9.38 min.
- Timestep: min 0.7846 s (first reached at t = 87300 s; LISFLOOD-FP reports the time only, not the cell), mean 0.812 s over 159,604 steps.
- Cumulative volume error: independent closure 63.1 m3 = 0.0042 % of total inflow 1,501,978 m3 (outflow 1,385,637 m3); solver last-row Verror -0.0 m3. Within the 1 % tolerance.
- Criteria: 7/7 pass. Boundary: free outflow along the west edge (LISFLOOD FREE, local slope).

### Run record - `scen_aoi_5m_100mm_freeout` (100 mm, free west outflow (supplementary))

- Recorded 2026-09-22 00:42:32 +0200. Wall-clock 993 s (incl. staging), compute 16.45 min.
- Timestep: min 0.6113 s (first reached at t = 68700 s; LISFLOOD-FP reports the time only, not the cell), mean 0.6689 s over 193,749 steps.
- Cumulative volume error: independent closure 1047.3 m3 = 0.0562 % of total inflow 1,862,536 m3 (outflow 1,661,099 m3); solver last-row Verror -0.0 m3. Within the 1 % tolerance.
- Criteria: 7/7 pass. Boundary: free outflow along the west edge (LISFLOOD FREE, local slope).


## Release batch — free outflow, corrected inflows (blocked), channel capacity, culvert cuts — 2026-09-22

### 1. Boundary condition: free outflow adopted as production

**Decision (project lead, 2026-09-22): free outflow along the west edge is now the production
boundary condition**, superseding every earlier closed-boundary run. LISFLOOD-FP syntax: `W <y0>
<y1> FREE` (no slope given -> local water-surface slope each timestep). **This approximates a
normal-depth condition at the outflow** — the standard engineering shorthand for "let the water
leave at whatever depth the local channel/floodplain slope implies," not a measured or
independently derived rating curve. The three closed-boundary runs (`pilot_aoi_5m_70mm`,
`scen_aoi_5m_40mm`, `scen_aoi_5m_100mm`) are **superseded**: moved to
`model/outputs/_superseded_closed_boundary/` and dropped from `web/data/results/manifest.json`.
Reason recorded here, per instruction: with every edge closed, 1.4-2.0 million m3 of inflow over
36 h had nowhere to go, and the western valley floor filled 3-7 m deep — an artefact of the
boundary condition, not of the storm or the river (see the now-superseded pilot's own write-up
above for the numbers). The free-outflow runs are the ones now published under the plain
`40mm`/`70mm`/`100mm` keys.

### 2. Event inflow hydrographs — computed, but the model queue is BLOCKED

**Catchment CN** (`scripts/scenario_catchment_cn.py`): area-weighted CN(II) over NMD2023 x SGU
soils, area outside the AOI, same TR-55 POOR-condition lookup as the AOI grid, sealed=98, water
excluded, group-B fallback. Catchment geometry: SVAR subcatchment polygons whose MAINDOWN
drainage-topology chain reaches each arm's own anchor (verified against `scenarios.yaml`'s
AREA_UPSTREAM figures — an EARLIER version of this walk used the wrong ARO_UUIDs, caught only
because the areas didn't match 77.61/62.22 km²; the corrected anchors are `8C58B808...`
"Ebbamölleån" for SUBID 184 and `1A0D99F7...` "södra armen" for SUBID 64474).

| Catchment | Area outside AOI | CN(II) | CN(III), AMC III |
|---|---|---|---|
| East (SUBID 184) | 76.844 km² (SVAR-based cross-check: 76.90) | 72.27 | 85.70 |
| South (SUBID 64474) | 61.968 km² (cross-check: 61.98) | 76.93 | 88.47 |

CN(III) = 23·CN(II)/(10+0.13·CN(II)) (Chow, Maidment & Mays, 1988), for the wet-November AMC III
assumption. ~5-22% of each catchment's NMD pixels are unmapped classes or fallback-group, same kind
of gap as the AOI-scale calculation, not investigated further.

**Longest flow path and mean slope** (`scripts/scenario_catchment_flowpath.py`, Copernicus GLO-30 at
native ~30 m, reprojected EPSG:4326→EPSG:3006, priority-flood fill, D8, flow-length-to-catchment-exit
by a single ascending-elevation topological pass): east 17,818 m / 6.16% mean slope; south 19,359 m
/ 4.27%. **Cross-check: the D8-derived catchment exit point lands 50 m (east) and 95 m (south) from
the actual boundary-inflow lat/lon in `scenarios.yaml`** — one to three 30 m pixels, strong
independent confirmation that the SVAR catchment delineation and the GLO-30 terrain agree.

> **Bug caught and fixed during this step:** the GLO-30 tile's embedded CRS WKT declares
> `AXIS["Latitude",NORTH]` before longitude. Reprojecting with that CRS object directly (rather
> than the bare string `"EPSG:4326"`) made PROJ apply the axis order literally, silently producing
> a near-constant (flat) reprojected DEM — mean slope computed as exactly 0.0, longest flow path a
> fraction of the plausible value. Caught by sanity-checking the reprojected array's std-dev before
> trusting it. Fixed by forcing the plain lon/lat string. Documented so nobody re-adds `src.crs`
> as a "more correct" source CRS for this file later.

> **Limitation, stated per instruction, not a validated parameter:** the NRCS lag equation (NEH
> Part 630, Ch. 15) is developed and validated for small catchments (commonly cited guidance:
> well under 10 km²). Both catchments here (62-77 km²) are one to two orders of magnitude larger.
> **NRCS lag: east 4.16 h, south 4.67 h** (Tp = D/2+L = 4.24 h / 4.76 h) — a documented
> extrapolation, not a calibrated lag time.

**SCS-CN effective rainfall + SCS unit hydrograph convolution + station-2128 baseflow**
(`scripts/scenario_compute_inflow_hydrographs.py`). Baseflow = median of station 2128 (HEÅKRA), 1-15
Nov 2023 daily values = recomputed programmatically = **4.47 m³/s** (matches the earlier
plausibility-check figure exactly), split by catchment area outside the AOI: **east 2.474 m³/s /
south 1.996 m³/s**. Plots: `docs/hydrographs/hydrograph_{40,70,100}mm.svg`.

| Storm | East peak (incl. baseflow) | South peak | Combined peak (time-aligned) | Combined time |
|---|---|---|---|---|
| 40 mm | 27.63 m³/s @ 14.7 h | 26.73 m³/s @ 15.2 h | **54.25 m³/s** | 14.8 h |
| 70 mm | 78.53 m³/s @ 14.3 h | 68.07 m³/s @ 14.8 h | **145.81 m³/s** | 14.7 h |
| 100 mm | 137.57 m³/s @ 14.2 h | 113.65 m³/s @ 14.7 h | **249.68 m³/s** | 14.3 h |

**Consistency check (not calibration), per instruction — FAILED:**

| | Value |
|---|---|
| Observed peak, station 2128, Nov 2023 event | 24.1 m³/s (17 Nov) |
| Comparable scenario | 40 mm (comparable in depth to the 36.9 mm pre-event rainfall) |
| Modelled 40 mm combined peak (time-aligned) | 54.25 m³/s |
| **Ratio (time-aligned)** | **2.251** |
| Modelled 40 mm sum of the two arms' own peaks | 54.36 m³/s |
| **Ratio (sum-of-peaks)** | **2.256** |
| Project-defined tolerance | 0.5 - 2.0 |
| **Verdict** | **STOP — both ratio definitions exceed 2.0 (by ~12.5-12.8%)** |

**>>> Per instruction, the model queue for the corrected inflows was NOT run. <<<** This is a
decision point for the project lead, not a silent auto-correction:
- The overshoot is modest (12-13% over the tolerance ceiling, not an order of magnitude), so this
  is plausibly a methodology mismatch rather than a gross error: (a) CN(III)/AMC III applied
  uniformly from t=0 assumes already-saturated ground for the whole 40 mm event, which is
  conservative (produces more runoff than a gradually-wetting catchment); (b) the two arms' peaks
  are simply added at matching model-time, with no channel/floodplain attenuation between each
  catchment's own pour point and the confluence — real travel-time lag and storage would flatten
  and spread the combined peak; (c) SCS methods are meant for single, compact catchments, not
  two 60-80 km² systems summed.
- **Not changed without confirmation:** CN, AMC assumption, baseflow split, or the tolerance
  itself — any of these could bring the ratio into range, but adjusting them now, after seeing the
  ratio fail, would be calibration by another name, which the instructions explicitly rule out.
- Everything needed to run the corrected-inflow scenarios is ready and unblocking this is a single
  decision: `scripts/scenario_build_dem_probe.py` needs a `--bdy` option (not yet added) to point at
  `data/scenario/derived/hydrograph_<mm>mm.bdy` in place of the constant `--q`; the `.bdy` files
  already exist for all three storms.

### 3. Channel capacity — Manning's equation, bankfull sized to MHQ

**Width stays 6 m.** The Lantmäteriet `breakgeometry` asset (`m619_41_brytgeometri.gpkg`, which
could supply a measured water-surface width) is **not accessible**: `dl1.lantmateriet.se` returns
HTTP 401 for the same credentials that already fail the DEM tile download (checked 2026-09-22,
same failure mode as ASSUMPTIONS.md's DEM section).

Depth solved from Q=(1/n)·A·R^(2/3)·S^(1/2), n=0.035, trapezoidal (6 m bottom, banks 1:2), S = local
bed slope sampled from the conditioned 5 m DEM along each reach (`scripts/scenario_channel_capacity.py`).
**Found and fixed while building this:** OSM way 77387390 ("Hörbyån") is ONE way spanning the
*entire* mainstem, both the east arm and the reach below the confluence — an earlier pass sized the
whole thing as one 6.25 m³/s reach, mixing pre- and post-confluence flow. Fixed by splitting the way
at its vertex nearest the confluence (55.84725 N, 13.66771 E) before sampling.

| Reach | Q (MHQ) | Length | Bed slope | Depth | Velocity | Top width |
|---|---|---|---|---|---|---|
| East arm (AOI edge -> confluence) | 6.25 m³/s | 1,578 m | 0.00712 | **0.585 m** | 1.49 m/s | 8.34 m |
| South arm (AOI edge -> confluence) | 4.76 m³/s | 2,568 m | 0.00449 | **0.571 m** | 1.17 m/s | 8.28 m |
| Below confluence -> west edge | 11.01 m³/s | 6,087 m | 0.00096 | **1.404 m** | 0.89 m/s | 11.61 m |

Applied: the channel burn now uses these three per-reach depths (was one uniform 1.0 m for the
whole mainstem) — `EAST_ARM_SPEC` / `BELOW_CONFLUENCE_SPEC` / `SOUTH_ARM_SPEC` in
`scripts/scenario_prep_dem.py`. The DEM was re-conditioned and all AOI/core 5 m rasters regenerated.
Every other waterway is unchanged (1.5 m wide / 0.5 m deep). The burn still uses the aggregation
rule from the original conditioning (block-**minimum** across the channel when resampling to 5 m),
so the deeper below-confluence reach survives resampling — unchanged mechanism, just applied
per-reach now instead of uniformly.

### 4. Culvert cuts — union of the three free-outflow runs, applied where evidenced

`scripts/scenario_apply_culvert_cuts.py`: unioned the missing-culvert candidates from
`scen_aoi_5m_{70,40,100}mm_freeout` (25 raw candidates across the three storms, deduplicated by
sill proximity <=15 m to **19 distinct features**). **Applied the proposed cut only where a mapped
OSM waterway lies within 25 m of the sill** (project-defined tolerance, not a literature value);
every other candidate is left as a genuine depression, uncut.

**2 applied, 17 rejected:**

| Sill (EPSG:3006) | Area | Depth | Nearest waterway | Decision |
|---|---|---|---|---|
| (415412, 6191502) | 400 m² | 0.61 m | drain, 4 m | **APPLIED** — 0.8 m cut, invert 86.14 m |
| (416672, 6190138) | 325 m² | 1.10 m | stream, 11 m | **APPLIED** — 1.5 m cut, invert 78.81 m |
| (414978, 6191308) | 8,850 m² | 1.21 m | 128 m away | rejected — no evidenced crossing |
| (415118, 6190438) | 850 m² | 2.27 m | 451 m away (Hörbyån) | rejected — nearest waterway too far to be this pond's crossing |
| *(15 more, 34-535 m from any mapped waterway)* | | | | rejected |

Full list with every candidate, reason, and the applied cuts' exact geometry:
`data/scenario/derived/culvert_cut_decisions.json`. The two applied cuts changed 36 cells on the
1 m conditioned grid (a first pass at the cut geometry only moved 5 cells — the stored path has
only a handful of vertices, one per step of `scenario_map_maxdepth.py`'s own tracing loop, so at a
narrow 0.8-1.5 m width most of a 20 m path fell between 1 m cell centres; fixed by densifying the
path to ~0.5 m spacing before stamping, the same technique the channel burn itself already uses).
**Re-derive-and-rerun-once step (per instruction) not yet done**, since it depends on the final
runs, which are blocked by §2 above.

### 5. Final runs (40/70/100 mm, corrected inflows + channel + cuts) — NOT RUN

Blocked on §2's consistency-check STOP. The DEM now has the corrected channel and the two
confirmed culvert cuts (both apply regardless of the inflow question), so the currently-published
free-outflow results are **already one step stale** (old channel, old placeholder inflow) even
before the inflow question is resolved. Nothing further was queued or run pending a decision.

### 6. Skattkistans förskola — resolved to a single location

**Accepted by the project lead, 2026-09-22:** Skolverket's Skolenhetsregistret API
(`api.skolverket.se/skolenhetsregistret`) returned HTTP 404 on every guessed REST/OpenAPI-spec
endpoint, and its Swagger UI is JS-rendered (not fetchable without a browser). Per instruction, the
`horby.se` source is accepted in its place. **Source: <https://www.horby.se/forskola-och-utbildning/forskola-och-barnomsorg/forskola/skattkistan/>,
retrieved 2026-09-22.** Address given there: **Ågatan 2B, 242 33 Hörby**. Geocoded to the nearest point on OSM's own Ågatan geometry (**street-
level, not rooftop-level** — no building in this AOI carries an `addr:housenumber` tag in OSM, so
an exact building-level geocode isn't possible from this data source): 13.6526198 E, 55.8484911 N,
the street's south end. Recorded in `data/scenario/landmarks.json`. **Klurifax förskola is excluded**
as a separate, independent preschool, per instruction. The three former OSM "candidate" kindergarten
entries are dropped from the reporting-location list (`scripts/scenario_postprocess_run.py`); the
website and `impacts.json` now report exactly four locations. Re-ran post-processing on the three
published free-outflow runs so their `impacts.json`/site reflect this (their underlying depth grids
are unchanged — same caveat as §5, they predate today's channel/cut update).

### 7. Uniform-CN simplification — flagged, not changed

Rain falling *inside* the AOI still uses one uniform area-mean CN (81.12, sealed=98) rather than a
per-cell CN map, per instruction not to implement spatial effective rainfall in this batch. Added
to the website's assumptions panel as an explicitly listed simplification (`web/scenarios/app.js`).

### 2b. Consistency-check metric corrected — project-lead decision, 2026-09-22 — ACCEPT

**Specification error in the original check, not a modelling error (project lead's own framing):**
the check as first specified compared an *instantaneous* modelled peak against an SMHI *daily-mean*
observed peak (station 2128's `Vattenföring (Dygn)` series is a daily mean, not an instantaneous
maximum). These are not the same quantity — a flood hydrograph's instantaneous peak necessarily
exceeds its own maximum daily mean, so the 2.25-2.26 ratio recorded above was comparing two
different things, not evidence the hydrographs are too large.

**Corrected metric — the maximum 24 h mean of the combined (both arms + baseflow) 40 mm-scenario
series**, computed two ways:

| Metric | Value | Ratio vs 24.1 m³/s |
|---|---|---|
| Instantaneous peak (original, kept for transparency) | 54.25 m³/s | 2.251 |
| **Maximum 24 h MOVING mean** (accepted metric) | **28.21 m³/s** | **1.171** |
| Maximum 24 h CALENDAR-DAY mean, t=0 = 06:00 UTC (matches the SMHI 06:00-06:00 daily window, README.md) | 22.94 m³/s | 0.952 |

**Both corrected ratios fall inside the 0.5-2.0 tolerance. Verdict: ACCEPT — proceed to the final
runs.** No adjustment was made to CN, antecedent condition, baseflow split or lag time to reach
this result; only the comparison metric itself was corrected, per the project lead's explicit
instruction not to calibrate to this check.

**Expected direction of the residual difference (recorded per instruction, before the final runs
were judged against it):** the moving-mean ratio (1.171) sits moderately above 1.0, which is the
*expected* direction, not a red flag, for two reasons:
1. **Floodplain storage attenuation** between each catchment's own pour point and station 2128 (at
   the AOI's west edge, downstream of the confluence) is not modelled in the SCS-CN/UH chain — real
   attenuation would flatten the modelled peak further, so the model is expected to run a little high.
2. **Storm intensity mismatch:** the Chicago Design Storm used here concentrates the same total
   depth into a shorter, more intense burst than a typical frontal November rainfall of equal
   depth (the kind that produced the observed 36.9 mm event) — a more intense storm of the same
   depth produces more, and more peaked, runoff under the SCS-CN method.

A ratio of exactly 1.0 would therefore have been slightly suspicious (implying either an
overcorrection elsewhere, or that the real event's attenuation and storm shape happened to cancel
out); 1.17 is judged consistent with correct hydrographs. This is a **plausibility test, not a
calibration** — nothing about the model was tuned to produce this number.

### 5b. Final runs — completed, 2026-09-22 (supersedes §5's "NOT RUN")

Unblocked by §2b's ACCEPT decision. Three runs (`final_aoi_5m_{40,70,100}mm`): free outflow (west
edge), corrected per-reach channel (§3, already applied to the DEM), the 2 confirmed culvert cuts
(§4, already applied), and the event inflow hydrographs (§2/§2b, `--bdy` QVAR point sources) in
place of the constant placeholder. 5 m cells, `acceleration` solver, `OMP_NUM_THREADS=7`, 36 h.
`scripts/scenario_build_dem_probe.py` gained a `--bdy` flag for this (QVAR point sources from the
computed `.bdy` files; everything else identical to the earlier `--q` constant-inflow path).
`scripts/scenario_postprocess_run.py` was extended to integrate a QVAR `.bdy` series (trapezoid
rule, clamped to `sim_time`) for the mass-balance closure check, since a QVAR boundary has no
single constant rate to multiply by `sim_time` the way QFIX does.

| Run | Wall-clock | Compute | Min timestep | Closure error | Criteria |
|---|---|---|---|---|---|
| 40 mm | 1,112 s | 18.4 min | 0.584 s | 0.0053 % | 7/7 pass |
| 70 mm | 1,632 s | 27.0 min | 0.507 s | 0.0081 % | 7/7 pass |
| 100 mm | 1,780 s | 29.5 min | 0.470 s | 0.0111 % | 7/7 pass |

**Reporting locations, max depth (m) / time of max (h into the 36 h run):**

| Location | 40 mm | 70 mm | 100 mm |
|---|---|---|---|
| Ågatan | 3.457 @ 15.6 h | 4.661 @ 15.4 h | 5.376 @ 15.2 h |
| Tvärgatan | 2.227 @ 15.2 h | 3.306 @ 14.7 h | 3.737 @ 14.5 h |
| ICA car park | 0.308 @ 24.0 h | 1.607 @ 15.4 h | 2.368 @ 15.2 h |
| Skattkistans förskola | 0.228 @ 22.4 h | 1.315 @ 15.4 h | 2.062 @ 15.2 h |

**Scenario contrast at Ågatan (100 mm minus 40 mm): 1.92 m.** All peaks land 14.5-15.6 h into the
run, matching the inflow hydrographs' own combined peak (14.3-14.8 h, §2) plus a short routing lag
through the domain — physically consistent. The 40 mm ICA/Skattkistans peaks occur much later
(22-24 h) because at that lower flow the depth there is governed by the storm's own smaller local
rainfall pulse rather than the river peak passing through, unlike the 70/100 mm runs where the
river dominates everywhere in the domain.

**Re-derived culvert candidates on these three runs** (`scripts/scenario_apply_culvert_cuts.py
--runs final_aoi_5m_40mm final_aoi_5m_70mm final_aoi_5m_100mm`, dry run): 25 candidates after
dedupe, same 2 already-applied cuts confirmed present, **zero new candidates meet the 25 m rule**.
No further DEM change and no second final-run pass were needed, per instruction.

Post-processing, the UI check and deploy preparation proceeded as specified after these runs; the
website now shows these three results by default (`web/data/results/manifest.json`). Nothing was
pushed.

## Depth-plausibility gate — Ågatan/Tvärgatan vs the Nov 2023 record — 2026-09-22

Read-only diagnosis (project lead, 2026-09-22). No change to the model, the DEM, or the forcing.
Script: `scripts/scenario_depth_plausibility_check.py`. Full numeric output:
`data/scenario/derived/depth_plausibility_gate.json`.

**1. Metric definition (exactly what is published, from `scripts/scenario_postprocess_run.py`):**
the statistic is the **maximum** water depth over the footprint mask — never mean or a percentile.
Footprints: Ågatan/Tvärgatan = the OSM street centreline dilated +-15 m (3 cells @ 5 m); ICA car
park = OSM parking polygons dilated +-5 m (1 cell); Skattkistans förskola = the single geocoded
point (horby.se) dilated +-15 m (3 cells). **Ågatan's footprint intersects the burned channel mask
(31 of 371 cells); Tvärgatan's does too (40 of 1631 cells).** ICA car park and Skattkistans
förskola do not touch the channel at all.

**2. Street-surface depth (water surface elevation from the model's own conditioned-ground + .max
depth, minus the UNCONDITIONED raw 1 m DTM, channel mask + 1-cell buffer removed, exactly as
instructed):**

| Location, 40 mm | Published max | Street max (channel excl. only) | Street p90 | Street median |
|---|---|---|---|---|
| Ågatan | 3.457 m | 10.005 m | 0.114 m | 0.003 m |
| Tvärgatan | 2.227 m | 10.006 m | 9.998 m | 0.004 m |
| ICA car park | 0.308 m | 10.006 m | 0.066 m | 0.002 m |
| Skattkistans förskola | 0.228 m | 10.005 m | 10.001 m | 0.108 m |

**Finding: the channel-only exclusion is not sufficient.** The instructed exclusion (channel mask
+ 1-cell buffer) leaves building-raised cells (+10 m, the flow-obstruction conditioning) inside
these dilated footprints — Ågatan/Tvärgatan run through the dense town centre, so the +-15 m
dilation catches building edges. A building cell's water surface there is (unconditioned ground +
10 m + a small real depth), so subtracting the unconditioned ground gives ~10 m: a raise-height
artefact, not water. This swamps the max and, for Tvärgatan and Skattkistans förskola, the p90 too
(17/324, 180/1631, 30/518 and 10/49 kept cells respectively are building-raised).

**A second variant, ALSO excluding building-raised cells, is reported for the real answer:**

| Location, 40 mm | Street max (excl. buildings too) | Street p90 | Street median |
|---|---|---|---|
| **Ågatan** | **0.225 m** | **0.071 m** | 0.003 m |
| Tvärgatan | 0.399 m | 0.036 m | 0.003 m |
| ICA car park | 0.311 m | 0.006 m | 0.001 m |
| Skattkistans förskola | 0.225 m | 0.184 m | 0.080 m |

**These are consistent with the Nov 2023 record** ("parts of Ågatan submerged," not multi-metre
inundation) — Ågatan's actual street surface is at most 0.225 m deep anywhere in its footprint at
40 mm, typically far less (median 3 mm). ICA car park, which never touches the channel and has
little building overlap, already matched its published value closely even before this fix
(0.311 m vs published 0.308 m) — a useful cross-check that the methodology itself is sound.

**Root cause of the published number, now explained: the published "max" statistic is dominated by
a channel cell within the dilated footprint, not by street flooding.** Ågatan's channel is now
sized to a bankfull MHQ capacity of 6.25 m³/s (§3), while the 40 mm event's peak inflow there is
27.6 m³/s — **4.4x over capacity** — so the channel itself runs several metres deep during the
event, entirely expected for a channel that size carrying that much flow. The reporting footprint
picking up 31 of those channel cells, and reporting their depth as "depth at Ågatan," is a
**reporting-statistic problem, not a hydraulic or DEM problem.**

**3. Proposed statistic — NOT applied, pending approval:** the 90th percentile of street-surface
depth (channel mask + 1-cell buffer AND building-raised cells excluded) over the footprint,
labelled `street_surface_excl_buildings_p90_m` in the report. Rationale, as instructed: a maximum
is set by one cell (here, a channel cell or a building edge) and is sensitive to local depressions
and to the channel itself; the 90th percentile represents conditions over most of the street
surface. **Marked as a project-defined statistic**, and this batch does **not** change the website
or `impacts.json` to use it.

**Gate trigger check (Ågatan, 40 mm, street-surface p90 excluding buildings): 0.071 m, well under
the 1.0 m project-defined trigger. Hydraulic diagnosis (step 4) was therefore NOT run**, per
instruction ("only if ... still exceeds 1.0 m"). At the larger, hypothetical 70/100 mm storms — not
directly comparable to the observed Nov 2023 event — the same statistic does rise (1.16 m / 1.91 m
at Ågatan), which is plausible given those events exceed the historical rainfall by design.

## Reporting decisions applied — project-defined statistics, river layer, area recompute — 2026-09-22

Approved by the project lead following the depth-plausibility gate above. Post-processing only —
no model runs, no DEM or forcing changes. `scripts/scenario_postprocess_run.py` was rewritten to
compute these directly from the three existing `final_aoi_5m_{40,70,100}mm` outputs, and re-run for
all three (same `--wall-s` as originally measured; `run_stats.json`/`criteria.json` — computed from
the unchanged `.mass`/`.max`/run.log files — are byte-identical in substance, all 7/7 criteria still
pass).

**Published location statistics (project-defined, replacing the single-cell maximum):**
1. **`street_surface_p90_m`** — 90th percentile of street-surface depth (water surface elevation
   from the model's own conditioned ground + LISFLOOD `.max` depth, minus the UNCONDITIONED raw
   1 m DTM) over the footprint, with the burned-channel mask + 1-cell buffer AND building-raised
   cells excluded.
2. **`wetted_fraction`** — share of those remaining footprint cells deeper than 0.05 m.

Both marked project-defined in `web/data/results/<mm>mm/impacts.json`'s own `note` field and in the
website's assumptions panel (`web/scenarios/app.js`, new "Reported location statistics" row) and in
this file. The old single-cell maximum is kept as `street_max_m_reference_only` in `impacts.json`
for reference but is **not displayed** on the site.

**Location results (all three storms), p90 street-surface depth / wetted fraction:**

| Location | 40 mm | 70 mm | 100 mm |
|---|---|---|---|
| Ågatan | 0.071 m / 13% | 1.161 m / 76% | 1.908 m / 90% |
| Tvärgatan | 0.036 m / 7% | 0.578 m / 47% | 1.316 m / 74% |
| ICA car park | 0.006 m / 5% | 1.170 m / 60% | 1.929 m / 63% |
| Skattkistans förskola | 0.184 m / 74% | 1.276 m / 100% | 2.023 m / 100% |

**Fly-to target changed from the deepest cell to the footprint centroid** (`fly_to_epsg3006` /
`fly_to_lonlat` in `impacts.json`), since the deepest cell frequently sits inside the channel.

**Depth map: channel cells excluded from the colour classes, rendered as a separate river layer.**
`scripts/scenario_postprocess_run.py` now masks burned-channel cells out of the depth-class ramp
entirely and paints them a fixed, uniform colour (`rgb(60,130,200)`, opaque) instead, recorded as
`river_layer` in each `meta.json`. `web/scenarios/app.js`'s legend now has a matching "River
(permanent channel, not depth-classified)" entry.

**Area statistics recomputed on the street-surface basis (channel + buildings excluded), old vs
new, `web/data/results/<mm>mm/impacts.json`'s `summary` (new) and
`summary.area_stats_old_basis_reference_only` (old, raw LISFLOOD depth above conditioned ground,
whole domain):**

| Storm | Metric | Old (whole domain, raw depth) | New (street-surface basis, channel+buildings excl.) |
|---|---|---|---|
| 40 mm | wet area (>0.05 m) | 0.443 km² | 0.323 km² |
| | area >0.3 m | 0.142 km² | 0.040 km² |
| | area >0.5 m | 0.104 km² | 0.013 km² |
| 70 mm | wet area (>0.05 m) | 0.972 km² | 0.815 km² |
| | area >0.3 m | 0.458 km² | 0.321 km² |
| | area >0.5 m | 0.334 km² | 0.208 km² |
| 100 mm | wet area (>0.05 m) | 1.423 km² | 1.254 km² |
| | area >0.3 m | 0.720 km² | 0.566 km² |
| | area >0.5 m | 0.543 km² | 0.401 km² |

The new figures are consistently smaller — expected, since they exclude the river itself (which is
"wet" by definition, often >0.5 m deep) and building-raise artefacts, leaving only genuine
overbank/street inundation.

**Website rebuilt and browser-tested** (external requests blocked): headline now reports p90 depth
and wetted-fraction language; location cards show p90 + wetted-fraction, not max; legend has the
river entry; only console message is the deliberately blocked Esri elevation request. No horizontal
overflow at phone width. One stale static caption under the reporting-location list (still describing
the old "maximum depth" statistic and the un-resolved Skattkistans candidates) was found and fixed
(`web/scenarios/index.html`).

**Nothing pushed.**

## Pre-deploy corrections — headline consistency, river colour, wording, boundary diagnosis — 2026-09-22

Post-processing and UI only; no model runs; nothing pushed.

**1. Headline consistency bug, found and fixed.** `exceeds_0p05_m` (drives the headline's "N of 4
reporting places exceed 0.05 m" count and each card's "wet" styling) was computed from
`wetted_fraction > 0` (any wet cell at all) instead of the actual published statistic,
`street_surface_p90_m > 0.05`. Fixed in `scripts/scenario_postprocess_run.py`. **40 mm now correctly
gives 2 of 4** (Ågatan 0.071 m, Skattkistans förskola 0.184 m; Tvärgatan 0.036 m and ICA car park
0.006 m do not exceed) — matches the figure given when this correction was requested.

**Every displayed number and its `impacts.json` source field**, audited:

| Displayed | Source field | Same statistic throughout? |
|---|---|---|
| Headline count ("N of 4 ... exceed 0.05 m") | `locations[].exceeds_0p05_m` (now = `street_surface_p90_m > 0.05`) | Yes |
| Headline "Highest street-surface depth" value | `locations[].street_surface_p90_m` | Yes |
| Headline "... % of footprint deeper than 0.05 m" | `locations[].wetted_fraction` | Yes (the paired published statistic) |
| Headline area figure ("Water deeper than 0.3 m covers X km²") | `summary.area_gt_0p3_km2` (street-surface basis, channel+buildings excluded) | Yes |
| Location card depth | `locations[].street_surface_p90_m` | Yes |
| Location card wetted % | `locations[].wetted_fraction` | Yes |
| Location card "peak at T h" | `locations[].time_of_max_h` (time of the reference-max cell within the footprint, NOT literally "when p90 was reached" — a percentile has no single instant; disclosed here, not elsewhere) | Reference figure, not the published depth statistic itself |
| Assumptions panel "Rain lost to the ground" mm | `summary.effective_rain_mm` | Different quantity (rainfall loss), not a depth/extent statistic |
| Assumptions panel "River inflow" m³/s | `summary.inflow.peak_m3s` | Different quantity (discharge), not a depth/extent statistic |
| `street_max_m_reference_only` | kept in `impacts.json`, **not displayed anywhere on the page** | N/A |

**2. River layer colour.** Changed from a mid-blue (`rgb(60,130,200)`, too close to the ramp's own
0.10-0.30 m class) to the site's own brand teal (`rgb(8,126,131)`), with a darker teal outline
(`rgb(4,61,64)`) painted on the river's own edge cells for a visible thin border. Legend swatch
updated to match (`web/scenarios/app.js`). Verified in the 100 mm screenshot: the river is now a
clearly distinct teal line running through the dark-navy >0.5 m class, not confusable with it.

**3. Wording.** `web/scenarios/app.js`: cards now read "90th-percentile depth X m · Y% of footprint
deeper than 0.05 m" (was "90th percentile X m over Y% of its footprint") and "peak at T h" (was "max
at T h"); the headline uses the identical phrasing.

**4. Straight flood-boundary diagnosis — read-only, DEM unchanged.**
`scripts/scenario_boundary_diagnosis.py`. Region: street-surface depth > 0.5 m (same basis as the
published `area_gt_0p5_km2`), south of the river's local alignment (per-column nearest burned-
channel row) and west of the confluence (EPSG:3006 x < 416583), channel+buildings excluded.
Straight-run detection: a tolerance-band line-follow along the boundary ring (perpendicular
deviation <= 5 m / one cell) — needed because at 5 m resolution a genuinely straight DIAGONAL
feature rasterises into an alternating-step staircase that is never collinear edge-to-edge; an
earlier, simpler collinearity test found nothing for exactly this reason and was replaced.

| Storm | Qualifying region | Straight runs > 100 m |
|---|---|---|
| 70 mm | 0.075 km² (3,008 cells) | **0** |
| 100 mm | 0.168 km² (6,732 cells) | **1** — 101 m, midpoint (415665, 6190188) |

**The one 100 mm segment: classified "possible artefact."** Nearest OSM road is Ågatan (service,
way 1122597108) at 18 m — within the 20 m search radius — but the **crest-height check does not
confirm a barrier**: the sampled "dry" side is **-2.29 m relative to the flooded water surface**
(i.e. lower, not higher), so proximity to a road alone was not accepted as confirmation (the
classifier requires a positive crest height in addition to road proximity, added after this exact
case first came back as a false "physical" match on proximity alone). No raised building, no burned-
channel mask, and not at the domain edge nearby either. **Railway data was never fetched for this
project's OSM extract** (`scripts/fetch_geography.py` only queries `highway`/`waterway`), so a
railway-embankment explanation cannot be ruled out at this location — flagged, not assumed absent.
**Per instruction: reported here, DEM not changed, and no further automated fix attempted.**

Full detail: `data/scenario/derived/boundary_diagnosis.json`.

**Rebuilt and re-screenshotted** (same camera position, `reset view`, no movement between
captures): `docs/release_screenshots/scenario_{40,70,100}mm.png`, replacing the previous set.
Browser test (external requests blocked): only the deliberately blocked Esri elevation request in
the console; no horizontal overflow at phone width. **Nothing pushed.**

## Perpendicular profile diagnosis of the 101 m segment — 2026-09-22 — CLASSIFICATION: B

Read-only, per the project lead's fixed classification rule, applied mechanically (no re-judgement).
No DEM change, no model run. Script: `scripts/scenario_boundary_profile_diagnosis.py`. Segment: the
one 100 mm "possible artefact" straight run from the previous diagnosis, EPSG:3006 (415715,6190195)
to (415615,6190180), midpoint (415665,6190188). Seven profiles at ~20 m intervals along the 101 m
segment (t=0,20,40,60,80,100,101), each spanning -30 m to +30 m perpendicular to the segment at 1 m
steps, sampled from both the CONDITIONED model DEM (the grid the 100 mm solver actually used) and
the UNCONDITIONED raw DTM.

| t (m along segment) | Max WSE, flooded side | Crest found? | Crest elevation (conditioned) | Crest cell type | Dry-side unconditioned ground |
|---|---|---|---|---|---|
| 0 | 74.932 m | **No** | 73.980 m (below WSE) | n/a | 72.023 m |
| 20 | 74.927 m | **No** | 73.930 m (below WSE) | n/a | 72.021 m |
| 40 | 74.923 m | **No** | 73.960 m (below WSE) | n/a | 72.484 m |
| 60 | 74.917 m | **No** | 73.970 m (below WSE) | n/a | 73.816 m |
| 80 | 74.914 m | **No** | 74.460 m (below WSE) | n/a | 73.896 m |
| 100 | 74.911 m | **Yes** | 83.890 m | **building-raised** | 73.743 m |
| 101 | 74.911 m | **Yes** | 83.890 m | **building-raised** | 73.743 m |

**Overall classification: B — diagnosis sampling error.** At 5 of 7 stations (t=0-80) no cell in the
±30 m conditioned-DEM profile rises above the flooded-side water surface at all — there is no
"crest" to classify. Only at the segment's downstream end (t=100/101) does the profile cross a
genuine barrier: conditioned z=83.89 m vs unconditioned z=73.885 m — exactly the +10 m building
raise, correctly typed `building-raised`.

**The sampling fault, identified:** the perpendicular direction used at every station is the single
normal of the overall 101 m chord, computed once and reused. But the straight-run detector that
found this segment (`scripts/scenario_boundary_diagnosis.py`) accepts up to a 5 m (one-cell)
perpendicular wobble from that chord as still "straight" — i.e. the TRUE local raster boundary
staircases within a band around the chord, and its local direction is not guaranteed to match the
chord's average direction at every station. A perpendicular cast computed from the chord can
therefore run close to parallel with the true LOCAL edge at intermediate stations instead of
cleanly crossing from wet to dry, which is consistent with what was found: t=0-80 show a slowly
falling "max WSE, flooded side" (74.932 -> 74.914 m, a gentle gradient along the segment, not a
discrete pond) and no crest, while only the segment's actual end (t=100/101, where the chord
happens to terminate directly at a building row) shows a clean crossing. **This reads as the
straight-run detector having found the edge of a broad, gently-sloping wet area next to a row of
buildings, not a "wall" spanning the whole 101 m** — the wall is real only at one end of the
detected chord.

**Not classification C.** No profile's crest is burned-channel or culvert-cut; the culvert-cut mask
(from the two applied cuts, §4 of the release batch) does not intersect any profile at this
location (both applied cuts are 1,000+ m away). Per instruction, since the outcome is B (not C):
site rebuilt, browser-tested, and the release marked as a candidate in `docs/RELEASE_REPORT.md`
(below) — no further automated correction attempted.

**Assumptions panel and this file, both updated per instruction:** "Buildings are represented as
impermeable blocks raised 10 m above the ground. At the 5 m model resolution, gaps between
buildings narrower than one cell are closed, so rows of buildings can block flow more than they do
in reality, and water can pond against them." (`web/scenarios/app.js`, "Buildings" row.)

Full per-offset data: `data/scenario/derived/boundary_profile_diagnosis.json`.