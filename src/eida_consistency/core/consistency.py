"""Consistency classification helpers."""

from __future__ import annotations

from typing import Any, Dict


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


def classify_consistency(available: bool, ds_result: Dict[str, Any]) -> Dict[str, Any]:
    """Classify an availability/dataselect comparison."""
    ds_success = bool(ds_result["success"])
    ds_status = ds_result.get("status")

    if is_transient_dataselect_failure(ds_success, ds_status):
        return {
            "consistent": None,
            "scoreable": False,
            "status": "Skipped",
            "reason": "TransientDataselectFailure",
        }

    consistent = available == ds_success
    return {
        "consistent": consistent,
        "scoreable": True,
        "status": "Consistent" if consistent else "Inconsistent",
        "reason": None,
    }
