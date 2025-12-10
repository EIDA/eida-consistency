import json
import pytest
from eida_consistency.utils import nodes


def test_ensure_cache_dir(tmp_path):
    # redirect cache file to tmp dir
    test_file = tmp_path / "nodes_cache.json"
    monkeyed = nodes
    monkeyed.CACHE_FILE = test_file
    nodes.ensure_cache_dir()
    assert test_file.parent.exists()


def test_refresh_cache_success(monkeypatch, tmp_path):
    payload = {
        "datacenters": [
            {
                "name": "FAKE",
                "repositories": [
                    {
                        "services": [
                            {"name": "fdsnws-station-1", "url": "https://fake.org/fdsnws/station/1"}
                        ]
                    }
                ],
            }
        ]
    }

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200

        def json(self):
            return self._payload

        def raise_for_status(self): 
            pass

    monkeypatch.setattr("requests.get", lambda *a, **k: DummyResponse(payload))
    monkeypatch.setattr(nodes, "CACHE_FILE", tmp_path / "nodes_cache.json")

    result = nodes.refresh_cache_from_routing()
    assert result == [("FAKE", "https://fake.org/fdsnws/", True)]
    # file should be written
    data = json.loads(nodes.CACHE_FILE.read_text())
    assert data["nodes"] == [["FAKE", "https://fake.org/fdsnws/", True]]


def test_refresh_cache_failure(monkeypatch):
    class BadResponse:
        def raise_for_status(self):
            raise Exception("fail")
        def json(self):
            return {}

    monkeypatch.setattr("requests.get", lambda *a, **k: BadResponse())

    with pytest.raises(RuntimeError):
        nodes.refresh_cache_from_routing()


def test_load_or_refresh_cache_from_existing(monkeypatch, tmp_path):
    cached = {"nodes": [["X", "http://x/", True]]}
    cache_file = tmp_path / "nodes_cache.json"
    cache_file.write_text(json.dumps(cached), encoding="utf-8")
    monkeypatch.setattr(nodes, "CACHE_FILE", cache_file)

    result = nodes.load_or_refresh_cache()
    assert result == [("X", "http://x/", True)]


def test_load_or_refresh_cache_bad_file(monkeypatch, tmp_path):
    cache_file = tmp_path / "nodes_cache.json"
    cache_file.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(nodes, "CACHE_FILE", cache_file)
    # patch refresh_cache_from_routing to throw
    monkeypatch.setattr(nodes, "refresh_cache_from_routing", lambda: (_ for _ in ()).throw(Exception("boom")))

    result = nodes.load_or_refresh_cache()
    # Should fall back to DEFAULT_NODES
    assert result == nodes.DEFAULT_NODES
    assert not cache_file.exists()  # file should be deleted


def test_load_node_url_and_error(monkeypatch, tmp_path):
    cache_file = tmp_path / "nodes_cache.json"
    cached = {"nodes": [["NOA", "http://fake.org/fdsnws/", True]]}
    cache_file.write_text(json.dumps(cached), encoding="utf-8")
    monkeypatch.setattr(nodes, "CACHE_FILE", cache_file)

    # works
    url = nodes.load_node_url("NOA")
    assert url == "http://fake.org/fdsnws/"

    # raises error
    with pytest.raises(ValueError):
        nodes.load_node_url("UNKNOWN")


def test_get_obspy_url():
    base_url = "https://eida.gein.noa.gr/fdsnws/"
    assert nodes.get_obspy_url(base_url) == "http://eida.gein.noa.gr"

    # fallback: if no hostname, return same
    assert nodes.get_obspy_url("not-a-url") == "not-a-url"
