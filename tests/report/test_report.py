import json
import time
from pathlib import Path
import eida_consistency.report.report as report


def make_record(consistent=True, available=True, ds_success=True, ds_type="M", status=200):
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
    }


# -----------------
# create_report_object
# -----------------

def test_create_report_object_basic():
    records = [make_record(True), make_record(False, available=True, ds_success=False)]
    rep = report.create_report_object("NODE", 123, 5, 600, records,
                                      candidates_requested=5, candidates_tested=2, station_queries=1)
    summary = rep["summary"]
    assert summary["node"] == "NODE"
    assert summary["total_checked"] == 2
    assert summary["total_consistent"] == 1
    assert summary["total_inconsistent"] == 1
    assert "availability_yes_dataselect_no" in summary
    assert "availability_no_dataselect_yes" in summary
    assert isinstance(summary["timestamp"], str)

def test_create_report_object_empty_records():
    rep = report.create_report_object("NODE", 1, 1, 600, [])
    assert rep["summary"]["score"] == 0.0
    assert rep["summary"]["total_checked"] == 0


# -----------------
# _make_unique_filename
# -----------------

def test_make_unique_filename_format(monkeypatch):
    fname = report._make_unique_filename("NODE", 42, "json")
    assert fname.startswith("node_42_")
    assert fname.endswith(".json")


# -----------------
# save_report_json
# -----------------

def test_save_report_json_and_content(tmp_path):
    recs = [make_record()]
    rep = report.create_report_object("NODE", 1, 1, 600, recs)
    path = report.save_report_json(rep, report_dir=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["summary"]["node"] == "NODE"


# -----------------
# save_report_markdown
# -----------------

def test_save_report_markdown(tmp_path):
    recs = [
        make_record(True, ds_type="A"),
        make_record(False, ds_type="B"),
    ]
    rep = report.create_report_object("NODE", 2, 2, 600, recs)
    path = report.save_report_markdown(rep, report_dir=tmp_path)
    text = path.read_text()
    assert "# EIDA Consistency Report" in text
    assert "Dataselect Response Types" in text
    assert "✔️" in text or "❌" in text


# -----------------
# delete_old_reports
# -----------------

def test_delete_old_reports(tmp_path):
    # Create 3 JSON + MD reports
    recs = [make_record()]
    rep = report.create_report_object("NODE", 1, 1, 600, recs)
    paths = []
    for i in range(3):
        p_json = report.save_report_json(rep, report_dir=tmp_path)
        p_md = report.save_report_markdown(rep, report_dir=tmp_path)
        paths.append((p_json, p_md))
        time.sleep(0.01)  # ensure mtime ordering

    # Keep only 1
    report.delete_old_reports(report_dir=tmp_path, keep=1)

    remaining = list(tmp_path.glob("*.json"))
    assert len(remaining) == 1
    # corresponding md should also remain
    md_remaining = list(tmp_path.glob("*.md"))
    assert len(md_remaining) == 1

def test_delete_old_reports_nonexistent_dir(tmp_path):
    non_existing = tmp_path / "not_here"
    # Should not raise
    report.delete_old_reports(non_existing, keep=1)
