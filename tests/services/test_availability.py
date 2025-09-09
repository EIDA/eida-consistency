import pytest
import types
from datetime import datetime
import eida_consistency.services.availability as avail


# -----------------
# _parse_iso
# -----------------

def test_parse_iso_strips_z():
    dt = avail._parse_iso("2023-01-01T00:00:00Z")
    assert isinstance(dt, datetime)
    assert dt.year == 2023


# -----------------
# _collect_spans
# -----------------

def test_collect_spans_availability_and_datasources():
    payload = {
        "availability": [
            {"start": "2023-01-01T00:00:00", "end": "2023-01-01T01:00:00",
             "network": "XX", "station": "STA", "location": "00", "channel": "BHZ", "quality": "M"}
        ],
        "datasources": [
            {
                "network": "YY", "station": "STA2", "location": "01", "channel": "HHN", "quality": "D",
                "timespans": [["2023-01-02T00:00:00", "2023-01-02T01:00:00"]]
            }
        ]
    }
    spans = avail._collect_spans(payload)
    assert len(spans) == 2
    assert spans[0]["network"] == "XX"
    assert spans[1]["network"] == "YY"

def test_collect_spans_empty():
    spans = avail._collect_spans({})
    assert spans == []


# -----------------
# _safe_request
# -----------------

class DummyResp:
    def __init__(self, status_code=200, json_data=None, raise_exc=None):
        self.status_code = status_code
        self._json = json_data or {}
        self._raise_exc = raise_exc
        self.text = str(self._json)

    def json(self):
        if isinstance(self._json, Exception):
            raise self._json
        return self._json

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc


def test_safe_request_success(monkeypatch):
    monkeypatch.setattr(avail.requests, "get", lambda url, timeout=240: DummyResp())
    r = avail._safe_request("http://fake/")
    assert isinstance(r, DummyResp)


def test_safe_request_failure(monkeypatch):
    calls = {"n": 0}
    def fail_get(url, timeout=240):
        calls["n"] += 1
        raise Exception("boom")
    monkeypatch.setattr(avail.requests, "get", fail_get)
    r = avail._safe_request("http://fake/", retries=2, backoff=0)
    assert r is None
    assert calls["n"] == 2


# -----------------
# check_availability_query
# -----------------

def test_check_availability_query_ok(monkeypatch):
    payload = {"availability": [
        {"start": "2023-01-01T00:00:00", "end": "2023-01-01T02:00:00"}
    ]}
    resp = DummyResp(status_code=200, json_data=payload)
    monkeypatch.setattr(avail, "_safe_request", lambda url: resp)
    result = avail.check_availability_query("http://fake/", "XX", "STA", "BHZ",
                                            "2023-01-01T00:30:00", "2023-01-01T01:00:00")
    assert result["ok"] is True
    assert result["matched_span"] is not None

def test_check_availability_query_not_covered(monkeypatch):
    payload = {"availability": [
        {"start": "2023-01-01T00:00:00", "end": "2023-01-01T01:00:00"}
    ]}
    resp = DummyResp(status_code=200, json_data=payload)
    monkeypatch.setattr(avail, "_safe_request", lambda url: resp)
    result = avail.check_availability_query("http://fake/", "XX", "STA", "BHZ",
                                            "2023-01-01T01:30:00", "2023-01-01T02:00:00")
    assert result["ok"] is False
    assert result["matched_span"] is None

def test_check_availability_query_resp_none(monkeypatch):
    monkeypatch.setattr(avail, "_safe_request", lambda url: None)
    result = avail.check_availability_query("http://fake/", "XX", "STA", "BHZ",
                                            "2023-01-01T00:00:00", "2023-01-01T01:00:00")
    assert result["ok"] is False
    assert result["status"] == 0

def test_check_availability_query_204(monkeypatch):
    resp = DummyResp(status_code=204, json_data={})
    monkeypatch.setattr(avail, "_safe_request", lambda url: resp)
    result = avail.check_availability_query("http://fake/", "XX", "STA", "BHZ",
                                            "2023-01-01T00:00:00", "2023-01-01T01:00:00")
    assert result["ok"] is False
    assert result["status"] == 204

def test_check_availability_query_bad_json(monkeypatch):
    resp = DummyResp(status_code=200, json_data=ValueError("badjson"))
    monkeypatch.setattr(avail, "_safe_request", lambda url: resp)
    result = avail.check_availability_query("http://fake/", "XX", "STA", "BHZ",
                                            "2023-01-01T00:00:00", "2023-01-01T01:00:00")
    assert result["ok"] is False


# -----------------
# get_availability_spans
# -----------------

def test_get_availability_spans_ok(monkeypatch):
    payload = {"availability": [{"start": "2023-01-01T00:00:00", "end": "2023-01-01T01:00:00"}]}
    resp = DummyResp(status_code=200, json_data=payload)
    monkeypatch.setattr(avail, "_safe_request", lambda url: resp)
    spans = avail.get_availability_spans("http://fake/", "XX", "STA", "BHZ",
                                         "2023-01-01T00:00:00", "2023-01-01T02:00:00")
    assert spans and spans[0]["start"] == "2023-01-01T00:00:00"

def test_get_availability_spans_204_with_retry(monkeypatch):
    calls = {"n": 0}
    def fake_safe_request(url):
        calls["n"] += 1
        if calls["n"] == 1:
            return DummyResp(status_code=204, json_data={})
        return DummyResp(status_code=200, json_data={"availability": [
            {"start": "2023-01-01T00:00:00", "end": "2023-01-01T01:00:00"}
        ]})
    monkeypatch.setattr(avail, "_safe_request", fake_safe_request)
    spans = avail.get_availability_spans("http://fake/", "XX", "STA", "BHZ",
                                         "2023-01-01T00:00:00", "2023-01-01T02:00:00",
                                         location="01")
    assert spans != [] and calls["n"] == 2

def test_get_availability_spans_204_no_retry(monkeypatch):
    monkeypatch.setattr(avail, "_safe_request", lambda url: DummyResp(status_code=204, json_data={}))
    spans = avail.get_availability_spans("http://fake/", "XX", "STA", "BHZ",
                                         "2023-01-01T00:00:00", "2023-01-01T02:00:00",
                                         location="*")
    assert spans == []

def test_get_availability_spans_parse_error(monkeypatch):
    resp = DummyResp(status_code=200, json_data={}, raise_exc=ValueError("bad"))
    monkeypatch.setattr(avail, "_safe_request", lambda url: resp)
    spans = avail.get_availability_spans("http://fake/", "XX", "STA", "BHZ",
                                         "2023-01-01T00:00:00", "2023-01-01T02:00:00")
    assert spans == []


# -----------------
# check_availability
# -----------------

def test_check_availability(monkeypatch):
    monkeypatch.setattr(avail, "check_availability_query",
                        lambda *a, **kw: {"ok": True, "url": "fakeurl"})
    assert avail.check_availability("http://fake/", "XX", "STA", "BHZ",
                                    "2023-01-01T00:00:00", "2023-01-01T01:00:00") is True
    url, ok = avail.check_availability("http://fake/", "XX", "STA", "BHZ",
                                       "2023-01-01T00:00:00", "2023-01-01T01:00:00",
                                       return_url=True)
    assert ok is True
    assert url == "fakeurl"
