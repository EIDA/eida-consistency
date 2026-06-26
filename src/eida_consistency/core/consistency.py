"""Consistency classification helpers."""

from __future__ import annotations

from typing import Any, Dict

from eida_consistency.core.coverage import (
    parse_iso, tolerance_seconds, clip_intervals, mismatch_intervals_directional,
)


def is_transient_dataselect_failure(success: bool, status: str | None) -> bool:
    """Return True for transient transport-style Dataselect failures."""
    if success:
        return False
    normalized = str(status or "").strip().lower()
    if not normalized:
        return False

    # Keywords for network issues or server-side transient errors
    transient_keywords = [
        "timeout",
        "connection",
        "http 5",        # HTTP 500, 502, 503, 504
        "http error 5",
        "proxy",
        "ssl",
        "remote end closed",
        "broken pipe",
        "gateway",
        "unavailable",
        "internal server error",
    ]
    return any(kw in normalized for kw in transient_keywords)


def _first_samplerate(segments, spans):
    """Pick a sample rate for tolerance: dataselect first, then availability."""
    for seg in segments or []:
        sr = seg[2] if len(seg) > 2 else None
        if sr:
            return sr
    for s in spans or []:
        sr = s.get("samplerate")
        if sr:
            return sr
    return None


def classify_consistency(spans, ds_result: Dict[str, Any], window) -> Dict[str, Any]:
    """Compare availability spans vs dataselect segments within `window`.

    spans:     list of availability span dicts ({"start","end","samplerate"}).
    ds_result: dict from dataselect(), incl. "success", "status", "segments".
    window:    (start_iso, end_iso) tuple of the test window.
    """
    ds_success = bool(ds_result["success"])
    ds_status = ds_result.get("status")

    if is_transient_dataselect_failure(ds_success, ds_status):
        return {
            "consistent": None,
            "scoreable": False,
            "status": "Skipped",
            "reason": "TransientDataselectFailure",
            "mismatch": [],
        }

    w0, w1 = parse_iso(window[0]), parse_iso(window[1])
    segments = ds_result.get("segments", [])
    tol = tolerance_seconds(_first_samplerate(segments, spans))

    avail_iv = [(parse_iso(s.get("start")), parse_iso(s.get("end"))) for s in (spans or [])]
    ds_iv = [(parse_iso(seg[0]), parse_iso(seg[1])) for seg in segments]

    a = clip_intervals(avail_iv, w0, w1)
    d = clip_intervals(ds_iv, w0, w1)
    mism = mismatch_intervals_directional(a, d, tol)
    consistent = len(mism) == 0

    return {
        "consistent": consistent,
        "scoreable": True,
        "status": "Consistent" if consistent else "Inconsistent",
        "reason": None,
        "mismatch": [
            {"start": s.isoformat(), "end": e.isoformat(), "who": who} for s, e, who in mism
        ],
        "coverage": {
            "availability": [[s.isoformat(), e.isoformat()] for s, e in a],
            "dataselect": [[s.isoformat(), e.isoformat()] for s, e in d],
        },
    }
