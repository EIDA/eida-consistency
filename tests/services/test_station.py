import pytest
import xml.etree.ElementTree as ET
import eida_consistency.services.station as station


# -----------------
# _fetch_xml
# -----------------

class DummyResp:
    def __init__(self, content=b"<root/>", status=200, raise_exc=None):
        self.content = content
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc


def test_fetch_xml_success(monkeypatch):
    xml_str = "<Root><A>ok</A></Root>"
    monkeypatch.setattr(station.requests, "get", lambda url, timeout=60: DummyResp(content=xml_str.encode()))
    tree = station._fetch_xml("http://fake/")
    assert isinstance(tree, ET.Element)
    assert tree.tag == "Root"

def test_fetch_xml_failure(monkeypatch):
    def bad_get(url, timeout=60): raise Exception("boom")
    monkeypatch.setattr(station.requests, "get", bad_get)
    result = station._fetch_xml("http://fake/")
    assert result is None


# -----------------
# fetch_candidates
# -----------------

NETWORK_XML = """<FDSNStationXML xmlns="http://www.fdsn.org/xml/station/1">
  <Network code="XX"/>
</FDSNStationXML>"""

STATION_XML = """<FDSNStationXML xmlns="http://www.fdsn.org/xml/station/1">
  <Network code="XX">
    <Station code="AAA"/>
    <Station code="BBB"/>
  </Network>
</FDSNStationXML>"""

CHANNEL_XML = """<FDSNStationXML xmlns="http://www.fdsn.org/xml/station/1">
  <Network code="XX">
    <Station code="AAA">
      <Channel code="BHZ" locationCode="00" startDate="2023-01-01T00:00:00" endDate="2023-01-01T01:00:00"/>
      <Channel code="HHN" locationCode="01" startDate="2023-01-01T00:00:00"/>
    </Station>
  </Network>
</FDSNStationXML>"""


def test_fetch_candidates_no_networks(monkeypatch):
    monkeypatch.setattr(station, "_fetch_xml", lambda url: ET.fromstring("<FDSNStationXML/>"))
    results = station.fetch_candidates("http://fake/")
    assert results == []


def test_fetch_candidates_no_stations(monkeypatch):
    # Stage 1: networks
    def fake_fetch(url):
        if "level=network" in url:
            return ET.fromstring(NETWORK_XML)
        if "level=station" in url:
            return ET.fromstring("<FDSNStationXML xmlns='http://www.fdsn.org/xml/station/1'><Network code='XX'/></FDSNStationXML>")
        return None
    monkeypatch.setattr(station, "_fetch_xml", fake_fetch)
    results = station.fetch_candidates("http://fake/")
    assert results == []


def test_fetch_candidates_success(monkeypatch):
    # Cycle through responses depending on URL
    def fake_fetch(url):
        if "level=network" in url:
            return ET.fromstring(NETWORK_XML)
        elif "level=station" in url:
            return ET.fromstring(STATION_XML)
        elif "level=channel" in url:
            return ET.fromstring(CHANNEL_XML)
        return None

    monkeypatch.setattr(station, "_fetch_xml", fake_fetch)

    results = station.fetch_candidates("http://fake/", max_stations=2, max_workers=1)
    assert len(results) <= 2
    for r in results:
        assert "network" in r and "station" in r and "channel" in r
        assert "starttime" in r
