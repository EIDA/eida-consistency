"""Re-run (re-verify) the inconsistencies of a report.

Unlike ``explore``, this does no boundary walking and emits no dmtri commands:
it re-checks each target row's exact reported window and reports a verdict
(PERSISTS / RESOLVED / SKIPPED, plus CONSISTENT / REGRESSED under ``--all``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from eida_consistency.reverify import (
    load_report,
    select_targets,
    reverify_row,
)
from eida_consistency.utils.nodes import load_node_url

SCHEMA_VERSION = "1.0"


def _label(row: dict) -> str:
    return f"{row['network']}.{row['station']}.{row['location']}.{row['channel']}"


def _window(row: dict) -> str:
    """``start → end``; show the end date too only when it differs from start."""
    start, end = str(row["starttime"]), str(row["endtime"])
    sd, st = (start.split("T") + [""])[:2]
    ed, et = (end.split("T") + [""])[:2]
    end_disp = et if ed == sd else f"{ed} {et}"
    return f"{sd} {st} → {end_disp}"


def rerun_report(
    report_path: str | Path,
    indices: Optional[List[int]] = None,
    all_rows: bool = False,
    verbose: bool = False,
) -> dict:
    """Re-verify a report's rows and return a machine-readable result dict."""
    report_path = str(report_path)
    report = load_report(report_path)
    node = report["summary"]["node"]
    targets = select_targets(report, indices, include_consistent=all_rows)

    if not targets:
        logging.info("No rows to re-run (all consistent, or no matching index).")
        return {
            "schema_version": SCHEMA_VERSION,
            "node": node,
            "report": report_path,
            "results": [],
        }

    base_url = load_node_url(node)
    total = len(targets)
    logging.info(f"Re-running {total} finding(s) from {Path(report_path).name} (node {node})")

    results: list[dict] = []
    for n, row in enumerate(targets, start=1):
        verdict = reverify_row(base_url, row, verbose)
        logging.info(f"[{n}/{total}] {_label(row):<16} {_window(row)} ... {verdict}")
        results.append(
            {
                "index": row["index"],
                "label": _label(row),
                "start": row["starttime"],
                "end": row["endtime"],
                "verdict": verdict,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "node": node,
        "report": report_path,
        "results": results,
    }


def render_summary(result: dict) -> str:
    """One-line tally, e.g. ``6 re-run — 3 persists, 2 resolved, 1 skipped``."""
    results = result["results"]
    if not results:
        return "0 re-run"
    order = ["PERSISTS", "RESOLVED", "REGRESSED", "CONSISTENT", "SKIPPED"]
    counts = {k: 0 for k in order}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    parts = [f"{counts[k]} {k.lower()}" for k in order if counts[k]]
    return f"{len(results)} re-run — " + ", ".join(parts)


def render_table(result: dict) -> List[str]:
    """Aligned verdict table for human output."""
    results = result["results"]
    if not results:
        return []
    idx_w = max(len(str(r["index"])) for r in results)
    idx_w = max(idx_w, len("#"))
    lbl_w = max(len(r["label"]) for r in results)
    lbl_w = max(lbl_w, len("Stream"))
    win_w = max(len(_window_from(r)) for r in results)
    win_w = max(win_w, len("Window (UTC)"))

    lines = [
        f"  {'#':>{idx_w}}  {'Stream':<{lbl_w}}  {'Window (UTC)':<{win_w}}  Verdict",
        f"  {'-' * idx_w}  {'-' * lbl_w}  {'-' * win_w}  {'-' * 9}",
    ]
    for r in results:
        lines.append(
            f"  {r['index']:>{idx_w}}  {r['label']:<{lbl_w}}  "
            f"{_window_from(r):<{win_w}}  {r['verdict']}"
        )
    return lines


def _window_from(r: dict) -> str:
    return _window({"starttime": r["start"], "endtime": r["end"]})
