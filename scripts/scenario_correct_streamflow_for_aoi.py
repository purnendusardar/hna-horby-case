"""Scale each inflow's own S-HYPE hydrograph down to represent only the
area OUTSIDE the model AOI — the double-counting correction from
ASSUMPTIONS.md, applied here as an actual scaling factor on the flow
series (not just recorded as a corrected area figure).

Why a scaling factor, and why on flow, not on area alone: the brief rains
on the whole 2D AOI grid AND adds these two boundary hydrographs. Each
hydrograph's catchment overlaps the AOI bbox by a real, nonzero amount. If
the unscaled hydrograph is added on top of rain-on-grid, the overlapping
land's contribution is counted twice. Scaling the whole flow series down by
(catchment_area - overlap) / catchment_area removes that double-counted
share.

ASSUMPTION being made here, stated plainly: flow scales linearly with
contributing area (a uniform specific-runoff assumption across each
catchment). This is a simplification, not a measurement — the overlapping
slice of each catchment is not necessarily hydrologically identical to the
rest of it (different soils/land cover/slope are plausible). No better
information is available without the catchment's own internal HRU
breakdown, which this project does not have. If that breakdown becomes
available, revisit this scaling.

Basis note (revised 2026-09-18 — see ASSUMPTIONS.md "Two more follow-ups,
round 3"): earlier revisions of this script used the SVAR polygon for each
named catchment intersected with the AOI bbox, mixing an SVAR-geometry
overlap with an S-HYPE-area denominator, because HydroNu's `coordinates`
field was believed to be only a local subbasin polygon. That assumption
was wrong: `coordinates` is each SUBID's own full aggregated upstream
polygon (verified against SUBID 64474, whose `subbasinArea` is 0.374 km²
but whose `coordinates` polygon has a shoelace area of 59.647 km²,
matching `upstreamArea` exactly). The overlap areas below are now each
SUBID's OWN upstream polygon intersected with the AOI bbox (EPSG:3006) —
basis-consistent throughout, no SVAR geometry involved. This is also the
crossing-based figure, not the (larger, misleading) straight-line
outlet-to-crossing distance — see
scripts/scenario_check_inflow_outlet_position.py and ASSUMPTIONS.md for
why the crossing-based area is the correct one: the outlet series
represents flow already inside the domain, so counting it unscaled would
double the area the rain-on-grid model already generates for the AOI-side
sliver.

What gets scaled: mq, mlq, mhq, and every value in chartData.coutHindcast
and chartData.coutForecast (all m^3/s, i.e. flow — scales with area).
psimHindcast/psimForecast (mm, precipitation intensity) are NOT scaled —
rainfall intensity does not change because less area is counted downstream
of it.

Usage:
    python scripts/scenario_correct_streamflow_for_aoi.py

Reads web/data/scenario_streamflow_subid{184,64474}.json (already fetched
by scripts/scenario_fetch_streamflow.py). Writes a separate
*_aoi_corrected.json next to each — two hydrographs stay two files
throughout; nothing here merges them. No parallel/versioned copies are
kept — each run overwrites the existing *_aoi_corrected.json in place;
git history is the record of prior corrections.
"""
import datetime
import json
import pathlib

root = pathlib.Path(__file__).resolve().parents[1]

# Areas in km^2. S-HYPE upstreamArea for each SUBID comes from the fetched
# response itself (read below, not hard-coded). Overlap areas are each
# SUBID's own `coordinates` upstream polygon intersected with the AOI bbox
# in EPSG:3006 — see scripts/scenario_check_inflow_outlet_position.py and
# ASSUMPTIONS.md for the exact figures and how they were computed
# (2.24809033984375 and 0.2803689753417969 km2).
INFLOWS = {
    "184": {
        "name": "Hörbyån mainstem (east edge, SVAR catchment Ebbamölleån)",
        "aoi_overlap_km2": 2.24809033984375,
    },
    "64474": {
        "name": "Southern arm (south edge, SVAR catchment 'södra armen')",
        "aoi_overlap_km2": 0.2803689753417969,
    },
}


def scale_series(series_dict, factor):
    if not series_dict or "data" not in series_dict:
        return series_dict
    return {
        **series_dict,
        "data": [[ts, v * factor if v is not None else v] for ts, v in series_dict["data"]],
    }


def main():
    for subid, info in INFLOWS.items():
        src = root / f"web/data/scenario_streamflow_subid{subid}.json"
        if not src.exists():
            raise SystemExit(f"Missing {src} — run scripts/scenario_fetch_streamflow.py {subid} first.")
        data = json.loads(src.read_text(encoding="utf-8"))

        shype_area_km2 = data["upstreamArea"] / 1e6
        overlap_km2 = info["aoi_overlap_km2"]
        corrected_area_km2 = shype_area_km2 - overlap_km2
        factor = corrected_area_km2 / shype_area_km2

        chart = data["chartData"]
        corrected = dict(data)
        corrected["chartData"] = {
            **chart,
            "mq": chart["mq"] * factor,
            "mlq": chart["mlq"] * factor,
            "mhq": chart["mhq"] * factor,
            "coutHindcast": scale_series(chart.get("coutHindcast"), factor),
            "coutForecast": scale_series(chart.get("coutForecast"), factor),
            # psimHindcast/psimForecast intentionally left unscaled — see module docstring.
        }
        corrected["_aoi_correction"] = {
            "applied_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "inflow_name": info["name"],
            "shype_upstream_area_km2": shype_area_km2,
            "aoi_overlap_km2": overlap_km2,
            "corrected_area_km2": corrected_area_km2,
            "scaling_factor": factor,
            "method": (
                "Linear area-proportional scaling (uniform specific runoff "
                "assumption). Overlap area is this SUBID's own S-HYPE "
                "upstream polygon (HydroNu 'coordinates') intersected with "
                "the AOI bbox in EPSG:3006 — basis-consistent with "
                "shype_upstream_area_km2, no SVAR geometry involved "
                "(revised 2026-09-18; see ASSUMPTIONS.md for why the "
                "earlier SVAR-polygon-based overlap was replaced). "
                "mq/mlq/mhq and every coutHindcast/coutForecast value are "
                "scaled; psimHindcast/psimForecast are not (precipitation "
                "intensity, not flow). See this script's module docstring "
                "and ASSUMPTIONS.md."
            ),
            "unscaled_source": str(src.relative_to(root)).replace("\\", "/"),
        }

        target = root / f"web/data/scenario_streamflow_subid{subid}_aoi_corrected.json"
        target.write_text(json.dumps(corrected, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"SUBID {subid} ({info['name']}):")
        print(f"  S-HYPE upstreamArea = {shype_area_km2:.3f} km2, AOI overlap = {overlap_km2:.3f} km2, "
              f"corrected = {corrected_area_km2:.3f} km2, factor = {factor:.5f}")
        print(f"  mq {chart['mq']:.4f} -> {chart['mq']*factor:.4f} m3/s")
        print(f"  Wrote {target}")


if __name__ == "__main__":
    main()
