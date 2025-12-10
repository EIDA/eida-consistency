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

    # fake spans always covering the candidate window
    fake_spans = [{
        "start": "2023-01-01T00:00:00",
        "end": "2023-01-01T23:59:59",
        "location": "00"
    }]

    monkeypatch.setattr(checker, "get_availability_spans", lambda *a, **kw: fake_spans)

    results, stats = checker.check_candidate("http://fake/", c, epochs=1, duration=600)

    assert len(results) == 1
    url, available, s, e, loc, span = results[0]
    assert url.startswith("http://fake/availability/1/query?")
    assert available is True
    assert loc == "00"
    assert isinstance(span, dict)
    assert stats["candidates_generated"] == 1
    assert stats["candidates_requested"] == 1


def test_check_candidate_spans_empty(monkeypatch):
    c = make_candidate()

    monkeypatch.setattr(checker, "get_availability_spans", lambda *a, **kw: [])

    results, stats = checker.check_candidate("http://fake/", c, epochs=1, duration=600)
    # no spans, so no usable epochs
    assert results == []
    assert stats["candidates_generated"] == 0


def test_check_candidate_endtime_missing(monkeypatch):
    c = make_candidate()
    c.pop("endtime")  # force code path that uses utcnow

    fake_spans = [{
        "start": "2023-01-01T00:00:00",
        "end": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        "location": "00"
    }]

    monkeypatch.setattr(checker, "get_availability_spans", lambda *a, **kw: fake_spans)

    results, stats = checker.check_candidate("http://fake/", c, epochs=1, duration=600)
    assert stats["candidates_generated"] in (0, 1)  # depends on timing
