import json
import time

import eida_consistency.report.report as report


def make_record(
    consistent=True,
    available=True,
    ds_success=True,
    ds_type="M",
    status=200,
    scoreable=True,
    reason=None,
):
    return {
        "network": "XX",
        "station": "STA",
        "location": "00",
        "channel": "BHZ",
        "starttime": "2023-01-01T00:00:00",
        "endtime": "2023-01-01T01:00:00",
        "available": available,
        "dataselect_success": ds_success,
        "dataselect_type": ds_type,
        "dataselect_status": status,
        "consistent": consistent,
        "scoreable": scoreable,
        "consistency_reason": reason,
    }


def test_create_report_object_basic():
    records = [
        make_record(True),
        make_record(False, available=True, ds_success=False),
        make_record(None, available=True, ds_success=False, status="ConnectionError", scoreable=False, reason="TransientDataselectFailure"),
    ]
    rep = report.create_report_object(
        "NODE",
        123,
        5,
        600,
        records,
        candidates_requested=5,
        candidates_tested=3,
        station_queries=1,
    )
    summary = rep["summary"]
    assert summary["node"] == "NODE"
    assert summary["total_checked"] == 3
    assert summary["total_evaluated"] == 2
    assert summary["total_skipped"] == 1
    assert summary["total_consistent"] == 1
    assert summary["total_inconsistent"] == 1
    assert summary["total_transient"] == 1
    assert summary["score"] == 50.0
    assert "availability_yes_dataselect_no" in summary
    assert "availability_no_dataselect_yes" in summary
    assert isinstance(summary["timestamp"], str)


def test_create_report_object_includes_tool_version():
    import eida_consistency

    rep = report.create_report_object("NODE", 1, 1, 600, [])
    assert rep["summary"]["version"] == eida_consistency.__version__
    assert isinstance(rep["summary"]["version"], str)
    assert rep["summary"]["version"]


def test_create_report_object_empty_records():
    rep = report.create_report_object("NODE", 1, 1, 600, [])
    assert rep["summary"]["score"] == 0.0
    assert rep["summary"]["total_checked"] == 0
    assert rep["summary"]["total_skipped"] == 0


def test_make_unique_filename_format():
    fname = report._make_unique_filename("NODE", 42, "json")
    assert fname.startswith("node_")
    assert "_42.json" in fname
    assert len(fname.split("_")) == 4


