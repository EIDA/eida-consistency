import json

import pytest

import eida_consistency.reverify as reverify
import eida_consistency.rerun as rerun_mod


def make_row(index, consistent, net="XX", sta="STA", loc="", cha="BHZ"):
    return {
        "index": index,
        "network": net,
        "station": sta,
        "location": loc,
        "channel": cha,
        "starttime": "2023-01-01T00:00:00",
        "endtime": "2023-01-01T00:10:00",
        "consistent": consistent,
    }


def make_report(rows, node="NODE"):
    return {"summary": {"node": node}, "results": rows}


# ----------------------- select_targets -----------------------

def test_select_targets_inconsistent_only():
    rep = make_report([make_row(1, True), make_row(2, False), make_row(3, None)])
    got = reverify.select_targets(rep)
    assert [r["index"] for r in got] == [2]


def test_select_targets_all_rows():
    rep = make_report([make_row(1, True), make_row(2, False)])
    got = reverify.select_targets(rep, include_consistent=True)
    assert [r["index"] for r in got] == [1, 2]


def test_select_targets_by_index_overrides_scope():
    rep = make_report([make_row(1, True), make_row(2, False), make_row(3, True)])
    got = reverify.select_targets(rep, indices=[1, 3])
    assert [r["index"] for r in got] == [1, 3]


# ----------------------- reverify_row verdicts -----------------------

@pytest.mark.parametrize(
    "prior,now,expected",
    [
        (False, True, reverify.RESOLVED),
        (False, False, reverify.PERSISTS),
        (True, True, reverify.CONSISTENT),
        (True, False, reverify.REGRESSED),
        (False, None, reverify.SKIPPED),
        (True, None, reverify.SKIPPED),
    ],
)
def test_reverify_row_verdicts(monkeypatch, prior, now, expected):
    monkeypatch.setattr(reverify, "_check_window", lambda *a, **k: now)
    assert reverify.reverify_row("http://node/", make_row(1, prior)) == expected


# ----------------------- load_report -----------------------

def test_load_report_local(tmp_path):
    rep = make_report([make_row(1, False)])
    p = tmp_path / "r.json"
    p.write_text(json.dumps(rep))
    assert reverify.load_report(str(p))["summary"]["node"] == "NODE"


# ----------------------- rerun_report orchestration -----------------------

def _patch_rerun(monkeypatch, verdict_by_index):
    monkeypatch.setattr(rerun_mod, "load_node_url", lambda node: "http://node/")
    monkeypatch.setattr(
        rerun_mod,
        "reverify_row",
        lambda base_url, row, verbose=False: verdict_by_index[row["index"]],
    )


def test_rerun_report_default_scope(monkeypatch, tmp_path):
    rep = make_report([make_row(1, True), make_row(2, False), make_row(3, False)])
    p = tmp_path / "r.json"
    p.write_text(json.dumps(rep))
    _patch_rerun(monkeypatch, {2: reverify.PERSISTS, 3: reverify.RESOLVED})

    result = rerun_mod.rerun_report(str(p))
    assert [(r["index"], r["verdict"]) for r in result["results"]] == [
        (2, "PERSISTS"),
        (3, "RESOLVED"),
    ]
    assert result["node"] == "NODE"
    assert result["schema_version"] == "1.0"


def test_rerun_report_all_rows(monkeypatch, tmp_path):
    rep = make_report([make_row(1, True), make_row(2, False)])
    p = tmp_path / "r.json"
    p.write_text(json.dumps(rep))
    _patch_rerun(monkeypatch, {1: reverify.CONSISTENT, 2: reverify.PERSISTS})

    result = rerun_mod.rerun_report(str(p), all_rows=True)
    assert len(result["results"]) == 2
    assert rerun_mod.render_summary(result) == "2 re-run — 1 persists, 1 consistent"


def test_rerun_report_empty_when_all_consistent(monkeypatch, tmp_path):
    rep = make_report([make_row(1, True)])
    p = tmp_path / "r.json"
    p.write_text(json.dumps(rep))
    _patch_rerun(monkeypatch, {})
    result = rerun_mod.rerun_report(str(p))
    assert result["results"] == []
    assert rerun_mod.render_summary(result) == "0 re-run"


# ----------------------- rendering -----------------------

def test_render_table_alignment_and_crossmidnight():
    result = {
        "results": [
            {"index": 4, "label": "HP.DRO..HHN", "start": "2015-09-15T17:43:32",
             "end": "2015-09-15T17:53:32", "verdict": "PERSISTS"},
            {"index": 14, "label": "CQ.DERY..HHZ", "start": "2025-11-10T23:50:10",
             "end": "2025-11-11T00:00:10", "verdict": "RESOLVED"},
        ]
    }
    lines = rerun_mod.render_table(result)
    body = [l for l in lines if "PERSISTS" in l or "RESOLVED" in l]
    # same-day window drops the repeated date on the end side...
    assert "2015-09-15 17:43:32 → 17:53:32" in body[0]
    # ...cross-midnight window keeps the end date, with no stray 'T'
    assert "2025-11-10 23:50:10 → 2025-11-11 00:00:10" in body[1]
    assert "T00:00:10" not in body[1]
    # verdict column is aligned across rows
    assert body[0].index("PERSISTS") == body[1].index("RESOLVED")
