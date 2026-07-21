import json
import pytest
import logging
from pathlib import Path
from click.testing import CliRunner
import eida_consistency.cli as cli


# -----------------
# normalize_log_level / _setup_logging
# -----------------

def test_check_outputs_timeline_and_direction(monkeypatch, caplog):
    import eida_consistency.services.availability as avail_mod
    import eida_consistency.services.dataselect as ds_mod
    import eida_consistency.utils.nodes as nodes_mod

    monkeypatch.setattr(nodes_mod, "load_node_url", lambda node: "http://fake/")
    monkeypatch.setattr(avail_mod, "check_availability_query",
                        lambda *a, **kw: {"ok": False, "status": 200, "matched_span": None,
                                          "spans": [{"start": "2014-02-15T05:17:09.6",
                                                     "end": "2014-02-15T05:19:01.6",
                                                     "samplerate": "100.0"}]})
    monkeypatch.setattr(ds_mod, "dataselect",
                        lambda *a, **kw: {"success": True, "status": "OK", "type": "SingleTrace",
                                          "segments": [("2014-02-15T05:17:09.6",
                                                        "2014-02-15T05:18:25.0", 100.0)]})
    import eida_consistency.services.psd as psd_mod
    monkeypatch.setattr(psd_mod, "psd_coverage",
                        lambda *a, **kw: {"success": True, "status": "NoData",
                                          "day_covered": False, "records": [],
                                          "url": "http://fake/eidaws/psd/1/coverage?net=FR"})
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    result = runner.invoke(cli.check, [
        "--node", "EPOSFR", "--net", "FR", "--sta", "MLS", "--loc", "00", "--cha", "HHN",
        "--start", "2014-02-15T05:09:53", "--end", "2014-02-15T05:19:53",
    ], obj={})
    assert result.exit_code == 0, result.output
    out = caplog.text
    assert "INCONSISTENT" in out
    assert "Availability: data · Dataselect: NO DATA" in out   # direction label on the gap
    assert "▼" in out                                          # down-triangle direction
    assert "█" in out                                          # timeline coverage block
    # PSD triangle surfaced in the check command
    assert "PSD:" in out                                       # PSD data line
    assert "Data vs PSD" in out                                # PSD verdict line
    assert "pre-2024 gap" in out                               # 2014 window, data but no PSD, not required
    assert "Triangle:" in out                                  # A/D/P triad line


def test_check_availability_line_reports_data_presence_not_legacy_no(monkeypatch, caplog):
    """Availability returned a span (HTTP 200) but doesn't cover the whole window.
    The line must say data is present, NOT the misleading legacy 'NO'."""
    import eida_consistency.services.availability as avail_mod
    import eida_consistency.services.dataselect as ds_mod
    import eida_consistency.utils.nodes as nodes_mod

    monkeypatch.setattr(nodes_mod, "load_node_url", lambda node: "http://fake/")
    monkeypatch.setattr(avail_mod, "check_availability_query",
                        lambda *a, **kw: {"ok": False, "status": 200, "matched_span": None,
                                          "spans": [{"start": "2014-02-15T05:17:09.6",
                                                     "end": "2014-02-15T05:19:01.6",
                                                     "samplerate": "100.0"}]})
    monkeypatch.setattr(ds_mod, "dataselect",
                        lambda *a, **kw: {"success": True, "status": "OK", "type": "SingleTrace",
                                          "segments": [("2014-02-15T05:17:09.6",
                                                        "2014-02-15T05:18:25.0", 100.0)]})
    import eida_consistency.services.psd as psd_mod
    monkeypatch.setattr(psd_mod, "psd_coverage",
                        lambda *a, **kw: {"success": True, "status": "NoData",
                                          "day_covered": False, "records": [],
                                          "url": "http://fake/eidaws/psd/1/coverage?net=FR"})
    caplog.set_level(logging.INFO)
    CliRunner().invoke(cli.check, [
        "--node", "EPOSFR", "--net", "FR", "--sta", "MLS", "--loc", "00", "--cha", "HHN",
        "--start", "2014-02-15T05:09:53", "--end", "2014-02-15T05:19:53",
    ], obj={})
    out = caplog.text
    assert "Availability: data present" in out
    assert "Availability: NO" not in out


