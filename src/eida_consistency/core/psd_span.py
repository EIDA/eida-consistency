"""Resolve a PSD finding into the full run of days it belongs to.

A PSD finding names one day. What a repair needs is the whole contiguous run of
days that have waveform data but no PSD, so it can be fixed in one pass instead
of one per day.

No day-by-day walk is needed. Both services answer range queries, so two
requests cover any span:

* ``eidaws/psd/1/coverage``    -> which days have a valid PSD record
* ``fdsnws/availability/1/query`` -> which days have waveform data

The per-day arithmetic happens here, on the responses. Contrast the
availability/dataselect boundary walk in ``explorer``, which must probe each day
separately because "was this window consistent?" is only answerable per window.

The run is only reported once it is closed by an observed non-missing day at
both ends. A run touching the edge of the queried window has not been measured,
only clipped -- so the window widens and the question is asked again. Without
that check a 90-day outage queried over 30 days reports 30 days, the repair
covers a third of it, and everything claims success.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional, Set

import requests

from eida_consistency.services.availability import _availability_request
from eida_consistency.services.psd import _endpoint_from_base, _parse_psd_csv
from eida_consistency.utils.constants import USER_AGENT

#: How far either side of the finding to look first. Nearly every run closes
#: well inside this; widening is the exception, not the rule.
DEFAULT_HALF_WINDOW_DAYS = 30
#: How many times to widen before giving up and saying so.
MAX_WIDEN_ROUNDS = 4

#: Sentinel for "the query failed" -- never conflated with "there is nothing".
UNKNOWN = object()

#: Bounds for the "is this channel processed at all?" probe. Only used when a
#: window comes back empty, to tell a long outage from a channel seedpsd never
#: touches. /coverage is cheap even across decades (~16 s for 12 years).
SCOPE_LO = date(2000, 1, 1)
SCOPE_HI = date(2100, 1, 1)


def _iso(d: date) -> str:
    return f"{d.isoformat()}T00:00:00"


def psd_days(base_url, net, sta, cha, loc, lo: date, hi: date, timeout: int = 90):
    """Days in [lo, hi) holding a *valid* PSD record.

    Returns a set, ``None`` when the node runs no PSD service (HTTP 404), or
    :data:`UNKNOWN` when the query failed. An empty set means the service
    answered and had nothing -- which is what marks a channel out of scope.
    The end is padded by two days because a PSD day file runs a little past
    midnight and the service matches records by containment, not overlap.
    """
    url = f"{_endpoint_from_base(base_url)}/eidaws/psd/1/coverage"
    params = {"net": net, "sta": sta, "loc": loc or "--", "cha": cha,
              "start": _iso(lo), "end": _iso(hi + timedelta(days=2))}
    try:
        r = requests.get(url, params=params, timeout=timeout,
                         headers={"User-Agent": USER_AGENT})
    except requests.exceptions.RequestException as e:
        logging.debug(f"[psd-span] coverage request failed: {e}")
        return UNKNOWN
    if r.status_code == 404:
        return None
    if r.status_code == 204 or not r.text.strip():
        return set()
    if r.status_code != 200:
        logging.debug(f"[psd-span] coverage HTTP {r.status_code}")
        return UNKNOWN
    return {date.fromisoformat(s[:10]) for s, _e, _sr, valid in _parse_psd_csv(r.text) if valid}


def data_days(base_url, net, sta, cha, loc, lo: date, hi: date):
    """Days in [lo, hi) with waveform data, or :data:`UNKNOWN` on failure.

    One request; the spans it returns are expanded to days here. Deliberately
    not ``get_availability_spans``, which returns ``[]`` for both "no data" and
    "the request blew up" -- a distinction this module has to keep.
    """
    try:
        resp, _url = _availability_request(
            base_url, net, sta, cha, _iso(lo), _iso(hi), loc or "*")
    except requests.exceptions.RequestException as e:
        logging.debug(f"[psd-span] availability request failed: {e}")
        return UNKNOWN
    if resp.status_code == 204:
        return set()
    if resp.status_code != 200:
        logging.debug(f"[psd-span] availability HTTP {resp.status_code}")
        return UNKNOWN
    out: Set[date] = set()
    for line in resp.text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            d = date.fromisoformat(parts[-2][:10])
            end = date.fromisoformat(parts[-1][:10])
        except ValueError:
            continue
        while d <= end and d < hi:
            out.add(d)
            d += timedelta(days=1)
    return out


def run_around(day: date, missing: Set[date]) -> list:
    """The contiguous block of missing days containing `day`."""
    if day not in missing:
        return []
    run = [day]
    d = day - timedelta(days=1)
    while d in missing:
        run.insert(0, d)
        d -= timedelta(days=1)
    d = day + timedelta(days=1)
    while d in missing:
        run.append(d)
        d += timedelta(days=1)
    return run


def resolve_span(
    base_url: str,
    record: Dict[str, Any],
    half_window: int = DEFAULT_HALF_WINDOW_DAYS,
    max_rounds: int = MAX_WIDEN_ROUNDS,
) -> Dict[str, Any]:
    """Resolve one PSD finding to its full run.

    ``status`` is one of:

    ``actionable``      the run, as inclusive ``start``/``end`` dates
    ``resolved-since``  the day has a PSD now -- either seedpsd produced it
                        since the report, or the report's reading was wrong
    ``no-data-now``     the day reports no waveform data any more, so no PSD is
                        owed. Not a fix: what the report saw has gone
    ``out-of-scope``    the channel has no PSD record at any date
    ``no-psd-service``  the node serves no PSD at all
    ``unknown``         a query failed; deliberately never reported as absence
    """
    net, sta = record["network"], record["station"]
    cha, loc = record["channel"], record.get("location", "")
    day = date.fromisoformat(str(record["starttime"])[:10])

    epoch_end = record.get("channel_epoch_end")
    hard_hi = date.fromisoformat(str(epoch_end)[:10]) + timedelta(days=1) if epoch_end else None

    # Geometric, not linear. Adding a fixed step means a multi-year run needs
    # dozens of rounds; quadrupling reaches ~21 years in four. Historical
    # channels really do have runs that long.
    reach = half_window
    lo = day - timedelta(days=reach)
    hi = day + timedelta(days=reach + 1)
    for _round in range(max_rounds):
        if hard_hi and hi > hard_hi:
            hi = hard_hi
        psd = psd_days(base_url, net, sta, cha, loc, lo, hi)
        if psd is UNKNOWN:
            return {"status": "unknown", "reason": "psd coverage query failed"}
        if psd is None:
            return {"status": "no-psd-service"}
        if not psd:
            # Nothing in *this window* does not mean nothing ever: an outage
            # longer than the window looks exactly like a channel that is not
            # processed at all. Only a wide query can tell those apart.
            wide = psd_days(base_url, net, sta, cha, loc, SCOPE_LO, SCOPE_HI)
            if wide is UNKNOWN:
                return {"status": "unknown", "reason": "psd scope query failed"}
            if wide is None:
                return {"status": "no-psd-service"}
            if not wide:
                return {"status": "out-of-scope"}
            psd = wide            # processed, just not anywhere near this day

        data = data_days(base_url, net, sta, cha, loc, lo, hi)
        if data is UNKNOWN:
            return {"status": "unknown", "reason": "availability query failed"}

        missing = {d for d in data if d not in psd}
        run = run_around(day, missing)
        if not run:
            # Two very different reasons the finding no longer stands, and they
            # must not share a name: the PSD was produced, or the waveform data
            # the report saw is no longer being served.
            if day not in data:
                return {"status": "no-data-now"}
            return {"status": "resolved-since"}

        # A run touching the edge has been clipped, not measured -- unless the
        # edge is the channel epoch, where there is genuinely nothing beyond.
        open_low = run[0] <= lo
        open_high = run[-1] >= hi - timedelta(days=1) and not (hard_hi and hi >= hard_hi)
        if not open_low and not open_high:
            return {"status": "actionable", "start": run[0], "end": run[-1], "days": len(run)}
        reach *= 4
        if open_low:
            lo = day - timedelta(days=reach)
        if open_high:
            hi = day + timedelta(days=reach + 1)

    return {"status": "unknown", "reason": f"run still open after {max_rounds} widenings"}
