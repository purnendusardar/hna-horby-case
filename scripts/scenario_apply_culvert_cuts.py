"""Union the missing-culvert candidates from a set of runs, apply the proposed cut only where a
mapped OSM waterway lies within 25 m (5 cells) of the sill (evidence of a real watercourse crossing
the embankment), and record every applied/rejected candidate with the reason.

25 m is a project-defined tolerance (release-batch instructions, 2026-09-22), not a literature
value. With --apply, edits the 1 m conditioned DEM state saved by scripts/scenario_prep_dem.py and
re-runs its own aggregation (to_model_grid) to regenerate the 5 m AOI/core conditioned rasters —
so a confirmed cut survives resampling exactly like the original channel/building conditioning does.

Runs in the data-prep venv, after scripts/scenario_prep_dem.py (needs its saved 1 m state) and after
the target runs have been mapped (artefact_candidates.json + the matching
proposed_corrections_UNAPPLIED.geojson from scripts/scenario_map_maxdepth.py):
    .venv\\Scripts\\python.exe scripts\\scenario_apply_culvert_cuts.py [--apply] [--cell 5] [--runs r1 r2 r3]
Without --apply, only reports what WOULD be cut (dry run) — the DEM is untouched.
Default --runs is the three free-outflow speed-probe-era runs (first pass, 2026-09-22 morning);
pass --runs explicitly for a second pass (e.g. on the final_aoi_5m_<mm>mm runs) so a re-derive step
only flags genuinely NEW candidates against the decisions already on record.
"""
import argparse
import json
import math
import os
import pathlib
import sys

for _v in ("GDAL_DATA", "PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_v, None)

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scenario_prep_dem as prep  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER = ROOT / "data/scenario/derived"
DEFAULT_RUNS = ["scen_aoi_5m_70mm_freeout", "scen_aoi_5m_40mm_freeout", "scen_aoi_5m_100mm_freeout"]
WATERWAY_DIST_TOLERANCE_M = 25.0
DEDUPE_DIST_M = 15.0  # candidates from different storms whose sills are this close are treated as the same feature


def load_candidates(runs):
    all_c = []
    for r in runs:
        p = ROOT / "model/outputs" / r / "artefact_candidates.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf8"))
        for i, c in enumerate(d["candidates"], 1):
            c["source_run"] = r
            c["_candidate_index_in_run"] = i
            all_c.append(c)
    return all_c


def dedupe(cands):
    groups = []
    for c in sorted(cands, key=lambda c: -c["area_m2"]):
        sx, sy = c["sill_epsg3006"]
        for g in groups:
            gx, gy = g[0]["sill_epsg3006"]
            if math.hypot(sx - gx, sy - gy) <= DEDUPE_DIST_M:
                g.append(c)
                break
        else:
            groups.append([c])
    return groups


def apply_cut(cond, tf1, cand):
    """Carve the proposed correction path into the 1 m conditioned array, in place. The stored
    path (from scripts/scenario_map_maxdepth.py) has only a handful of vertices — one per grid
    step of its own tracing loop — so it's densified to ~1 m spacing first (same technique as the
    channel burn's line_samples), or a narrow culvert would fall between grid-cell centres and
    barely change anything."""
    pc = cand["proposed_correction"]
    inv = ~tf1
    geo = json.loads((ROOT / "model/outputs" / cand["source_run"] / "proposed_corrections_UNAPPLIED.geojson").read_text(encoding="utf8"))
    feat = next(f for f in geo["features"] if f["properties"]["candidate"] == cand["_candidate_index_in_run"])
    pts = prep.line_samples(feat["geometry"]["coordinates"], step=0.5)
    half = pc["width_m"] / 2.0
    z_here = pc["invert_elevation_m"]  # flat invert along the cut — a defensible simplification, not a claim of a surveyed profile
    changed = 0
    rr = int(math.ceil(half)) + 1
    for x, y in pts:
        c0, r0 = inv * (x, y)
        c0, r0 = int(round(c0)), int(round(r0))
        r_lo, r_hi = max(0, r0 - rr), min(cond.shape[0], r0 + rr + 1)
        c_lo, c_hi = max(0, c0 - rr), min(cond.shape[1], c0 + rr + 1)
        cc, rw = np.meshgrid(np.arange(c_lo, c_hi), np.arange(r_lo, r_hi))
        cx, cy = tf1 * (cc + 0.5, rw + 0.5)
        d = np.hypot(cx - x, cy - y)
        sub = cond[r_lo:r_hi, c_lo:c_hi]
        m = (d <= half) & (z_here < sub)
        sub[m] = z_here
        changed += int(m.sum())
    return changed


