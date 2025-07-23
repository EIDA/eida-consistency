"""CLI entry point and orchestration for running consistency checks."""
import logging
import random
import concurrent.futures
from datetime import datetime

from .services.station import fetch_candidates
from .services.dataselect import dataselect
from .core.checker import check_candidate
from .utils.nodes import load_node_url
from .core.formatter import format_result
from .report.report import create_report_object, save_report_json, save_report_markdown

def run_consistency_check(
    node: str,
    epochs: int = 10,
    duration: int = 60,
    seed: int = None,
    delete_old: bool = False,
)-> None:
    """Run the consistency check."""
    if seed is None:
        seed = random.randint(0, 999999)
        logging.info(f" Using generated seed: {seed}")
    else:
        logging.info(f" Using provided seed: {seed}")

    random.seed(seed)
    base_url = load_node_url(node)

    logging.info(f" Fetching candidates for node: {node}...")
    candidates = fetch_candidates(base_url)

    if not candidates:
        logging.warning("No candidates fetched.")
        return

    logging.info(f"Total candidates fetched: {len(candidates)}")
    logging.info(f" Picking {epochs} random candidates...\n")

    results = check_candidate(base_url, candidates[0], candidates=candidates, epochs=epochs)

    logging.info("▶ Checking availability + dataselect consistency in parallel:\n")

    all_logs = []
    all_records = []

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
        log = format_result(idx, url, available, ds_result, match)
        record = {
            "index": idx,
            "url": url,
            "network": match["network"],
            "station": match["station"],
            "channel": match["channel"],
            "location": match.get("location", ""),
            "available": available,
            "dataselect_success": ds_result["success"],
            "dataselect_status": ds_result["status"],
            "dataselect_type": ds_result.get("type", "?"),
            "consistent": available == ds_result["success"],
            "starttime": str(start),
            "endtime": str(end),
        }
        return log, record

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
        for log, record in executor.map(worker, args_list):
            logging.info(log + "\n")
            all_logs.append(log)
            all_records.append(record)

    logging.info(f"✅ Collected {len(all_records)} results.")

    # Save reports (both JSON and Markdown)
    report = create_report_object(node=node, seed=seed, epochs=epochs, duration=duration, records=all_records)
    json_path = save_report_json(report)
    md_path = save_report_markdown(report)

    logging.info(f"📁 Report saved to: {json_path}")
    logging.info(f"📜 Markdown saved to: {md_path}")