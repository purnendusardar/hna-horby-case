"""Fetch SMHI S-HYPE flow data for Hörbyån via Vattenwebb (brief §4.4 —
"assumed wet-November baseflow (a value from SMHI S-HYPE...)").

Usage:
    python scripts/scenario_fetch_streamflow.py SUBID

SUBID is SMHI's S-HYPE numeric subbasin identifier. There is no
account-free, scriptable way to find it: SVAR's Delavrinningsområden WFS
(used by scripts/scenario_fetch_subcatchments.py) keys catchments by
ARO_UUID, not SUBID, and no crosswalk or spatial lookup API was found during
research for this script (2026-09-17) — confirmed by testing three plausible
REST endpoint guesses under vattenwebb.smhi.se, all 404, and by inspecting
the vattenwebb.smhi.se/nadia/ single-page app's JS bundle for a literal
lookup URL (none found). Even a third-party open-source client for this API
(Kaptensanders/smhi-waterflow on GitHub) documents finding the SUBID by hand
from the HydroNu map UI, not via any API.

To get the SUBID: open https://vattenwebb.smhi.se/hydronu/, navigate to
Hörbyån at or just upstream of Hörby (≈WGS84 55.849, 13.655), click the
river reach, and read the SUBID from the station info popup.

Endpoint (confirmed working, no account, during research 2026-09-17):
    https://vattenwebb.smhi.se/hydronu/data/point?subid={subid}

IMPORTANT LIMITATION: this endpoint's "cout" fields are a rolling ~30-day
window ending at the request time, not a queryable historical archive — it
cannot return a November 2023 flow value directly. Response shape (confirmed
against a live response, subid=14054, 2026-09-17 — not Hörby's own SUBID,
just a check that this code parses the real API correctly):
- subbasinArea / upstreamArea (m^2) — top-level.
- chartData.mq / chartData.mlq / chartData.mhq: long-run mean / low / high
  historical flow (m^3/s) — these ARE usable as a general baseflow
  reference, just not the specific event.
- chartData.coutHindcast / chartData.psimHindcast: recent modelled flow,
  [timestamp_ms, m3/s] pairs, last ~30 days only.
For the actual November 2023 event flow, the separate vattenwebb.smhi.se
/nadia/ bulk-download portal is the likely source, untested in this session
for whether it needs a login — check by hand once a SUBID is in hand.

License: SMHI's general open-data terms (CC BY 4.0) are the standing
assumption; not independently re-confirmed for this specific endpoint.

UNSUPPORTED ENDPOINT: data/point is not a documented, published API — it
was found by reading HydroNu's own client JS (see
scripts/scenario_lookup_subid.py's docstring). It may change or disappear
without notice. This script therefore caches every raw response and
rate-limits requests via scripts/_hydronu_cache.py — see ASSUMPTIONS.md.
Pass --force to bypass the cache and re-fetch.
"""
import sys
import json
import pathlib
import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _hydronu_cache import fetch_json_cached

root = pathlib.Path(__file__).resolve().parents[1]
ENDPOINT = "https://vattenwebb.smhi.se/hydronu/data/point"


def fetch(subid, force=False):
    url = f"{ENDPOINT}?subid={subid}"
    return fetch_json_cached(url, force=force)


def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    if len(args) != 1:
        sys.exit(
            "Usage: python scripts/scenario_fetch_streamflow.py SUBID [--force]\n"
            "No SUBID is hard-coded here — it must be looked up by hand at "
            "vattenwebb.smhi.se/hydronu/, or via scripts/scenario_lookup_subid.py "
            "(see that script's module docstring for how the lookup works)."
        )
    subid = args[0]
    data, request_url, from_cache = fetch(subid, force=force)
    if from_cache:
        print(f"(served from cache — pass --force to re-fetch)")
    data["_metadata"] = {
        "source": "SMHI S-HYPE via Vattenwebb HydroNu",
        "source_url": request_url,
        "license": "CC BY 4.0 (SMHI general open-data terms — not independently re-confirmed for this endpoint)",
        "endpoint_status": "UNDOCUMENTED/reverse-engineered, unsupported — see ASSUMPTIONS.md",
        "served_from_cache": from_cache,
        "annotated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "warning": (
            "coutHindcast/psimHindcast are a rolling ~30-day window ending at "
            "fetch time, NOT a queryable historical archive — this is not a "
            "November 2023 flow value. mq/mlq/mhq are long-run statistics and "
            "are the usable baseflow reference from this endpoint."
        ),
    }
    target = root / f"web/data/scenario_streamflow_subid{subid}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved SUBID {subid} response to {target}")
    chart = data.get("chartData", {})
    print(f"subbasinArea/upstreamArea (m^2): {data.get('subbasinArea')} / {data.get('upstreamArea')}")
    print(f"mq (mean) / mlq (low) / mhq (high) m3/s: "
          f"{chart.get('mq')} / {chart.get('mlq')} / {chart.get('mhq')}")
    print("Reminder: this is NOT the November 2023 event flow — see the module docstring "
          "for why, and check vattenwebb.smhi.se/nadia/ by hand for the historical archive.")


if __name__ == "__main__":
    main()
