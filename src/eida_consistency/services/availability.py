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
    """
    Check if availability data exists for a given time window.
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
