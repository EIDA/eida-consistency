"""Shared report re-verification core.

Loading a report, selecting which result rows to act on, and re-checking a
single row's exact reported window. Both ``explore`` (boundary walk + dmtri) and
``rerun`` (verdict only) sit on top of these helpers so the report loader and
the deterministic window check are defined once.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

import requests

from eida_consistency.explorer import _check_window, _parse_iso
from eida_consistency.services.psd import psd_coverage

# Verdicts, keyed by (prior consistent state, current consistent state).
# Prior is the row's ``consistent`` value in the report; current is the live
# re-check. ``None`` current means a transient dataselect failure.
RESOLVED = "RESOLVED"      # was inconsistent, now consistent
PERSISTS = "PERSISTS"      # was inconsistent, still inconsistent
CONSISTENT = "CONSISTENT"  # was consistent, still consistent (only via --all/-i)
REGRESSED = "REGRESSED"    # was consistent, now inconsistent (only via --all/-i)
SKIPPED = "SKIPPED"        # dataselect failed transiently; no verdict possible


def is_psd_finding(row: dict) -> bool:
    """Was this row reported as data-present-but-PSD-missing?

    Deliberately excludes Unsupported/Skipped (no verdict was reached) and
    Orphan (the reverse case -- PSD without data -- which a PSD recompute does
    not address).
    """
    return (
        row.get("psd_status") not in (None, "Unsupported", "Skipped", "Orphan")
        and bool(row.get("dataselect_success"))
        and not row.get("psd_present")
    )


def reverify_psd_row(base_url: str, row: dict, verbose: bool = False) -> Optional[str]:
    """Re-check whether the row's day has a PSD now.

    Returns None when the row carries no PSD information at all (a pre-PSD
    report), so the caller can leave the field off rather than invent a verdict.
    Same vocabulary as the availability/dataselect verdicts.
    """
    if row.get("psd_status") is None:
        return None
    res = psd_coverage(
        base_url, row["network"], row["station"], row["channel"],
        str(row["starttime"]), str(row["endtime"]), row.get("location", ""),
    )
    if verbose:
        logging.info(f"  PSD URL: {res.get('url')}")
    # A failed or unsupported check is not evidence either way.
    if not res.get("success") or res.get("status") in ("Unsupported",):
        return SKIPPED
    was_missing = is_psd_finding(row)
    now_present = bool(res.get("day_covered"))
    if was_missing:
        return RESOLVED if now_present else PERSISTS
    return CONSISTENT if now_present else REGRESSED


def load_report(path_or_url: str) -> dict:
    """Load a report from a local path or an http(s) URL."""
    path_or_url = str(path_or_url)
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        from eida_consistency.utils.constants import USER_AGENT

        logging.info(f"Fetching report from URL: {path_or_url}")
        response = requests.get(
            path_or_url, headers={"User-Agent": USER_AGENT}, timeout=30
        )
        response.raise_for_status()
        return response.json()
    return json.loads(Path(path_or_url).read_text())


def select_targets(
    report: dict,
    indices: Optional[List[int]] = None,
    include_consistent: bool = False,
) -> List[dict]:
    """Pick the result rows to re-verify.

    ``indices`` selects explicit rows (overrides everything else). Otherwise
    ``include_consistent`` chooses between every row and only the inconsistent
    ones (``consistent is False``).
    """
    results = report["results"]
    if indices:
        wanted = set(indices)
        return [r for r in results if r["index"] in wanted]
    if include_consistent:
        return list(results)
    # A row is worth re-running if either dimension was flagged. PSD findings
    # sit on rows whose availability/dataselect verdict is usually fine, so
    # selecting on `consistent` alone made them invisible to rerun.
    return [r for r in results if r.get("consistent") is False or is_psd_finding(r)]


def reverify_row(base_url: str, row: dict, verbose: bool = False) -> str:
    """Re-check a row's exact reported window and classify the outcome."""
    net, sta, cha, loc = row["network"], row["station"], row["channel"], row["location"]
    t0 = _parse_iso(row["starttime"])
    t1 = _parse_iso(row["endtime"])
    now = _check_window(base_url, net, sta, cha, loc, t0, t1, verbose)

    if now is None:
        return SKIPPED
    was_inconsistent = row.get("consistent") is False
    if now is True:
        return RESOLVED if was_inconsistent else CONSISTENT
    return PERSISTS if was_inconsistent else REGRESSED
