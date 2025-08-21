# tests/test_cli.py
import json
import logging
import runpy
import sys
from click.testing import CliRunner
from unittest.mock import patch
import pytest
import click

from eida_consistency.cli import cli


# ---------- Helpers ------------------------------------------------------------

def assert_called_with_subset(mock, **expected_subset):
    """Assert last call's kwargs contain at least this subset."""
    assert mock.call_args is not None, "Function was not called"
    actual = mock.call_args.kwargs
    for k, v in expected_subset.items():
        assert actual.get(k) == v, f"Expected {k}={v}, got {actual.get(k)}"


def _find_log_level_normalizer():
    """
    Try common helper names used for log-level normalization.
    We assume your cli.py defines one of these (private or public).
    """
    import eida_consistency.cli as cli_mod

    candidates = [
        "_normalize_log_level",
        "normalize_log_level",
        "_coerce_log_level",
        "coerce_log_level",
        "_parse_log_level",
        "parse_log_level",
    ]
    for name in candidates:
        fn = getattr(cli_mod, name, None)
        if callable(fn):
            return fn
    return None


# ---------- CLI tests ----------------------------------------------------------

@patch("eida_consistency.cli.run_consistency_check")
def test_consistency_prints_json_and_calls_runner(mock_run):
    # Simulate runner printing JSON to stdout; CLI should surface it
    mock_run.side_effect = lambda **kwargs: print(
        json.dumps({"summary": {"node": kwargs["node"], "epochs": kwargs["epochs"]}})
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--log-level", "DEBUG",
            "consistency",
            "--node", "NOA",
            "--epochs", "2",
            "--duration", "60",
            "--seed", "123",
        ],
    )

    assert result.exit_code == 0
    out = json.loads(result.output.strip())
    assert out["summary"]["node"] == "NOA"
    assert out["summary"]["epochs"] == 2

    assert_called_with_subset(
        mock_run,
        node="NOA",
        epochs=2,
        duration=60,
        seed=123,
    )


@patch("eida_consistency.cli.compare_reports")
def test_cli_compare_calls_compare_reports(mock_compare, tmp_path):
    f1 = tmp_path / "report1.json"
    f2 = tmp_path / "report2.json"
    f1.write_text("{}")
    f2.write_text("{}")

    runner = CliRunner()
    result = runner.invoke(cli, ["compare", str(f1), str(f2)])

    assert result.exit_code == 0
    mock_compare.assert_called_once_with(str(f1), str(f2))


@patch("eida_consistency.cli.run_consistency_check")
def test_cli_accepts_log_level_option_and_forwards_core_args(mock_run):
    mock_run.side_effect = lambda **kwargs: None

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--log-level", "INFO",
            "consistency",
            "--node", "RESIF",
            "--epochs", "1",
        ],
    )

    assert result.exit_code == 0
    # Default duration=600, seed=None (as implied by your earlier tests)
    assert_called_with_subset(
        mock_run,
        node="RESIF",
        epochs=1,
        duration=600,
        seed=None,
    )


def test_cli_no_subcommand_shows_usage_and_exits_nonzero():
    runner = CliRunner()
    result = runner.invoke(cli, [])
    assert result.exit_code != 0  # typically 2
    assert "Usage:" in result.output


def test_consistency_requires_node_option():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "consistency",
            "--epochs", "1",
        ],
    )
    assert result.exit_code != 0
    assert "Missing option" in result.output or "Error" in result.output


def test_consistency_requires_epochs_int():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "consistency",
            "--node", "NOA",
            "--epochs", "not-an-int",
        ],
    )
    assert result.exit_code != 0
    assert "Invalid value for" in result.output or "Error" in result.output


@patch("eida_consistency.cli.run_consistency_check")
def test_consistency_delete_old_flag_is_accepted_but_subset_assert(mock_run):
    mock_run.side_effect = lambda **kwargs: None

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "consistency",
            "--node", "NOA",
            "--epochs", "1",
            "--delete-old",
        ],
    )
    assert result.exit_code == 0
    # We only assert on the subset we know is forwarded
    assert_called_with_subset(
        mock_run,
        node="NOA",
        epochs=1,
        duration=600,
        seed=None,
    )


@patch("eida_consistency.cli.run_consistency_check")
def test_consistency_explicit_duration_forwarded(mock_run):
    mock_run.side_effect = lambda **kwargs: None

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "consistency",
            "--node", "ETH",
            "--epochs", "3",
            "--duration", "90",
        ],
    )
    assert result.exit_code == 0
    assert_called_with_subset(
        mock_run,
        node="ETH",
        epochs=3,
        duration=90,
        seed=None,
    )


@patch("eida_consistency.cli.run_consistency_check")
def test_consistency_runner_exception_propagates_nonzero(mock_run):
    mock_run.side_effect = RuntimeError("boom")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "consistency",
            "--node", "NOA",
            "--epochs", "1",
        ],
    )
    assert result.exit_code != 0
    if result.exception is not None:
        assert isinstance(result.exception, RuntimeError)


@patch("eida_consistency.cli.compare_reports")
def test_compare_requires_two_paths(mock_compare):
    runner = CliRunner()
    result = runner.invoke(cli, ["compare", "only_one.json"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output or "Error" in result.output
    mock_compare.assert_not_called()


@patch("eida_consistency.cli.compare_reports")
def test_compare_exception_is_nonzero(mock_compare, tmp_path):
    f1 = tmp_path / "report1.json"
    f2 = tmp_path / "report2.json"
    f1.write_text("{}")
    f2.write_text("{}")

    mock_compare.side_effect = ValueError("cannot compare")

    runner = CliRunner()
    result = runner.invoke(cli, ["compare", str(f1), str(f2)])
    assert result.exit_code != 0


# ---------- Direct coverage of log-level normalizer ---------------------------

def test_log_level_normalizer_invalid_raises_badparameter():
    """
    Covers: if not isinstance(numeric, int): raise click.BadParameter(...)
    We call the normalizer directly so Click's Choice validation doesn't intercept.
    """
    normalizer = _find_log_level_normalizer()
    assert normalizer is not None, (
        "Could not find a log-level normalizer helper in eida_consistency.cli "
        "(expected one of: _normalize_log_level, normalize_log_level, "
        "_coerce_log_level, coerce_log_level, _parse_log_level, parse_log_level)"
    )
    with pytest.raises(click.BadParameter) as excinfo:
        normalizer("BANANA")
    assert "Invalid log level" in str(excinfo.value)


def test_log_level_normalizer_valid_returns_int():
    """Positive path: valid levels map to logging.* ints."""
    normalizer = _find_log_level_normalizer()
    assert normalizer is not None
    val = normalizer("INFO")
    assert isinstance(val, int)
    assert val == logging.INFO


# ---------- __main__ guard coverage ------------------------------------------

def test_module_runs_via___main__(monkeypatch):
    """
    Covers: if __name__ == '__main__': cli()
    Simulate `python -m eida_consistency.cli --help` (clean exit 0).
    """
    monkeypatch.setattr(sys, "argv", ["eida_consistency.cli", "--help"])
    # Ensure we don't have a partially-imported module when running as __main__
    sys.modules.pop("eida_consistency.cli", None)
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("eida_consistency.cli", run_name="__main__")
    assert excinfo.value.code == 0
