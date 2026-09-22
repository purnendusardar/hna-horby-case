"""Compute a wet-antecedent baseflow figure from the HEÅKRA observed
discharge already fetched by scripts/scenario_fetch_observed_discharge.py
— deliberately NOT the flood-inclusive monthly mean (see ASSUMPTIONS.md:
"don't use the monthly mean, it contains the event").

Method: the day (or median of a run of days) immediately before each
event's onset, identified by inspection of the daily series printed below
(not a fixed calendar window assumed in advance — Nov's event starts on a
different day-of-month than Jan's).

Nov 2023: flow is flat/declining through 15 Nov (3.65 m3/s), then jumps on
16 Nov (11.1) ahead of the reported 17-19 Nov flood — 16 Nov is already
event onset, not pre-event. Two candidate pre-event figures: the single
last-clean day (15 Nov), and median(1-15 Nov) (more robust to one noisy
day, still entirely before onset).

Jan 2024: days 1-3 are elevated (9.9/10.8/7.65) but this is the recession
tail of a DIFFERENT, earlier event, not the buildup to the 22-27 Jan flood
seen later in the month — flow drops and stabilises 4-20 Jan before that
second event's onset on 21-22 Jan (4.74 -> 10.0 already rising). So Jan's
"median of the first half of the month" (1-15, matching Nov's instruction
literally) still includes 3 contaminated days from the unrelated first
event; a stricter stable-window median (4-20 Jan, i.e. after the first
recession and before the second event's onset) excludes them. Both are
reported; the stricter window is recommended.

The 4-20 Jan window's end is checked programmatically against the rising
limb (not just asserted by eye): a day counts as the rise's onset only if
it is a new running maximum relative to the whole window so far (filters
out ordinary day-to-day noise within the stable range). If the window's
last day is itself such a breakout, or the day after it isn't, the window
end is walked backward and the median is recomputed — see
check_window_ends_before_rise().
"""
import json
import pathlib
import statistics

root = pathlib.Path(__file__).resolve().parents[1]


def load():
    path = root / "web/data/scenario_observed_discharge_heakra.json"
    return json.loads(path.read_text(encoding="utf-8"))


def by_day(records):
    return {int(r["date"][-2:]): r["m3s"] for r in records}


def date_for_day(records, day):
    return next(r["date"] for r in records if int(r["date"][-2:]) == day)


def find_peak(day_values, day_range):
    peak_day = max(day_range, key=lambda d: day_values[d])
    return peak_day, day_values[peak_day]


def check_window_ends_before_rise(day_values, window_start, window_end):
    """Confirm `window_end` sits before the rising limb.

    A plain day-over-day ratio threshold is too blunt for this series: the
    "stable" 4-20 Jan window itself contains ~30-50% single-day wiggles
    (e.g. day 13 2.67 -> day 14 4.1) that are noise, not flood buildup, so
    a fixed ratio flags them as false rises. Instead: a day counts as the
    start of the rising limb only if it is a NEW RUNNING MAXIMUM relative
    to every day in the window so far (from window_start up to the day
    before it) — a genuine breakout above the whole stable range, not a
    wiggle within it.

    window_end is valid if (a) it is NOT itself such a breakout (the
    window's own last day still sits inside the established range) and
    (b) the very next day IS one (the true onset immediately follows).
    If invalid, window_end is walked backward one day at a time and
    retried — the window is moved, not silently kept. Returns
    (final_window_end, moved: bool, log: list[str]).
    """
    log = []
    end = window_end
    while end > window_start:
        history_max_at_end = max(day_values[d] for d in range(window_start, end))
        end_is_breakout = day_values[end] > history_max_at_end
        if end_is_breakout:
            log.append(f"  Day {end} ({day_values[end]} m3/s) is itself a new high above the "
                       f"{window_start}-{end - 1} range (max {history_max_at_end} m3/s) — window end is "
                       f"already on the rise, moving back.")
            end -= 1
            continue
        history_max_through_end = max(day_values[d] for d in range(window_start, end + 1))
        next_day = end + 1
        next_is_breakout = next_day in day_values and day_values[next_day] > history_max_through_end
        if next_is_breakout:
            log.append(f"  Day {end} ({day_values[end]} m3/s) stays within the {window_start}-{end} range "
                       f"(max {history_max_through_end} m3/s); day {next_day} ({day_values[next_day]} m3/s) "
                       f"breaks above it for the first time — confirmed rising-limb onset at day {next_day}. "
                       f"Window ending at day {end} is before the rise.")
            return end, end != window_end, log
        log.append(f"  Day {end} ({day_values[end]} m3/s) stays within range, but day {next_day} "
                   f"({day_values.get(next_day)} m3/s) is not yet a breakout above it either — window end "
                   f"does not clearly precede the rise here, moving back.")
        end -= 1
    raise RuntimeError(f"Could not find a window end after day {window_start} that precedes a confirmed rising limb.")


