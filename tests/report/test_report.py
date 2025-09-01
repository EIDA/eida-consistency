import json
import time
from pathlib import Path

import pytest

import eida_consistency.report.report as report


def make_dummy_records():
    base = {
        "network": "XX", "station": "AAA", "channel": "HHZ", "location": "00",
        "starttime": "2020-01-01T00:00:00", "endtime": "2020-01-01T00:10:00",
    }
    return [
        {**base, "consistent": True,  "available": True,  "dataselect_success": True,
         "dataselect_status": "OK", "dataselect_type": "SingleTrace"},
        {**base, "consistent": False, "available": True,  "dataselect_success": False,
         "dataselect_status": "NoData", "dataselect_type": "NoTrace"},
        {**base, "consistent": False, "available": False, "dataselect_success": True,
         "dataselect_status": "OK", "dataselect_type": "SingleTrace"},
    ]


def test_create_report_object_score_and_breakdown():
    recs = make_dummy_records()
    obj = report.create_report_object("RESIF", seed=123, epochs=3, duration=600, records=recs)

    summary = obj["summary"]

    assert summary["node"] == "RESIF"
    assert summary["total_checked"] == 3
    assert summary["total_consistent"] == 1
    assert summary["total_inconsistent"] == 2
    # Score = 1/3 * 100 = 33.33
    assert abs(summary["score"] - 33.33) < 0.01
    assert summary["availability_yes_dataselect_no"] == 1
    assert summary["availability_no_dataselect_yes"] == 1
    assert "timestamp" in summary


def test_save_report_json_and_load(tmp_path):
    recs = make_dummy_records()
    obj = report.create_report_object("NOA", seed=42, epochs=2, duration=600, records=recs)

    path = report.save_report_json(obj, output_dir=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["summary"]["node"] == "NOA"


def test_save_report_markdown_contains_score_and_breakdown(tmp_path):
    recs = make_dummy_records()
    obj = report.create_report_object("GFZ", seed=99, epochs=2, duration=600, records=recs)

    path = report.save_report_markdown(obj, output_dir=tmp_path)
    content = path.read_text()

    assert "# EIDA Consistency Report" in content
    assert "Score" in content
    assert "Inconsistency Breakdown" in content
    assert "Availability says YES" in content
    assert "Availability says NO" in content


def test_delete_old_reports(tmp_path):
    recs = make_dummy_records()
    obj = report.create_report_object("TEST", seed=1, epochs=1, duration=600, records=recs)

    # Create 3 reports with slight delay so mtime differs
    for seed in [1, 2, 3]:
        obj = report.create_report_object("TEST", seed=seed, epochs=1, duration=600, records=recs)
        report.save_report_json(obj, output_dir=tmp_path)
        time.sleep(0.05)

    # Ensure 3 files exist
    assert len(list(tmp_path.glob("*.json"))) == 3

    # Keep only 1
    report.delete_old_reports(tmp_path, keep=1)
    remaining = list(tmp_path.glob("*.json"))
    assert len(remaining) == 1
    # Only latest seed should remain
    text = remaining[0].read_text()
    assert '"seed": 3' in text


def test_delete_old_reports_dir_missing(tmp_path):
    # Non-existing dir → should just return
    missing = tmp_path / "nope"
    assert not missing.exists()
    report.delete_old_reports(missing, keep=1)  # should not raise

def test_delete_old_reports_file_not_found(monkeypatch, tmp_path):
    recs = make_dummy_records()
    obj = report.create_report_object("TEST", seed=10, epochs=1, duration=600, records=recs)

    # Save a JSON report
    json_path = report.save_report_json(obj, output_dir=tmp_path)
    md_path = json_path.with_suffix(".md")
    md_path.write_text("dummy-md")

    # Monkeypatch Path.unlink to raise FileNotFoundError only for this json file
    original_unlink = Path.unlink

    def fake_unlink(p: Path, *a, **kw):
        if p == json_path:
            raise FileNotFoundError
        return original_unlink(p, *a, **kw)

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    # Run cleanup → should trigger the FileNotFoundError branch
    report.delete_old_reports(tmp_path, keep=0)

    # Markdown should also be gone
    assert not md_path.exists()