import logging
import random
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional

from eida_consistency.services.availability import check_availability


def parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse ISO-8601 datetime string, return None on failure."""
    try:
        return datetime.fromisoformat(dt_str.replace("Z", ""))
    except Exception as e:
        logging.warning(f"Invalid datetime in candidate: {e}")
        return None


def check_candidate(
    base_url: str,
    candidate: Dict[str, str],
    candidates: Optional[List[Dict[str, str]]] = None,
    epochs: int = 10,
) -> List[Tuple[str, bool, str, str]]:
    """
    Check availability for `epochs` random 10-minute windows.

    Parameters
    ----------
    base_url : str
        FDSN base URL, e.g. https://eida.gein.noa.gr/fdsnws/
    candidate : dict
        Must contain keys: network, station, channel, starttime[, endtime].
    candidates : list[dict] | None
        Pool of candidates to draw from. If None, `candidate` is used alone.
    epochs : int
        Desired number of epochs to test.

    Returns
    -------
    list[tuple[str, bool, str, str]]
        (availability_url, is_available, starttime, endtime)
    """
    results = []
    used = set()

    # Filter valid candidates
    candidates_pool = [
        c for c in (candidates or [candidate])
        if all(k in c for k in ("network", "station", "channel", "starttime"))
    ]

    while len(results) < epochs and candidates_pool:
        sample = random.choice(candidates_pool)
        key = (sample["network"], sample["station"], sample["channel"])

        # Avoid re-checking the same network/station/channel
        if key in used:
            if len(used) >= len(candidates_pool):
                break  # 🔁 Prevent infinite loop when all keys have been used
            continue
        used.add(key)

        # Parse start/end times
        start = parse_datetime(sample["starttime"])
        end = parse_datetime(sample.get("endtime", "")) or (
            start + timedelta(minutes=30) if start else None
        )

        if not start or not end or (end - start).total_seconds() < 600:
            continue  # Skip invalid or too-short time windows

        # Compute latest valid start time for a 10-minute window
        max_start = end - timedelta(minutes=10)
        if start >= max_start:
            continue

        # Pick random 10-minute epoch within the range
        epoch_start = start + timedelta(
            seconds=random.randint(0, int((max_start - start).total_seconds()))
        )
        epoch_end = epoch_start + timedelta(minutes=10)

        epoch_start_str = epoch_start.strftime("%Y-%m-%dT%H:%M:%S")
        epoch_end_str = epoch_end.strftime("%Y-%m-%dT%H:%M:%S")

        net = sample["network"]
        sta = sample["station"]
        cha = sample["channel"]

        # Run availability check
        url, available = check_availability(
            base_url, net, sta, cha,
            epoch_start_str, epoch_end_str,
            return_url=True
        )

        results.append((url, available, epoch_start_str, epoch_end_str))

    return results
