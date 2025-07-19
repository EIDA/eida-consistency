import json
from pathlib import Path
from collections import Counter

def create_report_object(node: str, seed: int, epochs: int, duration: int, records: list):
    return {
        "summary": {
            "node": node,
            "seed": seed,
            "epochs": epochs,
            "duration": duration,
            "total_checked": len(records),
            "total_consistent": sum(1 for r in records if r["consistent"]),
            "total_inconsistent": sum(1 for r in records if not r["consistent"]),
        },
        "results": records,
    }

def save_report_json(report: dict, output_dir: str = "."):
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    filename = f"{report['summary']['node'].lower()}_{report['summary']['seed']}.json"
    filepath = path / filename

    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)

    return filepath

def save_report_markdown(report: dict, output_dir: str = "."):
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    filename = f"{report['summary']['node'].lower()}_{report['summary']['seed']}.md"
    filepath = path / filename

    summary = report["summary"]
    results = report["results"]

    # Type distribution (SingleTrace, MultiTrace, etc.)
    type_counts = Counter(r.get("dataselect_type", "?") for r in results if r.get("dataselect_type"))

    md_lines = [
        f"# EIDA Consistency Report for `{summary['node']}`",
        "",
        f"- **Seed**: `{summary['seed']}`",
        f"- **Epochs**: `{summary['epochs']}`",
        f"- **Duration**: `{summary['duration']}s`",
        f"- **Total Checks**: `{summary['total_checked']}`",
        f"- ✅ Consistent: `{summary['total_consistent']}`",
        f"- ❌ Inconsistent: `{summary['total_inconsistent']}`",
        "",
        "## Dataselect Response Types",
        *(f"- **{key}**: `{value}`" for key, value in sorted(type_counts.items())),
        "",
        "---",
        "",
        "## Full Entry Report",
    ]

    for r in results:
        md_lines.extend([
            f"### {r['network']}.{r['station']}.{r['location']}.{r['channel']}",
            f"- ⏱️ **Time**: `{r['starttime']} → {r['endtime']}`",
            f"- 🌐 **Availability Web Service**: `{r['available']}`",
            f"- 📡 **Dataselect Success**: `{r['dataselect_success']}`",
            f"- 📦 **Dataselect Type**: `{r.get('dataselect_type', '?')}`",
            f"- 📄 **Dataselect Status**: `{r['dataselect_status']}`",
            f"- ⚖️ **Consistency**: `{'✔️' if r['consistent'] else '❌'}`",
            ""
        ])

    with open(filepath, "w") as f:
        f.write("\n".join(md_lines))

    return filepath
