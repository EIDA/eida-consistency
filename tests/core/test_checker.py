import pytest
import random
from datetime import datetime, timedelta

import eida_consistency.core.checker as checker


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
class DummySpans:
    """Helper to patch get_availability_spans with controlled responses."""

    @staticmethod
    def good(*_a, **_k):
        # Return a span covering everything
        return [{
            "start": "2000-01-01T00:00:00",
            "end": "2100-01-01T00:00:00",
            "location": "XX"
        }]

    @staticmethod
    def empty(*_a, **_k):
        return []


# -------------------------------------------------------------------
# Tests for _parse_iso
# -------------------------------------------------------------------
def test_parse_iso_valid_and_invalid():
    # Valid
    dt = checker._parse_iso("2020-01-01T00:00:00")
    assert isinstance(dt, datetime)
    # Empty
    assert checker._parse_iso("") is None
    # Invalid format string
    assert checker._parse_iso("not-a-date") is None
    # Bad format to trigger exception inside fromisoformat
    assert checker._parse_iso("2020-13-99T99:99:99") is None


# -------------------------------------------------------------------
# Tests for _inside_any_span
# -------------------------------------------------------------------
def test_inside_any_span_true_and_false():
    t0 = datetime(2020, 1, 1, 0, 0, 0)
    t1 = datetime(2020, 1, 1, 1, 0, 0)
    spans = [{"start": "2020-01-01T00:00:00", "end": "2020-01-01T02:00:00"}]
    ok, span = checker._inside_any_span(t0, t1, spans)
    assert ok and span is not None

    # Outside span
    spans = [{"start": "2020-01-01T02:00:00", "end": "2020-01-01T03:00:00"}]
    ok, span = checker._inside_any_span(t0, t1, spans)
    assert not ok and span is None


def test_inside_any_span_exception_branch(monkeypatch):
    def boom(_):
        raise ValueError("bad date")

    monkeypatch.setattr(checker, "_parse_iso", boom)

    t0 = datetime(2020, 1, 1, 0, 0, 0)
    t1 = datetime(2020, 1, 1, 1, 0, 0)
    spans = [{"start": "bad", "end": "bad"}]

    ok, span = checker._inside_any_span(t0, t1, spans)
    assert not ok and span is None


def test_inside_any_span_missing_start_end():
    t0 = datetime(2020, 1, 1, 0, 0, 0)
    t1 = datetime(2020, 1, 1, 1, 0, 0)
    spans = [{"start": None, "end": None}]
    ok, span = checker._inside_any_span(t0, t1, spans)
    assert not ok and span is None


# -------------------------------------------------------------------
# Tests for check_candidate
# -------------------------------------------------------------------
def test_check_candidate_basic(monkeypatch):
    candidate = {
        "network": "XX", "station": "STA", "channel": "BHZ",
        "starttime": "2020-01-01T00:00:00",
        "endtime": "2020-01-02T00:00:00",
        "location": "00",
    }
    monkeypatch.setattr(checker, "get_availability_spans", DummySpans.good)
    results = checker.check_candidate("http://fake/", candidate, epochs=1, duration=600)
    assert len(results) == 1
    url, available, s, e, loc, span = results[0]
    assert url.startswith("http://fake/availability/1/query?")
    assert available
    assert loc == "XX"
    assert span is not None


def test_check_candidate_duration_too_short(monkeypatch):
    candidate = {
        "network": "XX", "station": "STA", "channel": "BHZ",
        "starttime": "2020-01-01T00:00:00",
        "endtime": "2020-01-01T00:01:00",  # less than 600s
    }
    monkeypatch.setattr(checker, "get_availability_spans", DummySpans.good)
    results = checker.check_candidate("http://fake/", candidate, epochs=1, duration=600)
    assert results == []


def test_check_candidate_no_spans(monkeypatch):
    candidate = {
        "network": "XX", "station": "STA", "channel": "BHZ",
        "starttime": "2020-01-01T00:00:00",
        "endtime": "2020-02-01T00:00:00",
    }
    monkeypatch.setattr(checker, "get_availability_spans", DummySpans.empty)
    results = checker.check_candidate("http://fake/", candidate, epochs=1, duration=600)
    assert results == []


def test_check_candidate_ch_start_ge_latest_start(monkeypatch):
    candidate = {
        "network": "XX", "station": "STA", "channel": "BHZ",
        "starttime": "2020-01-01T00:00:00",
        "endtime": "2020-01-01T00:09:59",  # shorter than duration
    }
    monkeypatch.setattr(checker, "get_availability_spans", DummySpans.good)
    results = checker.check_candidate("http://fake/", candidate, epochs=1, duration=600)
    assert results == []


def test_check_candidate_duplicate_keys(monkeypatch):
    candidates = [
        {
            "network": "XX", "station": "STA", "channel": "BHZ",
            "starttime": "2020-01-01T00:00:00",
            "endtime": "2020-01-02T00:00:00",
        },
        {
            "network": "XX", "station": "STA", "channel": "BHZ",  # duplicate key
            "starttime": "2020-01-01T00:00:00",
            "endtime": "2020-01-02T00:00:00",
        },
    ]
    monkeypatch.setattr(checker, "get_availability_spans", DummySpans.good)
    results = checker.check_candidate("http://fake/", candidates[0], candidates=candidates, epochs=2, duration=600)
    # Only one unique result, second skipped due to "key in used"
    assert len(results) == 1


def test_check_candidate_invalid_dates(monkeypatch):
    candidate = {
        "network": "XX", "station": "STA", "channel": "BHZ",
        "starttime": "bad-date",
        "endtime": "bad-date",
    }
    monkeypatch.setattr(checker, "get_availability_spans", DummySpans.good)
    results = checker.check_candidate("http://fake/", candidate, epochs=1, duration=600)
    assert results == []


def test_check_candidate_duration_too_small_raises(monkeypatch):
    candidate = {
        "network": "XX", "station": "STA", "channel": "BHZ",
        "starttime": "2020-01-01T00:00:00",
        "endtime": "2020-01-02T00:00:00",
    }
    with pytest.raises(ValueError, match="Duration must be at least 600"):
        checker.check_candidate("http://fake/", candidate, epochs=1, duration=100)


def test_check_candidate_empty_pool(monkeypatch):
    candidate = {"foo": "bar"}  # missing required keys
    results = checker.check_candidate("http://fake/", candidate, epochs=1, duration=600)
    assert results == []
