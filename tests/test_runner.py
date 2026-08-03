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
    monkeypatch.setattr(runner, "psd_coverage", lambda *a, **k: {
        "success": True, "status": "OK", "records": [], "day_covered": False, "url": "http://fake/psd"})
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


def test_unseeded_run(monkeypatch, tmp_path):
    # The seed mechanism was removed; run_consistency_check no longer accepts a seed.
    patch_all(monkeypatch, tmp_path)
    result = runner.run_consistency_check("FAKE", report_dir=tmp_path)
    assert result == tmp_path / "out.json"


def test_run_consistency_check_rejects_seed_kwarg(tmp_path):
    with pytest.raises(TypeError):
        runner.run_consistency_check("FAKE", seed=123, report_dir=tmp_path)


def test_print_stdout(monkeypatch, tmp_path, capsys):
    patch_all(monkeypatch, tmp_path)
    result = runner.run_consistency_check("FAKE", report_dir=tmp_path, print_stdout=True)
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
    monkeypatch.setattr(runner, "psd_coverage", lambda *a, **k: {
        "success": True, "status": "OK", "records": [], "day_covered": False, "url": "http://fake/psd"})

    captured = {}

    def fake_create_report_object(**kwargs):
        captured["records"] = kwargs["records"]
        return {"summary": {}, "results": kwargs["records"]}

    monkeypatch.setattr(runner, "create_report_object", fake_create_report_object)
    monkeypatch.setattr(runner, "save_report_json", lambda report, report_dir: tmp_path / "out.json")
    monkeypatch.setattr(runner, "save_report_markdown", lambda report, report_dir: tmp_path / "out.md")

    result = runner.run_consistency_check("FAKE", report_dir=tmp_path)
    assert result == tmp_path / "out.json"
    record = captured["records"][0]
    assert record["consistent"] is None
    assert record["scoreable"] is False
    assert record["consistency_status"] == "Skipped"


import eida_consistency.runner as runner_mod


def _stub_pipeline(monkeypatch, check_calls):
    """Stub network so run_consistency_check runs offline with one candidate."""
    cand = {"network": "HL", "station": "ACHA", "channel": "HNZ",
            "location": "00", "starttime": "2024-06-01T00:00:00", "endtime": "2024-07-01T00:00:00"}
    monkeypatch.setattr(runner_mod, "load_node_url", lambda node: "https://x/fdsnws/")
    monkeypatch.setattr(runner_mod, "fetch_candidates", lambda *a, **k: [cand])
    monkeypatch.setattr(runner_mod, "check_candidate", lambda *a, **k: (
        [("http://x?network=HL&station=ACHA&channel=HNZ", True,
          "2024-06-02T12:00:00", "2024-06-02T12:10:00", "00", {"start": None, "end": None, "location": "00"},
          [], 200)], {"candidates_pool": 1}))
    monkeypatch.setattr(runner_mod, "dataselect", lambda *a, **k: {
        "success": True, "status": "OK", "type": "SingleTrace",
        "segments": [("2024-06-02T12:00:00", "2024-06-02T12:10:00", 200.0)], "url": "http://ds", "debug": ""})
    monkeypatch.setattr(runner_mod, "classify_consistency", lambda *a, **k: {
        "consistent": True, "scoreable": True, "status": "Consistent",
        "reason": None, "mismatch": [], "coverage": {"availability": [], "dataselect": []}})

    def fake_psd(*a, **k):
        check_calls.append(a)
        return {"success": True, "status": "OK", "records": [], "day_covered": False, "url": "http://psd"}
    monkeypatch.setattr(runner_mod, "psd_coverage", fake_psd)


def test_runner_adds_psd_fields_when_enabled(monkeypatch, tmp_path):
    calls = []
    _stub_pipeline(monkeypatch, calls)
    runner_mod.run_consistency_check(node="NOA", epochs=1, check_psd=True, report_dir=tmp_path)
    assert len(calls) == 1  # psd_coverage was called


def test_runner_skips_psd_when_disabled(monkeypatch, tmp_path):
    calls = []
    _stub_pipeline(monkeypatch, calls)
    runner_mod.run_consistency_check(node="NOA", epochs=1, check_psd=False, report_dir=tmp_path)
    assert calls == []  # psd_coverage NOT called


def test_runner_report_json_contains_psd_fields(monkeypatch, tmp_path):
    calls = []
    _stub_pipeline(monkeypatch, calls)
    path = runner_mod.run_consistency_check(node="NOA", epochs=1, check_psd=True, report_dir=tmp_path)
    report = json.loads(path.read_text())
    rec = report["results"][0]
    assert "psd_status" in rec and "psd_present" in rec and "psd_required" in rec
    assert "psd" in rec["coverage"]
    assert "data_yes_psd_no" in report["summary"]

def test_runner_flags_orphan_psd_when_the_whole_day_is_dataless(monkeypatch, tmp_path):
    calls = []
    _stub_pipeline(monkeypatch, calls)
    # No data in the window ...
    monkeypatch.setattr(runner_mod, "dataselect", lambda *a, **k: {
        "success": False, "status": "NoData", "type": "None",
        "segments": [], "url": "http://ds", "debug": ""})
    # ... but PSD exists for the day ...
    monkeypatch.setattr(runner_mod, "psd_coverage", lambda *a, **k: {
        "success": True, "status": "OK", "records": [], "day_covered": True, "url": "http://psd"})
    # ... and availability reports nothing all day.
    probes = []

    def fake_day(*a, **k):
        probes.append((a, k))
        return {"ok": True, "has_spans": False, "url": "http://day"}

    monkeypatch.setattr(runner_mod, "day_has_spans", fake_day)

    path = runner_mod.run_consistency_check(node="NOA", epochs=1, check_psd=True, report_dir=tmp_path)
    report = json.loads(path.read_text())
    rec = report["results"][0]
    assert len(probes) == 1
    assert rec["psd_status"] == "Orphan"
    assert rec["psd_day_url"] == "http://day"
    assert report["summary"]["psd_yes_data_no"] == 1


def test_runner_does_not_probe_the_day_when_data_is_present(monkeypatch, tmp_path):
    calls = []
    _stub_pipeline(monkeypatch, calls)
    probes = []
    monkeypatch.setattr(runner_mod, "day_has_spans",
                        lambda *a, **k: probes.append(1) or {"ok": True, "has_spans": True, "url": "u"})
    runner_mod.run_consistency_check(node="NOA", epochs=1, check_psd=True, report_dir=tmp_path)
    assert probes == []
