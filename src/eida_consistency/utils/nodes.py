"""Node utilities for managing EIDA node information."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from appdirs import user_cache_dir, user_config_dir

ROUTING_URL = "https://www.orfeus-eu.org/eidaws/routing/1/globalconfig?format=fdsn"
CACHE_FILE = Path(user_cache_dir("eida_consistency")) / "nodes_cache.json"

# User-defined nodes (e.g. a new EIDA node not yet in routing, like AFAD).
# Kept apart from the routing cache so `reload-nodes` never wipes them.
CUSTOM_NODES_FILE = Path(user_config_dir("eida_consistency")) / "custom_nodes.json"
# Same thing via environment (Docker/CI): "AFAD=https://host/fdsnws/,FOO=https://..."
CUSTOM_NODES_ENV = "EIDA_CUSTOM_NODES"

DEFAULT_NODES = [
    ("GFZ", "https://geofon.gfz.de/fdsnws/", True),
    ("ODC", "https://orfeus-eu.org/fdsnws/", True),
    ("ETHZ", "https://eida.ethz.ch/fdsnws/", True),
    ("EPOSFR", "https://seisdata.epos-france.fr/fdsnws/", True),
    ("INGV", "https://webservices.ingv.it/fdsnws/", True),
    ("LMU", "https://erde.geophysik.uni-muenchen.de/fdsnws/", True),
    ("ICGC", "https://ws.icgc.cat/fdsnws/", True),
    ("NOA", "https://eida.gein.noa.gr/fdsnws/", True),
    ("BGR", "https://eida.bgr.de/fdsnws/", True),
    ("BGS", "https://eida.bgs.ac.uk/fdsnws/", True),
    ("NIEP", "https://eida-sc3.infp.ro/fdsnws/", True),
    ("KOERI", "https://eida.koeri.boun.edu.tr/fdsnws/", True),
    ("UIB-NORSAR", "https://eida.geo.uib.no/fdsnws/", True),
]


def ensure_cache_dir() -> None:
    """Ensure the cache directory exists."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)


def refresh_cache_from_routing() -> list[tuple[str, str, bool]]:
    """Fetch node list from routing service and cache it."""
    import requests

    try:
        response = requests.get(ROUTING_URL, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError("Failed to fetch routing data") from exc

    nodes: list[tuple[str, str, bool]] = []
    for dc in response.json().get("datacenters", []):
        name = dc.get("name")
        for repo in dc.get("repositories", []):
            for srv in repo.get("services", []):
                if srv.get("name") == "fdsnws-station-1":
                    url = srv["url"]
                    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}/fdsnws/"
                    nodes.append((name, base, True))
                    break
            if name and nodes and nodes[-1][0] == name:
                break

    CACHE_FILE.write_text(json.dumps({"nodes": nodes}), encoding="utf-8")
    return nodes


def load_or_refresh_cache() -> list[tuple[str, str, bool]]:
    """Return cached nodes or refresh from routing."""
    ensure_cache_dir()
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            nodes = data.get("nodes", [])
            if all(isinstance(n, list) and len(n) == 3 for n in nodes):
                return [(n[0], n[1], n[2]) for n in nodes]
        except Exception:  # noqa: BLE001
            CACHE_FILE.unlink()

    try:
        return refresh_cache_from_routing()
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.warning("Routing failed: %s", exc)
        return DEFAULT_NODES


