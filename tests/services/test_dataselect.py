import pytest
import eida_consistency.services.dataselect as ds


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
