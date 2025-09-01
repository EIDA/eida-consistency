import json
import runpy
import sys
import pytest
import click
from pathlib import Path
from click.testing import CliRunner

import eida_consistency.cli as cli


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def make_dummy_report(tmp_path: Path, name="r.json"):
    """Create a minimal dummy report JSON file."""
    path = tmp_path / name
    report = {"summary": {}, "results": []}
    path.write_text(json.dumps(report))
    return path


# -------------------------------------------------------------------
# consistency command
# -------------------------------------------------------------------
def test_consistency_with_node_and_delete_old(monkeypatch, tmp_path, caplog):
    runner = CliRunner()
    caplog.set_level("INFO")

    # Patch housekeeping
    monkeypatch.setattr(cli, "delete_old_reports", lambda *_a, **_k: caplog.messages.append("delete called"))

    result = runner.invoke(cli.cli, ["consistency", "--delete-old"])
    assert result.exit_code == 0
    assert any("delete called" in msg or "Old reports cleaned" in msg for msg in caplog.messages)


def test_consistency_with_node_and_seed(monkeypatch):
    runner = CliRunner()
    called = {}

    monkeypatch.setattr(cli, "run_consistency_check", lambda **kwargs: called.update(kwargs))

    result = runner.invoke(cli.cli, ["consistency", "--node", "FAKE", "--epochs", "2", "--seed", "123"])
    assert result.exit_code == 0
    assert called["node"] == "FAKE"
    assert called["epochs"] == 2
    assert called["seed"] == 123


def test_consistency_fails_without_node():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ["consistency"])
    assert result.exit_code != 0
    assert "--node is required" in result.output


def test_consistency_invalid_duration():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ["consistency", "--node", "FAKE", "--duration", "100"])
    assert result.exit_code != 0
    assert "Duration must be at least" in result.output


# -------------------------------------------------------------------
# compare command
# -------------------------------------------------------------------
def test_compare_command(monkeypatch, tmp_path):
    runner = CliRunner()
    dummy1 = make_dummy_report(tmp_path, "r1.json")
    dummy2 = make_dummy_report(tmp_path, "r2.json")

    called = {}
    monkeypatch.setattr(cli, "compare_reports", lambda a, b: called.update({"a": a, "b": b}))

    result = runner.invoke(cli.cli, ["compare", str(dummy1), str(dummy2)])
    assert result.exit_code == 0
    assert called["a"].endswith("r1.json")
    assert called["b"].endswith("r2.json")


# -------------------------------------------------------------------
# explore command
# -------------------------------------------------------------------
def test_explore_with_explicit_report_and_index(monkeypatch, tmp_path):
    runner = CliRunner()
    dummy_report = make_dummy_report(tmp_path)

    called = {}
    monkeypatch.setattr(cli, "explore_boundaries", lambda report, indices: called.update({"report": str(report), "indices": indices}))

    result = runner.invoke(cli.cli, ["explore", str(dummy_report), "--index", "1,2"])
    assert result.exit_code == 0
    assert called["report"].endswith("r.json")
    assert called["indices"] == [1, 2]


def test_explore_with_no_report_uses_latest(monkeypatch, tmp_path):
    runner = CliRunner()
    dummy_report = make_dummy_report(tmp_path, "latest.json")
    cli.REPORT_DIR = tmp_path  # point to tmp_path

    called = {}
    monkeypatch.setattr(cli, "explore_boundaries", lambda report, indices: called.update({"report": str(report), "indices": indices}))

    result = runner.invoke(cli.cli, ["explore"])
    assert result.exit_code == 0
    assert Path(called["report"]).name == "latest.json"
    assert called["indices"] is None


def test_explore_no_reports_found(monkeypatch, tmp_path):
    runner = CliRunner()
    cli.REPORT_DIR = tmp_path  # empty dir
    result = runner.invoke(cli.cli, ["explore"])
    assert result.exit_code != 0
    assert "No report files found" in result.output


# -------------------------------------------------------------------
# Extra coverage: uncovered lines in cli.py
# -------------------------------------------------------------------
def test_invalid_log_level_raises():
    with pytest.raises(click.BadParameter):
        cli.normalize_log_level("INVALID")


def test_cli_no_subcommand_shows_help_and_exits():
    runner = CliRunner()
    result = runner.invoke(cli.cli, [])
    assert result.exit_code == 1
    assert "EIDA consistency checker" in result.output


def test_module_runs_via___main__(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["eida_consistency.cli", "--help"])
    sys.modules.pop("eida_consistency.cli", None)
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("eida_consistency.cli", run_name="__main__")
    assert excinfo.value.code == 0