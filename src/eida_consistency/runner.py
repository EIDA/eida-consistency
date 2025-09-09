"""CLI entry point and orchestration for running consistency checks."""
from __future__ import annotations

import logging
import random
import concurrent.futures
import json
import sys
from pathlib import Path

from .services.station import fetch_candidates
from .services.dataselect import dataselect
from .core.checker import check_candidate
from .utils.nodes import load_node_url
from .core.formatter import format_result
from .report.report import (
    create_report_object,
    save_report_json,
    save_report_markdown,
    REPORT_DIR,
)


def run_consistency_check(
    node: str,
    epochs: int = 10,
    duration: int = 600,
    seed: int | None = None,
    delete_old: bool = False,
    max_workers: int = 10,
    print_stdout: bool = False,
    report_dir: Path = REPORT_DIR,
) -> None:
    if seed is None:
        seed = random.randint(0, 999_999)
        logging.info(f" Using generated seed: {seed}")
    else:
        logging.info(f" Using provided seed: {seed}")

    random.seed(seed)
    base_url = load_node_url(node)

    logging.info(f" Fetching random candidates for node: {node}...")

    # Always fetch 5 × epochs (minimum 20) to ensure enough usable candidates
    target_candidates = max(epochs * 5, 20)
    candidates = fetch_candidates(base_url, max_stations=target_candidates)

    if not candidates:
        logging.warning("No candidates fetched.")
        return

    # Each item: (url, available, start, end, loc_exact, matched_span)
    results, stats = check_candidate(
        base_url,
        candidates[0],
        candidates=candidates,
        epochs=epochs,
        duration=duration,
    )

    logging.info("▶ Checking availability + dataselect consistency in parallel:\n")

    all_logs, all_records = [], []

    def worker(args):
        idx, (url, available, start, end, loc_exact, matched_span), match = args
        loc_final = loc_exact or match.get("location", "")
        ds_result = dataselect(
            base_url,
            match["network"], match["station"], match["channel"],
            start, end, loc_final
        )
        log = format_result(
            idx,
            url,
            available,
            ds_result,
            {**match, "location": loc_final, "matched_span": matched_span},
        )
        record = {
            "index": idx,
            "url": url,
            "network": match["network"],
            "station": match["station"],
            "channel": match["channel"],
            "location": loc_final,
            "available": available,
            "dataselect_success": ds_result["success"],
            "dataselect_status": ds_result["status"],
            "dataselect_type": ds_result.get("type", "?"),
            "consistent": available == ds_result["success"],
            "starttime": str(start),
            "endtime": str(end),
            "debug": ds_result.get("debug", ""),
            "matched_span": {
                "start": matched_span.get("start") if matched_span else None,
                "end": matched_span.get("end") if matched_span else None,
                "location": matched_span.get("location") if matched_span else None,
            },
        }
        return log, record

    args_list = []
    for idx, (url, available, start, end, loc_exact, matched_span) in enumerate(results, 1):
        try:
            parts = url.split("?")[1].split("&")
            net = next(p.split("=")[1] for p in parts if p.startswith("network="))
            sta = next(p.split("=")[1] for p in parts if p.startswith("station="))
            cha = next(p.split("=")[1] for p in parts if p.startswith("channel="))
        except Exception:
            net, sta, cha = "?", "?", "?"

        match = next(
            (
                c
                for c in candidates
                if c["network"] == net and c["station"] == sta and c["channel"] == cha
            ),
            None,
        )
        if match:
            args_list.append((idx, (url, available, start, end, loc_exact, matched_span), match))

    pool_size = max(1, min(max_workers, len(args_list)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=pool_size) as executor:
        futures = [executor.submit(worker, a) for a in args_list]
        for fut in concurrent.futures.as_completed(futures):
            log, record = fut.result()
            logging.info(log + "\n")
            all_logs.append(log)
            all_records.append(record)

    logging.info(f"✅ Collected {len(all_records)} results.")

    # --- Save reports into chosen report_dir ---
    report = create_report_object(
        node=node,
        seed=seed,
        epochs=epochs,
        duration=duration,
        records=all_records,
    )
    report["summary"].update(stats)  # merge candidate stats into summary

    json_path = save_report_json(report, report_dir=report_dir)
    md_path = save_report_markdown(report, report_dir=report_dir)
    logging.info(f"📁 Report saved to: {json_path}")
    logging.info(f"📜 Markdown saved to: {md_path}")

    if print_stdout:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.flush()
