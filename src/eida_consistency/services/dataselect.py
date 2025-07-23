"""EIDA **dataselect** web-service.

Provides `dataselect()` to fetch waveform data via ObsPy’s
FDSN client and return a uniform result dictionary.
"""
from obspy.clients.fdsn import Client
from obspy import UTCDateTime
import traceback
from eida_consistency.utils.nodes import get_obspy_url

def dataselect(base_url, net, sta, cha, start, end, loc="", return_stream=False):
    """Try retrieving waveform data from dataselect service.

    Returns:
        dict with:
            - success (bool)
            - status (str)
            - type (str): "SingleTrace", "MultiTrace", or "NoData"
            - error (str or None)
            - debug (str)
            - stream (optional ObsPy Stream)

    """
    try:
        loc_used = loc if loc.strip() else "*"
        cleaned_url = get_obspy_url(base_url)
        query_url = (
            f"{cleaned_url}/fdsnws/dataselect/1/query?"
            f"network={net}&station={sta}&location={loc_used}&channel={cha}"
            f"&starttime={start}&endtime={end}&nodata=204"
        )

        client = Client(cleaned_url)
        st = client.get_waveforms(
            network=net,
            station=sta,
            location=loc_used,
            channel=cha,
            starttime=UTCDateTime(start),
            endtime=UTCDateTime(end)
        )

        trace_count = len(st)
        trace_info = "\n".join(str(tr) for tr in st)

        if trace_count == 0:
            return {
                "success": False,
                "status": "NoData",
                "type": "NoTrace",
                "error": None,
                "debug": f"❌ No waveform data returned.\n{query_url}"
            }

        result_type = "MultiTrace" if trace_count > 1 else "SingleTrace"

        result = {
            "success": True,
            "status": "OK",
            "type": result_type,
            "error": None,
            "debug": f"✅ Retrieved {trace_count} trace(s).\n{trace_info}\n{query_url}"
        }

        if return_stream:
            result["stream"] = st

        return result

    except Exception as e:
        return {
            "success": False,
            "status": type(e).__name__,  # e.g. FDSNNoDataException, HTTPError
            "type": "Error",
            "error": traceback.format_exc(),
            "debug": f"❌ {type(e).__name__} during request.\n{query_url}"
        }

