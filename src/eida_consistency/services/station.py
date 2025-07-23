"""EIDA **station** web-service.

Provides `fetch_candidates()` to pull network–station–channel
metadata from the StationXML endpoint and return a flat list
of candidate dictionaries.
"""
import logging
import requests
import xml.etree.ElementTree as ET

def fetch_candidates(base_url: str):
    """Fetch station-channel candidates from the StationXML.

    Args:
        base_url (str): Base FDSN URL (e.g., https://eida.gein.noa.gr/fdsnws/)

    Returns:
        List[dict]: List of candidate dictionaries.

    """
    url = f"{base_url}station/1/query?level=channel&format=xml&includerestricted=false&nodata=404"
    
    logging.debug(f"StationXML URL: {url}")

    response = requests.get(url, timeout=60)
    response.raise_for_status()

    tree = ET.fromstring(response.content)
    ns = {'': 'http://www.fdsn.org/xml/station/1'}
    candidates = []

    for network in tree.findall('Network', ns):
        net_code = network.attrib.get('code')
        for station in network.findall('Station', ns):
            sta_code = station.attrib.get('code')
            for channel in station.findall('Channel', ns):
                chan_code = channel.attrib.get('code')
                start = channel.attrib.get('startDate')
                end = channel.attrib.get('endDate')

                if not all([net_code, sta_code, chan_code, start]):
                    continue

                candidates.append({
                    "network": net_code,
                    "station": sta_code,
                    "channel": chan_code,
                    "starttime": start,
                    "endtime": end or ""
                })

    logging.info(f"Total candidates fetched: {len(candidates)}")
    return candidates
