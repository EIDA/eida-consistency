import logging
import pytest

import eida_consistency.services.availability as availability


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text="dummy"):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_collect_spans_with_availability_and_datasources():
    payload = {
        "availability": [
            {"start": "2020-01-01T00:00:00", "end": "2020-01-01T01:00:00",
             "network": "XX", "station": "AAA", "channel": "BHZ", "location": ""}
        ],
        "datasources": [
            {
                "network": "YY", "station": "BBB", "channel": "HHZ", "location": "00",
                "timespans": [["2020-01-01T02:00:00", "2020-01-01T03:00:00"]]
            }
        ]
    }
    spans = availability._collect_spans(payload)
    assert len(spans) == 2
    assert spans[0]["network"] == "XX"
    assert spans[1]["network"] == "YY"


def test_check_availability_query_happy_path(monkeypatch):
    payload = {
        "availability": [
            {"start": "2020-01-01T00:00:00", "end": "2020-01-01T01:00:00",
             "network": "XX", "station": "AAA", "channel": "BHZ", "location": ""}
        ]
    }
    monkeypatch.setattr(
        availability.requests,
        "get",
        lambda url, timeout: DummyResponse(200, payload),
    )

    result = availability.check_availability_query(
        "http://fake/", "XX", "AAA", "BHZ",
        "2020-01-01T00:10:00", "2020-01-01T00:20:00"
    )
    assert result["ok"] is True
    assert result["matched_span"] is not None


def test_non_200_status(monkeypatch, caplog):
    monkeypatch.setattr(
        availability.requests,
        "get",
        lambda url, timeout: DummyResponse(404, {}, text="not found"),
    )

    caplog.set_level(logging.DEBUG)
    result = availability.check_availability_query(
        "http://fake/", "XX", "AAA", "BHZ",
        "2020-01-01T00:10:00", "2020-01-01T00:20:00"
    )
    assert result["ok"] is False
    assert "Non-200" in caplog.text


def test_request_exception(monkeypatch):
    monkeypatch.setattr(
        availability.requests,
        "get",
        lambda url, timeout: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = availability.check_availability_query(
        "http://fake/", "XX", "AAA", "BHZ",
        "2020-01-01T00:10:00", "2020-01-01T00:20:00"
    )
    assert result["ok"] is False
    assert result["status"] == 0


def test_bad_json_parse(monkeypatch, caplog):
    class BadResponse(DummyResponse):
        def json(self):
            raise ValueError("bad json")

    monkeypatch.setattr(
        availability.requests,
        "get",
        lambda url, timeout: BadResponse(200),
    )

    caplog.set_level(logging.WARNING)
    result = availability.check_availability_query(
        "http://fake/", "XX", "AAA", "BHZ",
        "2020-01-01T00:10:00", "2020-01-01T00:20:00"
    )
    assert result["ok"] is False
    assert "Failed to parse" in caplog.text


def test_debug_logging_with_unserializable_json(monkeypatch, caplog):
    # object guaranteed unserialisable
    bad_obj = lambda: None
    bad_payload = {
        "availability": [
            {"start": "2020-01-01T00:00:00", "end": "2020-01-01T01:00:00", "bad": bad_obj}
        ]
    }

    monkeypatch.setattr(
        availability.requests,
        "get",
        lambda url, timeout: DummyResponse(200, bad_payload),
    )

    caplog.set_level(logging.DEBUG)
    result = availability.check_availability_query(
        "http://fake/", "XX", "AAA", "BHZ",
        "2020-01-01T00:10:00", "2020-01-01T00:20:00"
    )

    assert "<unserializable JSON>" in caplog.text
    assert result["ok"] is True   # span still covers window


def test_span_with_invalid_datetime_triggers_continue(monkeypatch):
    bad_payload = {
        "availability": [{"start": "NOT_A_DATE", "end": "ALSO_BAD"}]
    }

    monkeypatch.setattr(
        availability.requests,
        "get",
        lambda url, timeout: DummyResponse(200, bad_payload),
    )

    result = availability.check_availability_query(
        "http://fake/", "ZZ", "CCC", "HHN",
        "2020-01-01T00:00:00", "2020-01-01T00:10:00"
    )
    assert result["ok"] is False
    assert result["matched_span"] is None
    assert len(result["spans"]) == 1


def test_check_availability_wrapper(monkeypatch):
    payload = {
        "availability": [
            {"start": "2020-01-01T00:00:00", "end": "2020-01-01T01:00:00"}
        ]
    }
    monkeypatch.setattr(
        availability.requests,
        "get",
        lambda url, timeout: DummyResponse(200, payload),
    )

    result = availability.check_availability(
        "http://fake/", "XX", "AAA", "BHZ",
        "2020-01-01T00:10:00", "2020-01-01T00:20:00"
    )
    assert isinstance(result, bool)
    url, ok = availability.check_availability(
        "http://fake/", "XX", "AAA", "BHZ",
        "2020-01-01T00:10:00", "2020-01-01T00:20:00", return_url=True
    )
    assert url.startswith("http://fake/")
    assert isinstance(ok, bool)