def test_normalize_log_level_valid():
    assert cli.normalize_log_level("info") == logging.INFO
    assert cli.normalize_log_level("DEBUG") == logging.DEBUG

def test_normalize_log_level_invalid():
    with pytest.raises(Exception):
        cli.normalize_log_level("notalevel")

def test_setup_logging_runs(caplog):
    cli._setup_logging("DEBUG")
    logging.debug("hello debug")
    assert True  # just ensure no crash


# -----------------
# cli group
# -----------------

def test_cli_no_subcommand_shows_help():
    runner = CliRunner()
    result = runner.invoke(cli.cli, [])
    assert result.exit_code != 0
    assert "EIDA consistency checker." in result.output


# -----------------
# consistency command
# -----------------

def test_consistency_delete_old(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(cli, "delete_old_reports", lambda report_dir, keep=1: caplog.set_level(logging.INFO))
    runner = CliRunner()
    result = runner.invoke(cli.consistency, ["--delete-old"], obj={"report_dir": tmp_path})
    assert result.exit_code == 0

def test_consistency_missing_node():
    runner = CliRunner()
    result = runner.invoke(cli.consistency, [], obj={"report_dir": Path(".")})
    assert result.exit_code != 0
    assert "--node is required" in result.output

def test_consistency_duration_too_short():
    runner = CliRunner()
    result = runner.invoke(cli.consistency, ["--node", "NOA", "--duration", "100"], obj={"report_dir": Path(".")})
    assert result.exit_code != 0
    assert "Duration must be at least 600" in result.output

def test_consistency_runs(monkeypatch, tmp_path):
    called = {}
    def fake_run(**kwargs): called.update(kwargs)
    monkeypatch.setattr(cli, "run_consistency_check", fake_run)
    runner = CliRunner()
    result = runner.invoke(cli.consistency, ["--node", "NOA"], obj={"report_dir": tmp_path})
    assert result.exit_code == 0
    assert called["node"] == "NOA"


def test_consistency_report_dir_after_subcommand(monkeypatch, tmp_path):
    """--report-dir placed AFTER the subcommand overrides the group default."""
    target = tmp_path / "custom"
    called = {}
    monkeypatch.setattr(cli, "run_consistency_check", lambda **kw: called.update(kw))
    runner = CliRunner()
    result = runner.invoke(
        cli.consistency,
        ["--node", "NOA", "--report-dir", str(target)],
        obj={"report_dir": tmp_path},
    )
    assert result.exit_code == 0, result.output
    assert called["report_dir"] == target


def test_consistency_seed_option_removed(monkeypatch, tmp_path):
    """--seed was removed: passing it is a usage error, and it never reaches the runner."""
    called = {}
    monkeypatch.setattr(cli, "run_consistency_check", lambda **kw: called.update(kw))
    runner = CliRunner()
    result = runner.invoke(
        cli.consistency, ["--node", "NOA", "--seed", "123"], obj={"report_dir": tmp_path}
    )
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()
    assert called == {}  # runner not invoked at all


# -----------------
# compare command
# -----------------

def test_compare_invokes(monkeypatch):
    called = {}
    monkeypatch.setattr(cli, "compare_reports", lambda a, b, report_dir=None: called.update({"a": a, "b": b}))
    runner = CliRunner()
    result = runner.invoke(cli.compare, ["r1.json", "r2.json"], obj={"report_dir": Path(".")})
    assert result.exit_code == 0
    assert called == {"a": "r1.json", "b": "r2.json"}


# -----------------
# rerun command
# -----------------

_RERUN_RESULT = {
    "schema_version": "1.0",
    "node": "NOA",
    "report": "r.json",
    "results": [
        {"index": 2, "label": "XX.STA..BHZ", "start": "2023-01-01T00:00:00",
         "end": "2023-01-01T00:10:00", "verdict": "PERSISTS"},
    ],
}


def test_rerun_prints_summary(monkeypatch, tmp_path, caplog):
    # rerun_report is mocked, so per-row verdicts (which it streams itself) don't
    # appear here; the CLI's own output is just the closing tally.
    import eida_consistency.rerun as rerun_mod
    monkeypatch.setattr(rerun_mod, "rerun_report", lambda *a, **k: _RERUN_RESULT)
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    result = runner.invoke(cli.rerun, ["r.json"], obj={"report_dir": tmp_path})
    assert result.exit_code == 0, result.output
    assert "Summary: 1 re-run — 1 persists" in caplog.text


def test_rerun_json_is_pure_stdout(monkeypatch, tmp_path):
    import eida_consistency.rerun as rerun_mod
    monkeypatch.setattr(rerun_mod, "rerun_report", lambda *a, **k: _RERUN_RESULT)
    runner = CliRunner()
    result = runner.invoke(cli.rerun, ["r.json", "--json"], obj={"report_dir": tmp_path})
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["results"][0]["verdict"] == "PERSISTS"


def test_rerun_no_report_found(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli.rerun, [], obj={"report_dir": tmp_path})
    assert result.exit_code != 0
    assert "No report files found" in result.output


# -----------------
# explore command
# -----------------

def test_explore_with_file(monkeypatch, tmp_path):
    f = tmp_path / "rep.json"
    f.write_text("{}")
    called = {}
    monkeypatch.setattr(cli, "explore_boundaries",
                        lambda report, indices, max_days, verbose: called.update({"report": report}))
    runner = CliRunner()
    result = runner.invoke(cli.explore, [str(f)], obj={"report_dir": tmp_path})
    assert result.exit_code == 0
    assert "report" in called

def test_explore_with_latest(monkeypatch, tmp_path):
    f = tmp_path / "rep.json"
    f.write_text("{}")
    called = {}
    monkeypatch.setattr(cli, "explore_boundaries",
                        lambda report, indices, max_days, verbose: called.update({"report": report}))
    runner = CliRunner()
    result = runner.invoke(cli.explore, [], obj={"report_dir": tmp_path})
    assert result.exit_code == 0
    assert called["report"].name == "rep.json"

def test_explore_report_dir_after_subcommand(monkeypatch, tmp_path):
    """explore honors --report-dir placed after the subcommand when finding latest."""
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "rep.json").write_text("{}")
    called = {}
    monkeypatch.setattr(cli, "explore_boundaries",
                        lambda report, indices, max_days, verbose: called.update({"report": report}))
    runner = CliRunner()
    # group default (tmp_path) has no reports; the override (custom) does.
    result = runner.invoke(cli.explore, ["--report-dir", str(custom)],
                           obj={"report_dir": tmp_path})
    assert result.exit_code == 0, result.output
    assert called["report"].name == "rep.json"
    assert called["report"].parent == custom


