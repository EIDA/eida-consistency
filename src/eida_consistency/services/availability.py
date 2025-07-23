"""EIDA **availability** web-service.

Provides `check_availability()` for querying the `/availability/1/extent`
endpoint and determining whether waveform data exist for a given
network-station-channel-time window.
"""
import logging
import requests

def check_availability(
    base_url: str,
    network: str,
    station: str,
    channel: str,
    starttime: str,
    endtime: str,
    return_url: bool = False
) -> str | tuple[str, bool] | bool:
    """Query the availability service and report if data exist.

    Parameters
    ----------
    base_url : str
        FDSN base URL, e.g. ``https://eida.gein.noa.gr/fdsnws/``.
    network, station, channel : str
        Network, station and channel codes.
    starttime, endtime : str
        ISO-8601 start and end times.
    return_url : bool, optional
        If True, return a tuple ``(url, exists)``; otherwise return only
        the boolean flag. Defaults to False.

    Returns
    -------
    str or tuple[str, bool] or bool
        - When ``return_url=True``: ``(full_url, exists)``  
        - When ``return_url=False``: ``exists``  
        `exists` is True if HTTP 200 and non-empty response text.

    """
    url = (
        f"{base_url}availability/1/extent?"
        f"network={network}&station={station}&channel={channel}"
        f"&start={starttime}&end={endtime}&format=text"
    )

    try:
        response = requests.get(url, timeout=20)
        logging.debug(f"Availability query URL: {url}")
        if response.status_code == 200 and response.text.strip():
            return (url, True) if return_url else True
        return (url, False) if return_url else False
    except Exception as e:
        logging.warning(f"Request failed: {e}")
        return (url, False) if return_url else False
