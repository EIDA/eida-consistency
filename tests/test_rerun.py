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
    assert result["schema_version"] == "1.1"


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

def test_window_same_day_drops_repeated_date():
    w = rerun_mod._window({"starttime": "2015-09-15T17:43:32", "endtime": "2015-09-15T17:53:32"})
    assert w == "2015-09-15 17:43:32 → 17:53:32"


def test_window_crossmidnight_keeps_end_date_without_stray_t():
    w = rerun_mod._window({"starttime": "2025-11-10T23:50:10", "endtime": "2025-11-11T00:00:10"})
    assert w == "2025-11-10 23:50:10 → 2025-11-11 00:00:10"
    assert "T00:00:10" not in w


# --- PSD awareness --------------------------------------------------------

def make_psd_row(index, psd_present, consistent=True, status="Inconsistent",
                 ds_success=True, **kw):
    row = make_row(index, consistent, **kw)
    row.update({"psd_status": status, "psd_present": psd_present,
                "dataselect_success": ds_success})
    return row


def _patch_psd(monkeypatch, day_covered, success=True, status="OK"):
    monkeypatch.setattr(
        reverify, "psd_coverage",
        lambda *a, **k: {"success": success, "status": status,
                         "day_covered": day_covered, "url": "http://psd"},
    )


def test_is_psd_finding_only_for_data_present_psd_missing():
    assert reverify.is_psd_finding(make_psd_row(1, psd_present=False)) is True
    assert reverify.is_psd_finding(make_psd_row(2, psd_present=True)) is False
    # no verdict was reached -- not a finding
    assert reverify.is_psd_finding(make_psd_row(3, False, status="Unsupported")) is False
    assert reverify.is_psd_finding(make_psd_row(4, False, status="Skipped")) is False
    # the reverse case: PSD without data. A recompute does not address it.
    assert reverify.is_psd_finding(make_psd_row(5, True, status="Orphan")) is False
    # no data means no PSD was owed
    assert reverify.is_psd_finding(make_psd_row(6, False, ds_success=False)) is False
    # a pre-PSD report
    assert reverify.is_psd_finding(make_row(7, False)) is False


def test_select_targets_now_picks_up_psd_only_findings():
    """The bug: a PSD finding sits on an A/D-consistent row, so selecting on
    `consistent is False` alone made it invisible to rerun."""
    rows = [make_row(1, True),                       # nothing wrong
            make_row(2, False),                      # A/D finding
            make_psd_row(3, psd_present=False)]      # PSD finding, A/D fine
    picked = [r["index"] for r in reverify.select_targets(make_report(rows))]
    assert picked == [2, 3]


def test_psd_verdicts_use_the_same_vocabulary(monkeypatch):
    was_missing = make_psd_row(1, psd_present=False)
    was_present = make_psd_row(2, psd_present=True)

    _patch_psd(monkeypatch, day_covered=True)
    assert reverify.reverify_psd_row("u/", was_missing) == reverify.RESOLVED
    assert reverify.reverify_psd_row("u/", was_present) == reverify.CONSISTENT

    _patch_psd(monkeypatch, day_covered=False)
    assert reverify.reverify_psd_row("u/", was_missing) == reverify.PERSISTS
    assert reverify.reverify_psd_row("u/", was_present) == reverify.REGRESSED


def test_a_failed_psd_check_is_skipped_not_a_verdict(monkeypatch):
    row = make_psd_row(1, psd_present=False)
    _patch_psd(monkeypatch, day_covered=False, success=False, status="Timeout")
    assert reverify.reverify_psd_row("u/", row) == reverify.SKIPPED
    _patch_psd(monkeypatch, day_covered=False, status="Unsupported")
    assert reverify.reverify_psd_row("u/", row) == reverify.SKIPPED


def test_pre_psd_rows_get_no_psd_verdict_at_all(monkeypatch):
    # No psd_status -> no query, no invented verdict, and no field in the output.
    called = []
    monkeypatch.setattr(reverify, "psd_coverage", lambda *a, **k: called.append(1))
    assert reverify.reverify_psd_row("u/", make_row(1, False)) is None
    assert called == []


def test_rerun_emits_psd_verdict_and_tallies_it(monkeypatch, tmp_path):
    rows = [make_psd_row(1, psd_present=False), make_psd_row(2, psd_present=False)]
    p = tmp_path / "r.json"
    p.write_text(json.dumps(make_report(rows)))
    monkeypatch.setattr(rerun_mod, "load_node_url", lambda node: "http://node/")
    monkeypatch.setattr(rerun_mod, "reverify_row",
                        lambda base_url, row, verbose=False: reverify.CONSISTENT)
    monkeypatch.setattr(
        rerun_mod, "reverify_psd_row",
        lambda base_url, row, verbose=False:
            reverify.RESOLVED if row["index"] == 1 else reverify.PERSISTS,
    )
    result = rerun_mod.rerun_report(str(p))
    assert [(r["index"], r["psd_verdict"]) for r in result["results"]] == [
        (1, "RESOLVED"), (2, "PERSISTS")]
    summary = rerun_mod.render_summary(result)
    assert "PSD:" in summary
    assert "1 persists" in summary and "1 resolved" in summary


def test_summary_has_no_psd_clause_for_a_pre_psd_report():
    result = {"results": [{"index": 1, "verdict": "PERSISTS"}]}
    assert "PSD" not in rerun_mod.render_summary(result)