def test_explore_no_reports(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli.explore, [], obj={"report_dir": tmp_path})
    assert result.exit_code != 0
    assert "No report files found" in result.output

def test_explore_json_flag_outputs_json(monkeypatch, tmp_path):
    f = tmp_path / "rep.json"
    f.write_text("{}")
    sample = {
        "schema_version": "1.0",
        "node": "NOA",
        "report": str(f),
        "fixes": [{
            "index": 1, "network": "XX", "station": "STA",
            "location": "00", "channel": "BHZ",
            "start": "2008-01-01", "end": "2008-02-01",
            "direction": "refresh", "status": "actionable",
        }],
    }
    monkeypatch.setattr(cli, "explore_boundaries",
                        lambda report, indices, max_days, verbose: sample)
    runner = CliRunner()
    result = runner.invoke(cli.explore, [str(f), "--json"], obj={"report_dir": tmp_path})
    assert result.exit_code == 0
    parsed = json.loads(result.output)  # stdout must be pure JSON
    assert parsed["schema_version"] == "1.0"
    assert parsed["fixes"][0]["direction"] == "refresh"
    assert parsed["fixes"][0]["status"] == "actionable"

def test_explore_without_json_flag_prints_no_json(monkeypatch, tmp_path):
    f = tmp_path / "rep.json"
    f.write_text("{}")
    monkeypatch.setattr(cli, "explore_boundaries",
                        lambda report, indices, max_days, verbose: {"fixes": []})
    runner = CliRunner()
    result = runner.invoke(cli.explore, [str(f)], obj={"report_dir": tmp_path})
    assert result.exit_code == 0
    assert "schema_version" not in result.output  # no JSON dumped without the flag

