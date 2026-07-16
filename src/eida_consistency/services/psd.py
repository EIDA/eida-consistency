"""EIDA PSD (seedpsd) coverage service.

PSD is a once-per-day product served as CSV by {host}/eidaws/psd/1/coverage.
We query a ±1-day-padded window (tight windows return a false 204) and reduce
the response to a per-day "is there a valid PSD record for this slice's day".
"""
from __future__ import annotations

import csv
import io
import time
from datetime import timedelta
from urllib.parse import urlparse

import requests

from eida_consistency.core.coverage import parse_iso
from eida_consistency.utils.constants import USER_AGENT


def _parse_psd_csv(text: str) -> list[tuple[str, str, str, bool]]:
    """Parse coverage CSV into (start_iso, end_iso, samplerate, is_valid) rows."""
    rows: list[tuple[str, str, str, bool]] = []
    if not text or not text.strip():
        return rows
    for row in csv.DictReader(io.StringIO(text)):
        s, e = row.get("Start time"), row.get("End time")
        if not s or not e:
            continue
        is_valid = str(row.get("Is valid", "")).strip().lower() == "true"
        rows.append((s, e, row.get("Sampling rate"), is_valid))
    return rows


def _day_covered(records, slice_start: str, slice_end: str) -> bool:
    """True iff a valid record overlaps the UTC day(s) of [slice_start, slice_end]."""
    t0, t1 = parse_iso(slice_start), parse_iso(slice_end)
    if not t0 or not t1:
        return False
    day_lo = t0.replace(hour=0, minute=0, second=0, microsecond=0)
    day_hi = t1.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    for s, e, _sr, is_valid in records:
        if not is_valid:
            continue
        rs, re = parse_iso(s), parse_iso(e)
        if rs and re and max(rs, day_lo) < min(re, day_hi):
            return True
    return False


def _endpoint_from_base(base_url: str) -> str:
    """Reduce an FDSN base URL to scheme://host (like dataselect does)."""
    p = urlparse(base_url)
    scheme = p.scheme or "https"
    host = p.hostname or ""
    return f"{scheme}://{host}".rstrip("/")


def _pad(iso: str, days: int) -> str:
    dt = parse_iso(iso) + timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def psd_coverage(base_url, net, sta, cha, start, end, loc="",
                 timeout: int = 25, max_attempts: int = 3) -> dict:
    """Query {host}/eidaws/psd/1/coverage for the slice's day(s), padded ±1 day."""
    endpoint = _endpoint_from_base(base_url)
    url = f"{endpoint}/eidaws/psd/1/coverage"
    params = {
        "net": net, "sta": sta, "loc": loc if loc else "--", "cha": cha,
        "start": _pad(start, -1), "end": _pad(end, 1),
    }

    last_status, last_error = "Unknown", None
    last_url = url
    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers={"User-Agent": USER_AGENT})
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                requests.exceptions.RequestException) as e:
            last_status, last_error = type(e).__name__, str(e)
            if attempt < max_attempts:
                time.sleep(attempt)
                continue
            break

        full_url = getattr(r, "url", url)
        if r.status_code == 404:
            return {"success": False, "status": "Unsupported", "records": [],
                    "day_covered": False, "url": full_url, "error": None}
        if r.status_code == 204 or not r.text.strip():
            return {"success": True, "status": "NoData", "records": [],
                    "day_covered": False, "url": full_url, "error": None}
        if r.status_code >= 500:
            last_status = f"HTTP {r.status_code}"
            last_url = full_url
            if attempt < max_attempts:
                time.sleep(attempt)
                continue
            break
        ct = r.headers.get("content-type", "")
        if "text/plain" not in ct and "csv" not in ct:
            return {"success": False, "status": "Unsupported", "records": [],
                    "day_covered": False, "url": full_url, "error": None}

        records = _parse_psd_csv(r.text)
        return {"success": True, "status": "OK", "records": records,
                "day_covered": _day_covered(records, start, end),
                "url": full_url, "error": None}

    return {"success": False, "status": last_status, "records": [],
            "day_covered": False, "url": last_url, "error": last_error}
