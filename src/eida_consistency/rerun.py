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
    reverify_psd_row,
    is_psd_finding,
)
from eida_consistency.utils.nodes import load_node_url

SCHEMA_VERSION = "1.1"   # 1.1 adds the optional per-row psd_verdict


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
        psd_verdict = reverify_psd_row(base_url, row, verbose)
        # Name the dimension only when the row was flagged on it, so a plain
        # availability/dataselect finding still reads exactly as it used to.
        shown = []
        if row.get("consistent") is False or psd_verdict is None:
            shown.append(verdict)
        else:
            shown.append(f"A/D {verdict}")
        if psd_verdict is not None and (is_psd_finding(row) or row.get("consistent") is False):
            shown.append(f"PSD {psd_verdict}")
        elif psd_verdict is not None and not shown:
            shown.append(f"PSD {psd_verdict}")
        logging.info(f"[{n}/{total}] {_label(row):<16} {_window(row)} ... {'  '.join(shown)}")
        entry = {
            "index": row["index"],
            "label": _label(row),
            "start": row["starttime"],
            "end": row["endtime"],
            "verdict": verdict,
        }
        if psd_verdict is not None:
            entry["psd_verdict"] = psd_verdict
        results.append(entry)

    return {
        "schema_version": SCHEMA_VERSION,
        "node": node,
        "report": report_path,
        "results": results,
    }


_ORDER = ["PERSISTS", "RESOLVED", "REGRESSED", "CONSISTENT", "SKIPPED"]


def _tally(verdicts: list[str]) -> str:
    counts = {k: 0 for k in _ORDER}
    for v in verdicts:
        counts[v] = counts.get(v, 0) + 1
    return ", ".join(f"{counts[k]} {k.lower()}" for k in _ORDER if counts[k])


def render_summary(result: dict) -> str:
    """One-line tally, with a separate PSD clause when PSD was re-checked."""
    results = result["results"]
    if not results:
        return "0 re-run"
    line = f"{len(results)} re-run — " + _tally([r["verdict"] for r in results])
    psd = [r["psd_verdict"] for r in results if r.get("psd_verdict")]
    if psd:
        line += f" | PSD: {_tally(psd)}"
    return line
