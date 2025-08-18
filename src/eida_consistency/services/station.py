"""EIDA **station** web-service.

Fetch StationXML (level=channel) and return flat candidates:
{network, station, channel, starttime[, endtime][, location]}
"""
import logging
import requests
import xml.etree.ElementTree as ET


def fetch_candidates(base_url: str):
    url = f"{base_url}station/1/query?level=channel&format=xml&includerestricted=false&nodata=404"
    logging.debug(f"StationXML URL: {url}")

    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        logging.error(f"Failed to fetch StationXML: {e}")
        return []

    try:
        tree = ET.fromstring(resp.content)
    except Exception as e:
        logging.error(f"Failed to parse StationXML: {e}")
        return []

    ns = {'': 'http://www.fdsn.org/xml/station/1'}
    candidates, skipped = [], 0

    for network in tree.findall('Network', ns):
        net_code = network.attrib.get('code')
        for station in network.findall('Station', ns):
            sta_code = station.attrib.get('code')
            for channel in station.findall('Channel', ns):
                chan_code = channel.attrib.get('code')
                loc_code = channel.attrib.get('locationCode')
                start = channel.attrib.get('startDate')
                end = channel.attrib.get('endDate')

                if not (net_code and sta_code and chan_code and start and start.strip()):
                    skipped += 1
                    logging.debug(f"Skipping malformed: {net_code}.{sta_code}.{chan_code} start={start}")
                    continue

                entry = {
                    "network": net_code,
                    "station": sta_code,
                    "channel": chan_code,
                    "starttime": start,
                }
                if end and end.strip():
                    entry["endtime"] = end
                if loc_code and loc_code.strip():
                    entry["location"] = loc_code

                candidates.append(entry)

    logging.info(f"Total candidates fetched: {len(candidates)} (skipped: {skipped})")
    return candidates