def test_save_report_json_and_content(tmp_path):
    recs = [make_record()]
    rep = report.create_report_object("NODE", 1, 1, 600, recs)
    path = report.save_report_json(rep, report_dir=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["summary"]["node"] == "NODE"


def test_save_report_markdown_with_skipped(tmp_path):
    recs = [
        make_record(True, ds_type="A"),
        make_record(False, ds_type="B"),
        make_record(None, ds_success=False, ds_type="Error", status="ConnectionError", scoreable=False, reason="TransientDataselectFailure"),
    ]
    rep = report.create_report_object("NODE", 2, 3, 600, recs)
    path = report.save_report_markdown(rep, report_dir=tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "# EIDA Consistency Report" in text
    assert "## Detected Inconsistencies" in text
    assert "## Service & Network Errors" in text
    assert "Quality Breakdown" in text
    assert "Service/Network Errors: `1`" in text
    assert "Scored checks" in text
    import eida_consistency
    assert f"Tool version: `{eida_consistency.__version__}`" in text
    assert "Skipped checks" in text
    assert "TransientDataselectFailure" in text
    assert "| Channel | Window (UTC) | Mismatch (UTC) | Gap | Disagreement |" in text


def test_render_gap_table_plaintext_aligned():
    gaps = [
        {"start": "2014-02-15T05:18:25.006900+00:00",
         "end": "2014-02-15T05:19:01.606900+00:00", "who": "availability"},
        {"start": "2014-02-15T05:14:00+00:00",
         "end": "2014-02-15T05:15:30+00:00", "who": "dataselect"},
    ]
    lines = report.render_gap_table(gaps)
    text = "\n".join(lines)
    assert "Mismatch (UTC)" in text and "Gap" in text and "Disagreement" in text
    assert "36.6 s" in text
    assert "90.0 s" in text
    assert "▼ Availability: data · Dataselect: NO DATA" in text
    assert "▲ Availability: NO DATA · Dataselect: data" in text
    # rows are column-aligned: the duration column starts at the same offset
    body = [l for l in lines if "▼" in l or "▲" in l]
    assert body[0].index("36.6 s") == body[1].index("90.0 s")


def test_render_gap_table_empty():
    assert report.render_gap_table([]) == []


def _inconsistent_rec(index=5):
    rec = make_record(False)
    rec["index"] = index
    rec["starttime"] = "2014-02-15T05:09:53"
    rec["endtime"] = "2014-02-15T05:19:53"
    rec["url"] = ("https://node/fdsnws/availability/1/query?network=FR&station=MLS&location=*"
                  "&channel=HHN&start=2014-02-15T05:09:53&end=2014-02-15T05:19:53"
                  "&format=text&merge=quality,overlap&includerestricted=FALSE")
    rec["availability_status"] = 200
    rec["dataselect_url"] = ("https://node/fdsnws/dataselect/1/query?network=FR&station=MLS&location="
                             "&channel=HHN&starttime=2014-02-15T05:09:53&endtime=2014-02-15T05:19:53&nodata=204")
    rec["dataselect_status"] = "OK"
    rec["mismatch"] = [{"start": "2014-02-15T05:18:25+00:00",
                        "end": "2014-02-15T05:19:01+00:00", "who": "availability"}]
    rec["coverage"] = {"availability": [["2014-02-15T05:17:09", "2014-02-15T05:19:01"]],
                       "dataselect": [["2014-02-15T05:17:09", "2014-02-15T05:18:25"]]}
    return rec


def test_table_channel_links_to_detail_anchor():
    text = "\n".join(report.build_inconsistencies_table([_inconsistent_rec(index=7)]))
    assert "[`XX.STA.00.BHZ`](#rec-7)" in text


def test_detail_has_anchor_for_record(tmp_path):
    rep = report.create_report_object("NODE", 1, 1, 600, [_inconsistent_rec(index=7)])
    text = report.save_report_markdown(rep, report_dir=tmp_path).read_text(encoding="utf-8")
    assert '<a id="rec-7">' in text


def test_detail_gaps_include_gap_scoped_queries():
    # full-window request stays; each gap also gets queries scoped to the gap range
    lines = report.render_detail_gaps(_inconsistent_rec())
    text = "\n".join(lines)
    # availability query narrowed to the gap window 05:18:25 -> 05:19:01
    assert "availability/1/query" in text
    assert "start=2014-02-15T05:18:25" in text
    assert "end=2014-02-15T05:19:01" in text
    # dataselect query narrowed to the gap window
    assert "dataselect/1/query" in text
    assert "starttime=2014-02-15T05:18:25" in text
    assert "endtime=2014-02-15T05:19:01" in text
    # the full window times are NOT what the gap queries use
    assert "start=2014-02-15T05:09:53" not in text


def test_detail_shows_requests_and_status_for_inconsistency(tmp_path):
    rep = report.create_report_object("NODE", 1, 1, 600, [_inconsistent_rec(index=5)])
    text = report.save_report_markdown(rep, report_dir=tmp_path).read_text(encoding="utf-8")
    assert "availability/1/query?network=FR&station=MLS" in text
    assert "dataselect/1/query?network=FR&station=MLS" in text
    assert "HTTP 200" in text          # availability status
    assert "Dataselect request" in text and "OK" in text


def test_gap_direction_label():
    assert report.gap_direction_label("availability") == "▼ Availability: data · Dataselect: NO DATA"
    assert report.gap_direction_label("dataselect") == "▲ Availability: NO DATA · Dataselect: data"


def test_inconsistencies_table_one_row_per_gap_with_direction():
    rec = make_record(False)
    rec["mismatch"] = [
        {"start": "2014-02-15T05:18:25.006900+00:00",
         "end": "2014-02-15T05:19:01.606900+00:00", "who": "availability"},
    ]
    text = "\n".join(report.build_inconsistencies_table([rec]))
    assert "| Channel | Window (UTC) | Mismatch (UTC) | Gap | Disagreement |" in text
    assert "Availability: data · Dataselect: NO DATA" in text
    assert "▼" in text
    assert "36.6 s" in text


def test_inconsistencies_table_dataselect_direction():
    rec = make_record(False)
    rec["mismatch"] = [
        {"start": "2020-01-01T00:04:00+00:00", "end": "2020-01-01T00:05:30+00:00", "who": "dataselect"},
    ]
    text = "\n".join(report.build_inconsistencies_table([rec]))
    assert "Availability: NO DATA · Dataselect: data" in text
    assert "▲" in text


def test_inconsistencies_table_multiple_gaps_blank_continuation():
    rec = make_record(False)
    rec["mismatch"] = [
        {"start": "2020-01-01T00:01:00+00:00", "end": "2020-01-01T00:02:30+00:00", "who": "availability"},
        {"start": "2020-01-01T00:04:00+00:00", "end": "2020-01-01T00:05:30+00:00", "who": "dataselect"},
    ]
    lines = report.build_inconsistencies_table([rec])
    # the channel name appears on only the first of the two gap rows
    chan_rows = [l for l in lines if "XX.STA.00.BHZ" in l]
    assert len(chan_rows) == 1


def test_render_timeline_availability_only_uses_down_triangle():
    line = report.render_timeline(
        "2014-02-15T05:09:53", "2014-02-15T05:19:53",
        [("2014-02-15T05:17:09.6", "2014-02-15T05:19:01.6")],
        [("2014-02-15T05:17:09.6", "2014-02-15T05:18:25.0")],
        width=58,
    )
    assert len(line) == 58
    assert "█" in line          # both services have data
    assert "▼" in line          # availability-only tail (Avail YES / Data NO)
    assert "▲" not in line
    assert "·" in line          # empty lead-in (both empty)


def test_markdown_detail_includes_timeline_and_gaps(tmp_path):
    rec = make_record(False)
    rec["starttime"] = "2014-02-15T05:09:53"
    rec["endtime"] = "2014-02-15T05:19:53"
    rec["mismatch"] = [{"start": "2014-02-15T05:18:25.006900+00:00",
                        "end": "2014-02-15T05:19:01.606900+00:00", "who": "availability"}]
    rec["coverage"] = {
        "availability": [["2014-02-15T05:17:09.6", "2014-02-15T05:19:01.6"]],
        "dataselect": [["2014-02-15T05:17:09.6", "2014-02-15T05:18:25.0"]],
    }
    rep = report.create_report_object("NODE", 1, 1, 600, [rec])
    text = report.save_report_markdown(rep, report_dir=tmp_path).read_text(encoding="utf-8")
    assert "█" in text          # only the ASCII timeline draws coverage blocks
    assert "·" in text          # empty lead-in in the timeline
    assert "36.6 s" in text     # gap listed in the detail


def test_render_timeline_separates_gaps_with_pipe():
    line = report.render_timeline(
        "2020-01-01T00:00:00", "2020-01-01T00:10:00",
        [],
        [("2020-01-01T00:01:00", "2020-01-01T00:03:00"),
         ("2020-01-01T00:06:00", "2020-01-01T00:08:00")],
        gaps=[{"start": "2020-01-01T00:01:00+00:00", "end": "2020-01-01T00:03:00+00:00", "who": "dataselect"},
              {"start": "2020-01-01T00:06:00+00:00", "end": "2020-01-01T00:08:00+00:00", "who": "dataselect"}],
    )
    assert line.count("|") == 1     # one boundary between two gaps
    assert "▲" in line


def test_render_timeline_no_pipe_for_single_gap():
    line = report.render_timeline(
        "2020-01-01T00:00:00", "2020-01-01T00:10:00",
        [],
        [("2020-01-01T00:01:00", "2020-01-01T00:09:00")],
        gaps=[{"start": "2020-01-01T00:01:00+00:00", "end": "2020-01-01T00:09:00+00:00", "who": "dataselect"}],
    )
    assert "|" not in line


def test_render_timeline_dataselect_only_uses_up_triangle():
    line = report.render_timeline(
        "2020-01-01T00:00:00", "2020-01-01T00:10:00",
        [],
        [("2020-01-01T00:04:00", "2020-01-01T00:06:00")],
        width=20,
    )
    assert "▲" in line          # dataselect-only (Data YES / Avail NO)
    assert "▼" not in line


def test_delete_old_reports(tmp_path):
    recs = [make_record()]
    rep = report.create_report_object("NODE", 1, 1, 600, recs)
    for _ in range(3):
        report.save_report_json(rep, report_dir=tmp_path)
        report.save_report_markdown(rep, report_dir=tmp_path)
        time.sleep(0.01)

    report.delete_old_reports(report_dir=tmp_path, keep=1)

    remaining = list(tmp_path.glob("*.json"))
    assert len(remaining) == 1
    md_remaining = list(tmp_path.glob("*.md"))
    assert len(md_remaining) == 1


def test_delete_old_reports_nonexistent_dir(tmp_path):
    non_existing = tmp_path / "not_here"
    report.delete_old_reports(non_existing, keep=1)


from eida_consistency.report.report import triad


def test_triad_all_present_filled():
    assert triad(True, True, True) == "▼ ▲ ▶"


def test_triad_all_absent_hollow():
    assert triad(False, False, False) == "▽ △ ▷"


def test_triad_data_but_no_psd():
    assert triad(False, True, False) == "▽ ▲ ▷"


def test_triad_psd_none_shows_question():
    assert triad(True, True, None) == "▼ ▲ ?"


from eida_consistency.report.report import render_timeline

WS, WE = "2024-06-02T12:00:00", "2024-06-02T12:10:00"


def test_render_timeline_single_line_unchanged_without_psd():
    out = render_timeline(WS, WE, [(WS, WE)], [(WS, WE)])
    assert "\n" not in out  # still one line
    assert set(out) <= set("█▲▼·|")


def test_render_timeline_three_lanes_when_psd_present():
    out = render_timeline(WS, WE, [(WS, WE)], [(WS, WE)], psd_present=True)
    lines = out.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("▼ Avail")
    assert lines[1].startswith("▲ Data")
    assert lines[2].startswith("▶ PSD")
    assert "█" in lines[2] and "░" not in lines[2]  # PSD lane uniform present


def test_render_timeline_psd_lane_uniform_absent():
    out = render_timeline(WS, WE, [(WS, WE)], [(WS, WE)], psd_present=False)
    psd_line = out.splitlines()[2]
    assert "░" in psd_line and "█" not in psd_line


from eida_consistency.report.report import create_report_object


def _rec(**kw):
    base = dict(index=1, network="HL", station="A", channel="HNZ", location="",
                available=True, dataselect_success=True, dataselect_type="SingleTrace",
                consistent=True, scoreable=True, starttime="2024-06-02T12:00:00",
                endtime="2024-06-02T12:10:00")
    base.update(kw)
    return base


def test_summary_counts_data_but_no_psd():
    recs = [
        _rec(psd_consistent=False, psd_status="Inconsistent", psd_required=True),
        _rec(psd_consistent=True, psd_status="Consistent", psd_required=True),
        _rec(psd_consistent=None, psd_status="Unsupported", psd_required=True),
        _rec(psd_consistent=None, psd_status="Skipped", psd_required=False),
    ]
    summary = create_report_object("NOA", 1, 1, 600, recs)["summary"]
    assert summary["data_yes_psd_no"] == 1
    assert summary["psd_unsupported"] == 1
    assert summary["psd_skipped"] == 1
    assert summary["psd_required_count"] == 3
    # existing A–D score untouched (all A–D consistent)
    assert summary["score"] == 100.0


from eida_consistency.report.report import build_psd_section


def test_build_psd_section_empty_when_psd_not_checked():
    # records without a psd_status mean PSD was disabled -> no section at all
    assert build_psd_section([_rec()]) == []


def test_build_psd_section_separates_violations_from_pregaps():
    recs = [
        _rec(station="V", dataselect_success=True, psd_present=False,
             psd_required=True, psd_status="Inconsistent"),    # violation (>=2024)
        _rec(station="G", dataselect_success=True, psd_present=False,
             psd_required=False, psd_status="Inconsistent"),   # pre-2024 gap
        _rec(station="C", dataselect_success=True, psd_present=True,
             psd_required=True, psd_status="Consistent"),      # consistent
    ]
    body = "\n".join(build_psd_section(recs))
    # explanatory prose is present
    assert "## PSD Consistency" in body
    assert "ground truth" in body
    assert "2024-01-01" in body
    # summary counts
    assert "1 consistent" in body
    assert "1 violation(s)" in body
    assert "1 pre-2024 gap(s)" in body
    # the violation is under the Violations heading, the gap under the gaps heading
    v_head = body.index("### PSD Violations")
    g_head = body.index("### PSD gaps before 2024")
    assert v_head < body.index("HL.V..HNZ") < g_head        # violation in violations section
    assert body.index("HL.G..HNZ") > g_head                 # gap in gaps section


def test_build_psd_section_no_violations_shows_all_clear():
    recs = [_rec(station="C", dataselect_success=True, psd_present=True,
                 psd_required=True, psd_status="Consistent")]
    body = "\n".join(build_psd_section(recs))
    assert "None — every window" in body   # no violations
    assert "✅" in body


from eida_consistency.report.report import psd_scores


def _pr(**kw):
    """A minimal record for PSD scoring."""
    base = dict(dataselect_success=True, psd_status="Consistent",
                psd_present=True, psd_required=True)
    base.update(kw)
    return base


def test_psd_scores_population_excludes_nodata_skipped_unsupported():
    recs = [
        _pr(psd_status="Consistent", psd_present=True, psd_required=True),          # hit >=2024
        _pr(psd_status="Inconsistent", psd_present=False, psd_required=True),       # miss >=2024
        _pr(psd_status="Consistent", psd_present=True, psd_required=False),         # hit pre-2024
        _pr(psd_status="Inconsistent", psd_present=False, psd_required=False),      # miss pre-2024
        _pr(dataselect_success=False, psd_status="Consistent", psd_present=False),  # no data -> excluded
        _pr(psd_status="Skipped", psd_present=False),                               # skipped -> excluded
        _pr(psd_status="Unsupported", psd_present=False),                           # unsupported -> excluded
    ]
    s = psd_scores(recs)
    assert s["psd_evaluated"] == 4          # 4 data-bearing definitive windows
    assert s["psd_present"] == 2            # 2 hits
    assert s["psd_evaluated_2024"] == 2     # 2 required windows
    assert s["psd_present_2024"] == 1       # 1 hit among them
    assert s["psd_coverage_score"] == 50.0
    assert s["psd_compliance_score"] == 50.0


def test_psd_scores_na_when_no_required_windows():
    recs = [_pr(psd_required=False, psd_present=True),
            _pr(psd_required=False, psd_present=False)]
    s = psd_scores(recs)
    assert s["psd_compliance_score"] is None      # no >=2024 windows -> N/A
    assert s["psd_coverage_score"] == 50.0


def test_psd_scores_na_when_nothing_scoreable():
    recs = [_pr(dataselect_success=False, psd_status="Consistent"),
            _pr(psd_status="Unsupported")]
    s = psd_scores(recs)
    assert s["psd_evaluated"] == 0
    assert s["psd_coverage_score"] is None
    assert s["psd_compliance_score"] is None


def test_psd_scores_rounds_to_two_dp():
    recs = [_pr(psd_present=True), _pr(psd_present=False), _pr(psd_present=False)]  # 1/3 >=2024
    s = psd_scores(recs)
    assert s["psd_compliance_score"] == 33.33


from eida_consistency.report.report import create_report_object


def _rec_score(**kw):
    base = dict(index=1, network="HL", station="A", channel="HNZ", location="",
                available=True, dataselect_success=True, dataselect_type="SingleTrace",
                consistent=True, scoreable=True, starttime="2024-06-02T12:00:00",
                endtime="2024-06-02T12:10:00")
    base.update(kw)
    return base


def test_summary_carries_psd_scores_without_touching_ad_score():
    recs = [
        _rec_score(psd_status="Inconsistent", psd_present=False, psd_required=True,
                   psd_consistent=False),                                    # >=2024 miss
        _rec_score(psd_status="Consistent", psd_present=True, psd_required=True,
                   psd_consistent=True),                                     # >=2024 hit
    ]
    summary = create_report_object("NOA", 1, 1, 600, recs)["summary"]
    assert summary["psd_evaluated"] == 2
    assert summary["psd_present"] == 1
    assert summary["psd_evaluated_2024"] == 2
    assert summary["psd_compliance_score"] == 50.0
    assert summary["psd_coverage_score"] == 50.0
    # A/D score is unaffected by PSD misses (both records are A/D consistent)
    assert summary["score"] == 100.0
