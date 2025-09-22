import pytest
import requests
from datetime import datetime
import eida_consistency.services.availability as avail


class DummyResp:
    def __init__(self, text="", status=200, raise_exc=None):
        self.text = text
        self.status_code = status
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc


# -----------------
# _parse_iso
# -----------------

def test_parse_iso_with_z():
    dt = avail._parse_iso("2024-01-01T00:00:00Z")
    assert isinstance(dt, datetime)
    assert dt.year == 2024

def test_parse_iso_with_offset():
    dt = avail._parse_iso("2024-01-01T00:00:00+00:00")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None


# -----------------
# _parse_text_availability
# -----------------

def test_parse_empty_and_comments():
    assert avail._parse_text_availability("") == []
    txt = "# just a comment\n"
    assert avail._parse_text_availability(txt) == []

def test_parse_schema8():
    txt = "HL STA -- HHZ D 100.0 2024-01-01T00:00:00Z 2024-01-02T00:00:00Z"
    spans = avail._parse_text_availability(txt)
    assert len(spans) == 1
    s = spans[0]
    assert s["network"] == "HL"
    assert s["station"] == "STA"
    assert s["location"] == ""  # "--" stripped
    assert s["channel"] == "HHZ"
    assert s["quality"] == "D"
    assert s["samplerate"] == "100.0"

def test_parse_schema7():
    txt = "HL STA -- HHZ 50.0 2024-01-01T00:00:00Z 2024-01-02T00:00:00Z"
    spans = avail._parse_text_availability(txt)
    assert spans[0]["samplerate"] == "50.0"

def test_parse_schema6():
    txt = "HL STA HHZ 20.0 2024-01-01T00:00:00Z 2024-01-02T00:00:00Z"
    spans = avail._parse_text_availability(txt)
    assert spans[0]["channel"] == "HHZ"
    assert spans[0]["samplerate"] == "20.0"

def test_parse_schema5():
    txt = "HL STA HHZ 2024-01-01T00:00:00Z 2024-01-02T00:00:00Z"
    spans = avail._parse_text_availability(txt)
    assert spans[0]["channel"] == "HHZ"
    assert spans[0]["samplerate"] is None

def test_parse_invalid_timestamp_skipped():
    bad_txt = "HL STA HHZ 20.0 not-a-time 2024-01-02T00:00:00Z"
    spans = avail._parse_text_availability(bad_txt)
    assert spans == []

def test_parse_inconsistent_line_skipped():
    # schema detection says 5 fields, but second line has 6
    txt = (
        "HL STA HHZ 2024-01-01T00:00:00Z 2024-01-02T00:00:00Z\n"
        "HL STA HHZ 20.0 2024-01-01T00:00:00Z 2024-01-02T00:00:00Z"
    )
    spans = avail._parse_text_availability(txt)
    # only first line kept
    assert len(spans) == 1


# -----------------
# check_availability_query
# -----------------

def test_check_availability_query_204(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: DummyResp(status=204))
    result = avail.check_availability_query("http://x/", "HL", "STA", "HHZ",
                                            "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z")
    assert result["status"] == 204
    assert result["ok"] is False
    assert result["spans"] == []

def test_check_availability_query_ok(monkeypatch):
    txt = "HL STA -- HHZ D 100.0 2024-01-01T00:00:00Z 2024-01-03T00:00:00Z"
    monkeypatch.setattr(requests, "get", lambda *a, **k: DummyResp(text=txt))
    result = avail.check_availability_query("http://x/", "HL", "STA", "HHZ",
                                            "2024-01-01T12:00:00Z", "2024-01-02T12:00:00Z")
    assert result["ok"] is True
    assert result["matched_span"] is not None

def test_check_availability_query_notcovered(monkeypatch):
    txt = "HL STA -- HHZ D 100.0 2024-01-01T00:00:00Z 2024-01-01T01:00:00Z"
    monkeypatch.setattr(requests, "get", lambda *a, **k: DummyResp(text=txt))
    result = avail.check_availability_query("http://x/", "HL", "STA", "HHZ",
                                            "2024-01-01T02:00:00Z", "2024-01-01T03:00:00Z")
    assert result["ok"] is False
    assert result["matched_span"] is None

def test_check_availability_query_exception(monkeypatch):
    def bad_get(*a, **k): raise Exception("boom")
    monkeypatch.setattr(requests, "get", bad_get)
    result = avail.check_availability_query("http://x/", "HL", "STA", "HHZ",
                                            "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z")
    assert result["ok"] is False
    assert result["status"] == 0


# -----------------
# get_availability_spans
# -----------------

def test_get_availability_spans_204(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: DummyResp(status=204))
    spans = avail.get_availability_spans("http://x/", "HL", "STA", "HHZ",
                                         "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z")
    assert spans == []

def test_get_availability_spans_ok(monkeypatch):
    txt = "HL STA -- HHZ D 100.0 2024-01-01T00:00:00Z 2024-01-02T00:00:00Z"
    monkeypatch.setattr(requests, "get", lambda *a, **k: DummyResp(text=txt))
    spans = avail.get_availability_spans("http://x/", "HL", "STA", "HHZ",
                                         "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z")
    assert len(spans) == 1

def test_get_availability_spans_exception(monkeypatch):
    def bad_get(*a, **k): raise Exception("fail")
    monkeypatch.setattr(requests, "get", bad_get)
    spans = avail.get_availability_spans("http://x/", "HL", "STA", "HHZ",
                                         "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z")
    assert spans == []


# -----------------
# check_availability wrapper
# -----------------

def test_check_availability_wrapper(monkeypatch):
    txt = "HL STA -- HHZ D 100.0 2024-01-01T00:00:00Z 2024-01-03T00:00:00Z"
    monkeypatch.setattr(requests, "get", lambda *a, **k: DummyResp(text=txt))
    ok = avail.check_availability("http://x/", "HL", "STA", "HHZ",
                                  "2024-01-01T12:00:00Z", "2024-01-02T12:00:00Z")
    assert ok is True

def test_check_availability_wrapper_return_url(monkeypatch):
    txt = "HL STA -- HHZ D 100.0 2024-01-01T00:00:00Z 2024-01-03T00:00:00Z"
    monkeypatch.setattr(requests, "get", lambda *a, **k: DummyResp(text=txt))
    url, ok = avail.check_availability("http://x/", "HL", "STA", "HHZ",
                                       "2024-01-01T12:00:00Z", "2024-01-02T12:00:00Z",
                                       return_url=True)
    assert isinstance(url, str)
    assert ok is True
