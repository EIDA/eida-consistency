import pytest
import json
import logging
from pathlib import Path
import eida_consistency.runner as runner


def make_candidate():
    return {"network": "XX", "station": "STA", "channel": "BHZ", "starttime": "2023-01-01T00:00:00"}


def test_run_consistency_check_seed_provided(monkeypatch, tmp_path, capsys):
    # mocks
    monkeypatch.setattr(runner, "load_node_url", lambda node: "http://fake/")
    monkeypatch.setattr(runner, "fetch_candidates", lambda url, max_stations=10: [make_candidate()])
    monkeypatch.setattr(runner, "check_candidate",
                        lambda base_url, c, candidates, epochs, duration:
                        ([("url", True, "2023-01-01T00:00:00", "2023-01-01T00:10:00", "00", {"start": "s", "end": "e", "location": "00"})],
                         {"candidates_requested": 1, "candidates_generated": 1, "candidates_pool": 1, "queries_performed": 1}))
    monkeypatch.setattr(runner, "dataselect", lambda *a, **kw: {"success": True, "status": 200, "type": "M"})
    monkeypatch.setattr(runner, "format_result", lambda *a, **kw: "formatted-log")

    called = {}
    monkeypatch.setattr(runner, "create_report_object", lambda **kw: called.setdefault("report", {"summary": {}, "results": []}))
    monkeypatch.setattr(runner, "save_report_json", lambda report, report_dir: tmp_path / "r.json")
    monkeypatch.setattr(runner, "save_report_markdown", lambda report, report_dir: tmp_path / "r.md")

    runner.run_consistency_check("NOA", epochs=1, duration=600, seed=123, report_dir=tmp_path, print_stdout=True)

    out = capsys.readouterr().out
    assert "summary" in out or "results" in out
    assert "report" in called


def test_run_consistency_check_seed_generated(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(runner, "load_node_url", lambda node: "http://fake/")
    monkeypatch.setattr(runner, "fetch_candidates", lambda url, max_stations=10: [])
    caplog.set_level(logging.WARNING)
    runner.run_consistency_check("NOA", epochs=1, duration=600, seed=None, report_dir=tmp_path)
    assert "No candidates fetched." in caplog.text


def test_run_consistency_check_with_records(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "load_node_url", lambda node: "http://fake/")
    monkeypatch.setattr(runner, "fetch_candidates", lambda url, max_stations=10: [make_candidate()])
    monkeypatch.setattr(runner, "check_candidate",
                        lambda base_url, c, candidates, epochs, duration:
                        ([("url?network=XX&station=STA&channel=BHZ", True, "s", "e", "00", {"start": "s", "end": "e", "location": "00"})],
                         {"candidates_requested": 1, "candidates_generated": 1, "candidates_pool": 1, "queries_performed": 1}))
    monkeypatch.setattr(runner, "dataselect", lambda *a, **kw: {"success": False, "status": 204, "type": "X"})
    monkeypatch.setattr(runner, "format_result", lambda *a, **kw: "formatted-log")
    monkeypatch.setattr(runner, "create_report_object", lambda **kw: {"summary": {}, "results": []})
    monkeypatch.setattr(runner, "save_report_json", lambda report, report_dir: tmp_path / "r.json")
    monkeypatch.setattr(runner, "save_report_markdown", lambda report, report_dir: tmp_path / "r.md")

    runner.run_consistency_check("NOA", epochs=1, duration=600, seed=42, report_dir=tmp_path)
    assert (tmp_path / "r.json").name == "r.json"
    assert (tmp_path / "r.md").name == "r.md"
