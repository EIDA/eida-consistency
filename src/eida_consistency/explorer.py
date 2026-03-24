"""Explore inconsistency boundaries around reported results."""

import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import requests

from eida_consistency.services.availability import get_availability_spans
from eida_consistency.services.dataselect import dataselect
from eida_consistency.utils.nodes import load_node_url


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


def _slice_consistent(
    base_url: str,
    net: str,
    sta: str,
    cha: str,
    loc: str,
    t0: datetime,
    t1: datetime,
    verbose: bool = False,
) -> bool:
    """
    Check if a time slice is consistent between availability and dataselect.
    Returns True if consistent, False if inconsistent.
    """
    # 1. Get availability spans for this slice
    spans = get_availability_spans(
        base_url, net, sta, cha, _iso(t0), _iso(t1), location=loc or "*"
    )
    covered = any(
        _parse_iso(s["start"]) <= t0 and _parse_iso(s["end"]) >= t1
        for s in spans
    )

    # 2. Pick random 10-min window
    day_seconds = int((t1 - t0).total_seconds())
    if day_seconds > 600:
        offset = random.randint(0, day_seconds - 600)
        ds_t0 = t0 + timedelta(seconds=offset)
        ds_t1 = ds_t0 + timedelta(seconds=600)
    else:
        ds_t0, ds_t1 = t0, t1

    # 3. Run dataselect
    ds = dataselect(base_url, net, sta, cha, _iso(ds_t0), _iso(ds_t1), loc)

    consistent = covered == ds["success"]

    # 4. Logging -- verbose prints full URLs, otherwise DEBUG only (no noise)
    if verbose:
        logging.info(
            f"  Availability URL: {base_url}availability/1/query?"
            f"network={net}&station={sta}&location={loc}&channel={cha}"
            f"&start={_iso(t0)}&end={_iso(t1)}&format=json"
        )
        logging.info(
            f"  Dataselect URL:   {base_url}dataselect/1/query?"
            f"network={net}&station={sta}&location={loc}&channel={cha}"
            f"&starttime={_iso(ds_t0)}&endtime={_iso(ds_t1)}&nodata=204"
        )
        logging.info(
            f"  Result -> availability covered={covered}, "
            f"dataselect success={ds['success']}, "
            f"consistent={consistent}"
        )
    else:
        logging.debug(f"  Checked {t0.date()} -> consistent={consistent}")

    return consistent


def explore_boundaries(
    report_path: str | Path,
    indices: Optional[List[int]] = None,
    max_days: int = 30,
    verbose: bool = False,
) -> None:
    """
    Explore inconsistencies from a report.
    If indices is None, explores all inconsistent entries.
    Prints a summary table at the end with windows and dmtri commands.
    """
    report_path = str(report_path)
    if report_path.startswith("http://") or report_path.startswith("https://"):
        logging.info(f"Fetching report from URL: {report_path}")
        response = requests.get(report_path, timeout=30)
        response.raise_for_status()
        report = response.json()
    else:
        report = json.loads(Path(report_path).read_text())
    results = report["results"]

    # Filter results
    if indices:
        targets = [r for r in results if r["index"] in indices]
    else:
        targets = [r for r in results if not r["consistent"]]

    if not targets:
        logging.info("No targets to explore (all consistent or no matching index).")
        return

    node = report["summary"]["node"]
    base_url = load_node_url(node)
    total = len(targets)

    # Collect summary entries
    summary: list[dict] = []

    for item_num, r in enumerate(targets, start=1):
        if r.get("consistent", False):
            logging.debug(
                f"Index {r['index']} is marked consistent in the report -> skipping."
            )
            continue

        net, sta, cha, loc = r["network"], r["station"], r["channel"], r["location"]
        label = f"{net}.{sta}.{loc}.{cha}"
        slice_start = _parse_iso(r["starttime"])
        slice_end = _parse_iso(r["endtime"])

        logging.info(f"[{item_num}/{total}] {label} -- searching boundaries ...")

        # --- Walk backward ---
        back = slice_start.date()
        for back_step in range(1, max_days + 1):
            prev_day = back - timedelta(days=1)
            t0 = datetime.combine(prev_day, datetime.min.time(), tzinfo=timezone.utc)
            t1 = datetime.combine(prev_day, datetime.max.time(), tzinfo=timezone.utc)
            logging.info(f"  <- backward day {back_step}/{max_days} ({prev_day})")
            if _slice_consistent(base_url, net, sta, cha, loc, t0, t1, verbose):
                break
            back = prev_day
        else:
            logging.warning(f"  Reached max backward search limit ({max_days} days).")

        # --- Walk forward ---
        forward = slice_end.date()
        for fwd_step in range(1, max_days + 1):
            next_day = forward + timedelta(days=1)
            t0 = datetime.combine(next_day, datetime.min.time(), tzinfo=timezone.utc)
            t1 = datetime.combine(next_day, datetime.max.time(), tzinfo=timezone.utc)
            logging.info(f"  -> forward  day {fwd_step}/{max_days} ({next_day})")
            if _slice_consistent(base_url, net, sta, cha, loc, t0, t1, verbose):
                break
            forward = next_day
        else:
            logging.warning(f"  Reached max forward search limit ({max_days} days).")

        # Determine suggested action
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
