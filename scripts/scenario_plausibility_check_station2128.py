"""Plausibility check on SMHI station 2128 (HEÅKRA) before its data feeds
anything downstream: compute the long-term mean flow and specific runoff
(l/s per km^2) from the full period of record, compare against the
November 2023 monthly mean, and flag if the ratio is implausibly high.

Also reports SMHI's own stated drainage area for the station against two
different SVAR figures — the SAME point ("Vid mätstation HEÅKRA") and the
DIFFERENT, further-downstream anchor point ("Vid mätstation Hörbyån") —
since these are two different catchments and a gap against the latter is
expected, not a data quality problem.

Usage:
    python scripts/scenario_plausibility_check_station2128.py
"""
import csv
import pathlib
import statistics
import urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
CACHE = root / "web/data/_cache/smhi_hydroobs_station2128_corrected_archive.csv"
URL = (
    "https://opendata-download-hydroobs.smhi.se/api/version/1.0/parameter/1/"
    "station/2128/period/corrected-archive/data.csv"
)

AREA_SMHI_KM2 = 146.8
AREA_SVAR_HEAKRA_KM2 = 147.494  # same point (Vid mätstation HEÅKRA)
AREA_SVAR_ANCHOR_KM2 = 151.783  # different, further-downstream point (Vid mätstation Hörbyån)
NOV_2023_MONTHLY_MEAN_M3S = 7.1713  # from scripts/scenario_fetch_observed_discharge.py's output
FLAG_RATIO_THRESHOLD = 5.0


def fetch_raw():
    if CACHE.exists():
        return CACHE.read_bytes(), True
    req = urllib.request.Request(URL, headers={"User-Agent": "aegir-research/0.1"})
    with urllib.request.urlopen(req, timeout=90) as response:
        raw = response.read()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(raw)
    return raw, False


def specific_runoff_lspkm2(q_m3s, area_km2):
    return q_m3s * 1000 / area_km2


def main():
    raw, from_cache = fetch_raw()
    lines = raw.decode("utf-8-sig").splitlines()
    data_start = next(i for i, x in enumerate(lines) if x.startswith("Datum")) + 1

    values, dates = [], []
    for row in csv.reader(lines[data_start:], delimiter=";"):
        if len(row) < 2 or not row[0] or not row[1]:
            continue
        try:
            v = float(row[1])
        except ValueError:
            continue
        values.append(v)
        dates.append(row[0])

    mean_all = sum(values) / len(values)
    median_all = statistics.median(values)

    lt_specrunoff = specific_runoff_lspkm2(mean_all, AREA_SMHI_KM2)
    nov_specrunoff = specific_runoff_lspkm2(NOV_2023_MONTHLY_MEAN_M3S, AREA_SMHI_KM2)
    ratio = nov_specrunoff / lt_specrunoff

    print(f"Archive: {'cache' if from_cache else 'fresh fetch'}, {len(values)} daily records, "
          f"{dates[0]} to {dates[-1]}")
    print(f"Long-term mean flow: {mean_all:.4f} m3/s")
    print(f"Long-term median flow: {median_all:.4f} m3/s")
    print()
    print(f"SMHI stated drainage area for station 2128: {AREA_SMHI_KM2} km2")
    print(f"  vs SVAR 'Vid mätstation HEÅKRA' (same point): {AREA_SVAR_HEAKRA_KM2} km2 "
          f"({(AREA_SVAR_HEAKRA_KM2-AREA_SMHI_KM2)/AREA_SMHI_KM2*100:+.2f}%)")
    print(f"  vs SVAR 'Vid mätstation Hörbyån' anchor (DIFFERENT, further-downstream point): "
          f"{AREA_SVAR_ANCHOR_KM2} km2 ({(AREA_SVAR_ANCHOR_KM2-AREA_SMHI_KM2)/AREA_SMHI_KM2*100:+.2f}% "
          f"— expected to differ, not the same catchment)")
    print()
    print(f"Long-term mean specific runoff (area={AREA_SMHI_KM2} km2): {lt_specrunoff:.3f} l/s/km2")
    print(f"Nov 2023 monthly-mean specific runoff (area={AREA_SMHI_KM2} km2): {nov_specrunoff:.3f} l/s/km2")
    print(f"Ratio (Nov 2023 / long-term mean): {ratio:.3f}x")
    if ratio > FLAG_RATIO_THRESHOLD:
        print(f"*** FLAG: ratio exceeds {FLAG_RATIO_THRESHOLD}x — STOP, do not feed this downstream "
              f"before investigating. ***")
    else:
        print(f"OK — ratio is below the {FLAG_RATIO_THRESHOLD}x flag threshold. "
              f"Station 2128's Nov 2023 reading is plausible; safe to use.")


if __name__ == "__main__":
    main()
