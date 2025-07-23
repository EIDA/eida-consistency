"""Report-generation utilities.

Creates JSON and Markdown summaries for the EIDA-consistency
check results.
"""

import json
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
from typing import List, Dict, Any


def create_report_object(
    node: str, seed: int, epochs: int, duration: int, records: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build a serialisable dictionary summarising a full run."""
    return {
        "summary": {
            "node": node,
            "seed": seed,
            "epochs": epochs,
            "duration": duration,
            "total_checked": len(records),
            "total_consistent": sum(1 for r in records if r["consistent"]),
            "total_inconsistent": sum(1 for r in records if not r["consistent"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "results": records,
    }


def _make_unique_filename(node: str, seed: int, extension: str) -> str:
    """Create a unique file name for the report.

    The leading underscore marks this as a private helper.
    """
    short_time = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{node.lower()}_{seed}_{short_time}.{extension}"


def save_report_json(report: Dict[str, Any], output_dir: str = "reports") -> Path:
    """Save the full report as pretty-printed JSON."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    filename = _make_unique_filename(
        report["summary"]["node"], report["summary"]["seed"], "json"
    )
    filepath = path / filename

    with filepath.open("w") as f:
        json.dump(report, f, indent=2)

    return filepath


def save_report_markdown(report: Dict[str, Any], output_dir: str = "reports") -> Path:
    """Save the report as a human-readable Markdown file."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    filename = _make_unique_filename(
        report["summary"]["node"], report["summary"]["seed"], "md"
    )
    filepath = path / filename

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
        f"- Epochs: `{summary['epochs']}`",
        f"- Duration/epoch: `{summary['duration']} s`",
        f"- Total checks: `{summary['total_checked']}`",
        f"- Consistent: `{summary['total_consistent']}`",
        f"- Inconsistent: `{summary['total_inconsistent']}`",
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