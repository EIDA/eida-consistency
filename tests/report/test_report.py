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
    assert "Skipped checks" in text
    assert "TransientDataselectFailure" in text
    assert "| Channel | Window (UTC) | Avail | DS | Type | Status |" in text


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
