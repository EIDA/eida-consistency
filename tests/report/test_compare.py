import json
import sys
import pytest
from pathlib import Path
from eida_consistency.report.compare import compare_reports


def make_report(path: Path, seed: int, results: list):
    data = {
        "summary": {"seed": seed},
        "results": results,
    }
    with open(path, "w") as f:
        json.dump(data, f)


def test_different_seeds_exits(tmp_path):
    r1 = tmp_path / "r1.json"
    r2 = tmp_path / "r2.json"
    make_report(r1, seed=1, results=[])
    make_report(r2, seed=2, results=[])

    with pytest.raises(SystemExit) as e:
        compare_reports(r1, r2)
    assert e.value.code == 1

def test_improved_regressed_missing_and_unchanged(tmp_path, capsys):
    r1 = tmp_path / "r1.json"
    r2 = tmp_path / "r2.json"

    base_key = {
        "network": "XX",
        "station": "AAA",
        "location": "00",
        "starttime": "2020-01-01T00:00:00",
        "endtime": "2020-01-01T00:10:00",
    }

    # Report 1 has three entries:
    res1 = [
        {**base_key, "channel": "BHZ", "consistent": True},   # will regress
        {**base_key, "channel": "BHN", "consistent": False},  # will improve
        {**base_key, "channel": "BHE", "consistent": True},   # will be missing
    ]

    # Report 2 flips BHN (improved), BHZ (regressed), omits BHE (missing)
    res2 = [
        {**base_key, "channel": "BHZ", "consistent": False},  # regression
        {**base_key, "channel": "BHN", "consistent": True},   # improvement
    ]

    make_report(r1, seed=123, results=res1)
    make_report(r2, seed=123, results=res2)

    compare_reports(r1, r2)
    out = capsys.readouterr().out

    assert "Improvements: 1" in out
    assert "Regressions: 1" in out
    assert "Missing in Report 2: 1" in out
    assert "Unchanged: 0" in out
    assert "Improved entries" in out
    assert "Regressed entries" in out
    assert "Missing entries" in out


def test_unchanged_only(tmp_path, capsys):
    r1 = tmp_path / "r1.json"
    r2 = tmp_path / "r2.json"

    key = {
        "network": "YY",
        "station": "BBB",
        "location": "00",
        "channel": "BHZ",
        "starttime": "2020-01-01T00:00:00",
        "endtime": "2020-01-01T00:10:00",
    }

    res = [{**key, "consistent": True}]
    make_report(r1, seed=42, results=res)
    make_report(r2, seed=42, results=res)

    compare_reports(r1, r2)
    out = capsys.readouterr().out

    assert "Improvements: 0" in out
    assert "Regressions: 0" in out
    assert "Unchanged: 1" in out
    assert "Missing in Report 2: 0" in out
