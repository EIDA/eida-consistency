"""Day-level availability checks for EIDA.

For a given day, fetch availability spans and test consistency
against a random 10-minute dataselect window inside that day.
"""

from __future__ import annotations
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

import requests

from eida_consistency.services.dataselect import dataselect


def _normalize_location(loc: str | None) -> str:
    """Ensure location is valid for FDSN queries."""
    if not loc or not str(loc).strip():
        return "*"
    return loc


def _parse_iso(s: str) -> datetime:
    """Parse ISO string into UTC-aware datetime."""
    dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _collect_spans(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize payload from availability service into spans."""
    spans: List[Dict[str, Any]] = []

    for r in payload.get("availability", []) or []:
        if r.get("start") and r.get("end"):
            spans.append(r)

    for ds in payload.get("datasources", []) or []:
        for ts in ds.get("timespans", []) or []:
            if isinstance(ts, (list, tuple)) and len(ts) >= 2 and ts[0] and ts[1]:
                spans.append({
                    "network": ds.get("network"),
                    "station": ds.get("station"),
                    "location": ds.get("location"),
                    "channel": ds.get("channel"),
                    "quality": ds.get("quality"),
                    "start": ts[0],
                    "end": ts[1],
                })
    return spans


def check_day_availability(
    base_url: str,
    network: str,
    station: str,
    channel: str,
    day: datetime,
    location: str | None = "*",
    verbose: bool = False,
) -> Dict[str, Any]:
    """Check if availability covers a random 10-min dataselect window in a given day."""

    # Normalize location
    location = _normalize_location(location)

    # Day boundaries
    t0 = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    t1 = datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc)

    # Build availability URL
    avail_url = (
        f"{base_url}availability/1/query?"
        f"network={network}&station={station}&location={location}&channel={channel}"
        f"&start={t0.isoformat()}&end={t1.isoformat()}&format=json"
    )
    if verbose:
        logging.info(f"  Availability URL: {avail_url}")

    # Fetch availability spans
    try:
        resp = requests.get(avail_url, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        spans = _collect_spans(payload)
    except Exception as e:
        logging.error(f"[DayAvailability] Request failed: {e}")
        return {"ok": False, "consistent": False, "availability_url": avail_url, "dataselect_url": None}

    # Pick random 10-min window
    if not spans:
        return {"ok": False, "consistent": False, "availability_url": avail_url, "dataselect_url": None}

    rand_offset = random.randint(0, int((t1 - t0).total_seconds()) - 600)
    ds_start = t0 + timedelta(seconds=rand_offset)
    ds_end = ds_start + timedelta(minutes=10)

    # Check if availability spans cover this window
    covered = any(
        _parse_iso(s["start"]) <= ds_start and _parse_iso(s["end"]) >= ds_end
        for s in spans
    )

    # Run dataselect for the 10-min window
    ds_result = dataselect(
        base_url, network, station, channel,
        ds_start.isoformat(), ds_end.isoformat(), location
    )
    ds_url = ds_result.get("url")

    if verbose and ds_url:
        logging.info(f"  Dataselect URL:   {ds_url}")
        logging.info(
            f"  Result → availability covered={covered}, "
            f"dataselect success={ds_result['success']}, "
            f"consistent={covered == ds_result['success']}"
        )

    return {
        "ok": True,
        "consistent": covered == ds_result["success"],
        "availability_url": avail_url,
        "dataselect_url": ds_url,
        "availability_covered": covered,
        "dataselect_success": ds_result["success"],
    }
