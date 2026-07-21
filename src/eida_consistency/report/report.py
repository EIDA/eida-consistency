"""Report-generation utilities."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from eida_consistency import __version__
from eida_consistency.core.coverage import parse_iso

REPORT_DIR = Path("reports")

# Which service holds the data inside a mismatch gap -> display glyph + label.
_DIRECTION_SYMBOL = {"availability": "▼", "dataselect": "▲", "psd": "▶"}
_DIRECTION_LABEL = {
    "availability": "Availability: data · Dataselect: NO DATA",
    "dataselect": "Availability: NO DATA · Dataselect: data",
    "psd": "Dataselect: data · PSD: NO DATA",
}

_PRESENCE_GLYPH = {
    "availability": ("▼", "▽"),
    "dataselect": ("▲", "△"),
    "psd": ("▶", "▷"),
}


def triad(a_present, d_present, p_present) -> str:
    """Filled/hollow triangle triad: filled=present, hollow=absent, '?'=unknown."""

    def g(service, present):
        if present is None:
            return "?"
        filled, hollow = _PRESENCE_GLYPH[service]
        return filled if present else hollow

    return f"{g('availability', a_present)} {g('dataselect', d_present)} {g('psd', p_present)}"


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
        idx = r.get("index")
        chan_cell = f"[`{chan}`](#rec-{idx})" if idx is not None else f"`{chan}`"
        window = f"{r['starttime']} → {r['endtime']}"
        gaps = r.get("mismatch") or []
        if not gaps:
            lines.append(f"| {chan_cell} | `{window}` |  |  |  |")
            continue
        for i, m in enumerate(gaps):
            dur = _gap_duration_seconds(m.get("start", ""), m.get("end", ""))
            span = f"{m.get('start', '?')} → {m.get('end', '?')}"
            c = chan_cell if i == 0 else ""
            w = f"`{window}`" if i == 0 else ""
            lines.append(f"| {c} | {w} | `{span}` | {dur:.1f} s | {gap_direction_label(m.get('who', ''))} |")
    return lines


def _psd_bucket(rec: Dict[str, Any]) -> Optional[str]:
    """Classify one record's PSD outcome, or None if PSD was not checked.

    Buckets: ``consistent`` (data and PSD both present), ``violation`` (data on/after
    2024-01-01 but no PSD — a real fault), ``pregap`` (data before 2024-01-01 but
    no PSD — informational, PSD not required), ``nodata``, ``skipped``,
    ``unsupported``.
    """
    status = rec.get("psd_status")
    if status is None:
        return None
    if status == "Unsupported":
        return "unsupported"
    if status == "Skipped":
        return "skipped"
    if not rec.get("dataselect_success"):
        return "nodata"
    if rec.get("psd_present"):
        return "consistent"
    return "violation" if rec.get("psd_required") else "pregap"


def _psd_table(rows: List[Dict[str, Any]]) -> List[str]:
    """Channel / window / triangle table for a list of PSD records."""
    out = [
        "| Channel | Window (UTC) | ▼ Avail · ▲ Data · ▶ PSD |",
        "| :--- | :--- | :---: |",
    ]
    for r in rows:
        chan = f"{r['network']}.{r['station']}.{r['location']}.{r['channel']}"
        window = f"{r['starttime']} → {r['endtime']}"
        t = triad(r.get("available"), r.get("dataselect_success"), r.get("psd_present"))
        out.append(f"| `{chan}` | `{window}` | {t} |")
    return out


def build_psd_section(records: List[Dict[str, Any]]) -> List[str]:
    """Verbose, self-explanatory PSD (Availability / Dataselect / PSD) section.

    Returns ``[]`` when PSD checking was disabled (no record has a ``psd_status``).
    Otherwise returns Markdown lines that explain the triangle model, the
    2024-01-01 obligation, a one-line summary, and separate tables for real
    violations (data ≥ 2024 without PSD) and informational pre-2024 gaps.
    """
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    checked = False
    for r in records:
        b = _psd_bucket(r)
        if b is None:
            continue
        checked = True
        buckets.setdefault(b, []).append(r)
    if not checked:
        return []

    consistent = buckets.get("consistent", [])
    violations = buckets.get("violation", [])
    pregaps = buckets.get("pregap", [])
    nodata = buckets.get("nodata", [])
    skipped = buckets.get("skipped", []) + buckets.get("unsupported", [])

    sc = psd_scores(records)
    n_skipped = len(buckets.get("skipped", []))
    n_unsupported = len(buckets.get("unsupported", []))
    _fmt = lambda v: f"{v:.1f}%" if v is not None else "N/A"
    _score_lines = [
        "",
        f"- **PSD compliance (≥2024):** {_fmt(sc['psd_compliance_score'])} "
        f"— over {sc['psd_evaluated_2024']} data-bearing window(s).",
        f"- **PSD coverage (all dates):** {_fmt(sc['psd_coverage_score'])} "
        f"— over {sc['psd_evaluated']} data-bearing window(s).",
    ]
    if n_skipped or n_unsupported:
        _score_lines.append(
            f"- **Network / service note:** {n_skipped} window(s) skipped "
            f"(transient PSD error), {n_unsupported} unsupported (node has no PSD "
            f"service) — excluded from the PSD scores."
        )

    lines = [
        "## PSD Consistency — Availability / Dataselect / PSD",
        "",
        "Each tested window is cross-checked across three EIDA services. "
        "**Dataselect** (the actual waveform bytes) is the ground truth; each "
        "window is compared against the **Availability** service and against the "
        "**PSD** service (`eidaws/psd/1/coverage`). PSD is computed once per UTC "
        "day, so \"PSD present\" means the window's day has a valid PSD record.",
        "",
        "Coverage is shown as three triangles per window — **▼ Availability**, "
        "**▲ Dataselect**, **▶ PSD**. A *filled* triangle means that service has "
        "data for the window; a *hollow* triangle (▽ △ ▷) means it does not.",
        "",
        "EIDA only **requires** PSD for data on or after **2024-01-01**, so a "
        "missing PSD is judged differently by date:",
        "",
        "- **Violation** — a window on/after 2024-01-01 where dataselect has data "
        "but PSD is missing (`▲ ▷`). The node is not meeting its PSD obligation.",
        "- **Pre-2024 gap** — the same pattern before 2024-01-01. PSD was not "
        "required then, so it is only informational and is **not** counted as a "
        "fault.",
        "",
        f"**PSD summary:** {len(consistent)} consistent · "
        f"{len(violations)} violation(s) — data ≥ 2024 without PSD · "
        f"{len(pregaps)} pre-2024 gap(s) (informational) · "
        f"{len(nodata)} window(s) with no data"
        + (f" · {len(skipped)} skipped/unsupported" if skipped else "")
        + ".",
        "",
        "### PSD Violations — data on/after 2024-01-01 but PSD missing",
        "",
        "These are genuine inconsistencies: the node holds the waveform data but "
        "did not compute or serve the required PSD.",
        "",
    ]
    _i = next(i for i, l in enumerate(lines) if l.startswith("**PSD summary:**"))
    lines[_i + 1:_i + 1] = _score_lines

    if violations:
        lines += _psd_table(violations)
    else:
        lines.append(
            "None — every window on/after 2024-01-01 that had waveform data also "
            "had a valid PSD. ✅"
        )
    lines += [
        "",
        "### PSD gaps before 2024-01-01 (informational — PSD not yet required)",
        "",
        "Listed for completeness only; these are **not** violations because EIDA "
        "did not require PSD before 2024-01-01.",
        "",
    ]
    if pregaps:
        lines += _psd_table(pregaps)
    else:
        lines.append("None.")
    lines.append("")
    return lines


def psd_scores(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Two PSD scores over PSD-scoreable windows (see design 2026-07-21).

    Scoreable = dataselect returned data AND the PSD check got a definitive
    answer (status Consistent/Inconsistent). Skipped, Unsupported, and no-data
    windows are excluded — mirroring how A/D excludes transient failures.
    Returns the four counts and two nullable scores (None => N/A).
    """
    def scoreable(r):
        return bool(r.get("dataselect_success")) and \
            r.get("psd_status") in ("Consistent", "Inconsistent")

    pool = [r for r in records if scoreable(r)]
    evaluated = len(pool)
    present = sum(1 for r in pool if r.get("psd_present"))
    pool_2024 = [r for r in pool if r.get("psd_required") is True]
    evaluated_2024 = len(pool_2024)
    present_2024 = sum(1 for r in pool_2024 if r.get("psd_present"))

    coverage = round(present / evaluated * 100.0, 2) if evaluated else None
    compliance = round(present_2024 / evaluated_2024 * 100.0, 2) if evaluated_2024 else None

    return {
        "psd_evaluated": evaluated,
        "psd_present": present,
        "psd_evaluated_2024": evaluated_2024,
        "psd_present_2024": present_2024,
        "psd_compliance_score": compliance,
        "psd_coverage_score": coverage,
    }


