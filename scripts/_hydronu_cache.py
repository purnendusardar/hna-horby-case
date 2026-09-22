"""Shared caching + rate-limiting helper for scripts that call
vattenwebb.smhi.se/hydronu/data/point.

That endpoint is UNDOCUMENTED: found by reading HydroNu's own client JS
(see scripts/scenario_lookup_subid.py's docstring), not from any published
API reference. It is not a supported, versioned API and may change or
disappear without notice — see ASSUMPTIONS.md. Two mitigations live here,
used by both scripts/scenario_fetch_streamflow.py and
scripts/scenario_lookup_subid.py:

1. Cache every raw response under web/data/_cache/hydronu/ by request URL,
   so re-running a script (or a fresh session redoing prior work) does not
   silently re-hit an unsupported endpoint for data already on disk.
2. Rate-limit outgoing requests to at most one per MIN_INTERVAL_SECONDS,
   tracked across separate process invocations via a timestamp file in the
   same cache directory, out of courtesy since this is not a published
   public API with documented usage limits.
"""
import hashlib
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "web" / "data" / "_cache" / "hydronu"
RATE_LIMIT_FILE = CACHE_DIR / ".last_request_time"
MIN_INTERVAL_SECONDS = 2.0


def _cache_path(url):
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    safe = "".join(c if c.isalnum() else "_" for c in url.split("hydronu/")[-1])[:80]
    return CACHE_DIR / f"{safe}_{digest}.json"


def _rate_limit():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if RATE_LIMIT_FILE.exists():
        last = float(RATE_LIMIT_FILE.read_text().strip() or 0)
        wait = MIN_INTERVAL_SECONDS - (now - last)
        if wait > 0:
            time.sleep(wait)
    RATE_LIMIT_FILE.write_text(str(time.time()))


def fetch_json_cached(url, force=False):
    """GET url as JSON, using an on-disk cache and a shared rate limiter.

    Returns (data, source_url, from_cache: bool).
    """
    cache_file = _cache_path(url)
    if cache_file.exists() and not force:
        return json.loads(cache_file.read_text(encoding="utf-8")), url, True

    _rate_limit()
    req = urllib.request.Request(url, headers={"User-Agent": "aegir-research/0.1"})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(raw)
    return data, url, False
