"""EIDA **WFCatalog** web-service (advisory cross-check).

WFCatalog exposes precomputed *daily* waveform-quality metadata. Unlike
availability/dataselect (which live under ``/fdsnws/``), WFCatalog is served
under ``/eidaws/wfcatalog/1/query`` and only supports ``granularity=day``.

Observed behaviour (verified against ORFEUS/ODC, NOA, RESIF, GFZ):
- 200 → JSON array, one document per day, with ``percent_availability``,
        ``num_gaps``, ``num_records``, ``start_time``/``end_time`` etc.
- 204 → no metadata for the requested window (data not catalogued).
- 400 → bad request (e.g. start time in the future).
- 404 / connection error → service not deployed at this node.

Because metrics are daily, this is used only as an *advisory* signal — it tells
us whether the node's quality catalogue knows about data on the day(s) an epoch
touches. It is intentionally never folded into the pass/fail score.

Requests carry ``User-Agent = "eida-consistency"`` so operators can identify
the traffic.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from eida_consistency.utils.constants import USER_AGENT


def _wfcatalog_endpoint(base_url: str) -> str:
    """Derive the WFCatalog query URL from an fdsnws base URL.

    ``https://eida.gein.noa.gr/fdsnws/`` → ``https://eida.gein.noa.gr/eidaws/wfcatalog/1/query``
    """
    p = urlparse(base_url)
    scheme = p.scheme or "https"
    host = p.netloc or p.hostname or ""
    return f"{scheme}://{host}/eidaws/wfcatalog/1/query"


def _build_query_url(
    endpoint: str, net: str, sta: str, loc: str, cha: str, start: str, end: str
) -> str:
    loc_param = loc if loc else "--"
    return (
        f"{endpoint}?"
        f"network={net}&station={sta}&location={loc_param}&channel={cha}"
        f"&start={start}&end={end}"
        f"&granularity=day&format=json&include=default"
    )


def check_wfcatalog(
    base_url: str,
    net: str,
    sta: str,
    cha: str,
    start: str,
    end: str,
    loc: str = "",
    timeout: int = 60,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """Query WFCatalog for an epoch window and summarise the daily metadata.

    Returns a dict:
        {
          "deployed": bool,                 # False if service absent (404/conn)
          "has_data": Optional[bool],       # None if not deployed / unknown
          "percent_availability": Optional[float],  # max across overlapping days
          "num_docs": int,                  # number of daily documents returned
          "status": str,                    # OK | NoData | NotDeployed | Error | HTTP <n>
          "url": str,
        }
    """
    endpoint = _wfcatalog_endpoint(base_url)
    url = _build_query_url(endpoint, net, sta, loc, cha, start, end)
    logging.debug(f"WFCatalog URL: {url}")

    last_status = "Unknown"
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})

            if resp.status_code == 204:
                return _result(deployed=True, has_data=False, percent=None,
                               num_docs=0, status="NoData", url=url)

            # Service not present at this node — treat as advisory N/A, not an error.
            if resp.status_code == 404:
                return _result(deployed=False, has_data=None, percent=None,
                               num_docs=0, status="NotDeployed", url=url)

            if resp.status_code >= 500:
                last_status = f"HTTP {resp.status_code}"
                if attempt < max_attempts:
                    time.sleep(attempt * 2)
                    continue
                return _result(deployed=True, has_data=None, percent=None,
                               num_docs=0, status=last_status, url=url)

            if resp.status_code == 400:
                logging.debug(f"[wfcatalog] 400 Bad Request: {resp.text[:200]}")
                return _result(deployed=True, has_data=None, percent=None,
                               num_docs=0, status="HTTP 400", url=url)

            resp.raise_for_status()

            docs: List[Dict[str, Any]] = resp.json()
            if not isinstance(docs, list) or not docs:
                return _result(deployed=True, has_data=False, percent=None,
                               num_docs=0, status="NoData", url=url)

            percents = [
                float(d["percent_availability"])
                for d in docs
                if d.get("percent_availability") is not None
            ]
            percent = max(percents) if percents else None
            has_data = bool(percent and percent > 0) or any(
                (d.get("num_records") or 0) > 0 for d in docs
            )
            return _result(deployed=True, has_data=has_data, percent=percent,
                           num_docs=len(docs), status="OK", url=url)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_status = type(e).__name__
            if attempt < max_attempts:
                time.sleep(attempt * 2)
                continue
            # Persistent connection failure: most likely no WFCatalog here.
            return _result(deployed=False, has_data=None, percent=None,
                           num_docs=0, status="NotDeployed", url=url)
        except Exception as e:  # noqa: BLE001 - any parse/transport issue is advisory
            logging.debug(f"[wfcatalog] Failed ({url}): {e}")
            last_status = type(e).__name__
            if attempt < max_attempts:
                time.sleep(attempt)
                continue

    return _result(deployed=True, has_data=None, percent=None,
                   num_docs=0, status=last_status, url=url)


def _result(
    deployed: bool,
    has_data: Optional[bool],
    percent: Optional[float],
    num_docs: int,
    status: str,
    url: str,
) -> Dict[str, Any]:
    return {
        "deployed": deployed,
        "has_data": has_data,
        "percent_availability": percent,
        "num_docs": num_docs,
        "status": status,
        "url": url,
    }
