import json
import pytest
import eida_consistency.runner as runner


def test_generated_seed_branch(monkeypatch, caplog):
    """Covers: seed = random.randint... and logging.info generated seed."""
    caplog.set_level("INFO")

    # Force fetch_candidates to return [] so it exits quickly
    monkeypatch.setattr(runner, "fetch_candidates", lambda base_url: [])
    monkeypatch.setattr(runner, "load_node_url", lambda node: "http://fake/")

    runner.run_consistency_check(node="FAKE")
    assert "Using generated seed" in caplog.text


def test_no_candidates_branch(monkeypatch, caplog):
    """Covers: logging.warning('No candidates fetched.') and return."""
    caplog.set_level("INFO")

    monkeypatch.setattr(runner, "fetch_candidates", lambda base_url: [])
    monkeypatch.setattr(runner, "load_node_url", lambda node: "http://fake/")

    runner.run_consistency_check(node="FAKE", seed=123)
    assert "No candidates fetched." in caplog.text


def test_parse_failure_branch(monkeypatch, tmp_path):
    """Covers: except Exception -> net,sta,cha = '?','?','?'"""
    fake_candidate = {
        "network": "X",
        "station": "Y",
        "channel": "Z",
        "starttime": "2020-01-01T00:00:00",
    }

    monkeypatch.setattr(runner, "fetch_candidates", lambda base_url: [fake_candidate])
    monkeypatch.setattr(runner, "load_node_url", lambda node: "http://fake/")

    # Provide URL with no query string -> triggers parse failure
    monkeypatch.setattr(
        runner,
        "check_candidate",
        lambda *a, **k: [("http://fake/noquery", True, "2020-01-01T00:00:00",
                          "2020-01-01T00:10:00", "00", None)],
    )

    monkeypatch.setattr(
        runner,
        "dataselect",
        lambda *a, **k: {"success": True, "status": "OK", "type": "SingleTrace", "debug": "dbg"},
    )
    monkeypatch.setattr(runner, "format_result", lambda *a, **k: "formatted")

    monkeypatch.setattr(runner, "save_report_json", lambda r, **k: tmp_path / "r.json")
    monkeypatch.setattr(runner, "save_report_markdown", lambda r, **k: tmp_path / "r.md")

    # Should run without raising and hit parse-failure branch
    runner.run_consistency_check(node="FAKE", seed=123)


def test_print_stdout_branch(monkeypatch, tmp_path, capsys):
    """Covers: sys.stdout.write(...) and flush() when print_stdout=True."""
    fake_candidate = {
        "network": "X",
        "station": "Y",
        "channel": "Z",
        "starttime": "2020-01-01T00:00:00",
        "endtime": "2020-01-01T00:10:00",
    }

    monkeypatch.setattr(runner, "fetch_candidates", lambda base_url: [fake_candidate])
    monkeypatch.setattr(runner, "load_node_url", lambda node: "http://fake/")

    monkeypatch.setattr(
        runner,
        "check_candidate",
        lambda *a, **k: [("http://fake/availability?network=X&station=Y&channel=Z",
                          True, "2020-01-01T00:00:00", "2020-01-01T00:10:00", "00", None)],
    )

    monkeypatch.setattr(
        runner,
        "dataselect",
        lambda *a, **k: {"success": True, "status": "OK", "type": "SingleTrace", "debug": "dbg"},
    )
    monkeypatch.setattr(runner, "format_result", lambda *a, **k: "formatted")

    # Save reports to tmp_path
    def fake_save_json(r, **k):
        p = tmp_path / "r.json"
        p.write_text(json.dumps(r))
        return p

    def fake_save_md(r, **k):
        p = tmp_path / "r.md"
        p.write_text("# md")
        return p

    monkeypatch.setattr(runner, "save_report_json", fake_save_json)
    monkeypatch.setattr(runner, "save_report_markdown", fake_save_md)

    runner.run_consistency_check(node="FAKE", seed=123, print_stdout=True)

    out = capsys.readouterr().out
    assert "summary" in out
