# tests/core/test_picker.py
import re
import eida_consistency.core.picker as picker


def test_valid_candidate_with_endtime(monkeypatch):
    cands = [
        {"starttime": "2020-01-01T00:00:00", "endtime": "2020-01-01T00:05:00", "net": "XX"},
    ]

    # ensure deterministic shuffle
    monkeypatch.setattr(picker.random, "shuffle", lambda x: None)

    result = picker.pick_random_candidate(cands)
    assert result is not None
    assert result["starttime"].startswith("2020-01-01T00:00:00")
    assert result["endtime"].startswith("2020-01-01T00:05:00")
    assert result["net"] == "XX"


def test_valid_candidate_without_endtime(monkeypatch):
    cands = [{"starttime": "2020-01-01T00:00:00"}]

    monkeypatch.setattr(picker.random, "shuffle", lambda x: None)

    result = picker.pick_random_candidate(cands)
    assert result is not None
    # endtime should be 10 minutes after starttime
    assert "2020-01-01T00:10:00" in result["endtime"]


def test_candidate_too_short(monkeypatch):
    cands = [{"starttime": "2020-01-01T00:00:00", "endtime": "2020-01-01T00:01:00"}]

    monkeypatch.setattr(picker.random, "shuffle", lambda x: None)

    result = picker.pick_random_candidate(cands)
    assert result is None


def test_malformed_candidate(monkeypatch):
    # Missing starttime triggers exception branch
    cands = [{"endtime": "2020-01-01T00:05:00"}]

    monkeypatch.setattr(picker.random, "shuffle", lambda x: None)

    result = picker.pick_random_candidate(cands)
    assert result is None


def test_no_candidates(monkeypatch):
    monkeypatch.setattr(picker.random, "shuffle", lambda x: None)

    result = picker.pick_random_candidate([])
    assert result is None
