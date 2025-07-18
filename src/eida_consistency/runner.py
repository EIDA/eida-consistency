import logging
import random
import concurrent.futures
from datetime import datetime, timedelta

from .services.station import fetch_candidates
from .services.dataselect import dataselect
from .core.checker import check_candidate
from .utils.nodes import load_node_url
from .core.formatter import format_result

def run_consistency_check(
    node: str,
    epochs: int = 10,
    duration: int = 60,
    channels: str = "--",
    seed: int = None,
    delete_old: bool = False,
):
    if seed is not None:
        random.seed(seed)

    base_url = load_node_url(node)

    logging.info(f"📡 Fetching candidates for node: {node}...")
    candidates = fetch_candidates(base_url)

    if not candidates:
        logging.warning("No candidates fetched.")
        return

    logging.info(f"Total candidates fetched: {len(candidates)}")
    logging.info(f"🎲 Picking {epochs} random candidates...\n")

    results = check_candidate(base_url, candidates[0], candidates=candidates, epochs=epochs)

    logging.info("▶ Checking availability + dataselect consistency in parallel:\n")

    def worker(args):
        idx, (url, available, start, end), match = args
        ds_result = dataselect(
            base_url,
            match["network"],
            match["station"],
            match["channel"],
            start,
            end,
            match.get("location", "")
        )
        return format_result(idx, url, available, ds_result, match)

    args_list = []
    for idx, (url, available, start, end) in enumerate(results, 1):
        try:
            parts = url.split("?")[1].split("&")
            net = next(p.split("=")[1] for p in parts if p.startswith("network="))
            sta = next(p.split("=")[1] for p in parts if p.startswith("station="))
            cha = next(p.split("=")[1] for p in parts if p.startswith("channel="))
        except Exception:
            net, sta, cha = "?", "?", "?"

        match = next(
            (c for c in candidates if c["network"] == net and c["station"] == sta and c["channel"] == cha),
            None,
        )
        if match:
            args_list.append((idx, (url, available, start, end), match))

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for output in executor.map(worker, args_list):
            logging.info(output + "\n")

    logging.info(f"✅ Collected {len(args_list)} results.")
    logging.info("📦 Ready to save report.")
