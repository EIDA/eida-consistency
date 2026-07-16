import json
import pytest
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
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
                        lambda *a, **kw: {"success": True,
                                          "segments": [("2023-01-01T00:00:00",
                                                        "2023-01-01T02:00:00", 100.0)]})
    monkeypatch.setattr(explorer, "psd_coverage",
                        lambda *a, **kw: {"success": True, "status": "OK",
                                          "day_covered": True, "records": [],
                                          "url": "http://fake/eidaws/psd/1/coverage?net=XX"})

    caplog.set_level(logging.INFO)
    ok = explorer._slice_consistent("http://fake/", "XX", "STA", "BHZ", "00", t0, t1, verbose=True)
    assert ok is True
    assert "Availability URL" in caplog.text
    assert "Dataselect URL" in caplog.text
    assert "PSD URL" in caplog.text                 # PSD surfaced in explore
    assert "PSD present=True" in caplog.text

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

def test_explore_boundaries_no_targets_returns_empty(tmp_path):
    rep = make_report(tmp_path / "rep.json", consistent=True)
    result = explorer.explore_boundaries(rep)
    assert result["schema_version"] == explorer.SCHEMA_VERSION
    assert result["node"] == "NOA"
    assert result["fixes"] == []

def test_explore_boundaries_returns_structured_fixes(monkeypatch, tmp_path):
    rep = make_report(tmp_path / "rep.json", consistent=False, avail=True, ds_success=False)
    monkeypatch.setattr(explorer, "get_availability_spans",
                        lambda *a, **kw: [{"start": "2020-01-01T00:00:00", "end": "2025-01-01T00:00:00"}])
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **kw: {"success": False})
    monkeypatch.setattr(explorer, "load_node_url", lambda node: "http://fake/")

    result = explorer.explore_boundaries(rep, indices=[1], max_days=1)

    assert result["schema_version"] == explorer.SCHEMA_VERSION
    assert result["node"] == "NOA"
    assert len(result["fixes"]) == 1
    fix = result["fixes"][0]
    assert fix["index"] == 1
    assert (fix["network"], fix["station"], fix["location"], fix["channel"]) == ("XX", "STA", "00", "BHZ")
    # report row says available=True / dataselect_success=False -> clean direction
    assert fix["direction"] == "clean"
    assert fix["status"] == "actionable"
    assert fix["start"] and fix["end"]  # boundary window populated

def test_verify_rechecks_exact_reported_window(monkeypatch, tmp_path):
    """Re-verification must replay the EXACT reported window (deterministic),
    not a random 10-minute slice of the day."""
    rep = make_report(tmp_path / "rep.json", consistent=False, avail=True, ds_success=True)

    calls = []

    def fake_ds(base, net, sta, cha, start, end, loc=None, *a, **kw):
        calls.append((start, end))
        return {"success": True, "status": "OK", "segments": [(start, end, 100.0)]}

    monkeypatch.setattr(explorer, "get_availability_spans",
                        lambda *a, **kw: [{"start": "2023-01-01T00:00:00", "end": "2023-01-01T01:00:00"}])
    monkeypatch.setattr(explorer, "dataselect", fake_ds)
    monkeypatch.setattr(explorer, "load_node_url", lambda node: "http://fake/")

    explorer.explore_boundaries(rep, indices=[1], max_days=1)

    # first dataselect call is the re-verify of the original window
    assert calls[0] == ("2023-01-01T00:00:00", "2023-01-01T01:00:00")


