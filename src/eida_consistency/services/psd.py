"""EIDA PSD (seedpsd) coverage service.

PSD is a once-per-day product served as CSV by {host}/eidaws/psd/1/coverage.
We query a ±1-day-padded window (tight windows return a false 204) and reduce
the response to a per-day "is there a valid PSD record for this slice's day".
"""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from eida_consistency.core.coverage import parse_iso


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
