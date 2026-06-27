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
    assert "Summary: CONSISTENT" in caplog.text

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
    monkeypatch.setattr(av, "check_availability_query", fake_av)
    monkeypatch.setattr(ds, "dataselect", fake_ds)
    
    caplog.set_level(logging.DEBUG)
    runner = CliRunner()
    result = runner.invoke(cli.check, [
        "--node", "NOA", "--net", "HP", "--sta", "SERG", 
        "--cha", "HHN", "--start", "2016-09-20", "--end", "2016-10-19"
    ])
    
    assert result.exit_code == 0
    assert "Summary: INCONSISTENT" in caplog.text
    assert "Debug: NO DATA" in caplog.text

