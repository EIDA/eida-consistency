import json
import logging
import requests
from pathlib import Path
from urllib.parse import urlparse
from appdirs import user_cache_dir

# Constants
ROUTING_URL = "https://www.orfeus-eu.org/eidaws/routing/1/globalconfig?format=fdsn"
CACHE_FILE = Path(user_cache_dir("eida_consistency")) / "nodes_cache.json"

# Hardcoded fallback list
DEFAULT_NODES = [
    ("GFZ", "https://geofon.gfz.de/fdsnws/", True),
    ("ODC", "https://orfeus-eu.org/fdsnws/", True),
    ("ETHZ", "https://eida.ethz.ch/fdsnws/", True),
    ("RESIF", "https://ws.resif.fr/fdsnws/", True),
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

def ensure_cache_dir():
    """Ensure the cache directory exists."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

def refresh_cache_from_routing():
    """Try to refresh nodes from the routing service."""
    try:
        print("Fetching node list from routing service...")
        response = requests.get(ROUTING_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        nodes = []

        for node in data.get("datacenters", []):
            name = node.get("name")
            fdsnws_url = None
            for repo in node.get("repositories", []):
                for service in repo.get("services", []):
                    if service["name"] == "fdsnws-station-1":
                        fdsnws_url = service["url"]
                        break
                if fdsnws_url:
                    break
            if fdsnws_url:
                parsed = urlparse(fdsnws_url)
                base = f"{parsed.scheme}://{parsed.netloc}/fdsnws/"
                nodes.append((name, base, True))

        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"nodes": nodes}, f)
        return nodes

    except Exception as e:
        raise RuntimeError(f"Failed to fetch routing data: {e}")

def load_or_refresh_cache():
    """Load cached nodes or refresh from routing if unavailable."""
    ensure_cache_dir()
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                nodes = json.load(f).get("nodes", [])
                if all(isinstance(n, list) and len(n) == 3 for n in nodes):
                    return nodes
        except Exception:
            print("Cache invalid or corrupt. Re-fetching...")
            CACHE_FILE.unlink()

    try:
        return refresh_cache_from_routing()
    except Exception as e:
        logging.warning(f"Routing failed: {e}")
        return DEFAULT_NODES

def load_node_url(node_name: str) -> str:
    """Given a short node name (e.g. NOA), return its base URL."""
    nodes = load_or_refresh_cache()
    for name, base_url, _ in nodes:
        if name.upper() == node_name.upper():
            return base_url
    raise ValueError(f"Unknown node: {node_name}")
def get_obspy_url(base_url: str) -> str:
    """
    Convert a FDSN base_url (typically from routing service or cache) to a
    plain HTTP base URL suitable for ObsPy's FDSN Client.

    This:
    - Ensures HTTP (not HTTPS) since ObsPy defaults are hardcoded to HTTP.
    - Removes any subpaths (like /fdsnws/ or /fdsnws/dataselect/1).
    
    Example:
        Input:  https://eida.gein.noa.gr/fdsnws/
        Output: http://eida.gein.noa.gr
    """
    parsed = urlparse(base_url)
    hostname = parsed.hostname
    return f"http://{hostname}" if hostname else base_url
