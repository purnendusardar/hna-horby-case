"""Phase 1: storm shape (brief section 4.1) and default drainage capacity (4.2).

Generates a Chicago Design Storm (CDS) hyetograph for each rainfall total
(40, 70, 100 mm over 24 h, 10-minute steps, peak at r=0.4 of the storm
duration), and computes the default stormwater pipe-full capacity the brief
specifies (a 2-year rain at a 30-minute concentration time). Both derive from
this IDF formula (as specified for this project — see below):

    i(T_R, Å) = 190 * Å**(1/3) * ln(T_R) / T_R**0.98 + 2      [l/(s*ha)]

T_R = duration in minutes, Å = return period in MONTHS (not years). This
replaces an earlier, differently-shaped "commonly cited Dahlström formula"
that this script used before — that version's computed drainage capacity
(15.95 mm/h) fell outside the brief's own rough estimate of the same figure
("roughly 20-25 mm/h"); this formula's capacity output does not (see
capacity_mm_h below and scenarios.yaml). tests/test_scenario_generate_hyetographs.py
checks the implementation against the one worked example given for it
(Å=24, T_R=10 -> ~134 l/s*ha); that confirms this code matches the formula as
specified, not that the formula itself is independently verified against a
primary source (e.g. P104) — that citation is still open, see ASSUMPTIONS.md.

i(T_R, Å) is treated as the duration-averaged intensity over [0, T_R], as is
conventional for an IDF curve, so cumulative depth P(T_R) = i(T_R,Å) * T_R
(converted to mm). As T_R -> 0+, ln(T_R) -> -infinity, so P(T_R) has a genuine
removable singularity at T_R=0 (the "+2 l/s*ha" offset doesn't scale with
T_R, unlike the ln(T_R)/T_R**0.98 term, so it doesn't cancel the limit by
itself, but x**epsilon * ln(x) -> 0 as x -> 0+ still makes the T_R*i(T_R)
product -> 0). P(0) is set to 0 directly below rather than evaluated, since
the formula itself is undefined at T_R=0 (ln(0)).

Storm-shape return period: the brief specifies fixed rainfall TOTALS (40/70/
100 mm), not a return period for the design storm itself. This formula's
"+2" offset is not proportional to Å, so — unlike the previous formula, where
Å cancelled out entirely once rescaled to a fixed total — the choice of Å
here has a small effect on the final (rescaled) hyetograph's shape, mostly at
the low-intensity tail blocks. Å=24 months (2 years) is used, matching the
network capacity reference below; this is a recorded assumption
(scenarios.yaml -> storm.shape_return_period_months), not a brief requirement.

Storm-shape method: the brief calls for a Chicago Design Storm, but the
classic closed-form Chicago hyetograph (Keifer & Chu 1957) needs an IDF of
the form i = a/(t+b)**c with b != 0 to avoid a singularity at the peak; this
formula's ln(T_R) term has that same T_R=0 singularity (see above). This
script uses the discretised alternating block method instead (10-minute
minimum block, so the singularity is never evaluated), which is the standard
practical substitute and produces the same "single peak at a chosen fraction
of the storm duration, IDF-shaped falloff either side" result the brief asks
for. Recorded here, not just in a comment, because it's a real deviation from
"Chicago Design Storm" read literally.

Every number below is also written to scenarios.yaml, not just printed here.
"""
import csv
import math
import pathlib

root = pathlib.Path(__file__).resolve().parents[1]

DURATION_MIN = 24 * 60
BLOCK_MIN = 10
N_BLOCKS = DURATION_MIN // BLOCK_MIN
PEAK_R = 0.4
TOTALS_MM = [40, 70, 100]

CAPACITY_RETURN_PERIOD_MONTHS = 24  # 2 years, matching the brief's P110 default (section 4.2)
CAPACITY_CONCENTRATION_TIME_MIN = 30
STORM_SHAPE_RETURN_PERIOD_MONTHS = 24  # assumption, not a brief value — see module docstring
LPS_HA_TO_MM_PER_H = 0.36
CAPACITY_EXPECTED_RANGE_MM_H = (20, 25)  # brief section 4.2's own rough estimate


def dahlstrom_intensity_lps_ha(duration_min, return_period_months):
    """i(T_R, Å) = 190 * Å**(1/3) * ln(T_R) / T_R**0.98 + 2, per this project's spec.

    duration_min (T_R) must be > 0 — ln(0) is undefined; there is no rain
    below the discretisation's 10-minute block, so callers never need T_R<=0.
    """
    return 190 * return_period_months ** (1 / 3) * math.log(duration_min) / duration_min ** 0.98 + 2


def cumulative_depth_mm(duration_min, return_period_months):
    """Cumulative depth at a given duration, treating the IDF value as a duration-average intensity."""
    if duration_min <= 0:
        return 0.0  # limit as T_R -> 0+ of T_R * i(T_R, Å); the formula itself is undefined at T_R=0.
    intensity_mm_h = dahlstrom_intensity_lps_ha(duration_min, return_period_months) * LPS_HA_TO_MM_PER_H
    return intensity_mm_h * duration_min / 60


