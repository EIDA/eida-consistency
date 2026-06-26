"""Pure interval math for comparing availability vs dataselect coverage.

All functions work on lists of (start, end) datetime tuples ("intervals").
No obspy, no dicts, no I/O -- trivially unit-testable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

Interval = Tuple[datetime, datetime]

DEFAULT_TOLERANCE_FLOOR = 0.5  # seconds


def parse_iso(s: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string to an aware UTC datetime, or None."""
    if not s or not str(s).strip():
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def tolerance_seconds(samplerate, floor: float = DEFAULT_TOLERANCE_FLOOR) -> float:
    """One sample period in seconds, never below `floor`."""
    try:
        sr = float(samplerate)
    except (TypeError, ValueError):
        sr = 0.0
    if sr > 0:
        return max(1.0 / sr, floor)
    return floor


def clip_intervals(intervals: Sequence[Interval], w0: datetime, w1: datetime) -> List[Interval]:
    """Trim intervals to the window [w0, w1]; drop empty/None pieces."""
    out: List[Interval] = []
    for s, e in intervals:
        if s is None or e is None:
            continue
        cs, ce = max(s, w0), min(e, w1)
        if cs < ce:
            out.append((cs, ce))
    return out


def merge_intervals(intervals: Sequence[Interval], tol: float) -> List[Interval]:
    """Sort and glue intervals whose gap is <= tol seconds."""
    items = sorted(
        (s, e) for s, e in intervals
        if s is not None and e is not None and s < e
    )
    if not items:
        return []
    merged: List[Interval] = [items[0]]
    for s, e in items[1:]:
        ls, le = merged[-1]
        if (s - le).total_seconds() <= tol:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def _subtract(a: Sequence[Interval], b: Sequence[Interval]) -> List[Interval]:
    """Interval difference a \\ b. Inputs assumed merged + sorted."""
    result: List[Interval] = []
    for s, e in a:
        cur = s
        for bs, be in b:
            if be <= cur:
                continue
            if bs >= e:
                break
            if bs > cur:
                result.append((cur, min(bs, e)))
            cur = max(cur, be)
            if cur >= e:
                break
        if cur < e:
            result.append((cur, e))
    return result


def mismatch_intervals(a: Sequence[Interval], b: Sequence[Interval], tol: float) -> List[Interval]:
    """Regions covered by exactly one of a/b and wider than tol seconds.

    Empty result => the two coverage maps agree (Consistent).
    """
    ma = merge_intervals(a, tol)
    mb = merge_intervals(b, tol)
    diff = _subtract(ma, mb) + _subtract(mb, ma)
    diff = [(s, e) for (s, e) in diff if (e - s).total_seconds() > tol]
    return sorted(diff)


def mismatch_intervals_directional(
    avail: Sequence[Interval], ds: Sequence[Interval], tol: float
) -> List[Tuple[datetime, datetime, str]]:
    """Like :func:`mismatch_intervals` but tags each gap with the side that has data.

    Returns a sorted list of ``(start, end, who)`` where ``who`` is:

    - ``"availability"`` -> availability has data here, dataselect does not
    - ``"dataselect"``   -> dataselect has data here, availability does not

    Empty result => the two coverage maps agree (Consistent).
    """
    ma = merge_intervals(avail, tol)
    md = merge_intervals(ds, tol)
    avail_only = [
        (s, e, "availability") for s, e in _subtract(ma, md) if (e - s).total_seconds() > tol
    ]
    ds_only = [
        (s, e, "dataselect") for s, e in _subtract(md, ma) if (e - s).total_seconds() > tol
    ]
    return sorted(avail_only + ds_only, key=lambda x: (x[0], x[1]))
