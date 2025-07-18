import logging
import random
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

def pick_random_candidate(candidates: list) -> dict | None:
    """
    Pick a valid random candidate with duration > 2 minutes.
    """
    logging.getLogger(__name__).info("Picking random candidate...")
    random.shuffle(candidates)

    for candidate in candidates:
        try:
            logging.debug(f"Evaluating candidate: {candidate}")
            start = datetime.fromisoformat(candidate["starttime"].replace("Z", ""))
            end_str = candidate.get("endtime")
            end = datetime.fromisoformat(end_str.replace("Z", "")) if end_str else start + timedelta(minutes=10)
            duration = (end - start).total_seconds()

            logging.debug(f"Duration: {duration} seconds")

            if duration < 120:
                logging.debug("Duration too short, skipping.")
                continue

            logging.info("✅ Valid candidate found.")
            return {
                **candidate,
                "starttime": start.isoformat(),
                "endtime": end.isoformat()
            }
        except Exception as e:
            logging.debug(f"Skipping candidate due to error: {e}")
            continue

    logging.warning("No valid candidate found.")
    return None
