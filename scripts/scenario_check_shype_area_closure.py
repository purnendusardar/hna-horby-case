"""Close the AOI-drainage-area balance in S-HYPE's own terms, and retire
the earlier "SVAR arithmetic" subtraction (147.49 - inflow areas) as a
local-area check.

Why the SVAR subtraction is retired: scripts/scenario_compute_aoi_drainage_area.py
originally reported SVAR's own 147.49 - 139.83 = 7.66 km2 using the
UNCORRECTED inflow AREA_UPSTREAM figures (i.e. including the area each
inflow catchment shares with the AOI). Recomputed here with the CORRECTED
(outside-AOI) inflow areas from ASSUMPTIONS.md ("Inflow catchment polygons
DO overlap the AOI") instead:

    147.494 - (76.896 + 61.985) = 8.613 km2

That is LARGER than the AOI bounding box itself (7.8399 km2) — a
"local area" figure exceeding the box it is supposed to be local to is not
a coherent local-area check, so this arithmetic is retired for that
purpose. (Subtracting the corrected, smaller inflow areas from an
uncorrected, larger outflow area over-counts area that both delineations
already share near the boundary; it was never a real closure, only a
coincidence that it looked plausible with the uncorrected inputs.)

What replaces it: closing the SAME balance entirely in S-HYPE terms, using
S-HYPE's own upstreamArea for all three relevant points (SUBID 185 west
outflow, SUBID 184 and SUBID 64474 inflows) — no SVAR figures mixed in —
compared against scripts/scenario_compute_aoi_drainage_area.py's
independently-computed "AOI area draining to the outflow" (5.962 km2, a
SVAR MAINDOWN-topology walk intersected with the AOI bbox). This is a
cross-method check (S-HYPE subbasin arithmetic vs. SVAR topology + bbox
intersection), not a single-source identity, so a residual is expected
and reported rather than reconciled away.

Usage:
    python scripts/scenario_check_shype_area_closure.py
"""
import json
import pathlib

root = pathlib.Path(__file__).resolve().parents[1]

# Retired check's inputs, both in km^2 (see module docstring):
SVAR_OUTFLOW_UPSTREAM_KM2 = 147.494  # "Vid mätstation HEÅKRA" AREA_UPSTREAM
SVAR_INFLOW_CORRECTED_KM2 = {
    "Ebbamölleån": 76.896,
    "Södra armen": 61.985,
}
AOI_BBOX_KM2 = 7.8399

# Independently computed by scripts/scenario_compute_aoi_drainage_area.py
# (SVAR MAINDOWN topology walk, intersected with the AOI bbox in EPSG:3006).
AOI_DRAINAGE_AREA_KM2 = 5.962


def shype_upstream_area_km2(subid):
    path = root / f"web/data/scenario_streamflow_subid{subid}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["upstreamArea"] / 1e6


def main():
    print("=== Retired: SVAR subtraction as a local-area check ===")
    corrected_sum = sum(SVAR_INFLOW_CORRECTED_KM2.values())
    retired_figure = SVAR_OUTFLOW_UPSTREAM_KM2 - corrected_sum
    print(f"SVAR outflow upstream area (Vid mätstation HEÅKRA): {SVAR_OUTFLOW_UPSTREAM_KM2} km2")
    print(f"minus corrected (outside-AOI) inflow areas: "
          f"{' + '.join(f'{v} ({k})' for k, v in SVAR_INFLOW_CORRECTED_KM2.items())} = {corrected_sum:.3f} km2")
    print(f"= {retired_figure:.3f} km2")
    print(f"AOI bounding-box area: {AOI_BBOX_KM2} km2")
    print(f"*** RETIRED: {retired_figure:.3f} km2 > {AOI_BBOX_KM2} km2 — a 'local' area larger than the box "
          f"it should be local to is not a coherent check. Do not use this arithmetic as a local-area "
          f"cross-check going forward. ***")

    print()
    print("=== S-HYPE-terms closure (replacement) ===")
    area_185 = shype_upstream_area_km2(185)
    area_184 = shype_upstream_area_km2(184)
    area_64474 = shype_upstream_area_km2(64474)
    shype_closure = area_185 - (area_184 + area_64474)
    print(f"SUBID 185 (west outflow) S-HYPE upstreamArea: {area_185:.6f} km2")
    print(f"SUBID 184 (Ebbamölleån/east mainstem) S-HYPE upstreamArea: {area_184:.6f} km2")
    print(f"SUBID 64474 (södra armen) S-HYPE upstreamArea: {area_64474:.6f} km2")
    print(f"S-HYPE closure: {area_185:.6f} - ({area_184:.6f} + {area_64474:.6f}) = {shype_closure:.6f} km2")
    print()
    print(f"Computed AOI-draining area (SVAR MAINDOWN walk ∩ AOI bbox, "
          f"scripts/scenario_compute_aoi_drainage_area.py): {AOI_DRAINAGE_AREA_KM2} km2")
    residual = AOI_DRAINAGE_AREA_KM2 - shype_closure
    print(f"Residual (computed - S-HYPE closure): {residual:.6f} km2 "
          f"({residual / AOI_DRAINAGE_AREA_KM2 * 100:.2f}% of the computed figure)")
    print()
    print("Both figures are reported, not reconciled to agree: the S-HYPE closure is subbasin arithmetic "
          "on one delineation/vintage, while the computed figure is a topology walk on a different one "
          "(SVAR Delavrinningsområden) intersected with the AOI bbox. A residual of this size is "
          "consistent with two independent delineations, not evidence either one is wrong.")

    print()
    print("=== Re-run with crossing-based (AOI-corrected) inflow areas, 2026-09-18 ===")
    # Corrected (outside-AOI) areas taken directly from
    # scripts/scenario_correct_streamflow_for_aoi.py's current output, not
    # recomputed here, to avoid drifting from the production figures.
    corrected_184 = 79.35045166015624
    corrected_64474 = 59.366665024658204
    crossing_closure = area_185 - (corrected_184 + corrected_64474)
    residual_crossing = AOI_DRAINAGE_AREA_KM2 - crossing_closure
    print(f"SUBID 185 upstreamArea - (184 corrected {corrected_184:.4f} + 64474 corrected "
          f"{corrected_64474:.4f}) = {crossing_closure:.4f} km2")
    print(f"vs. computed {AOI_DRAINAGE_AREA_KM2} km2 -> residual {residual_crossing:.4f} km2 "
          f"({residual_crossing / AOI_DRAINAGE_AREA_KM2 * 100:.1f}%)")
    print(f"RESULT: residual does not shrink — it grows from {residual:.3f} km2 (~{residual/AOI_DRAINAGE_AREA_KM2*100:.1f}%) "
          f"to {residual_crossing:.3f} km2 (~{residual_crossing/AOI_DRAINAGE_AREA_KM2*100:.1f}%) and flips sign, "
          f"because subtracting AOI-corrected (outside-AOI-only) inflow areas from the outflow's still-"
          f"uncorrected full upstream area removes the AOI-side sliver twice — the same double-subtraction "
          f"failure mode as the retired SVAR check, just within S-HYPE's own basis this time.")


if __name__ == "__main__":
    main()
