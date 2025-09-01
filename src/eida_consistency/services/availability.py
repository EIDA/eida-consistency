"""EIDA availability (JSON spans).

Supports both payloads:
- {"availability": [{"start": "...", "end": "...", ...}, ...]}
- {"datasources": [{"timespans": [["start","end"], ...], ...}, ...]}

Functions:
- check_availability_query() → check if a specific [start,end] is covered (legacy).
- get_availability_spans() → fetch all spans for a channel in one request (epoch-span).
"""

from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import requests


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", ""))


def _collect_spans(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize payload from availability service into a flat list of spans."""
    spans: List[Dict[str, Any]] = []

    for r in payload.get("availability", []) or []:
        if r.get("start") and r.get("end"):
            spans.append({
                "network": r.get("network"),
                "station": r.get("station"),
                "location": r.get("location"),
                "channel": r.get("channel"),
                "quality": r.get("quality"),
                "start": r["start"],
                "end": r["end"],
            })

    for ds in payload.get("datasources", []) or []:
        ds_net, ds_sta = ds.get("network"), ds.get("station")
        ds_loc, ds_cha = ds.get("location"), ds.get("channel")
        ds_qual = ds.get("quality")
        for ts in ds.get("timespans", []) or []:
            if isinstance(ts, (list, tuple)) and len(ts) >= 2 and ts[0] and ts[1]:
                spans.append({
                    "network": ds_net, "station": ds_sta, "location": ds_loc,
                    "channel": ds_cha, "quality": ds_qual,
                    "start": ts[0], "end": ts[1],
                })
    return spans


def check_availability_query(
    base_url: str,
    network: str,
    station: str,
    channel: str,
    starttime: str,
    endtime: str,
    location: str = "*",
) -> Dict[str, Any]:
    """Legacy: query availability for a specific [start,end] and see if it is covered."""
    url = (
        f"{base_url}availability/1/query?"
        f"network={network}&station={station}&location={location}&channel={channel}"
        f"&start={starttime}&end={endtime}&format=json"
    )
    logging.debug(f"Availability (query) URL: {url}")

    try:
        resp = requests.get(url, timeout=20)

        if resp.status_code == 204:
            logging.debug(f"No availability data for {network}.{station}.{location}.{channel}")
            return {"ok": False, "matched_span": None, "spans": [], "status": 204, "url": url}

        resp.raise_for_status()
    except Exception as e:
        logging.warning(f"Availability request failed: {e}")
        return {"ok": False, "matched_span": None, "spans": [], "status": 0, "url": url}

    spans: List[Dict[str, Any]] = []
    matched_span: Optional[Dict[str, Any]] = None
    ok = False

    try:
        payload = resp.json()
        spans = _collect_spans(payload)

        # Debug dump
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            try:
                pretty = json.dumps(payload, indent=2, ensure_ascii=False)
            except Exception:
                pretty = "<unserializable JSON>"
            logging.debug(
                "[AVAIL DEBUG] URL: %s\n[AVAIL DEBUG] Keys: %s\n[AVAIL DEBUG] Total spans: %d\n%s",
                url, list(payload.keys()), len(spans), pretty
            )

        e_start, e_end = _parse_iso(starttime), _parse_iso(endtime)
        for s in spans:
            try:
                s_start, s_end = _parse_iso(s["start"]), _parse_iso(s["end"])
            except Exception:
                continue
            if s_start <= e_start and s_end >= e_end:
                ok, matched_span = True, s
                break
    except Exception as e:
        logging.warning(f"Failed to parse availability JSON: {e}")

    return {"ok": ok, "matched_span": matched_span, "spans": spans, "status": resp.status_code, "url": url}


def get_availability_spans(
    base_url: str,
    network: str,
    station: str,
    channel: str,
    starttime: str,
    endtime: str,
    location: str = "*",
) -> List[Dict[str, Any]]:
    """
    Query availability once for a channel's full epoch-span and return all spans.

    Parameters
    ----------
    base_url : str
        FDSN base URL, e.g. "https://ws.resif.fr/fdsnws/"
    network, station, channel : str
        Channel identifiers.
    starttime, endtime : str
        Epoch-span (from StationXML candidate).
    location : str
        Location code filter (default "*").

    Returns
    -------
    list of dict
        Availability spans with start/end ISO strings and metadata.
    """
    url = (
        f"{base_url}availability/1/query?"
        f"network={network}&station={station}&location={location}&channel={channel}"
        f"&start={starttime}&end={endtime}&format=json"
    )
    logging.debug(f"Availability (spans) URL: {url}")

    try:
        resp = requests.get(url, timeout=30)

        if resp.status_code == 204:
            logging.debug(f"No availability data for {network}.{station}.{location}.{channel}")
            # Retry once with location="*" if we didn't already
            if location != "*":
                logging.debug(f"Retrying with location='*' for {network}.{station}.{channel}")
                return get_availability_spans(
                    base_url, network, station, channel, starttime, endtime, location="*"
                )
            return []

        resp.raise_for_status()
        payload = resp.json()
        spans = _collect_spans(payload)
        logging.debug(f"Fetched {len(spans)} spans for {network}.{station}.{channel}")
        return spans

    except Exception as e:
        logging.error(f"Failed to fetch availability spans: {e}")
        return []


# Back-compat wrapper (keeps older call sites working)
def check_availability(
    base_url: str,
    network: str,
    station: str,
    channel: str,
    starttime: str,
    endtime: str,
    return_url: bool = False,
) -> str | Tuple[str, bool] | bool:
    result = check_availability_query(
        base_url, network, station, channel, starttime, endtime, location="*"
    )
    if return_url:
        return result["url"], bool(result["ok"])
    return bool(result["ok"])
