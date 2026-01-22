import pytest
import requests
import eida_consistency.services.station as station


class DummyResp:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status
    def raise_for_status(self): return None


# -----------------
# _fetch_text
# -----------------

def test_fetch_text_success(monkeypatch):
    text = "#comment\n\nNET1|STA1\nNET2|STA2"
    monkeypatch.setattr(requests, "get", lambda *a, **k: DummyResp(text=text))
    lines = station._fetch_text("http://fake/")
    assert lines == ["NET1|STA1", "NET2|STA2"]

def test_fetch_text_exception(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(Exception("boom")))
    assert station._fetch_text("http://fake/") == []


# -----------------
# fetch_candidates
# -----------------

def test_no_networks(monkeypatch):
    monkeypatch.setattr(station, "_fetch_text", lambda *a, **k: [])
    assert station.fetch_candidates("http://fake/") == []

def test_no_stations(monkeypatch):
    def fake_fetch(url, **k):
        if "level=network" in url:
            return ["NET1|meta"]
        return []
    monkeypatch.setattr(station, "_fetch_text", fake_fetch)
    assert station.fetch_candidates("http://fake/") == []

def test_no_channels(monkeypatch):
    def fake_fetch(url, **k):
        if "level=network" in url:
            return ["NET1|meta"]
        if "level=station" in url:
            return ["NET1|STA1"]
        if "level=channel" in url:
            return ["bad|line"]
        return []
    monkeypatch.setattr(station, "_fetch_text", fake_fetch)
    assert station.fetch_candidates("http://fake/") == []

def test_valid_candidates_with_location_and_endtime(monkeypatch):
    monkeypatch.setattr(station.random, "shuffle", lambda x: x)

    def fake_fetch(url, **k):
        if "level=network" in url:
            return ["NET1|meta"]
        if "level=station" in url:
            return ["NET1|STA1"]
        if "level=channel" in url:
            # Build valid line with >=16 fields
            parts = [
                "NET1","STA1","LOC1","BHZ"
            ] + ["x"]*11 + ["2024-01-01T00:00:00Z","2024-01-02T00:00:00Z"]
            return ["|".join(parts)]
        return []
    monkeypatch.setattr(station, "_fetch_text", fake_fetch)

    result = station.fetch_candidates("http://fake/", max_candidates=1)
    assert len(result) == 1
    cand = result[0]
    assert cand["network"] == "NET1"
    assert cand["station"] == "STA1"
    assert cand["channel"] == "BHZ"
    assert cand["location"] == "LOC1"
    assert "endtime" in cand

def test_valid_candidates_without_location_or_endtime(monkeypatch):
    monkeypatch.setattr(station.random, "shuffle", lambda x: x)

    def fake_fetch(url, **k):
        if "level=network" in url:
            return ["NET1|meta"]
        if "level=station" in url:
            return ["NET1|STA1"]
        if "level=channel" in url:
            parts = ["NET1","STA1","","HHZ"] + ["x"]*11 + ["2024-01-01T00:00:00Z",""]
            return ["|".join(parts)]
        return []
    monkeypatch.setattr(station, "_fetch_text", fake_fetch)

    result = station.fetch_candidates("http://fake/", max_candidates=1)
    cand = result[0]
    assert "location" not in cand
    assert "endtime" not in cand

def test_truncate_max_candidates(monkeypatch):
    monkeypatch.setattr(station.random, "shuffle", lambda x: x)

    def fake_fetch(url, **k):
        if "level=network" in url:
            return ["NET1|meta"]
        if "level=station" in url:
            # 5 stations available
            return [f"NET1|STA{i}" for i in range(5)]
        if "station=STA0" in url:
            parts = ["NET1","STA0","","HHZ"] + ["x"]*11 + ["2024-01-01T00:00:00Z",""]
            return ["|".join(parts)]
        return []
    monkeypatch.setattr(station, "_fetch_text", fake_fetch)

    result = station.fetch_candidates("http://fake/", max_candidates=2)
    # Only STA0 yields valid channel
    assert len(result) == 1
    assert result[0]["station"] == "STA0"

def test_percentage_candidates(monkeypatch):
    """Verify percentage argument correctly selects a subset of stations."""
    monkeypatch.setattr(station.random, "shuffle", lambda x: x)

    def fake_fetch(url, **k):
        if "level=network" in url:
            return ["NET1|meta"]
        if "level=station" in url:
            # 10 stations available
            return [f"NET1|STA{i}" for i in range(10)]
        if "level=channel" in url:
            # Fake channel for whatever station is queried
            # Extract station from url: ...station=STA0...
            # This is a bit simplistic, but suffices if requests are robust.
            # Using simple looping logic in fetch_candidates 
            # (which does: for net, sta in selected_sta: fetch...)
            # We just need to return a valid channel line.
            
            # Since fetch_candidates calls _fetch_text with specific URL
            # we can infer which station is asked.
            import re
            m = re.search(r"station=([^&]+)", url)
            sta = m.group(1) if m else "UNK"
            
            line_parts = ["NET1", sta, "", "HHZ"] + ["x"]*11 + ["2024-01-01T00:00:00Z", ""]
            return ["|".join(line_parts)]
        return []
    
    monkeypatch.setattr(station, "_fetch_text", fake_fetch)

    # Test 50% of 10 stations -> should pick 5 stations -> yield 5 candidates
    res_50 = station.fetch_candidates("http://fake/", max_candidates=30, percentage=0.5)
    assert len(res_50) == 5
    
    # Test 10% of 10 stations -> should pick 1 station
    res_10 = station.fetch_candidates("http://fake/", max_candidates=30, percentage=0.1)
    assert len(res_10) == 1

    # Test 100% -> 10 stations
    res_100 = station.fetch_candidates("http://fake/", max_candidates=30, percentage=1.0)
    assert len(res_100) == 10
    
    # Test very small percentage -> should min at 1
    res_small = station.fetch_candidates("http://fake/", max_candidates=30, percentage=0.01)
    assert len(res_small) == 1
