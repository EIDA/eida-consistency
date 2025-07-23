import pytest
import logging
from datetime import datetime
from unittest.mock import patch

from eida_consistency.core.checker import check_candidate, parse_datetime

logging.basicConfig(level=logging.INFO)

# --------------------------------------------------------------------------------
@patch("eida_consistency.core.checker.check_availability")
def test_check_candidate_multiple_epochs(mock_check_avail):
    """Test that multiple valid candidates return expected results."""
    mock_check_avail.return_value = ("https://mock.url/availability", True)

    sample_candidates = [
        {
            "network": "XX",
            "station": f"TEST{i}",
            "channel": "BHZ",
            "starttime": "2023-01-01T00:00:00Z",
            "endtime": "2023-01-01T01:00:00Z",
        }
        for i in range(10)
    ]

    results = check_candidate(
        base_url="https://example.org/fdsnws/",
        candidate=sample_candidates[0],
        candidates=sample_candidates,
        epochs=5,
    )

    assert len(results) == 5
    for url, available, start, end in results:
        assert url == "https://mock.url/availability"
        assert available is True
        datetime.fromisoformat(start)
        datetime.fromisoformat(end)

    assert mock_check_avail.call_count == 5

# --------------------------------------------------------------------------------
def test_parse_datetime_invalid():
    """Test that invalid datetime string returns None."""
    dt = parse_datetime("not-a-date")
    assert dt is None

# --------------------------------------------------------------------------------
@patch("eida_consistency.core.checker.check_availability")
def test_check_candidate_too_short_duration(mock_check_avail):
    """Test candidate skipped if duration is too short (<10min)."""
    short_window = {
        "network": "XX",
        "station": "SHORT",
        "channel": "BHZ",
        "starttime": "2023-01-01T00:00:00Z",
        "endtime": "2023-01-01T00:05:00Z",
    }

    results = check_candidate(
        base_url="https://example.org",
        candidate=short_window,
        candidates=[short_window],
        epochs=1,
    )

    assert results == []
    assert mock_check_avail.call_count == 0

# --------------------------------------------------------------------------------
@patch("eida_consistency.core.checker.check_availability")
def test_check_candidate_epoch_too_tight(mock_check_avail):
    """Test that candidate is skipped if no room for 10-minute epoch."""
    # Start and end exactly 10 minutes apart → start == max_start
    tight_window = {
        "network": "XX",
        "station": "TIGHT",
        "channel": "BHZ",
        "starttime": "2023-01-01T00:50:00Z",
        "endtime": "2023-01-01T01:00:00Z",
    }

    results = check_candidate(
        base_url="https://example.org",
        candidate=tight_window,
        candidates=[tight_window],
        epochs=1,
    )

    assert results == []  # No valid epochs possible
    assert mock_check_avail.call_count == 0
