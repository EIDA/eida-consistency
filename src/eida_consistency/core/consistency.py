"""Consistency classification helpers."""

from __future__ import annotations

from typing import Any, Dict

from eida_consistency.core.coverage import (
    parse_iso, tolerance_seconds, clip_intervals, mismatch_intervals_directional,
)
from eida_consistency.utils.constants import PSD_REQUIRED_SINCE


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


def classify_psd(ds_result: Dict[str, Any], psd_result: Dict[str, Any], window,
                 day_check=None) -> Dict[str, Any]:
    """Compare dataselect (ground truth) vs PSD day-coverage for `window`.

    `day_check` is an optional zero-argument probe returning
    ``{"ok", "has_spans", "url"}``. It is called only when PSD exists for a
    window that carries no data, to tell an ordinary intra-day gap (PSD is a
    per-day product, our windows are minutes) from an orphan PSD — a day the
    archive has no data for at all. Callers that cannot probe omit it and keep
    the previous behaviour.
    """
    w1 = parse_iso(window[1])
    required = bool(w1 and w1 >= parse_iso(PSD_REQUIRED_SINCE))

    base = {"applicable": True, "psd_required": required,
            "d_present": bool(ds_result.get("segments")),
            "p_present": bool(psd_result.get("day_covered"))}

    if psd_result.get("status") == "Unsupported":
        return {**base, "status": "Unsupported", "scoreable": False, "consistent": None}

    psd_transient = is_transient_dataselect_failure(
        psd_result.get("success", False), psd_result.get("status"))
    ds_transient = is_transient_dataselect_failure(
        ds_result.get("success", False), ds_result.get("status"))
    if psd_transient or ds_transient:
        return {**base, "status": "Skipped", "scoreable": False, "consistent": None}

    if not psd_result.get("success"):
        return {**base, "status": "Skipped", "scoreable": False, "consistent": None}

    # PSD without data: only a finding when the whole day is dataless.
    if base["p_present"] and not base["d_present"] and day_check is not None:
        probe = day_check() or {}
        if not probe.get("ok"):
            return {**base, "status": "Skipped", "scoreable": False, "consistent": None,
                    "day_url": probe.get("url")}
        if not probe.get("has_spans"):
            return {**base, "status": "Orphan", "scoreable": False, "consistent": None,
                    "day_url": probe.get("url")}

    consistent = not (base["d_present"] and not base["p_present"])
    return {**base, "scoreable": True, "consistent": consistent,
            "status": "Consistent" if consistent else "Inconsistent"}
