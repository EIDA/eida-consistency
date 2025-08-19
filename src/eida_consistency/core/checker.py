"""Pick random epochs and check availability coverage (returns location)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from eida_consistency.services.availability import check_availability_query


def _parse_iso(dt: Optional[str]) -> Optional[datetime]:
    if not dt or not str(dt).strip():
        return None
    try:
        return datetime.fromisoformat(dt.replace("Z", ""))
    except Exception:
        return None


def check_candidate(
    base_url: str,
    candidate: Dict[str, str],
    candidates: Optional[List[Dict[str, str]]] = None,
    epochs: int = 10,
) -> List[Tuple[str, bool, str, str, str]]:
    """
    Returns tuples:
      (availability_url, availability_ok, epoch_start_iso, epoch_end_iso, location_exact)
    """
    results: List[Tuple[str, bool, str, str, str]] = []

    pool = [
        c for c in (candidates or [candidate])
        if all(k in c for k in ("network", "station", "channel", "starttime"))
    ]
    if not pool:
        return results

    used: set[tuple[str, str, str]] = set()
    max_attempts = max(epochs * 20, len(pool) * 2)
    attempts = 0

    while len(results) < epochs and attempts < max_attempts:
        attempts += 1
        sample = random.choice(pool)
        key = (sample["network"], sample["station"], sample["channel"])
        if key in used:
            continue

        start = _parse_iso(sample.get("starttime"))
        end = _parse_iso(sample.get("endtime")) or datetime.now(timezone.utc).replace(tzinfo=None)
        if not start or not end:
            continue
        if (end - start).total_seconds() < 600:
            continue

        latest_start = end - timedelta(minutes=10)
        if start >= latest_start:
            continue

        epoch_start = start + timedelta(
            seconds=random.randint(0, int((latest_start - start).total_seconds()))
        )
        epoch_end = epoch_start + timedelta(minutes=10)

        s = epoch_start.strftime("%Y-%m-%dT%H:%M:%S")
        e = epoch_end.strftime("%Y-%m-%dT%H:%M:%S")

        net, sta, cha = sample["network"], sample["station"], sample["channel"]
        av = check_availability_query(base_url, net, sta, cha, s, e, location="*")
        available = bool(av["ok"])

        # decide single location: prefer availability's span location > candidate's > ""
        loc_exact = ""
        if av.get("matched_span") and av["matched_span"].get("location"):
            loc_exact = av["matched_span"]["location"]
        elif sample.get("location"):
            loc_exact = sample["location"]

        used.add(key)  # mark only after producing a result
        results.append((av["url"], available, s, e, loc_exact))

    return results
