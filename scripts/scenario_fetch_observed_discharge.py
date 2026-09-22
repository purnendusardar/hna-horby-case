"""Fetch observed daily discharge (Vattenföring, dygnsmedelvärde) from SMHI's
open Hydrological Observations API, for the real gauging station that the
SVAR "Vid mätstation HEÅKRA" subcatchment (the model's west outflow — see
scenarios.yaml -> inflow.boundary_outflow) is built around.

Why HEÅKRA and not a station literally named "Hörby"/"Hörbyån": the full
station list for parameter 1 (Vattenföring, Dygn — 720 stations, fetched
2026-09-18) was searched for any name containing "hörby"/"horby"; none
exists. The SVAR subcatchment named "Vid mätstation Hörbyån" (ARO_UUID
1D0DC07B, the original anchor used in scripts/scenario_fetch_subcatchments.py)
is a *different*, further-downstream catchment with no coincident open-data
gauge found nearby either (same 15 km search). The nearest and functionally
matching real gauge is HEÅKRA (SMHI station id 2128):
- 55.8449 N, 13.6350 E -- ~0.31 km from the already-identified west outflow
  boundary point (55.84508, 13.63971), i.e. effectively the same location.
- SMHI's own catchmentSize for this station (146.8 km^2) is close to SVAR's
  AREA_UPSTREAM for the "Vid mätstation HEÅKRA" polygon (147.494 km^2, i.e.
  the 147.49 km^2 used in scenarios.yaml) -- ~0.5% apart, consistent with the
  same point on the river measured by two independent delineations.
- region/catchmentName = 96 / "RÖNNE Å", the larger system Hörbyån feeds.

Endpoint (confirmed working, no account, 2026-09-18):
    https://opendata-download-hydroobs.smhi.se/api/version/1.0/parameter/1/station/2128/period/corrected-archive/data.csv
Full period of record at fetch time: 1973-05-23 to 2026-09-16 (station
"active": true -- ongoing). All November 2023 and January 2024 values carry
quality flag G ("Kontrollerade och godkända värden" -- checked and approved).

License: SMHI's general open-data terms (CC BY 4.0), same as already used
for the meteorological station in scripts/fetch_rainfall.py
(smhi.se/data/om-smhis-data/villkor-for-anvandning).
"""
import csv
import datetime
import hashlib
import json
import pathlib
import sys
import urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
STATION_ID = 2128
STATION_NAME = "HEÅKRA"
URL = (
    "https://opendata-download-hydroobs.smhi.se/api/version/1.0/parameter/1/"
    f"station/{STATION_ID}/period/corrected-archive/data.csv"
)


def fetch_raw():
    if len(sys.argv) > 1:
        return pathlib.Path(sys.argv[1]).read_bytes()
    req = urllib.request.Request(URL, headers={"User-Agent": "aegir-research/0.1"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()


def main():
    raw = fetch_raw()
    lines = raw.decode("utf-8-sig").splitlines()
    data_start = next(i for i, x in enumerate(lines) if x.startswith("Datum")) + 1

    all_records = []
    for row in csv.reader(lines[data_start:], delimiter=";"):
        if len(row) < 3 or not row[0] or not row[1]:
            continue
        try:
            value = float(row[1])
        except ValueError:
            continue
        all_records.append({"date": row[0], "m3s": value, "quality": row[2]})

    def month(records, prefix):
        return [r for r in records if r["date"].startswith(prefix)]

    nov2023 = month(all_records, "2023-11")
    jan2024 = month(all_records, "2024-01")
    assert len(nov2023) == 30, f"Expected 30 daily records for Nov 2023, got {len(nov2023)}"
    assert len(jan2024) == 31, f"Expected 31 daily records for Jan 2024, got {len(jan2024)}"

    nov_mean = sum(r["m3s"] for r in nov2023) / len(nov2023)
    jan_mean = sum(r["m3s"] for r in jan2024) / len(jan2024)

    payload = {
        "station": {
            "id": STATION_ID,
            "name": STATION_NAME,
            "latitude": 55.8449,
            "longitude": 13.6350,
            "owner": "SMHI",
            "svar_catchment_match": "Vid mätstation HEÅKRA (ARO_UUID A5BE7041-2F1C-4F41-B7AA-7ED73F0659FE)",
            "catchment_size_km2_smhi": 146.8,
            "catchment_size_km2_svar_area_upstream": 147.494,
            "period_of_record": {
                "first_record": all_records[0]["date"],
                "last_record": all_records[-1]["date"],
                "note": "From the fetched archive's own first/last rows; station status \"active\": true means ongoing at fetch time, not a fixed end date.",
            },
        },
        "parameter": "Vattenföring (Dygn) / discharge, daily mean",
        "unit": "m3/s",
        "source": URL,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "license": "CC BY 4.0 (SMHI general open-data terms, smhi.se/data/om-smhis-data/villkor-for-anvandning)",
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "quality_codes": {"G": "Kontrollerade och godkända värden (checked and approved)"},
        "note": (
            "No SMHI discharge station is literally named Hörby/Hörbyån (checked "
            "against the full 720-station list for parameter 1). HEÅKRA is the "
            "real gauge coincident with the model's west outflow boundary point "
            "-- see this script's module docstring."
        ),
        "first_record_date": all_records[0]["date"],
        "last_record_date": all_records[-1]["date"],
        "nov_2023_mean_m3s": round(nov_mean, 4),
        "jan_2024_mean_m3s": round(jan_mean, 4),
        "nov_2023_records": nov2023,
        "jan_2024_records": jan2024,
    }

    target_json = root / "web/data/scenario_observed_discharge_heakra.json"
    target_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    target_csv = root / "web/data/scenario_observed_discharge_heakra.csv"
    with target_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "m3s", "quality"])
        writer.writeheader()
        writer.writerows(nov2023 + jan2024)

    print(f"Station {STATION_NAME} ({STATION_ID}): records {all_records[0]['date']} .. {all_records[-1]['date']}")
    print(f"Nov 2023 mean discharge: {nov_mean:.3f} m3/s (n={len(nov2023)})")
    print(f"Jan 2024 mean discharge: {jan_mean:.3f} m3/s (n={len(jan2024)})")
    print(f"Wrote {target_json} and {target_csv}")


if __name__ == "__main__":
    main()
