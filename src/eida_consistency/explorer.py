"""Explore inconsistency boundaries around reported results."""

import logging
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from eida_consistency.services.availability import get_availability_spans
from eida_consistency.services.dataselect import dataselect
from eida_consistency.services.psd import psd_coverage
from eida_consistency.core.consistency import classify_consistency
from eida_consistency.utils.nodes import load_node_url

_BAR_WIDTH = 20

# Version of the machine-readable fix schema returned by explore_boundaries and
# emitted by `explore --json`. Bump on any breaking change to the fix records so
# consumers (e.g. dmtri fix) can guard against incompatible output.
SCHEMA_VERSION = "1.0"


def _progress(direction: str, step: int, max_days: int, date: str) -> None:
    """Print an in-place progress bar to stderr (overwrites the same line)."""
    filled = int(_BAR_WIDTH * step / max_days)
    bar = "=" * filled + ">" + " " * (_BAR_WIDTH - filled)
    arrow = "<-" if direction == "back" else "->"
    sys.stderr.write(f"\r  {arrow}  [{bar}] {step:2}/{max_days}  ({date})  ")
    sys.stderr.flush()


def _progress_done(direction: str, step: int, max_days: int, date: str, hit_limit: bool) -> None:
    """Finish the progress line and move to a new line."""
    status = "limit reached" if hit_limit else f"boundary found @ {date}"
    arrow = "<-" if direction == "back" else "->"
    sys.stderr.write(f"\r  {arrow}  [{'=' * _BAR_WIDTH}]  {step:2}/{max_days}  {status}\n")
    sys.stderr.flush()


