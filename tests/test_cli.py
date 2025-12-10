import pytest
import logging
from pathlib import Path
from click.testing import CliRunner
import eida_consistency.cli as cli


# -----------------
# normalize_log_level / _setup_logging
# -----------------

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