def alternating_block_hyetograph(total_mm):
    # Unscaled per-block depths from the IDF-derived cumulative curve (tallest block = shortest duration = most intense).
    shape_depths = [
        cumulative_depth_mm(n * BLOCK_MIN, STORM_SHAPE_RETURN_PERIOD_MONTHS)
        - cumulative_depth_mm((n - 1) * BLOCK_MIN, STORM_SHAPE_RETURN_PERIOD_MONTHS)
        for n in range(1, N_BLOCKS + 1)
    ]
    scale = total_mm / cumulative_depth_mm(DURATION_MIN, STORM_SHAPE_RETURN_PERIOD_MONTHS)
    ranked = sorted(shape_depths, reverse=True)

    peak_index = round(PEAK_R * N_BLOCKS)  # 1-indexed block position of the storm peak
    slots = [None] * (N_BLOCKS + 1)  # 1-indexed
    slots[peak_index] = ranked[0]
    before, after = peak_index - 1, peak_index + 1
    for depth in ranked[1:]:
        if after <= N_BLOCKS and (before < 1 or after - peak_index <= peak_index - before):
            slots[after] = depth
            after += 1
        elif before >= 1:
            slots[before] = depth
            before -= 1
        else:
            slots[after] = depth
            after += 1

    return [round(slots[n] * scale, 4) for n in range(1, N_BLOCKS + 1)]


def write_hyetograph(total_mm, block_depths_mm):
    out_dir = root / "docs/hyetographs"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"hyetograph_{total_mm}mm.csv"
    cumulative = 0.0
    rows = []
    for n, depth_mm in enumerate(block_depths_mm, start=1):
        cumulative += depth_mm
        rows.append({
            "block": n,
            "t_start_min": (n - 1) * BLOCK_MIN,
            "t_end_min": n * BLOCK_MIN,
            "block_depth_mm": depth_mm,
            "intensity_mm_per_h": round(depth_mm * (60 / BLOCK_MIN), 3),
            "cumulative_mm": round(cumulative, 4),
        })
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    peak_block = max(range(len(block_depths_mm)), key=lambda i: block_depths_mm[i])
    peak_intensity = block_depths_mm[peak_block] * (60 / BLOCK_MIN)
    max_depth = max(block_depths_mm)
    W, H, pad, base = 900, 220, 40, 190
    scale_y = (base - 20) / max_depth
    step_x = (W - pad - 10) / N_BLOCKS
    bars = "".join(
        f'<rect x="{pad + i * step_x:.1f}" y="{base - d * scale_y:.1f}" width="{max(step_x - 0.6, 0.4):.1f}" '
        f'height="{d * scale_y:.1f}" fill="{"#d95141" if i == peak_block else "#168c96"}"/>'
        for i, d in enumerate(block_depths_mm)
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Chicago design storm hyetograph, {total_mm} mm total over 24 h, '
        f'peak at r={PEAK_R} ({(n:=(peak_block+1)*BLOCK_MIN)//60}h{n%60:02d}m into the storm), '
        f'10-minute blocks, alternating-block method from a Dahlstrom IDF shape.">'
        f'<rect width="{W}" height="{H}" fill="white"/>'
        f'<line x1="{pad}" x2="{W-10}" y1="{base}" y2="{base}" stroke="#cbdce3"/>'
        f'{bars}'
        f'<text x="0" y="30" font-size="13" fill="#133849">{total_mm} mm CDS hyetograph &#183; 10-min blocks &#183; peak r={PEAK_R}</text>'
        f'<text x="0" y="48" font-size="11" fill="#536f7d">Peak block {peak_block+1} &#183; {peak_intensity:.1f} mm/h &#183; '
        f'shape from i(T_R,Å)=190*Å^(1/3)*ln(T_R)/T_R^0.98+2, Å={STORM_SHAPE_RETURN_PERIOD_MONTHS}mo, alternating-block placement</text>'
        f'</svg>'
    )
    (out_dir / f"hyetograph_{total_mm}mm.svg").write_text(svg, encoding="utf-8")
    return {"peak_block": peak_block + 1, "peak_intensity_mm_h": round(peak_intensity, 2),
            "total_mm_check": round(cumulative, 3)}


def main():
    capacity_lps_ha = dahlstrom_intensity_lps_ha(CAPACITY_CONCENTRATION_TIME_MIN, CAPACITY_RETURN_PERIOD_MONTHS)
    capacity_mm_h = round(capacity_lps_ha * LPS_HA_TO_MM_PER_H, 2)
    lo, hi = CAPACITY_EXPECTED_RANGE_MM_H
    in_range = lo <= capacity_mm_h <= hi
    print(f"Default drainage capacity (Å={CAPACITY_RETURN_PERIOD_MONTHS}mo, "
          f"T_R={CAPACITY_CONCENTRATION_TIME_MIN}min): {capacity_lps_ha:.2f} l/s*ha = {capacity_mm_h} mm/h")
    if in_range:
        print(f"Within the brief's own rough estimate ({lo}-{hi} mm/h) — mismatch flag cleared.")
    else:
        print(f"NOTE: brief section 4.2 estimates 'roughly {lo}-{hi} mm/h' for this; computed {capacity_mm_h} mm/h "
              f"does not fall in that range. Verify the formula before trusting either number.")

    summary = {}
    for total_mm in TOTALS_MM:
        depths = alternating_block_hyetograph(total_mm)
        summary[total_mm] = write_hyetograph(total_mm, depths)
        print(f"{total_mm} mm storm: peak block {summary[total_mm]['peak_block']} "
              f"({(summary[total_mm]['peak_block']-1)*BLOCK_MIN} min), "
              f"peak intensity {summary[total_mm]['peak_intensity_mm_h']} mm/h, "
              f"total check {summary[total_mm]['total_mm_check']} mm")
    return capacity_mm_h, summary


if __name__ == "__main__":
    main()