def _parse_iso(s: str) -> datetime:
    """Parse ISO string into UTC-aware datetime."""
    if not s:
        return None
    dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    """Format datetime as UTC ISO string (second precision)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _check_window(
    base_url: str,
    net: str,
    sta: str,
    cha: str,
    loc: str,
    t0: datetime,
    t1: datetime,
    verbose: bool = False,
) -> bool | None:
    """Consistency of the EXACT ``[t0, t1]`` window (no sampling).

    Deterministic: the same window always produces the same verdict. Used to
    re-verify the precise window a report flagged.
    """
    spans = get_availability_spans(
        base_url, net, sta, cha, _iso(t0), _iso(t1), location=loc or "*"
    )

    # Check if THIS specific window is covered by any availability span
    window_covered = any(
        (_parse_iso(s["start"]) <= t0 and _parse_iso(s["end"]) >= t1)
        for s in spans
    )

    ds = dataselect(base_url, net, sta, cha, _iso(t0), _iso(t1), loc)
    classification = classify_consistency(spans, ds, (_iso(t0), _iso(t1)))
    consistent = classification["consistent"]

    if verbose:
        logging.info(
            f"  Availability URL: {base_url}availability/1/query?"
            f"network={net}&station={sta}&location={loc}&channel={cha}"
            f"&start={_iso(t0)}&end={_iso(t1)}&format=json"
        )
        logging.info(
            f"  Dataselect URL:   {base_url}dataselect/1/query?"
            f"network={net}&station={sta}&location={loc}&channel={cha}"
            f"&starttime={_iso(t0)}&endtime={_iso(t1)}&nodata=204"
        )
        # PSD (day-granularity); informational alongside the A-D boundary walk.
        psd_res = psd_coverage(base_url, net, sta, cha, _iso(t0), _iso(t1), loc)
        psd_present = bool(psd_res.get("day_covered"))
        logging.info(f"  PSD URL:          {psd_res.get('url')}")
        logging.info(
            f"  Result -> availability window_covered={window_covered}, "
            f"dataselect success={ds['success']}, PSD present={psd_present}, "
            f"consistent={consistent}"
        )
    else:
        logging.debug(f"  Checked {t0.date()} -> consistent={consistent}")

    return consistent


def _slice_consistent(
    base_url: str,
    net: str,
    sta: str,
    cha: str,
    loc: str,
    t0: datetime,
    t1: datetime,
    verbose: bool = False,
) -> bool | None:
    """Check a (possibly day-long) range.

    If the range is longer than 600 s a random 600 s slice is sampled (used by
    the boundary walk over neighbouring days); otherwise the exact range is
    checked. Returns True if consistent, False if inconsistent.
    """
    day_seconds = int((t1 - t0).total_seconds())
    if day_seconds > 600:
        offset = random.randint(0, day_seconds - 600)
        ds_t0 = t0 + timedelta(seconds=offset)
        ds_t1 = ds_t0 + timedelta(seconds=600)
    else:
        ds_t0, ds_t1 = t0, t1

    return _check_window(base_url, net, sta, cha, loc, ds_t0, ds_t1, verbose)


def explore_boundaries(
    report_path: str | Path,
    indices: Optional[List[int]] = None,
    max_days: int = 30,
    verbose: bool = False,
) -> dict:
    """
    Explore inconsistencies from a report.
    If indices is None, explores all inconsistent entries.
    Prints a human-readable summary table at the end with windows and dmtri
    commands (unchanged behavior).

    Returns a machine-readable result dict::

        {
            "schema_version": SCHEMA_VERSION,
            "node": "<node>",
            "report": "<path or url>",
            "fixes": [
                {
                    "index": <int>,
                    "network": "..", "station": "..",
                    "location": "..", "channel": "..",
                    "start": "YYYY-MM-DD" | None,
                    "end":   "YYYY-MM-DD" | None,
                    "direction": "refresh" | "clean" | None,
                    "status": "actionable" | "fixed" | "transient",
                },
                ...
            ],
        }

    Only ``status == "actionable"`` fixes carry a window/direction; "fixed"
    (already consistent again) and "transient" (dataselect failed transiently)
    rows are reported with null window so a consumer can see they were evaluated
    but need no action. The ``--json`` CLI flag dumps this dict to stdout.
    """
    # Shared report loader / target selector (function-local import avoids a
    # circular import: reverify imports the window-check primitives from here).
    from eida_consistency.reverify import load_report, select_targets

    report_path = str(report_path)
    report = load_report(report_path)
    targets = select_targets(report, indices)

    if not targets:
        logging.info("No targets to explore (all consistent or no matching index).")
        return {
            "schema_version": SCHEMA_VERSION,
            "node": report["summary"]["node"],
            "report": report_path,
            "fixes": [],
        }

    node = report["summary"]["node"]
    base_url = load_node_url(node)
    total = len(targets)
    summary: list[dict] = []
    fixes: list[dict] = []

    for item_num, r in enumerate(targets, start=1):
        if r.get("consistent") is not False:
            logging.debug(f"Index {r['index']} is marked consistent -> skipping.")
            continue

        net, sta, cha, loc = r["network"], r["station"], r["channel"], r["location"]
        label = f"{net}.{sta}.{loc}.{cha}"
        slice_start = _parse_iso(r["starttime"])
        slice_end = _parse_iso(r["endtime"])

        logging.info(f"[{item_num}/{total}] {label}")

        # --- Re-verify current status on the EXACT reported window (deterministic) ---
        logging.info(f"  Verifying current status of {slice_start} → {slice_end}...")
        current_status = _check_window(base_url, net, sta, cha, loc, slice_start, slice_end, verbose)
        if current_status is True:
            logging.info(f"  FIXED: This window is now consistent. Skipping exploration.")
            summary.append({
                "label": label,
                "window": f"{slice_start.date()} (Verified Fixed)",
                "action": "Fixed",
                "cmd": "-",
            })
            fixes.append({
                "index": r["index"], "network": net, "station": sta,
                "location": loc, "channel": cha,
                "start": None, "end": None, "direction": None,
                "status": "fixed",
            })
            continue
        if current_status is None:
            logging.info("  TRANSIENT: Current Dataselect retrieval failed transiently. Skipping exploration.")
            summary.append({
                "label": label,
                "window": f"{slice_start.date()} (Transient retrieval failure)",
                "action": "Skipped",
                "cmd": "-",
            })
            fixes.append({
                "index": r["index"], "network": net, "station": sta,
                "location": loc, "channel": cha,
                "start": None, "end": None, "direction": None,
                "status": "transient",
            })
            continue

        # --- Walk backward ---
        back = slice_start.date()
        hit_limit = True
        for back_step in range(1, max_days + 1):
            prev_day = back - timedelta(days=1)
            t0 = datetime.combine(prev_day, datetime.min.time(), tzinfo=timezone.utc)
            t1 = datetime.combine(prev_day, datetime.max.time(), tzinfo=timezone.utc)
            _progress("back", back_step, max_days, str(prev_day))
            if _slice_consistent(base_url, net, sta, cha, loc, t0, t1, verbose):
                hit_limit = False
                _progress_done("back", back_step, max_days, str(prev_day), False)
                break
            back = prev_day
        else:
            _progress_done("back", max_days, max_days, str(back), True)

        # --- Walk forward ---
        forward = slice_end.date()
        for fwd_step in range(1, max_days + 1):
            next_day = forward + timedelta(days=1)
            t0 = datetime.combine(next_day, datetime.min.time(), tzinfo=timezone.utc)
            t1 = datetime.combine(next_day, datetime.max.time(), tzinfo=timezone.utc)
            _progress("fwd", fwd_step, max_days, str(next_day))
            if _slice_consistent(base_url, net, sta, cha, loc, t0, t1, verbose):
                _progress_done("fwd", fwd_step, max_days, str(next_day), False)
                break
            forward = next_day
        else:
            _progress_done("fwd", max_days, max_days, str(forward), True)

        # Determine action
        if r["available"] and not r["dataselect_success"]:
            cmd = "clean"
            action = "Availability YES / Dataselect NO -> clean needed"
        elif not r["available"] and r["dataselect_success"]:
            cmd = "refresh"
            action = "Dataselect YES / Availability NO -> refresh needed"
        else:
            cmd = "refresh"
            action = "Unclear direction -> defaulting to refresh"

        dmtri_cmd = (
            f"uvx dmtri {cmd} --network={net} --station={sta} "
            f"--channel={cha} --start={back} --end={forward}"
        )

        summary.append({
            "label": label,
            "window": f"{back} -> {forward}",
            "action": action,
            "cmd": dmtri_cmd,
        })
        fixes.append({
            "index": r["index"], "network": net, "station": sta,
            "location": loc, "channel": cha,
            "start": str(back), "end": str(forward),
            "direction": cmd, "status": "actionable",
        })

    # -- Final summary ---------------------------------------------------------
    sep = "-" * 72
    n = len(summary)
    logging.info("")
    logging.info(sep)
    logging.info(f"  EXPLORATION SUMMARY  ({n} inconsistenc{'y' if n == 1 else 'ies'})")
    logging.info(sep)
    for i, s in enumerate(summary, start=1):
        logging.info(f"  [{i}/{n}] {s['label']}")
        logging.info(f"        Window : {s['window']}")
        logging.info(f"        Action : {s['action']}")
        logging.info(f"        Command: {s['cmd']}")
        if i < n:
            logging.info("")
    logging.info(sep)

    return {
        "schema_version": SCHEMA_VERSION,
        "node": node,
        "report": report_path,
        "fixes": fixes,
    }