def test_explore_json_end_to_end(monkeypatch, tmp_path):
    """--json runs the REAL explore_boundaries and emits structured fixes on stdout."""
    import eida_consistency.explorer as explorer
    report = tmp_path / "rep.json"
    report.write_text(json.dumps({
        "summary": {"node": "NOA"},
        "results": [{
            "index": 1, "network": "XX", "station": "STA",
            "channel": "BHZ", "location": "00",
            "starttime": "2023-01-01T00:00:00Z", "endtime": "2023-01-01T01:00:00Z",
            "consistent": False, "available": True, "dataselect_success": False,
        }],
    }))
    # availability covers the window, dataselect always fails -> inconsistent/actionable
    monkeypatch.setattr(explorer, "get_availability_spans",
                        lambda *a, **kw: [{"start": "2020-01-01T00:00:00", "end": "2025-01-01T00:00:00"}])
    monkeypatch.setattr(explorer, "dataselect", lambda *a, **kw: {"success": False})
    monkeypatch.setattr(explorer, "load_node_url", lambda node: "http://fake/")

    runner = CliRunner()
    result = runner.invoke(cli.explore, [str(report), "--json", "--days", "1"],
                           obj={"report_dir": tmp_path})
    assert result.exit_code == 0
    # CliRunner folds stderr (progress/logs) into output; in a real terminal they
    # are separate fds. The JSON block is emitted last, so parse from its first '{'.
    parsed = json.loads(result.output[result.output.index("{"):])
    assert parsed["schema_version"] == "1.0"
    assert parsed["node"] == "NOA"
    assert len(parsed["fixes"]) == 1
    fix = parsed["fixes"][0]
    assert (fix["network"], fix["station"], fix["location"], fix["channel"]) == ("XX", "STA", "00", "BHZ")
    assert fix["direction"] == "clean"   # report: available=True, dataselect=False
    assert fix["status"] == "actionable"
    assert fix["start"] and fix["end"]


# -----------------
# reload-nodes command
# -----------------

def test_reload_nodes_success(monkeypatch, caplog):
    monkeypatch.setattr(cli.nodes, "refresh_cache_from_routing", lambda: [("X", "http://fake/", True)])
    runner = CliRunner()
    caplog.set_level(logging.INFO)
    result = runner.invoke(cli.reload_nodes)
    assert result.exit_code == 0
    assert "Reloaded" in caplog.text

def test_reload_nodes_failure(monkeypatch):
    def fail(): raise Exception("boom")
    monkeypatch.setattr(cli.nodes, "refresh_cache_from_routing", fail)
    runner = CliRunner()
    result = runner.invoke(cli.reload_nodes)
    assert result.exit_code != 0
    assert "Failed to reload nodes" in result.output


# -----------------
# list-nodes command
# -----------------

def test_list_nodes(monkeypatch, caplog):
    monkeypatch.setattr(cli.nodes, "load_or_refresh_cache", lambda: [("X", "http://fake/", True)])
    runner = CliRunner()
    caplog.set_level(logging.INFO)
    result = runner.invoke(cli.list_nodes)
    assert result.exit_code == 0
    assert "nodes currently cached" in caplog.text


