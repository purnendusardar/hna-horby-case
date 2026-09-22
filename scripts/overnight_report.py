"""Regenerate docs/OVERNIGHT_REPORT.md from docs/overnight_static.md plus the per-run output files.

Stdlib only:  python scripts/overnight_report.py
Layout: (1) generated header and run-status table, (2) the hand-written static part (blockers and decisions first),
(3) per-run detail (criteria, impacts, artefact candidates). Called by the overnight watcher after every finished run.
Both docs/overnight_static.md and docs/OVERNIGHT_REPORT.md are internal and excluded from the public build.
"""
import datetime
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = [  # (run, storm, results key, status file, label)
    ("pilot_aoi_5m_70mm", 70, "70mm", None, "70 mm, closed boundary (pilot = production run)"),
    ("scen_aoi_5m_40mm", 40, "40mm", "queue_status.txt", "40 mm, closed boundary"),
    ("scen_aoi_5m_100mm", 100, "100mm", "queue_status.txt", "100 mm, closed boundary"),
    ("scen_aoi_5m_70mm_freeout", 70, "freeout_70mm", "queue_status_freeout.txt", "70 mm, free west outflow (supplementary)"),
    ("scen_aoi_5m_40mm_freeout", 40, "freeout_40mm", "queue_status_freeout.txt", "40 mm, free west outflow (supplementary)"),
    ("scen_aoi_5m_100mm_freeout", 100, "freeout_100mm", "queue_status_freeout.txt", "100 mm, free west outflow (supplementary)"),
]


def status_of(run, status_file):
    if status_file is None:
        return "completed (pilot)", None
    p = ROOT / "model" / status_file
    txt = p.read_text(encoding="utf8", errors="ignore") if p.exists() else ""
    lines = [l for l in txt.splitlines() if run in l]
    ok = [l for l in lines if " OK " in l]
    if ok:
        m = re.search(r"attempt (\d) OK rc=\d+ wall_s=(\d+)", ok[-1])
        return f"completed (attempt {m.group(1)})", int(m.group(2))
    failed = [l for l in lines if "FAILED" in l]
    if len(failed) >= 2:
        return "FAILED twice (see model/" + status_file + ")", None
    if lines:
        return ("running (retrying after one failure)" if failed else "running"), None
    return "queued", None


def jload(p):
    try:
        return json.loads(p.read_text(encoding="utf8"))
    except Exception:
        return None


def record_in_assumptions(run, label, stats, crit, wall):
    """Append one idempotent run record to ASSUMPTIONS.md (wall-clock, timesteps, volume error, criteria)."""
    p = ROOT / "ASSUMPTIONS.md"
    txt = p.read_text(encoding="utf8")
    marker = f"### Run record - `{run}`"
    if marker in txt:
        return
    if "## Run records (overnight queue)" not in txt:
        txt += "\n\n## Run records (overnight queue)\n\nWritten automatically by `scripts/overnight_report.py` after each finished run. Thresholds (1 % volume error, criteria C1-C7) are project-defined tolerances, not literature values.\n"
    failed = [k for k, v in crit.items() if not v["passed"]]
    txt += (f"\n{marker} ({label})\n\n"
            f"- Recorded {datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}. Wall-clock {wall if wall else stats.get('wall_s_incl_staging')} s (incl. staging), compute {stats['compute_min']} min.\n"
            f"- Timestep: min {stats['min_timestep_s']} s (first reached at t = {stats['time_min_timestep_first_reached_s']:.0f} s; LISFLOOD-FP reports the time only, not the cell), mean {stats['mean_timestep_s']} s over {stats['n_timesteps']:,} steps.\n"
            f"- Cumulative volume error: independent closure {stats['independent_closure_error_m3']} m3 = {stats['closure_error_pct_of_total_inflow']} % of total inflow {stats['total_inflow_volume_m3']:,} m3 "
            f"(outflow {stats.get('outflow_volume_m3', 0):,} m3); solver last-row Verror {stats['last_row_Verror_m3']} m3. "
            f"{'Within the 1 % tolerance.' if stats['closure_error_pct_of_total_inflow'] <= 1 and stats['Verror_pct_of_total_inflow'] <= 1 else 'EXCEEDS the 1 % tolerance: FAILED RUN.'}\n"
            f"- Criteria: {len(crit) - len(failed)}/{len(crit)} pass" + (f"; failed: {', '.join(failed)}" if failed else "") + ". Boundary: " + stats['outflow_boundary'] + ".\n")
    p.write_text(txt, encoding="utf8")