def decide(runs):
    all_c = load_candidates(runs)
    groups = dedupe(all_c)
    decisions = []
    for g in groups:
        best = max(g, key=lambda c: c["area_m2"])
        nearest = min((c["nearest_waterway"]["distance_m"] for c in g if c.get("nearest_waterway")), default=None)
        applied = nearest is not None and nearest <= WATERWAY_DIST_TOLERANCE_M
        decisions.append(dict(
            sill_epsg3006=best["sill_epsg3006"], seen_in_runs=sorted({c["source_run"] for c in g}),
            max_area_m2=best["area_m2"], max_depth_m=max(c["max_depth_m"] for c in g),
            nearest_waterway_distance_m=nearest, nearest_waterway=best.get("nearest_waterway"),
            decision="APPLIED" if applied else "REJECTED (genuine depression)",
            reason=(f"mapped waterway {nearest:.0f} m from the sill, <= {WATERWAY_DIST_TOLERANCE_M:g} m tolerance -> real watercourse crossing"
                    if applied else
                    (f"nearest mapped waterway {nearest:.0f} m from the sill, exceeds the {WATERWAY_DIST_TOLERANCE_M:g} m tolerance -> no evidence of a crossing here"
                     if nearest is not None else "no waterway found near this candidate at all")),
            representative_candidate=best))
    return decisions


def already_applied_sills():
    p = DER / "culvert_cut_decisions.json"
    if not p.exists():
        return []
    prev = json.loads(p.read_text(encoding="utf8"))
    return [d["sill_epsg3006"] for d in prev.get("decisions", []) if d["decision"] == "APPLIED"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="edit the conditioned DEM and regenerate the 5 m rasters; default is a dry run")
    ap.add_argument("--cell", type=int, default=5)
    ap.add_argument("--runs", nargs="+", default=DEFAULT_RUNS)
    ap.add_argument("--out", default="culvert_cut_decisions.json", help="output filename under data/scenario/derived/")
    args = ap.parse_args()

    decisions = decide(args.runs)
    already = already_applied_sills()
    for d in decisions:
        d["already_applied_in_a_previous_pass"] = any(math.hypot(d["sill_epsg3006"][0] - ax, d["sill_epsg3006"][1] - ay) <= DEDUPE_DIST_M for ax, ay in already)
    new_to_apply = [d for d in decisions if d["decision"] == "APPLIED" and not d["already_applied_in_a_previous_pass"]]
    n_applied = sum(1 for d in decisions if d["decision"] == "APPLIED")

    if args.apply and new_to_apply:
        state_path = DER / "dem_1m_conditioned_state.npz"
        if not state_path.exists():
            raise SystemExit(f"{state_path} not found — run scripts/scenario_prep_dem.py first.")
        state = np.load(state_path)
        cond, burned, bmask = state["cond"].astype("float64"), state["burned"].astype(bool), state["bmask"].astype(bool)
        _, tf1, meta = prep.mosaic_clip(prep.clip_bounds())
        total_changed = 0
        for d in decisions:
            if d["decision"] == "APPLIED":  # re-apply everything already on record too, since this rewrites the 1 m state from scratch
                total_changed += apply_cut(cond, tf1, d["representative_candidate"])
        full, core = prep.domain_bounds(args.cell)
        for name, b in (("aoi", full), ("core", core)):
            arr, tf, n_ch = prep.to_model_grid(cond, burned, bmask, tf1, b, args.cell)
            prep.write_tif(DER / f"dem_rh2000_{args.cell}m_{name}_conditioned.tif", arr, tf, meta["crs"])
            prep.write_asc(DER / f"dem_rh2000_{args.cell}m_{name}_conditioned.asc", arr, tf)
        print(f"Applied {n_applied} cut(s) total ({len(new_to_apply)} new this pass), {total_changed} 1 m cells changed; regenerated {args.cell} m aoi/core conditioned rasters.")
    elif args.apply:
        print("No NEW candidates to apply (all APPLIED candidates were already on record) — DEM not touched.")

    out = dict(runs=args.runs, waterway_distance_tolerance_m=WATERWAY_DIST_TOLERANCE_M, dedupe_distance_m=DEDUPE_DIST_M,
               candidates_before_dedupe=len(load_candidates(args.runs)), candidates_after_dedupe=len(decisions),
               applied_total=n_applied, applied_new_this_pass=len(new_to_apply), rejected=len(decisions) - n_applied,
               applied_to_dem_this_pass=bool(args.apply and new_to_apply), decisions=decisions)
    (DER / args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf8")
    print(json.dumps({k: v for k, v in out.items() if k != "decisions"}, indent=1))
    for d in decisions:
        tag = " (already applied)" if d["already_applied_in_a_previous_pass"] else " (NEW)" if d["decision"] == "APPLIED" else ""
        print(d["decision"] + tag, d["sill_epsg3006"], f"{d['max_area_m2']} m2, {d['max_depth_m']} m,", d["reason"])


if __name__ == "__main__":
    main()
