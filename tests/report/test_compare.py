import pytest
import json
import logging
from pathlib import Path
import eida_consistency.report.compare as cmp


# -----------------
# _load_report
# -----------------

def test_load_report_success(tmp_path):
    data = {"summary": {"node": "X", "total_checked": 1,
                        "total_consistent": 1, "total_inconsistent": 0,
                        "score": 100}}
    p = tmp_path / "report.json"
    p.write_text(json.dumps(data))
    result = cmp._load_report(p)
    assert result["summary"]["node"] == "X"

def test_load_report_failure(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json}")
    with pytest.raises(Exception):
        cmp._load_report(p)


# -----------------
# compare_reports
# -----------------

def make_report(path: Path, node: str, checked=10, consistent=8, inconsistent=2, score=80):
    data = {
        "summary": {
            "node": node,
            "total_checked": checked,
            "total_consistent": consistent,
            "total_inconsistent": inconsistent,
            "score": score,
        }
    }
    path.write_text(json.dumps(data))
    return path

def test_compare_reports_logs(tmp_path, caplog):
    r1 = make_report(tmp_path / "r1.json", "NODE1", 10, 8, 2, 80)
    r2 = make_report(tmp_path / "r2.json", "NODE2", 12, 9, 3, 75)

    caplog.set_level(logging.INFO)
    cmp.compare_reports(r1, r2)

    logs = "\n".join(caplog.messages)
    assert "Report comparison" in logs
    assert "NODE1" in logs and "NODE2" in logs
    assert "Total checks" in logs
    assert "Score" in logs

def test_compare_reports_with_report_dir(tmp_path, caplog):
    r1 = make_report(tmp_path / "a.json", "A")
    r2 = make_report(tmp_path / "b.json", "B")

    caplog.set_level(logging.INFO)
    # pass only filenames, but supply report_dir
    cmp.compare_reports("a.json", "b.json", report_dir=tmp_path)

    logs = "\n".join(caplog.messages)
    assert "A vs B" in logs
