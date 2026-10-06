from datetime import date, timedelta

import pytest

from eida_consistency.core import psd_span
from eida_consistency.core.psd_span import UNKNOWN, resolve_span, run_around


def _rec(day="2026-01-06", epoch_end=None):
    r = {"network": "HP", "station": "LTHK", "location": "", "channel": "HHZ",
         "starttime": f"{day}T12:00:00", "endtime": f"{day}T12:10:00"}
    if epoch_end:
        r["channel_epoch_end"] = epoch_end
    return r


def _days(lo, hi):
    """Every day in [lo, hi) as a set."""
    out, d = set(), date.fromisoformat(lo)
    end = date.fromisoformat(hi)
    while d < end:
        out.add(d)
        d += timedelta(days=1)
    return out


def _stub(monkeypatch, *, psd, data):
    """Serve fixed day-sets, clipped to whatever window is asked for."""
    calls = []

    def fake_psd(base, n, s, c, l, lo, hi, **k):
        calls.append(("psd", lo, hi))
        return psd if psd in (None, UNKNOWN) else {d for d in psd if lo <= d < hi}

    def fake_data(base, n, s, c, l, lo, hi):
        calls.append(("data", lo, hi))
        return data if data is UNKNOWN else {d for d in data if lo <= d < hi}

    monkeypatch.setattr(psd_span, "psd_days", fake_psd)
    monkeypatch.setattr(psd_span, "data_days", fake_data)
    return calls


# --- the run itself -------------------------------------------------------

def test_run_around_finds_the_contiguous_block():
    missing = {date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3),
               date(2026, 1, 9)}                      # a separate, later run
    run = run_around(date(2026, 1, 2), missing)
    assert run == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]


def test_run_around_empty_when_the_day_is_not_missing():
    assert run_around(date(2026, 1, 5), {date(2026, 1, 1)}) == []


def test_resolves_a_multi_day_run(monkeypatch):
    data = _days("2025-12-01", "2026-03-01")
    psd = data - _days("2026-01-01", "2026-01-14")     # 13 days missing
    _stub(monkeypatch, psd=psd, data=data)
    r = resolve_span("http://node/", _rec("2026-01-06"))
    assert r["status"] == "actionable"
    assert r["start"] == date(2026, 1, 1)
    assert r["end"] == date(2026, 1, 13)
    assert r["days"] == 13


def test_resolves_an_isolated_single_day(monkeypatch):
    data = _days("2025-12-01", "2026-03-01")
    psd = data - {date(2026, 1, 6)}
    _stub(monkeypatch, psd=psd, data=data)
    r = resolve_span("http://node/", _rec("2026-01-06"))
    assert (r["status"], r["start"], r["end"], r["days"]) == \
           ("actionable", date(2026, 1, 6), date(2026, 1, 6), 1)


def test_days_without_data_neither_extend_nor_break_a_run(monkeypatch):
    # 2026-01-03/04 have no data at all, so no PSD is owed for them. They are
    # not part of the run, and they do not join the two halves either.
    data = _days("2025-12-01", "2026-03-01") - _days("2026-01-03", "2026-01-05")
    psd = data - _days("2026-01-01", "2026-01-08")
    _stub(monkeypatch, psd=psd, data=data)
    r = resolve_span("http://node/", _rec("2026-01-06"))
    assert r["start"] == date(2026, 1, 5) and r["end"] == date(2026, 1, 7)


# --- the edge check, which is the whole point -----------------------------

def test_widens_when_the_run_touches_the_window_edge(monkeypatch):
    """A 90-day run must not be reported as the 61 days that fit in ±30."""
    data = _days("2025-01-01", "2027-01-01")
    psd = data - _days("2025-11-15", "2026-02-13")     # 90 days missing
    calls = _stub(monkeypatch, psd=psd, data=data)
    r = resolve_span("http://node/", _rec("2026-01-06"))
    assert r["status"] == "actionable"
    assert r["start"] == date(2025, 11, 15)
    assert r["end"] == date(2026, 2, 12)
    assert r["days"] == 90
    assert len(calls) > 2, "should have widened rather than answered from one window"