def main():
    data = load()
    nov = by_day(data["nov_2023_records"])
    jan = by_day(data["jan_2024_records"])

    print("=== November 2023 ===")
    print("Daily series, day 1-20:", [nov[d] for d in range(1, 21)])
    nov_peak_day, nov_peak_val = find_peak(nov, range(1, 31))
    nov_peak_date = date_for_day(data["nov_2023_records"], nov_peak_day)
    print(f"Event: 17-19 Nov (reported). Peak: {nov_peak_val} m3/s on {nov_peak_date} (day {nov_peak_day}).")
    nov_med_1_15 = statistics.median(nov[d] for d in range(1, 16))
    print(f"Day 15 (last clean pre-event day): {nov[15]} m3/s")
    print(f"Day 16 (already rising — event onset, NOT pre-event): {nov[16]} m3/s")
    print(f"Median(1-15 Nov): {nov_med_1_15} m3/s")
    print(f"Monthly mean (CONTEXT ONLY — includes the flood peak): {data['nov_2023_mean_m3s']} m3/s")
    print(f"RECOMMENDED wet-antecedent baseflow for Nov 2023: median(1-15 Nov) = {nov_med_1_15} m3/s")

    print()
    print("=== January 2024 ===")
    print("Daily series, day 1-31:", [jan[d] for d in range(1, 32)])
    jan_peak_day, jan_peak_val = find_peak(jan, range(16, 32))
    jan_peak_date = date_for_day(data["jan_2024_records"], jan_peak_day)
    print(f"Event: 22-27 Jan (reported); days 1-3 are a DIFFERENT event's recession tail. "
          f"Peak: {jan_peak_val} m3/s on {jan_peak_date} (day {jan_peak_day}).")

    print()
    print("Window check — does the 4-20 Jan stable window end before the rising limb?")
    confirmed_end, moved, log = check_window_ends_before_rise(jan, window_start=4, window_end=20)
    for line in log:
        print(line)
    if not moved:
        print(f"CONFIRMED: window 4-{confirmed_end} Jan ends before the rising limb — no shift needed.")
    else:
        print(f"*** Window end MOVED from day 20 to day {confirmed_end} to clear the rising limb. ***")

    jan_med_1_15 = statistics.median(jan[d] for d in range(1, 16))
    jan_med_4_20 = statistics.median(jan[d] for d in range(4, confirmed_end + 1))
    print(f"Day {confirmed_end} (last clean pre-event day): {jan[confirmed_end]} m3/s")
    print(f"Day {confirmed_end + 1} (already rising — event onset, NOT pre-event): {jan[confirmed_end + 1]} m3/s")
    print(f"Median(1-15 Jan) [literal mirror of Nov's window]: {jan_med_1_15} m3/s "
          f"(includes days 1-3, contaminated by the unrelated earlier recession)")
    print(f"Median(4-{confirmed_end} Jan) [stable window, excludes the unrelated earlier recession and "
          f"this event's onset]: {jan_med_4_20} m3/s")
    print(f"Monthly mean (CONTEXT ONLY — includes the flood peak): {data['jan_2024_mean_m3s']} m3/s")
    print(f"RECOMMENDED wet-antecedent baseflow for Jan 2024: median(4-{confirmed_end} Jan) = {jan_med_4_20} m3/s")

    print()
    print("=== Event peaks (for comparison alongside the Nov flood) ===")
    print(f"November 2023 peak: {nov_peak_val} m3/s on {nov_peak_date}")
    print(f"January 2024 peak:  {jan_peak_val} m3/s on {jan_peak_date}")


if __name__ == "__main__":
    main()
