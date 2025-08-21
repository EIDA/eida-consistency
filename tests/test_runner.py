import pytest
import logging
from unittest.mock import patch
from eida_consistency import runner
import json

@pytest.fixture(autouse=True)
def patch_dependencies(tmp_path):
    """Patch external dependencies of runner so tests stay isolated."""
    with patch("eida_consistency.runner.fetch_candidates") as mock_fetch, \
         patch("eida_consistency.runner.dataselect") as mock_ds, \
         patch("eida_consistency.runner.check_candidate") as mock_check, \
         patch("eida_consistency.runner.load_node_url") as mock_url, \
         patch("eida_consistency.runner.format_result") as mock_fmt, \
         patch("eida_consistency.runner.create_report_object") as mock_create, \
         patch("eida_consistency.runner.save_report_json") as mock_save_json, \
         patch("eida_consistency.runner.save_report_markdown") as mock_save_md:

        # defaults
        mock_url.return_value = "http://example/fdsnws"
        mock_fetch.return_value = [
            {"network": "XX", "station": "AAA", "channel": "BHZ", "location": ""}
        ]
        mock_check.return_value = [
            ("http://example?network=XX&station=AAA&channel=BHZ", True, "2020-01-01", "2020-01-02", "")
        ]
        mock_ds.return_value = {"success": True, "status": "200", "type": "mseed"}
        mock_fmt.side_effect = lambda *a, **k: "formatted-log"
        mock_create.side_effect = lambda **kw: {
            "summary": {"node": kw["node"], "seed": kw["seed"]},
            "results": kw["records"],
        }
        mock_save_json.return_value = tmp_path / "report.json"
        mock_save_md.return_value = tmp_path / "report.md"

        yield {
            "fetch": mock_fetch,
            "dataselect": mock_ds,
            "check": mock_check,
            "url": mock_url,
            "fmt": mock_fmt,
            "create": mock_create,
            "save_json": mock_save_json,
            "save_md": mock_save_md,
        }


def test_run_consistency_check_normal(patch_dependencies, caplog):
    caplog.set_level(logging.INFO)

    runner.run_consistency_check("NOA", epochs=1, duration=60, seed=123, max_workers=2)

    patch_dependencies["fetch"].assert_called_once()
    patch_dependencies["check"].assert_called_once()
    assert patch_dependencies["dataselect"].called
    assert patch_dependencies["save_json"].called
    assert patch_dependencies["save_md"].called
    assert any("Collected" in rec.message for rec in caplog.records)


def test_run_consistency_check_no_candidates(patch_dependencies, caplog):
    patch_dependencies["fetch"].return_value = []
    caplog.set_level(logging.WARNING)

    result = runner.run_consistency_check("NOA", seed=1)
    assert result is None
    assert any("No candidates" in rec.message for rec in caplog.records)


def test_run_consistency_check_uses_generated_seed(patch_dependencies, caplog):
    caplog.set_level(logging.INFO)
    runner.run_consistency_check("NOA")  # no seed passed
    assert any("Using generated seed" in rec.message for rec in caplog.records)


def test_worker_builds_inconsistent_record(patch_dependencies):
    """Force available != dataselect.success → inconsistent=False case covered."""
    # mismatch here: available=True but dataselect.success=False
    patch_dependencies["check"].return_value = [
        ("http://example?network=XX&station=AAA&channel=BHZ", True, "2020-01-01", "2020-01-02", "")
    ]
    patch_dependencies["dataselect"].return_value = {
        "success": False,
        "status": "500",
        "type": "mseed",
        "debug": "fail",
    }

    runner.run_consistency_check("NOA", epochs=1, seed=42)

    records = patch_dependencies["create"].call_args[1]["records"]
    assert records[0]["consistent"] is False
    assert records[0]["dataselect_status"] == "500"


def test_url_parse_fallback_to_question_marks(patch_dependencies):
    """Covers the except branch when URL has no query string."""
    patch_dependencies["check"].return_value = [
        ("http://example_without_query", True, "2020-01-01", "2020-01-02", "")
    ]
    # Make candidate that matches the fallback "?" values
    patch_dependencies["fetch"].return_value = [
        {"network": "?", "station": "?", "channel": "?", "location": ""}
    ]

    runner.run_consistency_check("NOA", epochs=1, seed=77)

    records = patch_dependencies["create"].call_args[1]["records"]
    assert records[0]["network"] == "?"
    assert records[0]["station"] == "?"
    assert records[0]["channel"] == "?"

def test_run_consistency_check_prints_stdout(patch_dependencies, capsys):
    """Ensure JSON report is written to stdout when print_stdout=True."""
    runner.run_consistency_check("NOA", epochs=1, seed=123, print_stdout=True)

    captured = capsys.readouterr().out
    assert captured.strip()  # not empty
    data = json.loads(captured)
    assert "summary" in data
    assert data["summary"]["node"] == "NOA"
    assert data["summary"]["seed"] == 123