def normalize_node_url(url: str) -> str:
    """Normalize a node endpoint to the ``scheme://host/fdsnws/`` form used by routing.

    Accepts ``https://host``, ``https://host/fdsnws`` or any service URL below it.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid node URL (expected http(s)://host[/fdsnws/]): {url}")
    return f"{parsed.scheme}://{parsed.netloc}/fdsnws/"


def _custom_nodes_from_env() -> list[tuple[str, str, bool]]:
    """Parse ``EIDA_CUSTOM_NODES`` ("NAME=URL,NAME=URL") into node tuples."""
    raw = os.environ.get(CUSTOM_NODES_ENV, "").strip()
    nodes: list[tuple[str, str, bool]] = []
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        name, sep, url = entry.partition("=")
        if not sep or not name.strip():
            raise ValueError(f"Invalid {CUSTOM_NODES_ENV} entry (expected NAME=URL): {entry}")
        nodes.append((name.strip().upper(), normalize_node_url(url), True))
    return nodes


def _read_custom_nodes_file() -> dict[str, str]:
    if not CUSTOM_NODES_FILE.exists():
        return {}
    try:
        data = json.loads(CUSTOM_NODES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Corrupt custom nodes file {CUSTOM_NODES_FILE}: {exc}") from exc
    return {str(k).upper(): str(v) for k, v in data.get("nodes", {}).items()}


def _write_custom_nodes_file(nodes: dict[str, str]) -> None:
    CUSTOM_NODES_FILE.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM_NODES_FILE.write_text(json.dumps({"nodes": nodes}, indent=2), encoding="utf-8")


def load_custom_nodes() -> list[tuple[str, str, bool]]:
    """Return user-defined nodes; env entries override file entries of the same name."""
    merged = dict(_read_custom_nodes_file())
    merged.update({name: url for name, url, _ in _custom_nodes_from_env()})
    return [(name, url, True) for name, url in merged.items()]


def add_custom_node(name: str, url: str) -> tuple[str, str]:
    """Define (or redefine) a node by name and endpoint. Returns the stored pair."""
    name = name.strip().upper()
    if not name:
        raise ValueError("Node name must not be empty")
    base = normalize_node_url(url)
    nodes = _read_custom_nodes_file()
    nodes[name] = base
    _write_custom_nodes_file(nodes)
    return name, base


def remove_custom_node(name: str) -> bool:
    """Remove a user-defined node. Returns False if it was not defined."""
    nodes = _read_custom_nodes_file()
    if nodes.pop(name.strip().upper(), None) is None:
        return False
    _write_custom_nodes_file(nodes)
    return True


def routing_node_url(node_name: str) -> str | None:
    """Return the routing (cached) URL for a node, or None if routing does not list it."""
    for name, url, _ in load_or_refresh_cache():
        if name.upper() == node_name.upper():
            return url
    return None


# Services `consistency` relies on; probed by `add-node` to catch a wrong URL early.
PROBE_SERVICES = ("station", "dataselect", "availability")


def probe_node(base_url: str, timeout: int = 10) -> dict[str, str | None]:
    """GET each service's ``/version``. Maps service -> None if it answered, else the reason.

    A real FDSN service answers with a bare version string ("1.1.2"). A 200 is not
    enough: some hosts serve their website (HTML) for every path.
    """
    import requests

    from eida_consistency.utils.constants import USER_AGENT

    results: dict[str, str | None] = {}
    for service in PROBE_SERVICES:
        url = f"{base_url}{service}/1/version"
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        except requests.RequestException as exc:
            results[service] = type(exc).__name__
            continue
        if not resp.ok:
            results[service] = f"HTTP {resp.status_code}"
        elif not re.fullmatch(r"\d+(\.\d+)*", resp.text.strip()):
            results[service] = "not an FDSN service (no version string; got a web page?)"
        else:
            results[service] = None
    return results


def load_node_url(node_name: str) -> str:
    """Return the FDSN base URL for a given node short name.

    User-defined nodes take precedence over the routing list, so a node can be
    used (or an endpoint overridden) before EIDA routing knows about it.
    """
    key = node_name.upper()
    custom = {name: url for name, url, _ in load_custom_nodes()}
    routing = {name.upper(): url for name, url, _ in load_or_refresh_cache()}

    if key in custom:
        url = custom[key]
        if key not in routing:
            logging.info(f"Node {key}: using user-defined endpoint {url}")
        elif routing[key] == url:
            logging.info(
                f"Node {key} is now in EIDA routing with the same URL; "
                f"the user-defined entry can be removed (remove-node {key})."
            )
        else:
            logging.warning(
                f"Node {key}: using user-defined endpoint {url} "
                f"INSTEAD OF the EIDA routing endpoint {routing[key]}."
            )
        return url
    if key in routing:
        return routing[key]

    known = ", ".join(sorted(set(custom) | set(routing)))
    raise ValueError(
        f"Unknown node: {node_name}. Known nodes: {known}. Define a new one with "
        f"`eida-consistency add-node {key} <url>` or {CUSTOM_NODES_ENV}."
    )


def get_obspy_url(base_url: str) -> str:
    """Convert an FDSN base URL to plain HTTP host name for ObsPy.

    Example:
    -------
    get_obspy_url("https://eida.gein.noa.gr/fdsnws/")
    'http://eida.gein.noa.gr'

    """
    hostname = urlparse(base_url).hostname
    return f"http://{hostname}" if hostname else base_url
