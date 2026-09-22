"""Event inflow hydrographs for the two Hörbyån boundary inflows (SUBID 184 east arm,
SUBID 64474 south arm), replacing the constant-placeholder inflow used in every run so far.

Pipeline (release-batch instructions, 2026-09-22), per catchment, per storm (40/70/100 mm):
  1. Catchment CN(III) from scripts/scenario_catchment_cn.py (AMC III via Chow/Maidment/Mays 1988).
  2. SCS-CN cumulative effective rainfall on the 10-min design-storm hyetograph -> incremental
     effective rainfall per block (USDA NRCS TR-55, 1986).
  3. NRCS lag time from scripts/scenario_catchment_flowpath.py (NEH Part 630 Ch.15) -> Tp = D/2+L.
  4. SCS dimensionless unit hydrograph, scaled by (Tp, qp=0.208*A*Q/Tp), convolved with the
     effective-rainfall increments -> direct-runoff hydrograph.
  5. + pre-event baseflow (median of station 2128, 1-15 Nov 2023), split by catchment area.
  6. Consistency check (not calibration): 40 mm scenario vs the observed 24.1 m3/s peak at
     station 2128 (comparable in depth to the 36.9 mm pre-event rainfall). Ratio outside
     0.5-2.0 (project-defined tolerance) => STOP, do not feed into a model run.
  7. Duration: extend past 36 h if the latest peak + 6 h would otherwise be cut off.
  8. Write LISFLOOD-FP .bdy-ready series (data/scenario/derived/hydrograph_<mm>mm.bdy) and an
     SVG plot per storm (docs/hydrographs/).

Runs in the data-prep venv, after scenario_catchment_cn.py and scenario_catchment_flowpath.py:
    .venv\\Scripts\\python.exe scripts\\scenario_compute_inflow_hydrographs.py
"""
import csv
import json
import pathlib
import statistics
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER = ROOT / "data/scenario/derived"
HYDRO_DOCS = ROOT / "docs/hydrographs"
STATION_CACHE = ROOT / "web/data/_cache/smhi_hydroobs_station2128_corrected_archive.csv"
STORMS = [40, 70, 100]
BLOCK_MIN = 10.0
CELL_M = 5.0  # must match the model grid (scripts/scenario_build_dem_probe.py --cell)
OBSERVED_PEAK_24_1_DATE = "2023-11-17"
COMPARABLE_STORM_MM = 40  # ~ 36.9 mm pre-event rainfall (VALIDATION.md)
RATIO_TOLERANCE = (0.5, 2.0)  # project-defined, per the release instructions
EXTEND_MARGIN_H = 6.0
MIN_SIM_H = 36.0

# SCS dimensionless unit hydrograph (NEH-4 / TR-55, standard published table), t/Tp -> Q/Qp.
SCS_UH = [
    (0.0, 0.000), (0.1, 0.030), (0.2, 0.100), (0.3, 0.190), (0.4, 0.310), (0.5, 0.470),
    (0.6, 0.660), (0.7, 0.820), (0.8, 0.930), (0.9, 0.990), (1.0, 1.000), (1.1, 0.990),
    (1.2, 0.930), (1.3, 0.860), (1.4, 0.780), (1.5, 0.680), (1.6, 0.560), (1.7, 0.460),
    (1.8, 0.390), (1.9, 0.330), (2.0, 0.280), (2.2, 0.207), (2.4, 0.147), (2.6, 0.107),
    (2.8, 0.077), (3.0, 0.055), (3.2, 0.040), (3.4, 0.029), (3.6, 0.021), (3.8, 0.015),
    (4.0, 0.011), (4.5, 0.005), (5.0, 0.000),
]


def interp(table, x):
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return 0.0
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return 0.0


def fetch_station_2128():
    if STATION_CACHE.exists():
        raw = STATION_CACHE.read_bytes()
    else:
        url = ("https://opendata-download-hydroobs.smhi.se/api/version/1.0/parameter/1/"
               "station/2128/period/corrected-archive/data.csv")
        req = urllib.request.Request(url, headers={"User-Agent": "aegir-research/0.1"})
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
        STATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
        STATION_CACHE.write_bytes(raw)
    lines = raw.decode("utf-8-sig").splitlines()
    start = next(i for i, x in enumerate(lines) if x.startswith("Datum")) + 1
    by_date = {}
    for row in csv.reader(lines[start:], delimiter=";"):
        if len(row) < 2 or not row[0] or not row[1]:
            continue
        try:
            by_date[row[0]] = float(row[1])
        except ValueError:
            continue
    pre_event = [v for d, v in by_date.items() if "2023-11-01" <= d <= "2023-11-15"]
    baseflow = statistics.median(pre_event)
    nov_peak_date = max((d for d in by_date if d.startswith("2023-11")), key=lambda d: by_date[d])
    return dict(baseflow_median_1_15nov2023_m3s=round(baseflow, 3), n_days_used=len(pre_event),
                observed_peak_m3s=by_date[nov_peak_date], observed_peak_date=nov_peak_date)


