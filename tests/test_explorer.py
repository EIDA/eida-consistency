import pytest
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import eida_consistency.explorer as explorer


# -----------------
# _parse_iso / _iso
# -----------------

def test_parse_iso_variants():
    dt1 = explorer._parse_iso("2023-01-01T00:00:00Z")
    dt2 = explorer._parse_iso("2023-01-01T00:00:00+00:00")
    dt3 = explorer._parse_iso("2023-01-01T00:00:00")
    assert dt1.tzinfo and dt2.tzinfo and dt3.tzinfo

def test_iso_roundtrip():
    dt = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    s = explorer._iso(dt)
    assert s.startswith("2023-01-01T12:00:00")


# -----------------
# _slice_consistent
# -----------------

def test_slice_consistent_available_and_dataselect(monkeypatch, caplog):
    t0 = datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)

    monkeypatch.setattr(explorer, "get_availability_spans",
                        lambda *a, **kw: [{"start": "2023-01-01T00:00:00",
                                           "end": "2023-01-01T02:00:00"}])
    monkeypatch.setattr(explorer, "dataselect",
                        lambda *a, **kw: {"success": True})

    caplog.set_level(logging.INFO)
    ok = explorer._slice_consistent("http://fake/", "XX", "STA", "BHZ", "00", t0, t1, verbose=True)
    assert ok is True
    assert "Availability URL" in caplog.text
    assert "Dataselect URL" in caplog.text

def test_slice_consistent_not_covered(monkeypatch):
    t0 = datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)
    monkeypatch.setattr(explorer, "get_availability_spans", lambda *a, **kw: [])
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **kw: {"success": False})
    ok = explorer._slice_consistent("http://fake/", "XX", "STA", "BHZ", "00", t0, t1)
    assert ok is True  # both say no → consistent


# -----------------
# explore_boundaries
# -----------------

def make_report(path: Path, consistent=False, avail=True, ds_success=False):
    data = {
        "summary": {"node": "NOA"},
        "results": [
            {
                "index": 1,
                "network": "XX",
                "station": "STA",
                "channel": "BHZ",
                "location": "00",
                "starttime": "2023-01-01T00:00:00Z",
                "endtime": "2023-01-01T01:00:00Z",
                "consistent": consistent,
                "available": avail,
                "dataselect_success": ds_success,
            }
        ],
    }
    path.write_text(__import__("json").dumps(data))
    return path

def test_explore_boundaries_no_targets(tmp_path, caplog):
    rep = make_report(tmp_path / "rep.json", consistent=True)
    caplog.set_level(logging.INFO)
    explorer.explore_boundaries(rep)
    assert "No targets to explore" in caplog.text

def test_explore_boundaries_with_targets(monkeypatch, tmp_path, caplog):
    rep = make_report(tmp_path / "rep.json", consistent=False, avail=True, ds_success=False)

    # availability never covers
    monkeypatch.setattr(explorer, "get_availability_spans", lambda *a, **kw: [])
    # dataselect always fails
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **kw: {"success": False})
    # base url loader
    monkeypatch.setattr(explorer, "load_node_url", lambda node: "http://fake/")

    caplog.set_level(logging.INFO)
    explorer.explore_boundaries(rep, indices=[1], max_days=1, verbose=True)
    logs = caplog.text
    assert "Exploring inconsistency" in logs
    assert "Inconsistency window" in logs
    assert "Suggested action" in logs
    assert "uvx dmtri" in logs
