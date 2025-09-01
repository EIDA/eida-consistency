import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import eida_consistency.explorer as explorer


class DummyDS:
    """Dummy dataselect responses."""
    ok = {"success": True, "status": "OK"}
    fail = {"success": False, "status": "NoData"}


class DummyAvail:
    """Dummy availability spans."""

    @staticmethod
    def covered(*args, **kwargs):
        return [{"start": "2020-01-01T00:00:00", "end": "2100-01-01T00:00:00"}]

    @staticmethod
    def empty(*args, **kwargs):
        return []


def make_report(tmp_path: Path, results):
    report = {
        "summary": {"node": "RESIF", "seed": 123, "epochs": 1,
                    "duration": 600, "total_checked": len(results),
                    "total_consistent": 0, "total_inconsistent": 0,
                    "timestamp": "2025-01-01T00:00:00"},
        "results": results,
    }
    p = tmp_path / "report.json"
    p.write_text(json.dumps(report))
    return p


def test_parse_iso_variants():
    # With Z suffix
    dt = explorer._parse_iso("2020-01-01T00:00:00Z")
    assert dt.tzinfo == timezone.utc
    # Naive string
    dt2 = explorer._parse_iso("2020-01-01T00:00:00")
    assert dt2.tzinfo == timezone.utc
    # None
    assert explorer._parse_iso(None) is None


def test_iso_format_roundtrip():
    now = datetime.now(timezone.utc)
    s = explorer._iso(now)
    assert "T" in s and s.endswith(":00") is False


def test_slice_consistent_true(monkeypatch):
    monkeypatch.setattr(explorer, "get_availability_spans", DummyAvail.covered)
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **k: DummyDS.ok)
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=10)
    res = explorer._slice_consistent("url", "XX", "STA", "BHZ", "00", t0, t1)
    assert res is True


def test_slice_consistent_false(monkeypatch):
    # availability covered but dataselect fails
    monkeypatch.setattr(explorer, "get_availability_spans", DummyAvail.covered)
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **k: DummyDS.fail)
    t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=10)
    res = explorer._slice_consistent("url", "XX", "STA", "BHZ", "00", t0, t1)
    assert res is False


def test_explore_boundaries_no_targets(tmp_path, caplog):
    report = make_report(tmp_path, results=[{"index": 1, "consistent": True}])
    caplog.set_level(logging.INFO)
    explorer.explore_boundaries(report)
    assert "No targets" in caplog.text


def test_explore_boundaries_with_indices(monkeypatch, tmp_path, caplog):
    # One inconsistent record
    results = [{
        "index": 7, "network": "XX", "station": "STA", "channel": "BHZ", "location": "00",
        "starttime": "2020-01-01T00:00:00", "endtime": "2020-01-01T00:10:00",
        "available": True, "dataselect_success": False, "consistent": False
    }]
    report = make_report(tmp_path, results)

    # Mocks: availability empty, dataselect fail always
    monkeypatch.setattr(explorer, "get_availability_spans", DummyAvail.empty)
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **k: DummyDS.fail)
    monkeypatch.setattr(explorer, "load_node_url", lambda n: "http://fake/")

    caplog.set_level(logging.INFO)
    explorer.explore_boundaries(report, indices=[7], max_days=1)

    # Should log exploration and suggest clean
    assert "Exploring inconsistency" in caplog.text
    assert "Suggested command:" in caplog.text
    assert "dmtri clean" in caplog.text


def test_explore_boundaries_forward_backward_limits(monkeypatch, tmp_path, caplog):
    results = [{
        "index": 1, "network": "XX", "station": "STA", "channel": "BHZ", "location": "00",
        "starttime": "2020-01-01T00:00:00", "endtime": "2020-01-01T00:10:00",
        "available": False, "dataselect_success": True, "consistent": False
    }]
    report = make_report(tmp_path, results)

    # Force always inconsistent (covered vs ds mismatch)
    monkeypatch.setattr(explorer, "get_availability_spans", DummyAvail.covered)
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **k: DummyDS.fail)
    monkeypatch.setattr(explorer, "load_node_url", lambda n: "http://fake/")

    caplog.set_level(logging.INFO)
    explorer.explore_boundaries(report, max_days=1)

    # Should warn about reaching limits
    assert "⚠️ Reached max" in caplog.text
    assert "dmtri refresh" in caplog.text
def test_explore_boundaries_backward_limit_else(monkeypatch, tmp_path, caplog):
    """Covers the 'else:' block of the backward search loop."""
    results = [{
        "index": 42, "network": "XX", "station": "STA", "channel": "BHZ", "location": "00",
        "starttime": "2020-01-01T00:00:00", "endtime": "2020-01-01T00:10:00",
        "available": True, "dataselect_success": False, "consistent": False
    }]
    report = make_report(tmp_path, results)

    # Always inconsistent → never breaks the loop
    monkeypatch.setattr(explorer, "get_availability_spans", DummyAvail.covered)
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **k: DummyDS.fail)
    monkeypatch.setattr(explorer, "load_node_url", lambda n: "http://fake/")

    caplog.set_level(logging.INFO)
    explorer.explore_boundaries(report, max_days=0)  # forces the `else` branch

    assert "⚠️ Reached max backward search limit" in caplog.text


def test_explore_boundaries_cmd_refresh_fallback(monkeypatch, tmp_path, caplog):
    """Covers the fallback cmd = 'refresh' branch when available == ds_success."""
    results = [{
        "index": 99, "network": "XX", "station": "STA", "channel": "BHZ", "location": "00",
        "starttime": "2020-01-01T00:00:00", "endtime": "2020-01-01T00:10:00",
        "available": True, "dataselect_success": True, "consistent": True
    }]
    report = make_report(tmp_path, results)

    # These values won’t be used since the record is already consistent
    monkeypatch.setattr(explorer, "get_availability_spans", DummyAvail.empty)
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **k: DummyDS.ok)
    monkeypatch.setattr(explorer, "load_node_url", lambda n: "http://fake/")

    caplog.set_level(logging.INFO)
    explorer.explore_boundaries(report, indices=[99], max_days=1)

    assert "dmtri refresh" in caplog.text
