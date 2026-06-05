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


# WFCatalog advisory verdicts (day-level, never affects the score).
WF_AGREE = "agree"            # catalog matches dataselect
WF_CATALOG_GAP = "catalog-gap"  # dataselect served data, catalog is empty
WF_DAY_PARTIAL = "day-partial"  # catalog has data but dataselect returned none
WF_NA = "n/a"                 # not deployed / bad request / transient


def classify_wfcatalog(ds_result: Dict[str, Any], wf_result: Dict[str, Any]) -> str:
    """Collapse the WFCatalog cross-check into a single advisory verdict.

    Compares the day-level WFCatalog signal against dataselect (the ground
    truth). Returns one of WF_AGREE / WF_CATALOG_GAP / WF_DAY_PARTIAL / WF_NA.
    """
    if not wf_result.get("deployed", False):
        return WF_NA

    status = str(wf_result.get("status") or "")
    has_data = wf_result.get("has_data")
    if has_data is None or status not in ("OK", "NoData"):
        return WF_NA

    ds_success = bool(ds_result["success"])
    if bool(has_data) == ds_success:
        return WF_AGREE
    if ds_success and not has_data:
        return WF_CATALOG_GAP
    return WF_DAY_PARTIAL  # catalog has data, dataselect returned none
