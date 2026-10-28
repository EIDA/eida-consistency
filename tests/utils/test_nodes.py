import json
import logging
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


# ----------------------------------------------------------------------
# user-defined nodes (issue #64: e.g. AFAD, not yet in routing / obspy)
# ----------------------------------------------------------------------
@pytest.fixture
def custom_env(monkeypatch, tmp_path):
    """Isolate custom-node file, env var and routing cache."""
    monkeypatch.setattr(nodes, "CUSTOM_NODES_FILE", tmp_path / "custom_nodes.json")
    monkeypatch.delenv(nodes.CUSTOM_NODES_ENV, raising=False)
    monkeypatch.setattr(
        nodes, "load_or_refresh_cache", lambda: [("NOA", "https://eida.gein.noa.gr/fdsnws/", True)]
    )
    return tmp_path


@pytest.mark.parametrize("url", [
    "https://afad.example.org",
    "https://afad.example.org/",
    "https://afad.example.org/fdsnws",
    "https://afad.example.org/fdsnws/station/1/query",
    "  https://afad.example.org/fdsnws/  ",
])
def test_normalize_node_url(url):
    assert nodes.normalize_node_url(url) == "https://afad.example.org/fdsnws/"


def test_normalize_node_url_keeps_port_and_http():
    assert nodes.normalize_node_url("http://host:8080/fdsnws/") == "http://host:8080/fdsnws/"


@pytest.mark.parametrize("url", ["afad.example.org", "ftp://afad.example.org", "https://", ""])
def test_normalize_node_url_rejects_invalid(url):
    with pytest.raises(ValueError):
        nodes.normalize_node_url(url)


def test_add_custom_node_resolves(custom_env):
    assert nodes.add_custom_node("afad", "https://afad.example.org") == (
        "AFAD", "https://afad.example.org/fdsnws/"
    )
    assert nodes.load_node_url("AFAD") == "https://afad.example.org/fdsnws/"
    assert nodes.load_node_url("afad") == "https://afad.example.org/fdsnws/"
    # routing nodes still resolve
    assert nodes.load_node_url("NOA") == "https://eida.gein.noa.gr/fdsnws/"


def test_custom_node_overrides_routing(custom_env):
    nodes.add_custom_node("NOA", "https://mirror.example.org/")
    assert nodes.load_node_url("NOA") == "https://mirror.example.org/fdsnws/"


def test_custom_nodes_survive_routing_reload(custom_env, monkeypatch):
    nodes.add_custom_node("AFAD", "https://afad.example.org")
    monkeypatch.setattr(nodes, "CACHE_FILE", custom_env / "nodes_cache.json")
    nodes.CACHE_FILE.write_text(json.dumps({"nodes": []}), encoding="utf-8")
    assert nodes.load_node_url("AFAD") == "https://afad.example.org/fdsnws/"


def test_remove_custom_node(custom_env):
    nodes.add_custom_node("AFAD", "https://afad.example.org")
    assert nodes.remove_custom_node("afad") is True
    assert nodes.remove_custom_node("AFAD") is False
    with pytest.raises(ValueError, match="add-node AFAD"):
        nodes.load_node_url("AFAD")


def test_custom_nodes_from_env(custom_env, monkeypatch):
    monkeypatch.setenv(
        nodes.CUSTOM_NODES_ENV, "afad=https://afad.example.org, FOO=http://foo.org/fdsnws/ ,"
    )
    assert nodes.load_node_url("AFAD") == "https://afad.example.org/fdsnws/"
    assert nodes.load_node_url("FOO") == "http://foo.org/fdsnws/"


def test_env_overrides_file(custom_env, monkeypatch):
    nodes.add_custom_node("AFAD", "https://file.example.org")
    monkeypatch.setenv(nodes.CUSTOM_NODES_ENV, "AFAD=https://env.example.org")
    assert nodes.load_node_url("AFAD") == "https://env.example.org/fdsnws/"


@pytest.mark.parametrize("raw", ["AFAD", "=https://x.org", "AFAD=not-a-url"])
def test_custom_nodes_env_invalid(custom_env, monkeypatch, raw):
    monkeypatch.setenv(nodes.CUSTOM_NODES_ENV, raw)
    with pytest.raises(ValueError):
        nodes.load_custom_nodes()


def test_corrupt_custom_nodes_file(custom_env):
    nodes.CUSTOM_NODES_FILE.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupt custom nodes file"):
        nodes.load_custom_nodes()


def test_load_node_url_warns_on_routing_override(custom_env, caplog):
    nodes.add_custom_node("NOA", "https://mirror.example.org")
    with caplog.at_level(logging.INFO):
        assert nodes.load_node_url("noa") == "https://mirror.example.org/fdsnws/"
    assert any(
        r.levelno == logging.WARNING and "INSTEAD OF the EIDA routing endpoint" in r.message
        for r in caplog.records
    )


def test_load_node_url_flags_redundant_custom_node(custom_env, caplog):
    nodes.add_custom_node("NOA", "https://eida.gein.noa.gr/fdsnws/")
    with caplog.at_level(logging.INFO):
        nodes.load_node_url("NOA")
    assert "can be removed (remove-node NOA)" in caplog.text


def test_unknown_node_lists_known_nodes(custom_env):
    nodes.add_custom_node("AFAD", "https://afad.example.org")
    with pytest.raises(ValueError, match=r"Known nodes: AFAD, NOA\..*add-node XYZ <url>"):
        nodes.load_node_url("xyz")


def test_probe_node(monkeypatch):
    import requests

    class Resp:
        def __init__(self, status, text="1.1.2\n"):
            self.status_code = status
            self.ok = status < 400
            self.text = text

    def fake_get(url, **k):
        if "dataselect" in url:
            return Resp(503)
        if "availability" in url:
            raise requests.ConnectionError("no route")
        return Resp(200)

    monkeypatch.setattr(requests, "get", fake_get)
    assert nodes.probe_node("https://afad.example.org/fdsnws/") == {
        "station": None,
        "dataselect": "HTTP 503",
        "availability": "ConnectionError",
    }

    # A host that serves its website (200 + HTML) for every path is not FDSN.
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(200, "<!DOCTYPE html><html>..."))
    assert all(
        problem.startswith("not an FDSN service")
        for problem in nodes.probe_node("https://afad.example.org/fdsnws/").values()
    )