def main():
    now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    static = (ROOT / "docs/overnight_static.md").read_text(encoding="utf8") if (ROOT / "docs/overnight_static.md").exists() else "(static part missing)\n"
    rows, detail = [], []
    for run, storm, key, sf, label in RUNS:
        st, wall = status_of(run, sf)
        od = ROOT / "model/outputs" / run
        stats, crit, cands = jload(od / "run_stats.json"), jload(od / "criteria.json"), jload(od / "artefact_candidates.json")
        if stats:
            npass = sum(1 for v in crit.values() if v["passed"]) if crit else 0
            if sf is not None and st.startswith("completed"):
                record_in_assumptions(run, label, stats, crit, wall)
            rows.append(f"| {label} | {st} | {(wall or stats.get('wall_s_incl_staging') or 0):.0f} s | {stats['compute_min']} min | {stats['min_timestep_s']} / {stats['mean_timestep_s']} s | "
                        f"{stats['closure_error_pct_of_total_inflow']} % | {npass}/{len(crit)} |")
            d = [f"### {label}  (`{run}`)", "", f"- Status: {st}. Outflow boundary: {stats['outflow_boundary']}.",
                 f"- Min timestep {stats['min_timestep_s']} s first reached at t = {stats['time_min_timestep_first_reached_s']:.0f} s "
                 f"(the solver reports the time only, not the cell); mean {stats['mean_timestep_s']} s over {stats['n_timesteps']:,} steps.",
                 f"- Volume: inflow + rain {stats['total_inflow_volume_m3']:,} m3; outflow {stats.get('outflow_volume_m3', 0):,} m3; independent closure error "
                 f"{stats['independent_closure_error_m3']} m3 ({stats['closure_error_pct_of_total_inflow']} %); LISFLOOD last-row Verror {stats['last_row_Verror_m3']} m3 "
                 f"({stats['Verror_pct_of_total_inflow']} %). Threshold 1 % of total inflow (project-defined): "
                 f"{'within' if stats['closure_error_pct_of_total_inflow'] <= 1 and stats['Verror_pct_of_total_inflow'] <= 1 else 'EXCEEDED - failed run'}.",
                 f"- Intermediate max-depth grids: {stats['intermediate_max_grids']}.", "", "| Criterion | Result | Value |", "|---|---|---|"]
            d += [f"| {k} | {'pass' if v['passed'] else '**FAIL**'} | {v['value']} |" for k, v in crit.items()]
            imp = jload(ROOT / "web/data/results" / key / "impacts.json")
            if imp:
                d += ["", "| Reporting location | Max depth | Time of max | > 0.05 m |", "|---|---|---|---|"]
                d += [f"| {l['location']} | {l.get('max_depth_m', 'n/a')} m | {l.get('time_of_max_h', 'n/a')} h | {l.get('exceeds_0p05_m', 'n/a')} |" for l in imp["locations"]]
            if cands:
                d += ["", f"Missing-culvert candidates (depth > 0.3 m, downstream edge on a road embankment): **{cands['candidates_found']}** "
                      f"(of {cands['ponds_over_threshold_and_min_cells']} ponds); wet area > 0.3 m {cands['area_gt_0p3_km2']} km2. Proposed cuts are UNAPPLIED in "
                      f"`model/outputs/{run}/proposed_corrections_UNAPPLIED.geojson`.", "",
                      "| # | Deepest cell (EPSG:3006) | Sill (EPSG:3006) | Area m2 | Max depth m | Road at sill | Nearest waterway | Proposed cut |", "|---|---|---|---|---|---|---|---|"]
                for i, c in enumerate(cands["candidates"], 1):
                    nw = c["nearest_waterway"]
                    pc = c.get("proposed_correction", {})
                    d.append(f"| {i} | {c['deepest_cell_epsg3006']} | {c['sill_epsg3006']} | {c['area_m2']} | {c['max_depth_m']} | {'; '.join(c['roads_at_sill'][:1])} | "
                             f"{nw['type']} {nw['name'] or ''} (OSM {nw['osm_id']}, {nw['distance_m']} m) | {pc.get('width_m', '')} m wide, invert {pc.get('invert_elevation_m', '')} m, {pc.get('length_m', '')} m long |")
            detail.append("\n".join(d) + "\n")
        else:
            rows.append(f"| {label} | {st} | - | - | - | - | - |")
    out = [f"# Overnight report", "", f"Generated {now} by `scripts/overnight_report.py` (internal; not published).", "",
           static.rstrip(), "", "## Model runs: status", "",
           "| Run | Status | Wall-clock (incl. staging) | Compute | Min / mean timestep | Volume closure error | Criteria passed |", "|---|---|---|---|---|---|---|",
           *rows, "", "Wall-clock for the 70 mm pilot is the measured 2,177 s. Criteria C1-C7 and the 1 % volume tolerance are project-defined (ASSUMPTIONS.md).", "",
           "## Per-run detail", "", *detail]
    (ROOT / "docs/OVERNIGHT_REPORT.md").write_text("\n".join(out) + "\n", encoding="utf8")
    mf = [dict(key=d.parent.name, storm_mm=json.loads(d.read_text(encoding="utf8"))["storm_mm"], run=json.loads(d.read_text(encoding="utf8"))["run"])
          for d in sorted((ROOT / "web/data/results").glob("*/meta.json"))]
    (ROOT / "web/data/results/manifest.json").write_text(json.dumps(dict(scenarios=mf), indent=1), encoding="utf8")
    print("wrote docs/OVERNIGHT_REPORT.md and manifest.json", now)


if __name__ == "__main__":
    main()
