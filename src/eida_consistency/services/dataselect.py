from obspy.clients.fdsn import Client
from obspy import UTCDateTime
import traceback
from eida_consistency.utils.nodes import get_obspy_url

def dataselect(base_url, net, sta, cha, start, end, loc="", return_stream=False):
    """
    Try retrieving waveform data from dataselect service.

    Returns:
        dict with:
            - success (bool)
            - status (str)
            - error (str or None)
            - debug (str)
            - stream (optional ObsPy Stream)
    """
    try:
        # If location is empty, request all
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

        if len(st) == 0:
            return {
                "success": False,
                "status": "NoData",
                "error": None,
                "debug": f"❌ No traces returned.\n{query_url}"
            }

        trace_count = len(st)
        if trace_count > 1:
            trace_info = "\n".join(str(tr) for tr in st)
            return {
                "success": False,
                "status": "Fragmented",
                "error": None,
                "debug": f"⚠️ Multiple traces ({trace_count}) returned:\n{trace_info}\n{query_url}"
            }

        result = {
            "success": True,
            "status": "OK",
            "error": None,
            "debug": f"✅ Waveform retrieved successfully.\n{query_url}"
        }
        if return_stream:
            result["stream"] = st
        return result

    except Exception:
        return {
            "success": False,
            "status": "Exception",
            "error": traceback.format_exc(),
            "debug": f"❌ Exception during request.\n{query_url}"
        }
