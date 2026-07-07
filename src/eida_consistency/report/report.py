"""Report-generation utilities."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from eida_consistency.core.coverage import parse_iso

REPORT_DIR = Path("reports")

# Which service holds the data inside a mismatch gap -> display glyph + label.
_DIRECTION_SYMBOL = {"availability": "▼", "dataselect": "▲"}
_DIRECTION_LABEL = {
    "availability": "Availability: data · Dataselect: NO DATA",
    "dataselect": "Availability: NO DATA · Dataselect: data",
}


def gap_direction_label(who: str) -> str:
    """Glyph + plain-language label for a mismatch gap's direction.

    e.g. ``"availability"`` -> ``"▼ Availability: data · Dataselect: NO DATA"``.
    """
    return f"{_DIRECTION_SYMBOL.get(who, '')} {_DIRECTION_LABEL.get(who, '')}".strip()


def render_gap_table(mismatch: List[Dict[str, Any]]) -> List[str]:
    """Plain-text, column-aligned table of mismatch gaps (for console output).

    Returns ``[]`` when there are no gaps. Columns: mismatch window, duration,
    direction label.
    """
    rows = []
    for m in mismatch or []:
        span = f"{m.get('start', '?')} → {m.get('end', '?')}"
        dur = f"{_gap_duration_seconds(m.get('start', ''), m.get('end', '')):.1f} s"
        rows.append((span, dur, gap_direction_label(m.get("who", ""))))
    if not rows:
        return []
    w_span = max(len("Mismatch (UTC)"), *(len(r[0]) for r in rows))
    w_gap = max(len("Gap"), *(len(r[1]) for r in rows))
    out = [
        f"{'Mismatch (UTC)'.ljust(w_span)}  {'Gap'.ljust(w_gap)}  Disagreement",
        f"{'-' * w_span}  {'-' * w_gap}  {'-' * len('Disagreement')}",
    ]
    for span, dur, label in rows:
        out.append(f"{span.ljust(w_span)}  {dur.ljust(w_gap)}  {label}")
    return out


def _gap_duration_seconds(start: str, end: str) -> float:
    """Seconds spanned by a mismatch gap, or 0.0 if unparseable."""
    s, e = parse_iso(start), parse_iso(end)
    if s is None or e is None:
        return 0.0
    return (e - s).total_seconds()


def build_inconsistencies_table(inconsistent_recs: List[Dict[str, Any]]) -> List[str]:
    """Markdown table with one row per mismatch gap, tagged with direction.

    Channel and window are shown on the first gap row of each record and left
    blank on continuation rows, so multiple gaps in one window read as a group.
    """
    lines = [
        "| Channel | Window (UTC) | Mismatch (UTC) | Gap | Disagreement |",
        "| :--- | :--- | :--- | :---: | :--- |",
    ]
    for r in inconsistent_recs:
        chan = f"{r['network']}.{r['station']}.{r['location']}.{r['channel']}"
        window = f"{r['starttime']} → {r['endtime']}"
        gaps = r.get("mismatch") or []
        if not gaps:
            lines.append(f"| `{chan}` | `{window}` |  |  |  |")
            continue
        for i, m in enumerate(gaps):
            dur = _gap_duration_seconds(m.get("start", ""), m.get("end", ""))
            span = f"{m.get('start', '?')} → {m.get('end', '?')}"
            c = f"`{chan}`" if i == 0 else ""
            w = f"`{window}`" if i == 0 else ""
            lines.append(f"| {c} | {w} | `{span}` | {dur:.1f} s | {gap_direction_label(m.get('who', ''))} |")
    return lines


def render_timeline(window_start, window_end, avail, ds, width: int = 58) -> str:
    """Single-line coverage timeline across ``[window_start, window_end]``.

    ``avail`` / ``ds`` are lists of ``(start_iso, end_iso)`` coverage intervals.
    Each cell is one glyph:

    - ``█`` data in both        ``·`` no data in either
    - ``▼`` availability only (Avail YES / Data NO)
    - ``▲`` dataselect only (Data YES / Avail NO)
    """
    w0, w1 = parse_iso(window_start), parse_iso(window_end)
    total = (w1 - w0).total_seconds() if (w0 and w1) else 0.0
    avail_iv = [(parse_iso(s), parse_iso(e)) for s, e in (avail or [])]
    ds_iv = [(parse_iso(s), parse_iso(e)) for s, e in (ds or [])]

    def sec(x):
        return (x - w0).total_seconds()

    def covered(iv, i):
        if total <= 0:
            return False
        cs, ce = i * total / width, (i + 1) * total / width
        return any(
            s and e and max(cs, sec(s)) < min(ce, sec(e)) - 1e-9 for s, e in iv
        )

    out = []
    for i in range(width):
        a, d = covered(avail_iv, i), covered(ds_iv, i)
        out.append("█" if a and d else "▼" if a else "▲" if d else "·")
    return "".join(out)


def render_detail_gaps(r: Dict[str, Any]) -> List[str]:
    """Detail block for one inconsistent record: ASCII timeline + exact gap list.

    Returns an empty list when the record has no mismatch gaps (consistent or
    skipped records get no timeline).
    """
    gaps = r.get("mismatch") or []
    if not gaps:
        return []
    cov = r.get("coverage") or {}
    timeline = render_timeline(
        r["starttime"], r["endtime"],
        cov.get("availability", []), cov.get("dataselect", []),
    )
    lines = [
        "```",
        timeline,
        "▲ Data YES / Avail NO    ▼ Avail YES / Data NO    █ both    · none",
        "```",
        f"- Gaps ({len(gaps)}):",
    ]
    for m in gaps:
        dur = _gap_duration_seconds(m.get("start", ""), m.get("end", ""))
        lines.append(
            f"  - `{m.get('start', '?')} → {m.get('end', '?')}`  ({dur:.1f} s)  {gap_direction_label(m.get('who', ''))}"
        )
    return lines


def create_report_object(
    node: str,
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


def _make_unique_filename(node: str, timestamp: str, extension: str) -> str:
    """Create a unique file name for the report, derived from its timestamp.

    Scheme: ``{node}_{YYYYMMDD}_{HHMMSS}_{ffffff}.{ext}`` where the last field is
    microseconds. This replaces the former trailing ``_{seed}`` slot (the seed
    mechanism was removed -- a seed cannot reproduce a finding once the node's
    live inventory drifts; reproduce via ``explore``/``check`` instead). The
    4-part underscore shape and numeric last field are preserved so downstream
    filename parsers keep working.

    Deriving the stem from ``summary.timestamp`` (rather than a fresh clock read)
    keeps the ``.json`` and ``.md`` of one run a matched pair, since microsecond
    precision would otherwise differ between two ``datetime.now()`` calls.
    """
    dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    stamp = dt.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"{node.lower()}_{stamp}.{extension}"


def save_report_json(report: Dict[str, Any], report_dir: Path = REPORT_DIR) -> Path:
    """Save the full report as pretty-printed JSON and return the file path."""
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = _make_unique_filename(report["summary"]["node"], report["summary"]["timestamp"], "json")
    filepath = report_dir / filename
    filepath.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return filepath


def save_report_markdown(report: Dict[str, Any], report_dir: Path = REPORT_DIR) -> Path:
    """Save the report as a human-readable Markdown file."""
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = _make_unique_filename(report["summary"]["node"], report["summary"]["timestamp"], "md")
    filepath = report_dir / filename

    summary = report["summary"]
    results = report["results"]
    type_counts = Counter(r.get("dataselect_type", "?") for r in results if r.get("dataselect_type"))
    inconsistent_recs = [r for r in results if r.get("consistent") is False]
    skipped_recs = [r for r in results if not r.get("scoreable", True)]

    md_lines = [f"# EIDA Consistency Report: `{summary['node']}`", ""]

    if inconsistent_recs:
        md_lines.extend(["## Detected Inconsistencies", ""])
        md_lines.extend(build_inconsistencies_table(inconsistent_recs))
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
            ]
        )
        md_lines.extend(render_detail_gaps(r))
        md_lines.append("")

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
