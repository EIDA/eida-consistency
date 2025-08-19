"""Pick random epochs and check availability coverage (returns location).

This module selects up to `epochs` unique (network, station, channel) items from the
candidate pool, places a random 10-minute epoch within each channel's lifetime, and
queries /availability/1/query?format=json to determine if the epoch is fully covered.
If a covering span is found, we prefer its exact location code for the later dataselect
request (to avoid wildcards and MultiTrace).

Return value (list of tuples):
    [
      (availability_url, availability_ok, epoch_start_iso, epoch_end_iso, location_exact),
      ...
    ]
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from eida_consistency.services.availability import check_availability_query


def _parse_iso(dt: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string (tolerate trailing 'Z'). Return None on failure/empty."""
    if not dt or not str(dt).strip():
        return None
    try:
        return datetime.fromisoformat(str(dt).replace("Z", ""))
    except Exception:
        return None


def check_candidate(
    base_url: str,
    candidate: Dict[str, str],
    candidates: Optional[List[Dict[str, str]]] = None,
    epochs: int = 10,
) -> List[Tuple[str, bool, str, str, str]]:
    """
    Build up to `epochs` test cases and check availability coverage.

    Parameters
    ----------
    base_url : str
        FDSN base URL, e.g. "https://ws.resif.fr/fdsnws/"
    candidate : dict
        A single candidate (ignored if `candidates` provided). Keys: network, station,
        channel, starttime[, endtime][, location]
    candidates : list[dict] | None
        Full pool of candidates. If None, only `candidate` is used.
    epochs : int
        Number of unique channels (NET,STA,CHA) to sample.

    Returns
    -------
    list[tuple[str, bool, str, str, str]]
        For each tested epoch:
        (availability_url, availability_ok, epoch_start_iso, epoch_end_iso, location_exact)
    """
    results: List[Tuple[str, bool, str, str, str]] = []

    # Ensure we have a usable pool
    pool = [
        c for c in (candidates or [candidate])
        if all(k in c for k in ("network", "station", "channel", "starttime"))
    ]
    if not pool:
        return results

    used: set[tuple[str, str, str]] = set()  # to enforce uniqueness by (NET, STA, CHA)

    # Avoid infinite loops if many candidates are invalid/too short
    max_attempts = max(epochs * 20, len(pool) * 2)
    attempts = 0

    while len(results) < epochs and attempts < max_attempts:
        attempts += 1
        sample = random.choice(pool)
        key = (sample["network"], sample["station"], sample["channel"])
        if key in used:
            continue

        # Channel lifetime bounds
        ch_start = _parse_iso(sample.get("starttime"))
        ch_end = _parse_iso(sample.get("endtime")) or datetime.utcnow()
        if not ch_start or not ch_end:
            continue

        # Require at least 10 minutes of lifetime
        if (ch_end - ch_start).total_seconds() < 600:
            continue

        # Latest valid start time to fit a 10-minute window
        latest_start = ch_end - timedelta(minutes=10)
        if ch_start >= latest_start:
            continue

        # Pick a random epoch within [ch_start, ch_end-10min]
        seconds_span = int((latest_start - ch_start).total_seconds())
        epoch_start_dt = ch_start + timedelta(seconds=random.randint(0, seconds_span))
        epoch_end_dt = epoch_start_dt + timedelta(minutes=10)

        s = epoch_start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        e = epoch_end_dt.strftime("%Y-%m-%dT%H:%M:%S")

        net, sta, cha = sample["network"], sample["station"], sample["channel"]

        # Ask availability /query (JSON) using location="*" to discover the exact location
        av = check_availability_query(base_url, net, sta, cha, s, e, location="*")
        available = bool(av.get("ok", False))

        # Decide single location to use later with dataselect:
        # prefer the covering span's location; else fall back to StationXML candidate; else ""
        loc_exact = ""
        matched_span = av.get("matched_span") or {}
        if matched_span.get("location"):
            loc_exact = matched_span["location"]
        elif sample.get("location"):
            loc_exact = sample["location"]

        # Accept the test case and mark this (NET,STA,CHA) as used
        used.add(key)
        results.append((av.get("url", ""), available, s, e, loc_exact))

    return results
