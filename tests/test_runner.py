import json
import sys
import io
import pytest
import types
import eida_consistency.runner as runner


def make_fake_candidate():
    return {"network": "N", "station": "S", "channel": "C", "starttime": "2024-01-01T00:00:00Z"}


def make_fake_result():
    url = "http://fake/fdsnws/availability/1/query?network=N&station=S&channel=C"
    matched_span = {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T01:00:00Z", "location": ""}
    spans = [{"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T01:00:00Z", "samplerate": "100.0"}]
    return [(url, True, "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", "", matched_span, spans, 200)], {"stat": 1}


def patch_all(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "fetch_candidates", lambda *a, **k: [make_fake_candidate()])
    monkeypatch.setattr(runner, "check_candidate", lambda *a, **k: make_fake_result())
    monkeypatch.setattr(runner, "dataselect", lambda *a, **k: {"success": True, "status": "OK", "type": "SingleTrace", "debug": "ok"})
    monkeypatch.setattr(runner, "format_result", lambda *a, **k: "LOG")
    monkeypatch.setattr(runner, "load_node_url", lambda node: "http://fake/")
    monkeypatch.setattr(runner, "create_report_object", lambda **k: {"summary": {}, "results": []})
    monkeypatch.setattr(runner, "save_report_json", lambda report, report_dir: tmp_path / "out.json")
    monkeypatch.setattr(runner, "save_report_markdown", lambda report, report_dir: tmp_path / "out.md")


# -----------------
# Tests
# -----------------

def test_no_candidates(monkeypatch):
    monkeypatch.setattr(runner, "fetch_candidates", lambda *a, **k: [])
    monkeypatch.setattr(runner, "load_node_url", lambda n: "http://fake/")
    result = runner.run_consistency_check("FAKE")
    assert result is None


def test_seed_provided(monkeypatch, tmp_path):
    patch_all(monkeypatch, tmp_path)
    result = runner.run_consistency_check("FAKE", seed=123, report_dir=tmp_path)
    assert result == tmp_path / "out.json"


def test_seed_generated(monkeypatch, tmp_path):
    patch_all(monkeypatch, tmp_path)
    # seed=None triggers random generation
    result = runner.run_consistency_check("FAKE", seed=None, report_dir=tmp_path)
    assert result == tmp_path / "out.json"


def test_print_stdout(monkeypatch, tmp_path, capsys):
    patch_all(monkeypatch, tmp_path)
    result = runner.run_consistency_check("FAKE", seed=1, report_dir=tmp_path, print_stdout=True)
    out = capsys.readouterr().out
    assert "summary" in out
    assert result == tmp_path / "out.json"


def test_transient_dataselect_failure_is_marked_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "fetch_candidates", lambda *a, **k: [make_fake_candidate()])
    monkeypatch.setattr(runner, "check_candidate", lambda *a, **k: make_fake_result())
    monkeypatch.setattr(
        runner,
        "dataselect",
        lambda *a, **k: {"success": False, "status": "ConnectionError", "type": "Error", "debug": "network"},
    )
    monkeypatch.setattr(runner, "format_result", lambda *a, **k: "LOG")
    monkeypatch.setattr(runner, "load_node_url", lambda node: "http://fake/")

    captured = {}

    def fake_create_report_object(**kwargs):
        captured["records"] = kwargs["records"]
        return {"summary": {}, "results": kwargs["records"]}

    monkeypatch.setattr(runner, "create_report_object", fake_create_report_object)
    monkeypatch.setattr(runner, "save_report_json", lambda report, report_dir: tmp_path / "out.json")
    monkeypatch.setattr(runner, "save_report_markdown", lambda report, report_dir: tmp_path / "out.md")

    result = runner.run_consistency_check("FAKE", seed=1, report_dir=tmp_path)
    assert result == tmp_path / "out.json"
    record = captured["records"][0]
    assert record["consistent"] is None
    assert record["scoreable"] is False
    assert record["consistency_status"] == "Skipped"