# -----------------
# check command
# -----------------

def test_check_command_consistent(monkeypatch, caplog):
    import eida_consistency.utils.nodes as nodes
    monkeypatch.setattr(nodes, "load_node_url", lambda n: "http://fake/")
    
    def fake_av(*args, **kwargs):
        return {"ok": True, "status": 200}
    
    def fake_ds(*args, **kwargs):
        return {"success": True, "status": 200, "debug": ""}
    
    import eida_consistency.services.availability as av
    import eida_consistency.services.dataselect as ds
    import eida_consistency.services.psd as psd_mod
    monkeypatch.setattr(psd_mod, "psd_coverage",
                        lambda *a, **kw: {"success": True, "status": "NoData",
                                          "day_covered": False, "records": [],
                                          "url": "http://fake/psd"})
    monkeypatch.setattr(av, "check_availability_query", fake_av)
    monkeypatch.setattr(ds, "dataselect", fake_ds)

    caplog.set_level(logging.INFO)
    runner = CliRunner()
    result = runner.invoke(cli.check, [
        "--node", "NOA", "--net", "HP", "--sta", "SERG",
        "--cha", "HHN", "--start", "2016-09-20", "--end", "2016-10-19"
    ])

    assert result.exit_code == 0
    assert "Checking Availability" in caplog.text
    assert "Checking Dataselect" in caplog.text
    assert "Summary (Avail vs Data): CONSISTENT" in caplog.text
    assert "PSD:" in caplog.text

def test_check_command_inconsistent(monkeypatch, caplog):
    import eida_consistency.utils.nodes as nodes
    monkeypatch.setattr(nodes, "load_node_url", lambda n: "http://fake/")

    
    def fake_av(*args, **kwargs):
        return {"ok": True, "status": 200,
                "spans": [{"start": "2016-09-20T00:00:00", "end": "2016-10-19T00:00:00",
                           "samplerate": "100.0"}]}

    def fake_ds(*args, **kwargs):
        return {"success": False, "status": 204, "debug": "NO DATA", "segments": []}
    
    import eida_consistency.services.availability as av
    import eida_consistency.services.dataselect as ds
    import eida_consistency.services.psd as psd_mod
    monkeypatch.setattr(psd_mod, "psd_coverage",
                        lambda *a, **kw: {"success": True, "status": "NoData",
                                          "day_covered": False, "records": [],
                                          "url": "http://fake/psd"})
    monkeypatch.setattr(av, "check_availability_query", fake_av)
    monkeypatch.setattr(ds, "dataselect", fake_ds)

    caplog.set_level(logging.DEBUG)
    runner = CliRunner()
    result = runner.invoke(cli.check, [
        "--node", "NOA", "--net", "HP", "--sta", "SERG",
        "--cha", "HHN", "--start", "2016-09-20", "--end", "2016-10-19"
    ])

    assert result.exit_code == 0
    assert "Summary (Avail vs Data): INCONSISTENT" in caplog.text
    assert "Debug: NO DATA" in caplog.text


# -----------------
# consistency command: --psd/--no-psd flag
# -----------------

import eida_consistency.cli as cli_mod


def test_consistency_no_psd_passes_check_psd_false(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli_mod, "run_consistency_check",
                        lambda **kw: captured.update(kw) or None)
    res = CliRunner().invoke(cli_mod.cli, ["consistency", "--node", "NOA", "--no-psd"])
    assert res.exit_code == 0
    assert captured["check_psd"] is False


def test_consistency_defaults_check_psd_true(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli_mod, "run_consistency_check",
                        lambda **kw: captured.update(kw) or None)
    res = CliRunner().invoke(cli_mod.cli, ["consistency", "--node", "NOA"])
    assert res.exit_code == 0
    assert captured["check_psd"] is True

