import types
import pytest
import eida_consistency.services.dataselect as ds


def _fake_trace(start_iso, end_iso, sr):
    stats = types.SimpleNamespace(
        starttime=types.SimpleNamespace(isoformat=lambda s=start_iso: s),
        endtime=types.SimpleNamespace(isoformat=lambda e=end_iso: e),
        sampling_rate=sr,
    )
    return types.SimpleNamespace(stats=stats)


def test_segments_extracted_from_stream(monkeypatch):
    fake_stream = [
        _fake_trace("2020-01-09T23:59:19", "2020-01-09T23:59:59", 100.0),
        _fake_trace("2020-01-10T00:00:00", "2020-01-10T00:09:19", 100.0),
    ]
    monkeypatch.setattr(ds, "Client", lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    monkeypatch.setattr(ds.requests, "get", lambda *a, **k: DummyResp(content=b"ok"))
    monkeypatch.setattr(ds, "read", lambda bio, format=None: fake_stream)
    r = ds.dataselect("https://h", "N", "S", "C", "2020-01-09", "2020-01-10")
    assert r["success"]
    assert r["segments"] == [
        ("2020-01-09T23:59:19", "2020-01-09T23:59:59", 100.0),
        ("2020-01-10T00:00:00", "2020-01-10T00:09:19", 100.0),
    ]


def test_segments_empty_on_nodata(monkeypatch):
    monkeypatch.setattr(ds, "Client", lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    monkeypatch.setattr(ds.requests, "get", lambda *a, **k: DummyResp(status=204))
    r = ds.dataselect("https://h", "N", "S", "C", "2020", "2021")
    assert r["segments"] == []


class DummyResp:
    def __init__(self, content=b"", status=200):
        self.content = content
        self.status_code = status
    def raise_for_status(self): return None


# -----------------
# Helpers
# -----------------

def test_endpoint_from_base_variants():
    assert ds._endpoint_from_base("https://ws.resif.fr/abc") == "https://ws.resif.fr"
    assert ds._endpoint_from_base("http://example.com") == "http://example.com"
    # For a bare string without scheme, function returns "https:"
    assert ds._endpoint_from_base("example.com") == "https:"

def test_build_query_url():
    url = ds._build_query_url("https://h", "N","S","L","C","2024","2025")
    assert url.startswith("https://h/fdsnws/dataselect/1/query?")
    assert "network=N" in url and "channel=C" in url


# -----------------
# ObsPy client path
# -----------------

def test_client_attributeerror_fallback(monkeypatch):
    class FakeClient:
        def get_waveforms(self, **k): raise AttributeError("fail")
    monkeypatch.setattr(ds, "Client", lambda *a, **k: FakeClient())
    monkeypatch.setattr(ds.requests, "get", lambda *a, **k: DummyResp(content=b"ok"))
    monkeypatch.setattr(ds, "read", lambda bio, format=None: [object()])
    r = ds.dataselect("https://h","N","S","C","2024","2025")
    assert r["success"]

def test_client_otherexception_fallback(monkeypatch):
    class FakeClient:
        def get_waveforms(self, **k): raise RuntimeError("boom")
    monkeypatch.setattr(ds, "Client", lambda *a, **k: FakeClient())
    monkeypatch.setattr(ds.requests, "get", lambda *a, **k: DummyResp(content=b"ok"))
    monkeypatch.setattr(ds, "read", lambda bio, format=None: [object()])
    r = ds.dataselect("https://h","N","S","C","2024","2025")
    assert r["success"]


# -----------------
# Raw HTTP fallback
# -----------------

def test_raw_http_204(monkeypatch):
    monkeypatch.setattr(ds, "Client", lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    monkeypatch.setattr(ds.requests, "get", lambda *a, **k: DummyResp(status=204))
    r = ds.dataselect("https://h","N","S","C","2024","2025")
    assert not r["success"] and r["status"]=="NoData"

def test_raw_http_parse_success(monkeypatch):
    monkeypatch.setattr(ds, "Client", lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    monkeypatch.setattr(ds.requests, "get", lambda *a, **k: DummyResp(content=b"ok"))
    monkeypatch.setattr(ds, "read", lambda bio, format=None: [object()])
    r = ds.dataselect("https://h","N","S","C","2024","2025", return_stream=True)
    assert r["success"] and "stream" in r

def test_raw_http_parse_empty(monkeypatch):
    monkeypatch.setattr(ds, "Client", lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    monkeypatch.setattr(ds.requests, "get", lambda *a, **k: DummyResp(content=b"ok"))
    monkeypatch.setattr(ds, "read", lambda bio, format=None: [])
    r = ds.dataselect("https://h","N","S","C","2024","2025")
    assert not r["success"] and r["status"]=="ParseError"

def test_raw_http_exception(monkeypatch):
    monkeypatch.setattr(ds, "Client", lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    monkeypatch.setattr(ds.requests, "get", lambda *a, **k: (_ for _ in ()).throw(Exception("network down")))
    r = ds.dataselect("https://h","N","S","C","2024","2025")
    assert not r["success"] and r["type"]=="Error"
    assert "debug" in r and "Dataselect failed" in r["debug"]