def test_two_calls_when_the_run_closes_inside_the_window(monkeypatch):
    data = _days("2025-12-01", "2026-03-01")
    psd = data - _days("2026-01-01", "2026-01-14")
    calls = _stub(monkeypatch, psd=psd, data=data)
    resolve_span("http://node/", _rec("2026-01-06"))
    assert len(calls) == 2


def test_epoch_end_stops_the_widening(monkeypatch):
    # The run reaches the end of the channel epoch: there is nothing beyond it,
    # so that edge is real and the run is complete.
    data = _days("2025-12-01", "2026-01-21")
    psd = data - _days("2026-01-01", "2026-01-21")
    _stub(monkeypatch, psd=psd, data=data)
    r = resolve_span("http://node/", _rec("2026-01-06", epoch_end="2026-01-20T00:00:00"))
    assert r["status"] == "actionable"
    assert r["end"] == date(2026, 1, 20)


def test_gives_up_loudly_rather_than_guessing(monkeypatch):
    # Processed (one ancient PSD day, so not out-of-scope) but missing ever
    # since: the run never closes, so say so instead of reporting a clipped one.
    data = _days("2000-01-01", "2030-01-01")
    psd = {date(2000, 1, 1)}
    _stub(monkeypatch, psd=psd, data=data)
    r = resolve_span("http://node/", _rec("2026-01-06"), max_rounds=2)
    assert r["status"] == "unknown"
    assert "still open" in r["reason"]


def test_a_long_outage_is_not_mistaken_for_out_of_scope(monkeypatch):
    """Empty *in this window* is not empty *ever*.

    A 200-day outage leaves no PSD record anywhere in a ±30-day window, which
    looks exactly like a channel seedpsd never processes. Only the wide scope
    probe separates them.
    """
    data = _days("2025-01-01", "2027-01-01")
    psd = data - _days("2025-09-01", "2026-03-20")     # ~200 days missing
    _stub(monkeypatch, psd=psd, data=data)
    r = resolve_span("http://node/", _rec("2026-01-06"))
    assert r["status"] == "actionable", "a long outage must not read as out-of-scope"
    assert r["start"] == date(2025, 9, 1)
    assert r["end"] == date(2026, 3, 19)


# --- the states that are not findings -------------------------------------

def test_no_psd_record_at_any_date_is_out_of_scope(monkeypatch):
    _stub(monkeypatch, psd=set(), data=_days("2025-12-01", "2026-03-01"))
    assert resolve_span("http://node/", _rec())["status"] == "out-of-scope"


def test_404_is_no_psd_service_not_out_of_scope(monkeypatch):
    _stub(monkeypatch, psd=None, data=_days("2025-12-01", "2026-03-01"))
    assert resolve_span("http://node/", _rec())["status"] == "no-psd-service"


def test_day_with_psd_again_is_resolved_since(monkeypatch):
    data = _days("2025-12-01", "2026-03-01")
    _stub(monkeypatch, psd=data, data=data)
    assert resolve_span("http://node/", _rec())["status"] == "resolved-since"


@pytest.mark.parametrize("which", ["psd", "data"])
def test_a_failed_query_is_unknown_never_absence(monkeypatch, which):
    """The bug this module exists to avoid: a 500 read as 'no PSD'."""
    good = _days("2025-12-01", "2026-03-01")
    _stub(monkeypatch,
          psd=UNKNOWN if which == "psd" else good,
          data=UNKNOWN if which == "data" else good)
    r = resolve_span("http://node/", _rec())
    assert r["status"] == "unknown"
    assert r["status"] != "out-of-scope"


def test_no_data_now_is_not_called_resolved(monkeypatch):
    """Data that has gone missing since the report is not a fix.

    Both cases stop the finding standing, but one means seedpsd caught up and
    the other means waveform data the report saw is no longer served.
    """
    data = _days("2025-12-01", "2026-03-01") - {date(2026, 1, 6)}
    psd = data - {date(2026, 1, 7)}
    _stub(monkeypatch, psd=psd, data=data)
    assert resolve_span("http://node/", _rec("2026-01-06"))["status"] == "no-data-now"


def test_resolved_since_means_the_psd_arrived(monkeypatch):
    data = _days("2025-12-01", "2026-03-01")
    _stub(monkeypatch, psd=data, data=data)
    assert resolve_span("http://node/", _rec("2026-01-06"))["status"] == "resolved-since"
