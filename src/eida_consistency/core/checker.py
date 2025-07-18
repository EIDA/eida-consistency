import logging
import random
from datetime import datetime, timedelta
from eida_consistency.services.availability import check_availability

def parse_datetime(dt_str: str) -> datetime:
    """
    Parse ISO datetime string safely.
    """
    try:
        return datetime.fromisoformat(dt_str.replace("Z", ""))
    except Exception as e:
        logging.warning(f"Invalid datetime in candidate: {e}")
        return None

def check_candidate(base_url: str, candidate: dict, candidates: list = None, epochs: int = 10):
    """
    Check availability for multiple epochs derived from different candidates.

    Args:
        base_url (str): The base FDSN node URL (e.g. https://eida.gein.noa.gr/fdsnws/)
        candidate (dict): A valid candidate containing 'network', 'station', 'channel', 'starttime', 'endtime'
        candidates (list): Optional list of all fetched candidates to choose from
        epochs (int): Number of epochs to test

    Returns:
        List[Tuple[str, bool, str, str]]: (availability_url, is_available, starttime, endtime)
    """
    results = []

    used = set()
    candidates_pool = [c for c in candidates if all(k in c for k in ("network", "station", "channel", "starttime"))]

    while len(results) < epochs and candidates_pool:
        sample = random.choice(candidates_pool)
        key = (sample["network"], sample["station"], sample["channel"])
        if key in used:
            continue
        used.add(key)

        start = parse_datetime(sample["starttime"])
        end = parse_datetime(sample["endtime"]) if sample.get("endtime") else start + timedelta(minutes=30)

        if not start or not end or (end - start).total_seconds() < 600:
            continue

        # Pick a 10-minute random epoch in the window
        max_start = end - timedelta(minutes=10)
        if start >= max_start:
            continue

        epoch_start = start + timedelta(seconds=random.randint(0, int((max_start - start).total_seconds())))
        epoch_end = epoch_start + timedelta(minutes=10)

        epoch_start_str = epoch_start.strftime("%Y-%m-%dT%H:%M:%S")
        epoch_end_str = epoch_end.strftime("%Y-%m-%dT%H:%M:%S")

        net = sample["network"]
        sta = sample["station"]
        cha = sample["channel"]

        url, available = check_availability(
            base_url, net, sta, cha, epoch_start_str, epoch_end_str, return_url=True
        )

        results.append((url, available, epoch_start_str, epoch_end_str))

    return results