def scs_cn_effective_rain(depths_mm, cn):
    """Cumulative SCS-CN applied to the cumulative storm depth, then differenced per block."""
    s = 25400.0 / cn - 254.0
    ia = 0.2 * s
    cum_p, cum_q, out = 0.0, 0.0, []
    for d in depths_mm:
        cum_p += d
        q = (cum_p - ia) ** 2 / (cum_p - ia + s) if cum_p > ia else 0.0
        out.append(max(0.0, q - cum_q))
        cum_q = q
    return out, s, ia


def unit_hydrograph(area_km2, tp_h, dt_min, n_steps):
    """Ordinates (m3/s) of the D-minute unit hydrograph for 1 mm of effective rainfall over `area_km2`,
    at dt_min spacing, SCS dimensionless shape scaled by (Tp, qp=0.208*A*1mm/Tp)."""
    qp = 0.208 * area_km2 * 1.0 / tp_h
    out = []
    for i in range(n_steps):
        t_h = i * dt_min / 60.0
        out.append(qp * interp(SCS_UH, t_h / tp_h))
    return out


def convolve(increments_mm, uh):
    n_q, n_u = len(increments_mm), len(uh)
    out = [0.0] * (n_q + n_u - 1)
    for i, p in enumerate(increments_mm):
        if p == 0:
            continue
        for j, u in enumerate(uh):
            out[i + j] += p * u
    return out


