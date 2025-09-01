import pytest
import logging
from datetime import datetime

import eida_consistency.services.availability as avail


def test_parse_iso_variants():
    assert avail._parse_iso("2020-01-01T00:00:00") == datetime(2020, 1, 1, 0, 0)
    assert avail._parse_iso("2020-01-01T00:00:00Z") == datetime(2020, 1, 1, 0, 0)


def test_collect_spans_from_availability_and_datasources():
    payload = {
        "availability": [
            {"network": "XX", "station": "AAA", "channel": "HHZ",
             "location": "00", "quality": "B",
             "start": "2020-01-01T00:00:00", "end": "2020-01-01T01:00:00"}
        ],
        "datasources": [
            {
                "network": "YY", "station": "BBB", "channel": "EHN", "location": "01", "quality": "M",
                "timespans": [["2021-01-01T00:00:00", "2021-01-01T02:00:00"]]
            }
        ]
    }
    spans = avail._collect_spans(payload)
    assert len(spans) == 2
    assert spans[0]["network"] == "XX"
    assert spans[1]["network"] == "YY"


class DummyResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.content = b"{}"

    def json(self):
        if self._json is None:
            raise ValueError("No JSON")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP error")


def test_check_availability_query_success_covering(monkeypatch):
    def fake_get(url, timeout=20):
        return DummyResp(
            200,
            {"availability": [
                {"network": "XX", "station": "AAA", "channel": "HHZ", "location": "00",
                 "start": "2020-01-01T00:00:00", "end": "2020-01-01T02:00:00"}
            ]}
        )
    monkeypatch.setattr(avail.requests, "get", fake_get)

    result = avail.check_availability_query(
        "http://fake/", "XX", "AAA", "HHZ",
        "2020-01-01T00:30:00", "2020-01-01T01:00:00", location="00"
    )
    assert result["ok"] is True
    assert result["matched_span"] is not None
    assert result["status"] == 200


def test_check_availability_query_success_not_covering(monkeypatch):
    def fake_get(url, timeout=20):
        return DummyResp(
            200,
            {"availability": [
                {"network": "XX", "station": "AAA", "channel": "HHZ", "location": "00",
                 "start": "2020-01-01T00:00:00", "end": "2020-01-01T00:10:00"}
            ]}
        )
    monkeypatch.setattr(avail.requests, "get", fake_get)

    result = avail.check_availability_query(
        "http://fake/", "XX", "AAA", "HHZ",
        "2020-01-01T00:30:00", "2020-01-01T01:00:00", location="00"
    )
    assert result["ok"] is False
    assert result["matched_span"] is None


def test_check_availability_query_204(monkeypatch):
    def fake_get(url, timeout=20):
        return DummyResp(204, json_data={}, text="")
    monkeypatch.setattr(avail.requests, "get", fake_get)

    result = avail.check_availability_query(
        "http://fake/", "XX", "AAA", "HHZ", "2020-01-01T00:00:00", "2020-01-01T01:00:00"
    )
    assert result["ok"] is False
    assert result["status"] == 204


def test_check_availability_query_non_200(monkeypatch):
    def fake_get(url, timeout=20):
        return DummyResp(500, json_data=None, text="err")
    monkeypatch.setattr(avail.requests, "get", fake_get)

    result = avail.check_availability_query(
        "http://fake/", "X", "A", "HHZ", "s", "e"
    )
    assert result["ok"] is False
    assert result["status"] == 0   # code catches error and forces 0


def test_check_availability_query_invalid_json(monkeypatch):
    def fake_get(url, timeout=20):
        return DummyResp(200, json_data=None)
    monkeypatch.setattr(avail.requests, "get", fake_get)

    result = avail.check_availability_query(
        "http://fake/", "X", "A", "HHZ", "2020-01-01T00:00:00", "2020-01-01T00:10:00"
    )
    assert result["ok"] is False
    assert result["spans"] == []


def test_get_availability_spans_success(monkeypatch):
    def fake_get(url, timeout=30):
        return DummyResp(
            200,
            {"availability": [
                {"network": "X", "station": "A", "channel": "HHZ",
                 "start": "2020-01-01T00:00:00", "end": "2020-01-01T01:00:00"}
            ]}
        )
    monkeypatch.setattr(avail.requests, "get", fake_get)
    spans = avail.get_availability_spans("http://fake/", "X", "A", "HHZ", "s", "e")
    assert len(spans) == 1


def test_get_availability_spans_204_retry_then_empty(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, timeout=30):
        calls["n"] += 1
        if calls["n"] == 1:
            return DummyResp(204, json_data={})
        return DummyResp(204, json_data={})
    monkeypatch.setattr(avail.requests, "get", fake_get)

    spans = avail.get_availability_spans("http://fake/", "X", "A", "HHZ", "s", "e", location="00")
    assert spans == []


def test_get_availability_spans_exception(monkeypatch):
    def fake_get(url, timeout=30):
        raise Exception("boom")
    monkeypatch.setattr(avail.requests, "get", fake_get)

    spans = avail.get_availability_spans("http://fake/", "X", "A", "HHZ", "s", "e")
    assert spans == []


def test_check_availability_backcompat(monkeypatch):
    def fake_query(*a, **k):
        return {"ok": True, "url": "http://fake", "spans": [], "matched_span": {}}
    monkeypatch.setattr(avail, "check_availability_query", fake_query)

    res = avail.check_availability("http://fake/", "X", "A", "HHZ", "s", "e")
    assert res is True

    url, ok = avail.check_availability("http://fake/", "X", "A", "HHZ", "s", "e", return_url=True)
    assert url == "http://fake"
    assert ok is True


# --- NEW TESTS FOR UNCOVERED BRANCHES ---

def test_check_availability_query_unserializable_json(monkeypatch, caplog):
    """Force unserializable JSON payload so pretty-print fails but code continues."""
    class BadObj:
        # Not JSON serializable
        pass

    bad_payload = {"availability": [{"network": "X", "station": "A", "channel": "HHZ",
                                     "location": "00", "start": "2020-01-01T00:00:00",
                                     "end": "2020-01-01T00:10:00",
                                     "extra": BadObj()}]}

    def fake_get(url, timeout=20):
        return DummyResp(200, json_data=bad_payload)

    monkeypatch.setattr(avail.requests, "get", fake_get)
    caplog.set_level(logging.DEBUG)

    result = avail.check_availability_query(
        "http://fake/", "X", "A", "HHZ",
        "2020-01-01T00:00:00", "2020-01-01T00:10:00"
    )

    assert isinstance(result, dict)
    # The pretty string should fall back to "<unserializable JSON>"
    assert "<unserializable JSON>" in caplog.text

def test_check_availability_query_span_parse_exception(monkeypatch):
    """Force _parse_iso to fail so except Exception: continue is exercised."""
    payload = {"availability": [{"start": "bad-date", "end": "also-bad"}]}

    def fake_get(url, timeout=20):
        return DummyResp(200, json_data=payload)

    monkeypatch.setattr(avail.requests, "get", fake_get)

    result = avail.check_availability_query(
        "http://fake/", "X", "A", "HHZ",
        "2020-01-01T00:00:00", "2020-01-01T00:10:00"
    )

    assert result["ok"] is False
    assert result["matched_span"] is None
