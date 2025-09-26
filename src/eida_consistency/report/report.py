"""Report-generation utilities.

Creates JSON and Markdown summaries for the EIDA-consistency
check results and provides cleanup helpers.
"""

import json
import os
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# Default directory where reports are stored
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
    """Build a serialisable dictionary summarising a full run."""

    total_checked = len(records)
    total_consistent = sum(1 for r in records if r["consistent"])
    total_inconsistent = total_checked - total_consistent
    score = (total_consistent / total_checked * 100.0) if total_checked > 0 else 0.0

    # Breakdown by inconsistency type
    avail_yes_ds_no = sum(
        1 for r in records if r["available"] and not r["dataselect_success"]
    )
    avail_no_ds_yes = sum(
        1 for r in records if (not r["available"]) and r["dataselect_success"]
    )

    return {
        "summary": {
            "node": node,
            "seed": seed,
            "epochs_requested": epochs,
            "candidates_requested": candidates_requested,
            "candidates_tested": candidates_tested,
            "station_queries": station_queries,
            "duration": duration,  # per-epoch duration window
            "test_duration_sec": test_duration_sec,  
            "total_checked": total_checked,
            "total_consistent": total_consistent,
            "total_inconsistent": total_inconsistent,
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
    return f"{node.lower()}_{seed}_{short_time}.{extension}"


def save_report_json(report: Dict[str, Any], report_dir: Path = REPORT_DIR) -> Path:
    """Save the full report as pretty-printed JSON and return the file path."""
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = _make_unique_filename(
        report["summary"]["node"], report["summary"]["seed"], "json"
    )
    filepath = report_dir / filename
    filepath.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return filepath


def save_report_markdown(report: Dict[str, Any], report_dir: Path = REPORT_DIR) -> Path:
    """Save the report as a human-readable Markdown file."""
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = _make_unique_filename(
        report["summary"]["node"], report["summary"]["seed"], "md"
    )
    filepath = report_dir / filename

    summary = report["summary"]
    results = report["results"]
    type_counts = Counter(
        r.get("dataselect_type", "?") for r in results if r.get("dataselect_type")
    )

    md_lines = [
        f"# EIDA Consistency Report: `{summary['node']}`",
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
        f"- Consistent: `{summary['total_consistent']}`",
        f"- Inconsistent: `{summary['total_inconsistent']}`",
        f"- Score: **{summary['score']} %**",
        "",
        "## Inconsistency Breakdown",
        f"- Availability says YES, Dataselect says NO: `{summary['availability_yes_dataselect_no']}`",
        f"- Availability says NO, Dataselect says YES: `{summary['availability_no_dataselect_yes']}`",
        "",
        "## Dataselect Response Types",
        *(f"- **{key}**: `{value}`" for key, value in sorted(type_counts.items())),
        "",
        "---",
        "",
        "## Detailed Results",
    ]

    for r in results:
        md_lines.extend(
            [
                f"### `{r['network']}.{r['station']}.{r['location']}.{r['channel']}`",
                f"- Window: `{r['starttime']} → {r['endtime']}`",
                f"- Availability: `{r['available']}`",
                f"- Dataselect: `{r['dataselect_success']}`",
                f"- Type: `{r.get('dataselect_type', '?')}`",
                f"- Status: `{r['dataselect_status']}`",
                f"- Consistent: `{'✔️' if r['consistent'] else '❌'}`",
                "",
            ]
        )

    filepath.write_text("\n".join(md_lines))
    return filepath


def delete_old_reports(report_dir: Path = REPORT_DIR, keep: int = 1) -> None:
    """Keep only the latest `keep` reports (json+md pairs) and delete older ones."""
    if not report_dir.exists():
        return

    json_reports = sorted(report_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
    to_delete = json_reports[keep:]

    for json_file in to_delete:
        md_file = json_file.with_suffix(".md")
        for f in (json_file, md_file):
            try:
                f.unlink()
            except FileNotFoundError:
                pass
