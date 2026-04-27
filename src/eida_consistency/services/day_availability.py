"""Day-level availability checks for EIDA."""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

from eida_consistency.core.consistency import classify_consistency
from eida_consistency.services.dataselect import dataselect
from eida_consistency.utils.constants import USER_AGENT


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


def _parse_text_availability(text: str) -> List[Dict[str, Any]]:
    """Parse text format availability response into spans."""
    spans: List[Dict[str, Any]] = []
    for line in text.strip().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 7:
            net, sta, loc, cha, qual, start, end = parts
            spans.append(
                {
                    "network": net,
                    "station": sta,
                    "location": "" if loc in ("--", "*") else loc,
                    "channel": cha,
                    "quality": qual,
                    "start": start,
                    "end": end,
                }
            )
        elif len(parts) >= 8:
            net, sta, loc, cha, qual, samplerate, start, end = parts[:8]
            spans.append(
                {
                    "network": net,
                    "station": sta,
                    "location": "" if loc in ("--", "*") else loc,
                    "channel": cha,
                    "quality": qual,
                    "samplerate": samplerate,
                    "start": start,
                    "end": end,
                }
            )
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
    """Check if availability covers a random 10-minute Dataselect window in a given day."""
    location = _normalize_location(location)
    t0 = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    t1 = datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc)

    avail_url = (
        f"{base_url}availability/1/query?"
        f"network={network}&station={station}&location={location}&channel={channel}"
        f"&start={t0.isoformat()}&end={t1.isoformat()}&format=text&merge=quality,overlap"
    )
    if verbose:
        logging.info(f"  Availability URL: {avail_url}")

    try:
        resp = requests.get(avail_url, timeout=20, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        spans = _parse_text_availability(resp.text)
    except Exception as exc:
        logging.error(f"[DayAvailability] Request failed: {exc}")
        return {"ok": False, "consistent": False, "availability_url": avail_url, "dataselect_url": None}

    if not spans:
        return {"ok": False, "consistent": False, "availability_url": avail_url, "dataselect_url": None}

    rand_offset = random.randint(0, int((t1 - t0).total_seconds()) - 600)
    ds_start = t0 + timedelta(seconds=rand_offset)
    ds_end = ds_start + timedelta(minutes=10)

    covered = any(_parse_iso(s["start"]) <= ds_start and _parse_iso(s["end"]) >= ds_end for s in spans)

    ds_result = dataselect(base_url, network, station, channel, ds_start.isoformat(), ds_end.isoformat(), location)
    ds_url = ds_result.get("url")
    classification = classify_consistency(covered, ds_result)

    if verbose and ds_url:
        logging.info(f"  Dataselect URL:   {ds_url}")
        logging.info(
            f"  Result → availability covered={covered}, "
            f"dataselect success={ds_result['success']}, "
            f"consistent={classification['consistent']}"
        )

    return {
        "ok": True,
        "consistent": classification["consistent"],
        "scoreable": classification["scoreable"],
        "availability_url": avail_url,
        "dataselect_url": ds_url,
        "availability_covered": covered,
        "dataselect_success": ds_result["success"],
    }
