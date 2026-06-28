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
    rec["url"] = "https://node/fdsnws/availability/1/query?network=FR&station=MLS"
    rec["availability_status"] = 200
    rec["dataselect_url"] = "https://node/fdsnws/dataselect/1/query?network=FR&station=MLS"
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
