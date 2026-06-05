import json

import requests

import eida_consistency.services.wfcatalog as wf


class DummyResp:
    def __init__(self, content=b"", status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        return None

    def json(self):
        return json.loads(self.content)

    @property
    def text(self):
        return self.content.decode() if isinstance(self.content, bytes) else self.content


# -----------------
# URL building
# -----------------

def test_endpoint_uses_eidaws_path():
    ep = wf._wfcatalog_endpoint("https://eida.gein.noa.gr/fdsnws/")
    assert ep == "https://eida.gein.noa.gr/eidaws/wfcatalog/1/query"


def test_build_query_url_blank_location():
    url = wf._build_query_url("https://h/eidaws/wfcatalog/1/query", "N", "S", "", "C", "a", "b")
    assert "location=--" in url
    assert "granularity=day" in url and "format=json" in url


# -----------------
# Response handling
# -----------------

def test_200_with_data(monkeypatch):
    docs = [{"percent_availability": 100, "num_records": 8747}]
    monkeypatch.setattr(
        wf.requests, "get",
        lambda *a, **k: DummyResp(content=json.dumps(docs).encode()),
    )
    r = wf.check_wfcatalog("https://h/fdsnws/", "N", "S", "C", "a", "b")
    assert r["deployed"] is True
    assert r["has_data"] is True
    assert r["percent_availability"] == 100
    assert r["status"] == "OK"


def test_200_multiple_days_takes_max(monkeypatch):
    docs = [
        {"percent_availability": 0, "num_records": 0},
        {"percent_availability": 80, "num_records": 10},
    ]
    monkeypatch.setattr(
        wf.requests, "get",
        lambda *a, **k: DummyResp(content=json.dumps(docs).encode()),
    )
    r = wf.check_wfcatalog("https://h/fdsnws/", "N", "S", "C", "a", "b")
    assert r["percent_availability"] == 80
    assert r["has_data"] is True
    assert r["num_docs"] == 2


def test_204_no_data(monkeypatch):
    monkeypatch.setattr(wf.requests, "get", lambda *a, **k: DummyResp(status=204))
    r = wf.check_wfcatalog("https://h/fdsnws/", "N", "S", "C", "a", "b")
    assert r["deployed"] is True
    assert r["has_data"] is False
    assert r["status"] == "NoData"


def test_404_not_deployed(monkeypatch):
    monkeypatch.setattr(wf.requests, "get", lambda *a, **k: DummyResp(status=404))
    r = wf.check_wfcatalog("https://h/fdsnws/", "N", "S", "C", "a", "b")
    assert r["deployed"] is False
    assert r["has_data"] is None
    assert r["status"] == "NotDeployed"


def test_400_bad_request(monkeypatch):
    monkeypatch.setattr(
        wf.requests, "get",
        lambda *a, **k: DummyResp(content=b"future time", status=400),
    )
    r = wf.check_wfcatalog("https://h/fdsnws/", "N", "S", "C", "a", "b")
    assert r["deployed"] is True
    assert r["has_data"] is None
    assert r["status"] == "HTTP 400"


def test_connection_error_treated_as_not_deployed(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("no route")

    monkeypatch.setattr(wf.requests, "get", boom)
    monkeypatch.setattr(wf.time, "sleep", lambda *a, **k: None)
    r = wf.check_wfcatalog("https://h/fdsnws/", "N", "S", "C", "a", "b", max_attempts=2)
    assert r["deployed"] is False
    assert r["status"] == "NotDeployed"
