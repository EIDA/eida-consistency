"""Report-generation utilities."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPORT_DIR = Path("reports")


def create_report_object(
    node: str,
    seed: int,
    epochs: int,
    duration: int,
    records: List[Dict[str, Any]],
    candidates_requested: Optional[int] = None,
    candidates_tested: Optional[int] = None,
    station_queries: Optional[int] = None,
    test_duration_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a serializable dictionary summarizing a full run."""
    total_checked = len(records)
    scoreable_records = [r for r in records if r.get("scoreable", True)]
    total_evaluated = len(scoreable_records)
    total_skipped = total_checked - total_evaluated
    total_consistent = sum(1 for r in scoreable_records if r["consistent"] is True)
    total_inconsistent = sum(1 for r in scoreable_records if r["consistent"] is False)
    score = (total_consistent / total_evaluated * 100.0) if total_evaluated > 0 else 0.0

    avail_yes_ds_no = sum(
        1
        for r in scoreable_records
        if r["consistent"] is False and r["available"] and not r["dataselect_success"]
    )
    avail_no_ds_yes = sum(
        1
        for r in scoreable_records
        if r["consistent"] is False and (not r["available"]) and r["dataselect_success"]
    )

    return {
        "summary": {
            "node": node,
            "seed": seed,
            "epochs_requested": epochs,
            "candidates_requested": candidates_requested,
            "candidates_tested": candidates_tested,
            "station_queries": station_queries,
            "duration": duration,
            "test_duration_sec": test_duration_sec,
            "total_checked": total_checked,
            "total_evaluated": total_evaluated,
            "total_skipped": total_skipped,
            "total_consistent": total_consistent,
            "total_inconsistent": total_inconsistent,
            "total_transient": total_skipped,
            "score": round(score, 2),
            "availability_yes_dataselect_no": avail_yes_ds_no,
            "availability_no_dataselect_yes": avail_no_ds_yes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "results": records,
    }


def _make_unique_filename(node: str, seed: int, extension: str) -> str:
    """Create a unique file name for the report."""
    short_time = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{node.lower()}_{short_time}_{seed}.{extension}"


def save_report_json(report: Dict[str, Any], report_dir: Path = REPORT_DIR) -> Path:
    """Save the full report as pretty-printed JSON and return the file path."""
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = _make_unique_filename(report["summary"]["node"], report["summary"]["seed"], "json")
    filepath = report_dir / filename
    filepath.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return filepath


def save_report_markdown(report: Dict[str, Any], report_dir: Path = REPORT_DIR) -> Path:
    """Save the report as a human-readable Markdown file."""
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = _make_unique_filename(report["summary"]["node"], report["summary"]["seed"], "md")
    filepath = report_dir / filename

    summary = report["summary"]
    results = report["results"]
    type_counts = Counter(r.get("dataselect_type", "?") for r in results if r.get("dataselect_type"))
    inconsistent_recs = [r for r in results if r.get("consistent") is False]
    skipped_recs = [r for r in results if not r.get("scoreable", True)]

    md_lines = [f"# EIDA Consistency Report: `{summary['node']}`", ""]

    if inconsistent_recs:
        md_lines.extend(
            [
                "## Detected Inconsistencies",
                "",
                "| Channel | Window (UTC) | Avail | DS | Type | Status |",
                "| :--- | :--- | :---: | :---: | :---: | :--- |",
            ]
        )
        for r in inconsistent_recs:
            chan = f"{r['network']}.{r['station']}.{r['location']}.{r['channel']}"
            window = f"{r['starttime']} → {r['endtime']}"
            avail = "Y" if r["available"] else "N"
            ds = "Y" if r["dataselect_success"] else "N"
            md_lines.append(
                f"| `{chan}` | `{window}` | {avail} | {ds} | {r.get('dataselect_type', '?')} | `{r['dataselect_status']}` |"
            )
        md_lines.append("")
    elif skipped_recs:
        md_lines.extend(
            [
                "## No Scored Inconsistencies",
                "",
                "No scored inconsistencies were detected in this run, but some transient Dataselect failures were skipped.",
                "",
            ]
        )
    else:
        md_lines.extend(["## Status: All Consistent", "", "No inconsistencies were detected in this run.", ""])

    if skipped_recs:
        md_lines.extend(
            [
                "## Service & Network Errors",
                "",
                "The following windows were skipped for scoring because Dataselect failed with a transient error (Connection, Timeout, 5xx).",
                "While these are not counted as data inconsistencies, they may indicate service instability.",
                "",
                "| Channel | Window (UTC) | Avail | DS | Status |",
                "| :--- | :--- | :---: | :---: | :--- |",
            ]
        )
        for r in skipped_recs:
            chan = f"{r['network']}.{r['station']}.{r['location']}.{r['channel']}"
            window = f"{r['starttime']} → {r['endtime']}"
            avail = "Y" if r["available"] else "N"
            ds = "Y" if r["dataselect_success"] else "N"
            status = r.get("consistency_reason") or r["dataselect_status"]
            md_lines.append(f"| `{chan}` | `{window}` | {avail} | {ds} | `{status}` |")
        md_lines.append("")

    md_lines.extend(
        [
            "---",
            "",
            "## Run Summary",
            "",
            f"- Seed: `{summary['seed']}`",
            f"- Time: `{summary['timestamp']}`",
            f"- Epochs requested: `{summary['epochs_requested']}`",
            f"- Candidates requested: `{summary.get('candidates_requested', '?')}`",
            f"- Candidates tested: `{summary.get('candidates_tested', '?')}`",
            f"- Station queries performed: `{summary.get('station_queries', '?')}`",
            f"- Duration/epoch: `{summary['duration']} s`",
            f"- Test runtime: `{summary.get('test_duration_sec', '?')} s`",
            f"- Total checks run: `{summary['total_checked']}`",
            f"- Scored checks: `{summary.get('total_evaluated', summary['total_checked'])}`",
            f"- Skipped checks: `{summary.get('total_skipped', 0)}`",
            f"- Consistent: `{summary['total_consistent']}`",
            f"- Inconsistent: `{summary['total_inconsistent']}`",
            f"- Score: **{summary['score']} %**",
            "",
            "### Quality Breakdown",
            f"- Data Inconsistencies: `{summary['total_inconsistent']}`",
            f"- Service/Network Errors: `{summary.get('total_transient', 0)}`",
            "",
            "### Inconsistency Breakdown",
            f"- Availability says YES, Dataselect says NO: `{summary['availability_yes_dataselect_no']}`",
            f"- Availability says NO, Dataselect says YES: `{summary['availability_no_dataselect_yes']}`",
            "",
            "### Dataselect Response Types",
            *(f"- **{key}**: `{value}`" for key, value in sorted(type_counts.items())),
            "",
            "---",
            "",
            "## Detailed Results",
            "",
        ]
    )

    for r in results:
        if r["consistent"] is True:
            consistency_text = "✔️"
        elif r["consistent"] is False:
            consistency_text = "❌"
        else:
            consistency_text = "Skipped"

        md_lines.extend(
            [
                f"### `{r['network']}.{r['station']}.{r['location']}.{r['channel']}`",
                f"- Window: `{r['starttime']} → {r['endtime']}`",
                f"- Availability: `{r['available']}`",
                f"- Dataselect: `{r['dataselect_success']}`",
                f"- Type: `{r.get('dataselect_type', '?')}`",
                f"- Status: `{r['dataselect_status']}`",
                f"- Scored: `{r.get('scoreable', True)}`",
                f"- Consistent: `{consistency_text}`",
                "",
            ]
        )

    filepath.write_text("\n".join(md_lines), encoding="utf-8")
    return filepath


def delete_old_reports(report_dir: Path = REPORT_DIR, keep: int = 1) -> None:
    """Keep only the latest `keep` reports (json+md pairs) and delete older ones."""
    if not report_dir.exists():
        return

    json_reports = sorted(report_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
    to_delete = json_reports[keep:]

    for json_file in to_delete:
        md_file = json_file.with_suffix(".md")
        for file_path in (json_file, md_file):
            try:
                file_path.unlink()
            except FileNotFoundError:
                pass