def render_timeline(window_start, window_end, avail, ds, width: int = 58, gaps=None,
                    psd_present=None) -> str:
    """Single-line coverage timeline across ``[window_start, window_end]``.

    ``avail`` / ``ds`` are lists of ``(start_iso, end_iso)`` coverage intervals.
    Each cell is one glyph:

    - ``█`` data in both        ``·`` no data in either
    - ``▼`` availability only (Avail YES / Data NO)
    - ``▲`` dataselect only (Data YES / Avail NO)

    If ``gaps`` (the mismatch list) is given, a ``|`` is drawn at the boundary
    between consecutive gaps so distinct gaps stay visible even when the
    consistent break between them is narrower than one cell.
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

    if psd_present is not None:
        def lane(iv):
            return "".join("█" if covered(iv, i) else "░" for i in range(width))
        psd_lane = ("█" if psd_present else "░") * width
        return (f"▼ Avail  {lane(avail_iv)}\n"
                f"▲ Data   {lane(ds_iv)}\n"
                f"▶ PSD    {psd_lane}")

    out = []
    for i in range(width):
        a, d = covered(avail_iv, i), covered(ds_iv, i)
        out.append("█" if a and d else "▼" if a else "▲" if d else "·")

    if gaps and total > 0:
        ordered = sorted(gaps, key=lambda m: m.get("start", ""))
        for a, b in zip(ordered, ordered[1:]):
            ae, bs = parse_iso(a.get("end")), parse_iso(b.get("start"))
            if ae is None or bs is None:
                continue
            mid = (sec(ae) + sec(bs)) / 2
            cell = min(width - 1, max(0, int(mid / total * width)))
            out[cell] = "|"

    return "".join(out)


def _query_time(iso: str) -> str:
    """Format an ISO timestamp for an FDSN query string (drop the UTC suffix)."""
    return str(iso).replace("+00:00", "").replace("Z", "")


def _swap_query_time(url: str, key: str, value: str) -> str:
    """Return ``url`` with the ``key=...`` query parameter set to ``value``."""
    return re.sub(rf"([?&]{re.escape(key)}=)[^&]*", lambda m: m.group(1) + value, url)


def render_request_lines(r: Dict[str, Any]) -> List[str]:
    """The actual availability/dataselect requests + status codes (issue #49).

    Only emitted for inconsistent records, so the report shows exactly what was
    queried and what each service answered.
    """
    if r.get("consistent") is not False:
        return []
    lines = []
    if r.get("url"):
        lines.append(f"- Availability request: `{r['url']}` → HTTP {r.get('availability_status', '?')}")
    if r.get("dataselect_url"):
        lines.append(f"- Dataselect request: `{r['dataselect_url']}` → {r.get('dataselect_status', '?')}")
    return lines


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
        cov.get("availability", []), cov.get("dataselect", []), gaps=gaps,
    )
    lines = [
        "```",
        timeline,
        "▲ Data YES / Avail NO    ▼ Avail YES / Data NO    █ both    · none    | gap boundary",
        "```",
        f"- Gaps ({len(gaps)}):",
    ]
    for m in gaps:
        dur = _gap_duration_seconds(m.get("start", ""), m.get("end", ""))
        lines.append(
            f"  - `{m.get('start', '?')} → {m.get('end', '?')}`  ({dur:.1f} s)  {gap_direction_label(m.get('who', ''))}"
        )
        # queries narrowed to this exact gap range, so the inconsistency is reproducible
        gs, ge = _query_time(m.get("start", "")), _query_time(m.get("end", ""))
        if r.get("url"):
            aq = _swap_query_time(_swap_query_time(r["url"], "start", gs), "end", ge)
            lines.append(f"    - availability: `{aq}`")
        if r.get("dataselect_url"):
            dq = _swap_query_time(_swap_query_time(r["dataselect_url"], "starttime", gs), "endtime", ge)
            lines.append(f"    - dataselect: `{dq}`")
    return lines


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

    data_yes_psd_no = sum(1 for r in records if r.get("psd_consistent") is False)
    psd_unsupported = sum(1 for r in records if r.get("psd_status") == "Unsupported")
    psd_skipped = sum(1 for r in records if r.get("psd_status") == "Skipped")
    psd_required_count = sum(1 for r in records if r.get("psd_required") is True)
    _pscores = psd_scores(records)

    return {
        "summary": {
            "version": __version__,
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
            "data_yes_psd_no": data_yes_psd_no,
            "psd_unsupported": psd_unsupported,
            "psd_skipped": psd_skipped,
            "psd_required_count": psd_required_count,
            **_pscores,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "results": records,
    }


def _make_unique_filename(node: str, seed: int, extension: str) -> str:
    """Create a unique file name for the report.

    OPEN ISSUE (seed removal): the trailing ``_{seed}`` here, and the ``seed``
    field in the run summary, are slated for removal because a seed does not
    reproduce a finding across time (the live station inventory drifts, so the
    same seed picks different channels later). Before removing, confirm the
    Oculus / dmtri pipeline does not parse the seed from the filename or read
    ``summary.seed`` — those consume these report files. Until then, kept as-is.
    """
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

    md_lines.extend(build_psd_section(results))

    md_lines.extend(
        [
            "---",
            "",
            "## Run Summary",
            "",
            f"- Tool version: `{summary.get('version', '?')}`",
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

        idx = r.get("index")
        if idx is not None:
            md_lines.append(f'<a id="rec-{idx}"></a>')
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
        md_lines.extend(render_request_lines(r))
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