def write_plot(path, storm_mm, t_h, q_east, q_south, peak_e, peak_s):
    W, H, pad_l, pad_b, pad_t = 900, 320, 55, 40, 30
    tmax = t_h[-1]
    qmax = max(max(q_east), max(q_south)) * 1.08
    x = lambda t: pad_l + (W - pad_l - 15) * t / tmax
    y = lambda q: H - pad_b - (H - pad_b - pad_t) * q / qmax

    def path_d(series):
        return "M " + " L ".join(f"{x(t):.1f},{y(q):.1f}" for t, q in zip(t_h, series))

    ticks_x = "".join(f'<text x="{x(t):.1f}" y="{H-pad_b+16}" font-size="10" fill="#536f7d" text-anchor="middle">{t:g}h</text>'
                       for t in range(0, int(tmax) + 1, max(1, int(tmax) // 8)))
    ticks_y = "".join(f'<text x="{pad_l-8}" y="{y(q)+3:.1f}" font-size="10" fill="#536f7d" text-anchor="end">{q:.0f}</text>'
                       for q in [0, qmax / 4, qmax / 2, 3 * qmax / 4, qmax])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="Inflow hydrographs, {storm_mm} mm storm: east arm peak {peak_e:.1f} m3/s, south arm peak {peak_s:.1f} m3/s">'
           f'<rect width="{W}" height="{H}" fill="white"/>'
           f'<line x1="{pad_l}" x2="{W-10}" y1="{H-pad_b}" y2="{H-pad_b}" stroke="#cbdce3"/>'
           f'<line x1="{pad_l}" x2="{pad_l}" y1="{pad_t}" y2="{H-pad_b}" stroke="#cbdce3"/>'
           f'{ticks_x}{ticks_y}'
           f'<path d="{path_d(q_east)}" fill="none" stroke="#168c96" stroke-width="2"/>'
           f'<path d="{path_d(q_south)}" fill="none" stroke="#d95141" stroke-width="2"/>'
           f'<text x="0" y="16" font-size="13" fill="#133849">{storm_mm} mm storm &#8212; inflow hydrographs (incl. baseflow)</text>'
           f'<text x="{pad_l}" y="{pad_t-10}" font-size="11" fill="#168c96">&#9644; east arm (SUBID 184), peak {peak_e:.1f} m3/s</text>'
           f'<text x="{pad_l+280}" y="{pad_t-10}" font-size="11" fill="#d95141">&#9644; south arm (SUBID 64474), peak {peak_s:.1f} m3/s</text>'
           f'<text x="0" y="{H-8}" font-size="10" fill="#536f7d">SCS-CN + SCS unit hydrograph + station-2128 baseflow. NRCS lag equation used far outside its validated small-catchment range — see ASSUMPTIONS.md.</text>'
           f'</svg>')
    path.write_text(svg, encoding="utf-8")


def main():
    cn = json.loads((DER / "catchment_cn.json").read_text(encoding="utf8"))["catchments"]
    flowpath = json.loads((DER / "catchment_flowpath.json").read_text(encoding="utf8"))
    station = fetch_station_2128()
    HYDRO_DOCS.mkdir(parents=True, exist_ok=True)

    areas = {k: cn[k]["area_outside_aoi_km2"] for k in ("east_184", "south_64474")}
    total_area = sum(areas.values())
    baseflow_split = {k: round(station["baseflow_median_1_15nov2023_m3s"] * areas[k] / total_area, 3) for k in areas}

    results = {"station_2128": station, "baseflow_split_by_area_m3s": baseflow_split,
               "catchment_area_km2": areas, "storms": {}}
    for mm in STORMS:
        hy = list(csv.DictReader((ROOT / f"docs/hyetographs/hyetograph_{mm}mm.csv").open(encoding="utf-8")))
        depths = [float(r["block_depth_mm"]) for r in hy]
        t_min = [float(r["t_start_min"]) for r in hy]
        series = {}
        for key, aro in (("east_184", "184"), ("south_64474", "64474")):
            cn3 = cn[key]["cn3_amc3"]
            area = areas[key]
            lag_h = flowpath[key]["nrcs_lag_h"]
            tp_h = BLOCK_MIN / 60.0 / 2.0 + lag_h
            eff, s_mm, ia_mm = scs_cn_effective_rain(depths, cn3)
            tb_h = 5 * tp_h  # SCS base time ~= 5*Tp
            n_uh = int(tb_h * 60 / BLOCK_MIN) + 2
            uh = unit_hydrograph(area, tp_h, BLOCK_MIN, n_uh)
            direct = convolve(eff, uh)
            n_total = len(direct)
            t_h_full = [i * BLOCK_MIN / 60.0 for i in range(n_total)]
            q_total = [d + baseflow_split[key] for d in direct]
            peak_q = max(q_total)
            peak_t_h = t_h_full[q_total.index(peak_q)]
            series[key] = dict(subid=aro, cn3_amc3=cn3, tp_h=round(tp_h, 3), tb_h=round(tb_h, 3),
                               s_mm=round(s_mm, 1), ia_mm=round(ia_mm, 1), total_effective_rain_mm=round(sum(eff), 2),
                               peak_direct_runoff_m3s=round(max(direct), 3), peak_total_m3s=round(peak_q, 3),
                               peak_time_h=round(peak_t_h, 2), t_h=t_h_full, q_total_m3s=[round(v, 4) for v in q_total])

        n = max(len(series["east_184"]["t_h"]), len(series["south_64474"]["t_h"]))
        for k in series:
            pad = n - len(series[k]["t_h"])
            if pad > 0:
                series[k]["q_total_m3s"] += [baseflow_split[k]] * pad
                series[k]["t_h"] = [i * BLOCK_MIN / 60.0 for i in range(n)]
        combined = [series["east_184"]["q_total_m3s"][i] + series["south_64474"]["q_total_m3s"][i] for i in range(n)]
        peak_combined = max(combined)
        peak_combined_h = series["east_184"]["t_h"][combined.index(peak_combined)]
        peak_sum_of_arms = series["east_184"]["peak_total_m3s"] + series["south_64474"]["peak_total_m3s"]
        latest_peak_h = max(series["east_184"]["peak_time_h"], series["south_64474"]["peak_time_h"])
        sim_h = max(MIN_SIM_H, latest_peak_h + EXTEND_MARGIN_H)

        entry = dict(peak_combined_timeseries_m3s=round(peak_combined, 3), peak_combined_time_h=round(peak_combined_h, 2),
                     peak_sum_of_arm_peaks_m3s=round(peak_sum_of_arms, 3), latest_arm_peak_time_h=round(latest_peak_h, 2),
                     recommended_sim_hours=round(sim_h, 2), east=series["east_184"], south=series["south_64474"])
        if mm == COMPARABLE_STORM_MM:
            ratio_ts = peak_combined / station["observed_peak_m3s"]
            ratio_sum = peak_sum_of_arms / station["observed_peak_m3s"]
            # Corrected metric (project-lead decision, 2026-09-22): the original check compared an
            # INSTANTANEOUS modelled peak against an observed DAILY-MEAN peak — not comparable, since
            # a flood hydrograph's instantaneous peak always exceeds its own maximum daily mean. This
            # is recorded as a specification error in the check as originally given, not a modelling
            # error. Corrected: the maximum 24 h MOVING mean of the combined series, and separately
            # the maximum 24 h CALENDAR-DAY mean with the storm's t=0 treated as 06:00 UTC (matching
            # the SMHI daily-observation window: "16 November" = 16 Nov 06:00 -> 17 Nov 06:00, README.md),
            # so day boundaries fall at t=0, 24, 48h... by construction.
            block_per_day = int(round(24 * 60 / BLOCK_MIN))
            mov = [sum(combined[i:i + block_per_day]) / block_per_day for i in range(0, max(1, n - block_per_day + 1))]
            max_moving_24h_mean = max(mov) if mov else combined[0]
            day_means = [sum(combined[d:d + block_per_day]) / len(combined[d:d + block_per_day])
                         for d in range(0, n, block_per_day) if combined[d:d + block_per_day]]
            max_calendar_day_mean = max(day_means)
            ratio_moving = max_moving_24h_mean / station["observed_peak_m3s"]
            ratio_calendar = max_calendar_day_mean / station["observed_peak_m3s"]
            accept = RATIO_TOLERANCE[0] <= ratio_moving <= RATIO_TOLERANCE[1]
            entry["consistency_check"] = dict(
                observed_peak_m3s=station["observed_peak_m3s"], observed_peak_date=station["observed_peak_date"],
                comparable_because="40 mm is comparable in depth to the 36.9 mm recorded before the Nov 2023 event (VALIDATION.md)",
                specification_note="The observed figure is an SMHI DAILY MEAN; comparing it to an instantaneous modelled peak is not "
                                    "like-for-like (a hydrograph's instantaneous peak always exceeds its own daily mean) — a specification "
                                    "error in the check as originally given, corrected here per the project lead's 2026-09-22 decision.",
                ratio_instantaneous_peak_of_combined_timeseries=round(ratio_ts, 3), ratio_instantaneous_sum_of_arm_peaks=round(ratio_sum, 3),
                max_moving_24h_mean_m3s=round(max_moving_24h_mean, 3), ratio_max_moving_24h_mean=round(ratio_moving, 3),
                max_calendar_day_mean_m3s=round(max_calendar_day_mean, 3), ratio_max_calendar_day_mean=round(ratio_calendar, 3),
                tolerance=list(RATIO_TOLERANCE), acceptance_metric="max_moving_24h_mean (the corrected, comparable-quantity metric)",
                verdict=("ACCEPT - 24 h moving-mean ratio within the 0.5-2.0 tolerance; proceed to final runs" if accept else
                          "STOP - 24 h moving-mean ratio still exceeds tolerance; do not run the model with this inflow"))
        results["storms"][mm] = entry

        with open(DER / f"hydrograph_{mm}mm.bdy", "w", newline="\n") as f:
            f.write("# Hörbyån inflow hydrographs (SCS-CN + SCS UH + station-2128 baseflow); QVAR values are per unit width (Q/dx, dx=5 m)\n")
            for label, k in (("east184", "east_184"), ("south64474", "south_64474")):
                t_min_series = [t * 60 for t in series[k]["t_h"]]
                f.write(f"{label}\n{len(t_min_series)} minutes\n")
                for t, qq in zip(t_min_series, series[k]["q_total_m3s"]):
                    f.write(f"{qq / CELL_M:.6f} {t:g}\n")

        peak_e, peak_s = series["east_184"]["peak_total_m3s"], series["south_64474"]["peak_total_m3s"]
        write_plot(HYDRO_DOCS / f"hydrograph_{mm}mm.svg", mm, series["east_184"]["t_h"], series["east_184"]["q_total_m3s"], series["south_64474"]["q_total_m3s"], peak_e, peak_s)
        print(f"{mm} mm: east peak {peak_e:.2f} m3/s @ {series['east_184']['peak_time_h']:.1f} h, "
              f"south peak {peak_s:.2f} m3/s @ {series['south_64474']['peak_time_h']:.1f} h, "
              f"combined peak {peak_combined:.2f} m3/s @ {peak_combined_h:.1f} h, sim_h={sim_h:.1f}")
        if "consistency_check" in entry:
            print(f"  consistency check: {entry['consistency_check']['verdict']} "
                  f"(instantaneous ratio={entry['consistency_check']['ratio_instantaneous_peak_of_combined_timeseries']}, "
                  f"24h moving-mean ratio={entry['consistency_check']['ratio_max_moving_24h_mean']}, "
                  f"calendar-day-mean ratio={entry['consistency_check']['ratio_max_calendar_day_mean']})")

    # trim the huge per-timestep arrays out of the printed/summary JSON companion (kept in full in the .bdy files)
    summary = json.loads(json.dumps(results))
    for mm in summary["storms"]:
        for k in ("east", "south"):
            summary["storms"][mm][k] = {kk: vv for kk, vv in summary["storms"][mm][k].items() if kk not in ("t_h", "q_total_m3s")}
    (DER / "inflow_hydrographs_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf8")
    print(f"Wrote {DER / 'inflow_hydrographs_summary.json'}, per-storm .bdy files, and {HYDRO_DOCS}/*.svg")


if __name__ == "__main__":
    main()
