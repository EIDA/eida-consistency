import pytest
import builtins
from datetime import datetime, timedelta

import eida_consistency.core.checker as checker


# -----------------
# _parse_iso tests
# -----------------

def test_parse_iso_valid():
    dt_str = "2023-01-01T12:00:00"
    result = checker._parse_iso(dt_str)
    assert isinstance(result, datetime)
    assert result.year == 2023 and result.hour == 12

def test_parse_iso_valid_with_z():
    dt_str = "2023-01-01T12:00:00Z"
    result = checker._parse_iso(dt_str)
    assert isinstance(result, datetime)

def test_parse_iso_invalid():
    assert checker._parse_iso("") is None
    assert checker._parse_iso(None) is None
    assert checker._parse_iso("not-a-date") is None


# -----------------
# _inside_any_span tests
# -----------------

def test_inside_any_span_match():
    t0 = datetime(2023, 1, 1, 0, 0, 0)
    t1 = datetime(2023, 1, 1, 1, 0, 0)
    spans = [{"start": "2023-01-01T00:00:00", "end": "2023-01-01T02:00:00"}]
    ok, span = checker._inside_any_span(t0, t1, spans)
    assert ok is True
    assert span == spans[0]

def test_inside_any_span_no_match():
    t0 = datetime(2023, 1, 1, 0, 0, 0)
    t1 = datetime(2023, 1, 1, 1, 0, 0)
    spans = [{"start": "2023-01-01T02:00:00", "end": "2023-01-01T03:00:00"}]
    ok, span = checker._inside_any_span(t0, t1, spans)
    assert ok is False
    assert span is None

def test_inside_any_span_bad_data():
    t0 = datetime(2023, 1, 1, 0, 0, 0)
    t1 = datetime(2023, 1, 1, 1, 0, 0)
    spans = [{"start": "xxx", "end": "yyy"}]
    ok, span = checker._inside_any_span(t0, t1, spans)
    assert ok is False
    assert span is None


# -----------------
# check_candidate tests
# -----------------

def make_candidate():
    return {
        "network": "XX",
        "station": "TEST",
        "channel": "BHZ",
        "location": "00",
        "starttime": "2023-01-01T00:00:00",
        "endtime": "2023-01-01T12:00:00",
    }


def test_check_candidate_duration_too_short():
    c = make_candidate()
    with pytest.raises(ValueError):
        checker.check_candidate("http://fake/", c, epochs=1, duration=100)


def test_check_candidate_no_valid_pool():
    # missing channel -> invalid candidate
    bad_candidate = {"network": "XX", "station": "TEST", "starttime": "2023-01-01"}
    results, stats = checker.check_candidate("http://fake/", bad_candidate, epochs=1)
    assert results == []
    assert stats["candidates_generated"] == 0
    assert stats["candidates_pool"] == 0


def test_check_candidate_success(monkeypatch):
    c = make_candidate()

    # Mock availability query response
    def fake_query(*args, **kwargs):
        return {
            "ok": True,
            "matched_span": {"start": "2023-01-01T00:00:00", "end": "2023-01-01T23:59:59", "location": "00"},
            "status": 200,
            "url": "http://fake/availability/1/query?..."
        }

    monkeypatch.setattr(checker, "check_availability_query", fake_query)

    results, stats = checker.check_candidate("http://fake/", c, epochs=1, duration=600)

    assert len(results) == 1
    url, available, s, e, loc, span = results[0]
    assert url.startswith("http://fake/availability/1/query?")
    assert available is True
    assert loc == "00"
    assert isinstance(span, dict)
    assert stats["candidates_generated"] == 1
    assert stats["candidates_requested"] == 1


def test_check_candidate_not_available(monkeypatch):
    c = make_candidate()

    # Mock availability query response -> unavailable
    def fake_query(*args, **kwargs):
        return {
            "ok": False,
            "matched_span": None,
            "status": 200,
            "url": "http://fake/query"
        }

    monkeypatch.setattr(checker, "check_availability_query", fake_query)

    results, stats = checker.check_candidate("http://fake/", c, epochs=1, duration=600)
    
    assert len(results) == 1
    url, available, s, e, loc, span = results[0]
    assert available is False
    assert span is None
    assert stats["candidates_generated"] == 1


def test_check_candidate_endtime_missing(monkeypatch):
    c = make_candidate()
    c.pop("endtime")  # force code path that uses utcnow

    def fake_query(*args, **kwargs):
        return {
            "ok": True,
            "matched_span": {"start": "2023-01-01T00:00:00", "end": "2024-01-01T00:00:00"},
            "status": 200,
            "url": "http://fake/query"
        }

    monkeypatch.setattr(checker, "check_availability_query", fake_query)

    results, stats = checker.check_candidate("http://fake/", c, epochs=1, duration=600)
    assert stats["candidates_generated"] == 1
    assert len(results) == 1
