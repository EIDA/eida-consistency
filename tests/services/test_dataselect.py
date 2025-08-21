import pytest
import types
from io import BytesIO

import eida_consistency.services.dataselect as dataselect


# -------------------------------------------------------------------
# Dummy classes to simulate ObsPy Stream/Trace
# -------------------------------------------------------------------
class DummyTrace:
    def __str__(self):
        return "Trace XX.AAA..BHZ | 2020-01-01T00:00:00 - 2020-01-01T01:00:00"


class DummyStream(list):
    def __init__(self, traces=None):
        super().__init__(traces or [])
    def __len__(self):
        return list.__len__(self)


def make_client_mock(stream_or_exc):
    """Return a dummy Client replacement."""
    class DummyClient:
        def __init__(self, *a, **k):
            pass
        def get_waveforms(self, *a, **k):
            if isinstance(stream_or_exc, Exception):
                raise stream_or_exc
            return stream_or_exc
    return DummyClient


class DummyResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", errors="ignore") if isinstance(content, (bytes, bytearray)) else str(content)


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------

def test_success_via_obspy_client(monkeypatch):
    dummy_stream = DummyStream([DummyTrace()])
    monkeypatch.setattr(dataselect, "Client", make_client_mock(dummy_stream))

    result = dataselect.dataselect("http://fake/", "XX", "AAA", "BHZ",
                                   "2020-01-01T00:00:00", "2020-01-01T01:00:00")
    assert result["success"] is True
    assert result["status"] == "OK"
    assert "ObsPy client" in result["debug"]


def test_no_data_via_obspy_client(monkeypatch):
    dummy_stream = DummyStream([])
    monkeypatch.setattr(dataselect, "Client", make_client_mock(dummy_stream))

    result = dataselect.dataselect("http://fake/", "XX", "AAA", "BHZ",
                                   "2020-01-01T00:00:00", "2020-01-01T01:00:00")
    assert result["success"] is False
    assert result["status"] == "NoData"
    assert "No waveform data" in result["debug"]


def test_fallback_to_http(monkeypatch):
    # Force client to raise
    monkeypatch.setattr(dataselect, "Client", make_client_mock(Exception("boom")))

    # Patch requests.get to return fake bytes
    def fake_get(url, timeout):
        return DummyResponse(200, b"FAKESEED")
    monkeypatch.setattr(dataselect.requests, "get", fake_get)

    # Patch obspy.read to return dummy traces
    monkeypatch.setattr(dataselect, "read", lambda *a, **k: DummyStream([DummyTrace()]))

    result = dataselect.dataselect("http://fake/", "XX", "AAA", "BHZ",
                                   "2020-01-01T00:00:00", "2020-01-01T01:00:00")
    assert result["success"] is True
    assert "raw HTTP" in result["debug"]


def test_http_nodata(monkeypatch):
    monkeypatch.setattr(dataselect, "Client", make_client_mock(Exception("boom")))

    def fake_get(url, timeout):
        return DummyResponse(204, b"")
    monkeypatch.setattr(dataselect.requests, "get", fake_get)

    result = dataselect.dataselect("http://fake/", "XX", "AAA", "BHZ",
                                   "2020-01-01T00:00:00", "2020-01-01T01:00:00")
    assert result["success"] is False
    assert result["status"] == "NoData"


def test_http_parse_error(monkeypatch):
    monkeypatch.setattr(dataselect, "Client", make_client_mock(Exception("boom")))

    def fake_get(url, timeout):
        return DummyResponse(200, b"FAKESEED")
    monkeypatch.setattr(dataselect.requests, "get", fake_get)

    # obspy.read returns empty stream
    monkeypatch.setattr(dataselect, "read", lambda *a, **k: DummyStream([]))

    result = dataselect.dataselect("http://fake/", "XX", "AAA", "BHZ",
                                   "2020-01-01T00:00:00", "2020-01-01T01:00:00")
    assert result["success"] is False
    assert result["status"] == "ParseError"


def test_http_exception(monkeypatch):
    monkeypatch.setattr(dataselect, "Client", make_client_mock(Exception("boom")))

    def fake_get(url, timeout):
        raise requests.RequestException("fail")
    monkeypatch.setattr(dataselect.requests, "get", fake_get)

    result = dataselect.dataselect("http://fake/", "XX", "AAA", "BHZ",
                                   "2020-01-01T00:00:00", "2020-01-01T01:00:00")
    assert result["success"] is False
    assert result["type"] == "Error"
    assert "Dataselect failed" in result["debug"]


def test_return_stream_flag(monkeypatch):
    dummy_stream = DummyStream([DummyTrace()])
    monkeypatch.setattr(dataselect, "Client", make_client_mock(dummy_stream))

    result = dataselect.dataselect("http://fake/", "XX", "AAA", "BHZ",
                                   "2020-01-01T00:00:00", "2020-01-01T01:00:00",
                                   return_stream=True)
    assert "stream" in result
    assert isinstance(result["stream"], DummyStream)
def test_return_stream_flag_via_http(monkeypatch):
    # Force ObsPy client to fail
    monkeypatch.setattr(dataselect, "Client", make_client_mock(Exception("boom")))

    # Fake HTTP response with bytes
    def fake_get(url, timeout):
        return DummyResponse(200, b"FAKESEED")
    monkeypatch.setattr(dataselect.requests, "get", fake_get)

    # Fake obspy.read returns non-empty stream
    dummy_stream = DummyStream([DummyTrace()])
    monkeypatch.setattr(dataselect, "read", lambda *a, **k: dummy_stream)

    result = dataselect.dataselect(
        "http://fake/", "XX", "AAA", "BHZ",
        "2020-01-01T00:00:00", "2020-01-01T01:00:00",
        return_stream=True
    )

    assert result["success"] is True
    assert "stream" in result
    assert isinstance(result["stream"], DummyStream)
def test_obspy_client_attribute_error_falls_back(monkeypatch):
    # Simulate ObsPy client raising AttributeError
    class FakeClient:
        def get_waveforms(self, *a, **k):
            raise AttributeError("simulated obspy bug")

    monkeypatch.setattr(dataselect, "Client", lambda *a, **k: FakeClient())

    # Fake HTTP fallback works
    def fake_get(url, timeout):
        return DummyResponse(200, b"FAKESEED")
    monkeypatch.setattr(dataselect.requests, "get", fake_get)

    dummy_stream = DummyStream([DummyTrace()])
    monkeypatch.setattr(dataselect, "read", lambda *a, **k: dummy_stream)

    result = dataselect.dataselect(
        "http://fake/", "XX", "AAA", "BHZ",
        "2020-01-01T00:00:00", "2020-01-01T01:00:00"
    )

    # Ensure it fell back and still succeeded
    assert result["success"] is True
    assert result["status"] == "OK"
    assert "FAKESEED" not in result["debug"]  # not raw bytes dump
