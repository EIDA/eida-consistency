"""EIDA **dataselect** web-service.

Robust waveform fetch:
- Use ObsPy FDSN Client first (HTTPS, exact location, timeout).
- On AttributeError / client hiccups, fall back to raw HTTP GET and parse with obspy.read().
"""

from __future__ import annotations

import time
import traceback
from io import BytesIO
from urllib.parse import urlparse
from eida_consistency.utils.constants import USER_AGENT
import requests
from obspy.clients.fdsn import Client
from obspy import UTCDateTime, read


def _segments_from_stream(st) -> list:
    """Extract (start_iso, end_iso, sampling_rate) per trace; defensive."""
    segs = []
    for tr in st:
        try:
            stats = tr.stats
            start = stats.starttime
            end = stats.endtime
            start_iso = start.isoformat() if hasattr(start, "isoformat") else str(start)
            end_iso = end.isoformat() if hasattr(end, "isoformat") else str(end)
            sr = float(getattr(stats, "sampling_rate", 0.0) or 0.0)
            segs.append((start_iso, end_iso, sr))
        except Exception:
            continue
    return segs


def _endpoint_from_base(base_url: str) -> str:
    """Preserve scheme/host (e.g. https://ws.resif.fr)."""
    p = urlparse(base_url)
    scheme = p.scheme or "https"
    host = p.hostname or ""
    return f"{scheme}://{host}".rstrip("/")


def _build_query_url(endpoint: str, net: str, sta: str, loc: str, cha: str, start: str, end: str) -> str:
    return (
        f"{endpoint}/fdsnws/dataselect/1/query?"
        f"network={net}&station={sta}&location={loc}&channel={cha}"
        f"&starttime={start}&endtime={end}&nodata=204"
    )


def dataselect(
    base_url: str,
    net: str,
    sta: str,
    cha: str,
    start: str,
    end: str,
    loc: str = "",
    return_stream: bool = False,
    timeout: int = 25,
    max_attempts: int = 3,
):
    """
    Retries dataselect query up to max_attempts on transient errors.
    Returns:
        dict: {
          success, status, type, error, debug, [stream]
        }
    """
    endpoint = _endpoint_from_base(base_url)
    loc_code = (loc or "").strip()
    q1 = _build_query_url(endpoint, net, sta, loc_code, cha, start, end)

    last_error = None
    last_status = "Unknown"

    for attempt in range(1, max_attempts + 1):
        try:
            # Attempt #1 — ObsPy FDSN Client
            client = Client(endpoint, timeout=timeout, user_agent=USER_AGENT)
            st = client.get_waveforms(
                network=net,
                station=sta,
                location=loc_code,
                channel=cha,
                starttime=UTCDateTime(start),
                endtime=UTCDateTime(end),
            )
            n = len(st)
            if n == 0:
                return {
                    "success": False,
                    "status": "NoData",
                    "type": "NoTrace",
                    "error": None,
                    "debug": f"❌ No waveform data (ObsPy client).\n{q1}",
                    "segments": [],
                }
            info = "\n".join(str(tr) for tr in st)
            res = {
                "success": True,
                "status": "OK",
                "type": "MultiTrace" if n > 1 else "SingleTrace",
                "error": None,
                "debug": f"✅ Retrieved {n} trace(s) via ObsPy client.\n{info}\n{q1}",
                "segments": _segments_from_stream(st),
            }
            if return_stream:
                res["stream"] = st
            return res

        except Exception as e:
            last_error = traceback.format_exc()
            last_status = type(e).__name__
            # Fall through to raw HTTP attempt below
            pass

        # Attempt #2 — raw HTTP GET + obspy.read
        try:
            r = requests.get(q1, timeout=timeout, headers={"User-Agent": USER_AGENT})
            if r.status_code == 204 or not r.content:
                return {
                    "success": False,
                    "status": "NoData",
                    "type": "NoTrace",
                    "error": None,
                    "debug": f"❌ No waveform bytes (HTTP {r.status_code}).\n{q1}",
                    "segments": [],
                }

            if r.status_code >= 500:
                last_status = f"HTTP {r.status_code}"
                last_error = f"Server returned error {r.status_code}:\n{r.text[:500]}"
                raise requests.exceptions.RequestException(f"Server Error {r.status_code}")

            # Try to parse MiniSEED from the raw bytes
            bio = BytesIO(r.content)
            st = read(bio, format="MSEED")
            n = len(st)
            if n == 0:
                return {
                    "success": False,
                    "status": "ParseError",
                    "type": "NoTrace",
                    "error": None,
                    "debug": f"❌ Could not parse MiniSEED from HTTP bytes.\n{q1}",
                    "segments": [],
                }

            info = "\n".join(str(tr) for tr in st)
            res = {
                "success": True,
                "status": "OK",
                "type": "MultiTrace" if n > 1 else "SingleTrace",
                "error": None,
                "debug": f"✅ Retrieved {n} trace(s) via raw HTTP+read().\n{info}\n{q1}",
                "segments": _segments_from_stream(st),
            }
            if return_stream:
                res["stream"] = st
            return res

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            last_status = last_status if "HTTP" in last_status else type(e).__name__
            last_error = last_error or traceback.format_exc()
            if attempt < max_attempts:
                wait = attempt * 2  # Linear backoff: 2s, 4s
                time.sleep(wait)
                continue
        except Exception as e2:
            last_status = type(e2).__name__
            last_error = traceback.format_exc()
            # If it's a parsing error or something non-network, don't retry?
            # Actually, sometimes network glitches lead to truncated content and ParseError.
            if attempt < max_attempts:
                time.sleep(attempt)
                continue

    return {
        "success": False,
        "status": last_status,
        "type": "Error",
        "error": last_error,
        "debug": f"❌ Dataselect failed after {max_attempts} attempts.\n{q1}",
        "segments": [],
    }
