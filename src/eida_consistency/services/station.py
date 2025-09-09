"""EIDA **station** web-service.

Fetch StationXML (level=channel) in a staged, lightweight way:
1. Get all networks
2. Get all stations per network (parallel)
3. Pick random (network, station) pairs
4. Fetch channels for those stations
5. Pick 1 random NSLC per station

Return flat candidates:
{network, station, channel, starttime[, endtime][, location]}
"""

import logging
import random
import requests
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed


def _fetch_xml(url: str, timeout: int = 60):
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return ET.fromstring(resp.content)
    except Exception as e:
        logging.error(f"Fetch failed {url}: {e}")
        return None


def fetch_candidates(base_url: str, max_stations: int = 10, max_workers: int = 5):
    # --- Step 1: Fetch networks ---
    url = f"{base_url}station/1/query?level=network&format=xml&includerestricted=false&nodata=404"
    root = _fetch_xml(url)
    if root is None:
        return []

    ns = {"": "http://www.fdsn.org/xml/station/1"}
    networks = [net.attrib.get("code") for net in root.findall("Network", ns)]
    if not networks:
        logging.warning("No networks found.")
        return []

    # --- Step 2: Fetch stations per network ---
    sta_pairs = []
    station_urls = [
        f"{base_url}station/1/query?network={net}&level=station&format=xml&includerestricted=false&nodata=404"
        for net in networks
    ]

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_xml, u): u for u in station_urls}
        for fut in as_completed(futures):
            tree = fut.result()
            if not tree:
                continue
            for network in tree.findall("Network", ns):
                net = network.attrib.get("code")
                for station in network.findall("Station", ns):
                    sta = station.attrib.get("code")
                    if net and sta:
                        sta_pairs.append((net, sta))

    if not sta_pairs:
        logging.warning("No stations found.")
        return []

    # --- Step 3–5: keep fetching until we hit max_stations ---
    candidates = []
    attempts = 0
    while len(candidates) < max_stations and attempts < max_stations * 5:
        net, sta = random.choice(sta_pairs)
        url = (
            f"{base_url}station/1/query?network={net}&station={sta}"
            f"&level=channel&format=xml&includerestricted=false&nodata=404"
        )

        tree = _fetch_xml(url)
        if not tree:
            attempts += 1
            continue

        chans = []
        for network in tree.findall("Network", ns):
            net_code = network.attrib.get("code")
            for station in network.findall("Station", ns):
                sta_code = station.attrib.get("code")
                for channel in station.findall("Channel", ns):
                    chan_code = channel.attrib.get("code")
                    loc_code = channel.attrib.get("locationCode")
                    start = channel.attrib.get("startDate")
                    end = channel.attrib.get("endDate")
                    if not (chan_code and start):
                        continue
                    entry = {
                        "network": net_code,
                        "station": sta_code,
                        "channel": chan_code,
                        "starttime": start,
                    }
                    if end:
                        entry["endtime"] = end
                    if loc_code:
                        entry["location"] = loc_code
                    chans.append(entry)
        if chans:
            candidates.append(random.choice(chans))

        attempts += 1

    return candidates
