import json
from pathlib import Path
import re

import pytest

from eida_consistency.report.report import (
    create_report_object,
    _make_unique_filename,
    save_report_json,
    save_report_markdown,
)


@pytest.fixture
def sample_records():
    return [
        {
            "network": "XX",
            "station": "AAA",
            "location": "00",
            "channel": "BHZ",
            "starttime": "2020-01-01T00:00:00",
            "endtime": "2020-01-01T00:10:00",
            "available": True,
            "dataselect_success": True,
            "dataselect_type": "miniseed",
            "dataselect_status": "200",
            "consistent": True,
        },
        {
            "network": "XX",
            "station": "BBB",
            "location": "",
            "channel": "BHN",
            "starttime": "2020-01-01T01:00:00",
            "endtime": "2020-01-01T01:05:00",
            "available": False,
            "dataselect_success": False,
            "dataselect_status": "404",
            "consistent": False,
        },
    ]


def test_create_report_object_counts(sample_records):
    """Check that summary fields are computed correctly."""
    report = create_report_object("NOA", 123, 5, 60, sample_records)

    summary = report["summary"]
    assert summary["node"] == "NOA"
    assert summary["seed"] == 123
    assert summary["epochs"] == 5
    assert summary["duration"] == 60
    assert summary["total_checked"] == 2
    assert summary["total_consistent"] == 1
    assert summary["total_inconsistent"] == 1
    # timestamp must look like an ISO string with timezone
    assert re.match(r"\d{4}-\d{2}-\d{2}T.*Z?", summary["timestamp"]) or summary["timestamp"].endswith("+00:00")


def test_make_unique_filename_changes_with_time(monkeypatch):
    """_make_unique_filename should return lowercase node and include timestamp."""
    import eida_consistency.report as report
    from datetime import datetime, timezone

    fixed_time = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    class FakeDateTime:
        @staticmethod
        def now(tz=None):
            return fixed_time

    monkeypatch.setattr(report, "datetime", FakeDateTime)

    filename = report._make_unique_filename("NOA", 123, "json")
    assert filename == "noa_123_20200101_120000.json"



def test_save_report_json_and_load(tmp_path, sample_records):
    """save_report_json should write valid JSON that can be read back."""
    report = create_report_object("GFZ", 42, 2, 120, sample_records)
    filepath = save_report_json(report, output_dir=tmp_path)

    assert filepath.exists()
    with open(filepath) as f:
        loaded = json.load(f)

    assert loaded["summary"]["node"] == "GFZ"
    assert loaded["results"][0]["station"] == "AAA"


def test_save_report_markdown(tmp_path, sample_records):
    """save_report_markdown should write a markdown file with key fields."""
    report = create_report_object("ETH", 99, 3, 300, sample_records)
    filepath = save_report_markdown(report, output_dir=tmp_path)

    assert filepath.exists()
    text = filepath.read_text()

    # summary section
    assert f"# EIDA Consistency Report: `ETH`" in text
    assert "- Seed: `99`" in text
    assert "- Epochs: `3`" in text
    assert "- Duration/epoch: `300 s`" in text

    # detailed results
    assert "XX.AAA.00.BHZ" in text
    assert "XX.BBB..BHN" in text
    assert "Consistent: `✔️`" in text or "Consistent: `❌`" in text
