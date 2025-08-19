# tests/test_checker.py
import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import patch

import eida_consistency.core.checker as checker


# --------------------------------------------------------------------------- #
# _parse_iso
# --------------------------------------------------------------------------- #

def test_parse_iso_none_empty_and_invalid():
    assert checker._parse_iso(None) is None
    assert checker._parse_iso("") is None
    assert checker._parse_iso("   ") is None
    assert checker._parse_iso("not-a-date") is None


def test_parse_iso_valid_with_and_without_z():
    dt = datetime(2020, 1, 1, 12, 0, 0)
    assert checker._parse_iso("2020-01-01T12:00:00") == dt
    assert checker._parse_iso("2020-01-01T12:00:00Z") == dt


# --------------------------------------------------------------------------- #
# check_candidate
# --------------------------------------------------------------------------- #

@patch("eida_consistency.core.checker.check_availability_query")
def test_check_candidate_missing_keys_returns_empty(mock_check):
    candidate = {"network": "XX"}  # missing required keys
    results = checker.check_candidate("url", candidate)
    assert results == []
    mock_check.assert_not_called()


@patch("eida_consistency.core.checker.check_availability_query")
def test_check_candidate_continue_if_start_or_end_invalid(mock_check):
    # invalid starttime → _parse_iso returns None → triggers "if not start or not end"
    cand = {
        "network": "N",
        "station": "S",
        "channel": "C",
        "starttime": "not-a-date",
        "endtime": datetime.now(UTC).replace(tzinfo=None).isoformat(),
    }
    results = checker.check_candidate("url", cand, epochs=1)
    assert results == []
    mock_check.assert_not_called()


@patch("eida_consistency.core.checker.check_availability_query")
def test_check_candidate_skips_short_duration(mock_check):
    start = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    cand = {
        "network": "N",
        "station": "S",
        "channel": "C",
        "starttime": start.isoformat(),
        "endtime": datetime.now(UTC).replace(tzinfo=None).isoformat(),
    }
    results = checker.check_candidate("url", cand, epochs=1)
    assert results == []
    mock_check.assert_not_called()


@patch("eida_consistency.core.checker.check_availability_query")
def test_check_candidate_continue_if_start_ge_latest_start(mock_check):
    # start >= end - 10 minutes → triggers that continue
    now = datetime.now(UTC).replace(tzinfo=None)
    start = now - timedelta(minutes=5)
    cand = {
        "network": "N",
        "station": "S",
        "channel": "C",
        "starttime": start.isoformat(),
        "endtime": now.isoformat(),
    }
    results = checker.check_candidate("url", cand, epochs=1)
    assert results == []
    mock_check.assert_not_called()

@patch("eida_consistency.core.checker.check_availability_query")
def test_check_candidate_continue_if_start_equals_latest_start(mock_check):
    # end - start = exactly 600s → not caught by the short-duration check
    # but start == latest_start → triggers the line 59 continue
    now = datetime.now(UTC).replace(tzinfo=None)
    start = now - timedelta(seconds=600)
    cand = {
        "network": "N",
        "station": "S",
        "channel": "C",
        "starttime": start.isoformat(),
        "endtime": now.isoformat(),
    }

    results = checker.check_candidate("url", cand, epochs=1)
    assert results == []
    mock_check.assert_not_called()

@patch("eida_consistency.core.checker.check_availability_query")
def test_check_candidate_valid_with_matched_span(mock_check):
    now = datetime.now(UTC).replace(tzinfo=None)
    start = now - timedelta(hours=2)
    end = now

    cand = {
        "network": "N",
        "station": "S",
        "channel": "C",
        "starttime": start.isoformat(),
        "endtime": end.isoformat(),
    }

    mock_check.return_value = {
        "ok": True,
        "url": "fake-url",
        "matched_span": {"location": "LOC1"},
    }

    with patch("random.choice", side_effect=lambda seq: seq[0]), \
         patch("random.randint", return_value=0):
        results = checker.check_candidate("base", cand, epochs=1)

    assert len(results) == 1
    url, available, s, e, loc = results[0]
    assert url == "fake-url"
    assert available is True
    assert loc == "LOC1"


@patch("eida_consistency.core.checker.check_availability_query")
def test_check_candidate_uses_candidate_location(mock_check):
    now = datetime.now(UTC).replace(tzinfo=None)
    start = now - timedelta(hours=2)
    cand = {
        "network": "N",
        "station": "S",
        "channel": "C",
        "starttime": start.isoformat(),
        "location": "CAND_LOC",
    }

    mock_check.return_value = {"ok": False, "url": "url2"}

    with patch("random.choice", side_effect=lambda seq: seq[0]), \
         patch("random.randint", return_value=0):
        results = checker.check_candidate("base", cand, epochs=1)

    assert results[0][1] is False
    assert results[0][4] == "CAND_LOC"


@patch("eida_consistency.core.checker.check_availability_query")
def test_check_candidate_location_empty_if_no_info(mock_check):
    now = datetime.now(UTC).replace(tzinfo=None)
    start = now - timedelta(hours=2)
    cand = {
        "network": "N",
        "station": "S",
        "channel": "C",
        "starttime": start.isoformat(),
    }

    mock_check.return_value = {"ok": True, "url": "url3"}

    with patch("random.choice", side_effect=lambda seq: seq[0]), \
         patch("random.randint", return_value=0):
        results = checker.check_candidate("base", cand, epochs=1)

    assert results[0][4] == ""


@patch("eida_consistency.core.checker.check_availability_query")
def test_check_candidate_respects_used_keys(mock_check):
    now = datetime.now(UTC).replace(tzinfo=None)
    start = now - timedelta(hours=2)
    cand = {
        "network": "N",
        "station": "S",
        "channel": "C",
        "starttime": start.isoformat(),
        "endtime": now.isoformat(),
    }

    mock_check.return_value = {"ok": True, "url": "url"}

    # epochs > pool → triggers duplicate key skip
    with patch("random.choice", side_effect=lambda seq: seq[0]), \
         patch("random.randint", return_value=0):
        results = checker.check_candidate("base", cand, epochs=2)

    assert len(results) == 1
