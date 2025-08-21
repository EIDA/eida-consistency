import logging
import pytest
from types import SimpleNamespace
import eida_consistency.services.station as station


class DummyResponse:
    def __init__(self, status=200, content=b"<root/>"):
        self.status_code = status
        self.content = content
    def raise_for_status(self):
        if self.status_code != 200:
            raise Exception("HTTP error")


def test_request_failure(monkeypatch):
    monkeypatch.setattr(station.requests, "get", lambda *a, **k: (_ for _ in ()).throw(Exception("boom")))
    result = station.fetch_candidates("http://fake/")
    assert result == []


def test_http_error(monkeypatch):
    def fake_get(*a, **k):
        r = DummyResponse(status=500, content=b"")
        def bad_raise():
            raise Exception("HTTP fail")
        r.raise_for_status = bad_raise
        return r
    monkeypatch.setattr(station.requests, "get", fake_get)
    result = station.fetch_candidates("http://fake/")
    assert result == []


def test_bad_xml(monkeypatch):
    bad = b"<not-closed"
    monkeypatch.setattr(station.requests, "get", lambda *a, **k: DummyResponse(200, bad))
    result = station.fetch_candidates("http://fake/")
    assert result == []


def test_valid_candidates(monkeypatch, caplog):
    xml = b"""
    <FDSNStationXML xmlns="http://www.fdsn.org/xml/station/1">
      <Network code="XX">
        <Station code="AAA">
          <Channel code="BHZ" locationCode="00" startDate="2020-01-01T00:00:00" endDate="2020-02-01T00:00:00"/>
        </Station>
      </Network>
    </FDSNStationXML>
    """
    monkeypatch.setattr(station.requests, "get", lambda *a, **k: DummyResponse(200, xml))
    caplog.set_level(logging.INFO)
    result = station.fetch_candidates("http://fake/")
    assert len(result) == 1
    c = result[0]
    assert c["network"] == "XX"
    assert c["station"] == "AAA"
    assert c["channel"] == "BHZ"
    assert c["starttime"] == "2020-01-01T00:00:00"
    assert c["endtime"] == "2020-02-01T00:00:00"
    assert c["location"] == "00"
    assert "Total candidates fetched: 1" in caplog.text


def test_skipped_malformed(monkeypatch, caplog):
    xml = b"""
    <FDSNStationXML xmlns="http://www.fdsn.org/xml/station/1">
      <Network code="YY">
        <Station code="BBB">
          <Channel code="HHZ"/>
        </Station>
      </Network>
    </FDSNStationXML>
    """
    monkeypatch.setattr(station.requests, "get", lambda *a, **k: DummyResponse(200, xml))
    caplog.set_level(logging.DEBUG)
    result = station.fetch_candidates("http://fake/")
    assert result == []  # skipped, missing startDate
    assert "Skipping malformed" in caplog.text