def test_verify_is_deterministic_across_runs(monkeypatch, tmp_path):
    """Same report re-verified twice must check the same window both times
    (no random daily sampling) -> no 'fixed/not-fixed' flapping."""
    rep = make_report(tmp_path / "rep.json", consistent=False, avail=True, ds_success=True)
    monkeypatch.setattr(explorer, "get_availability_spans",
                        lambda *a, **kw: [{"start": "2023-01-01T00:00:00", "end": "2023-01-01T01:00:00"}])
    monkeypatch.setattr(explorer, "load_node_url", lambda node: "http://fake/")

    def run_once():
        calls = []

        def fake_ds(base, net, sta, cha, start, end, loc=None, *a, **kw):
            calls.append((start, end))
            return {"success": True, "status": "OK", "segments": [(start, end, 100.0)]}

        monkeypatch.setattr(explorer, "dataselect", fake_ds)
        explorer.explore_boundaries(rep, indices=[1], max_days=1)
        return calls

    first, second = run_once(), run_once()
    assert first == second                       # identical windows both runs
    assert first[0] == ("2023-01-01T00:00:00", "2023-01-01T01:00:00")


def test_explore_boundaries_with_targets(monkeypatch, tmp_path, caplog):
    rep = make_report(tmp_path / "rep.json", consistent=False, avail=True, ds_success=False)

    # availability covers the time window so avail=True
    monkeypatch.setattr(explorer, "get_availability_spans", lambda *a, **kw: [{"start": "2020-01-01T00:00:00", "end": "2025-01-01T00:00:00"}])
    # dataselect always fails
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **kw: {"success": False})
    # PSD queried only in verbose mode; stub it so no real network call is made
    monkeypatch.setattr(explorer, "psd_coverage",
                        lambda *a, **kw: {"success": True, "status": "NoData",
                                          "day_covered": False, "records": [],
                                          "url": "http://fake/eidaws/psd/1/coverage"})
    # base url loader
    monkeypatch.setattr(explorer, "load_node_url", lambda node: "http://fake/")

    caplog.set_level(logging.INFO)
    explorer.explore_boundaries(rep, indices=[1], max_days=1, verbose=True)
    logs = caplog.text
    assert "[1/1]" in logs              # progress counter
    assert "XX.STA.00.BHZ" in logs      # channel label present
    assert "EXPLORATION SUMMARY" in logs
    assert "uvx dmtri" in logs


# -----------------
# URL report input
# -----------------

def _report_payload(consistent=True):
    return {
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
                "available": True,
                "dataselect_success": False,
            }
        ],
    }


def test_explore_boundaries_url_fetches_json(caplog):
    """When given a URL, explore_boundaries fetches via requests.get."""
    mock_response = MagicMock()
    mock_response.json.return_value = _report_payload(consistent=True)
    mock_response.raise_for_status.return_value = None

    with patch("eida_consistency.explorer.requests.get", return_value=mock_response) as mock_get:
        caplog.set_level(logging.INFO)
        explorer.explore_boundaries("https://example.com/report.json")

    mock_get.assert_called_once_with(
        "https://example.com/report.json", headers={"User-Agent": "eida-consistency"}, timeout=30
    )
    assert "Fetching report from URL" in caplog.text
    assert "No targets to explore" in caplog.text  # all consistent → nothing to do


def test_explore_boundaries_url_http_error():
    """An HTTP error from the remote URL propagates as an exception."""
    import requests as req

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = req.HTTPError("404 Not Found")

    with patch("eida_consistency.explorer.requests.get", return_value=mock_response):
        with pytest.raises(req.HTTPError):
            explorer.explore_boundaries("https://example.com/missing.json")


def test_explore_boundaries_url_inconsistent(monkeypatch, caplog):
    """URL report with inconsistencies triggers boundary exploration and dmtri command."""
    mock_response = MagicMock()
    mock_response.json.return_value = _report_payload(consistent=False)
    mock_response.raise_for_status.return_value = None

    monkeypatch.setattr(explorer, "get_availability_spans", lambda *a, **kw: [{"start": "2020-01-01T00:00:00", "end": "2025-01-01T00:00:00"}])
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **kw: {"success": False})
    monkeypatch.setattr(explorer, "load_node_url", lambda node: "http://fake/")

    with patch("eida_consistency.explorer.requests.get", return_value=mock_response):
        caplog.set_level(logging.INFO)
        explorer.explore_boundaries("https://example.com/report.json", max_days=1)

    assert "uvx dmtri" in caplog.text
    assert "EXPLORATION SUMMARY" in caplog.text
