from eida_consistency.services import psd

CSV = (
    "Network,Station,Location,Channel,Sampling rate,Start time,End time,Is valid,Last update\n"
    "HL,ACHA,00,HNZ,200.0,2024-06-02T00:00:00.070000Z,2024-06-03T00:00:00Z,True,2024-12-09T07:07:02Z\n"
    "HL,ACHA,00,HNZ,200.0,2024-06-03T00:00:01.750000Z,2024-06-04T00:00:00.515000Z,False,2024-12-09T07:08:28Z\n"
)


def test_parse_psd_csv_extracts_rows_and_validity():
    rows = psd._parse_psd_csv(CSV)
    assert len(rows) == 2
    assert rows[0][0] == "2024-06-02T00:00:00.070000Z"
    assert rows[0][3] is True
    assert rows[1][3] is False


def test_parse_psd_csv_empty_returns_empty():
    assert psd._parse_psd_csv("") == []
    assert psd._parse_psd_csv("Network,Station,Location,Channel,Sampling rate,Start time,End time,Is valid,Last update\n") == []


def test_day_covered_true_when_valid_record_covers_slice_day():
    rows = psd._parse_psd_csv(CSV)
    # slice inside 2024-06-02
    assert psd._day_covered(rows, "2024-06-02T12:00:00", "2024-06-02T12:10:00") is True


def test_day_covered_false_when_only_invalid_record_on_that_day():
    rows = psd._parse_psd_csv(CSV)
    # 2024-06-03 record is Is valid=False
    assert psd._day_covered(rows, "2024-06-03T12:00:00", "2024-06-03T12:10:00") is False


def test_day_covered_false_when_no_record():
    assert psd._day_covered([], "2024-06-02T12:00:00", "2024-06-02T12:10:00") is False


from eida_consistency.services import psd as psd_mod


class DummyResp:
    def __init__(self, status=200, text="", content_type="text/plain; charset=utf8"):
        self.status_code = status
        self.text = text
        self.url = "https://eida.example.org/eidaws/psd/1/coverage?net=HL"
        self.headers = {"content-type": content_type}


def test_psd_coverage_ok_returns_records_and_day_covered(monkeypatch):
    monkeypatch.setattr(psd_mod.requests, "get",
                        lambda *a, **k: DummyResp(status=200, text=CSV))
    res = psd_mod.psd_coverage("https://eida.example.org/fdsnws/", "HL", "ACHA",
                               "HNZ", "2024-06-02T12:00:00", "2024-06-02T12:10:00", loc="00")
    assert res["success"] is True
    assert res["status"] == "OK"
    assert res["day_covered"] is True
    assert "eidaws/psd/1/coverage" in res["url"]


def test_psd_coverage_204_is_nodata(monkeypatch):
    monkeypatch.setattr(psd_mod.requests, "get",
                        lambda *a, **k: DummyResp(status=204, text="", content_type="text/html"))
    res = psd_mod.psd_coverage("https://eida.example.org/fdsnws/", "HL", "X", "HHZ",
                               "2024-06-02T12:00:00", "2024-06-02T12:10:00")
    assert res["success"] is True
    assert res["status"] == "NoData"
    assert res["day_covered"] is False


def test_psd_coverage_404_is_unsupported(monkeypatch):
    monkeypatch.setattr(psd_mod.requests, "get",
                        lambda *a, **k: DummyResp(status=404, text='{"code":404}', content_type="application/json"))
    res = psd_mod.psd_coverage("https://eida.example.org/fdsnws/", "HL", "X", "HHZ",
                               "2024-06-02T12:00:00", "2024-06-02T12:10:00")
    assert res["success"] is False
    assert res["status"] == "Unsupported"


def test_psd_coverage_queries_the_whole_utc_day(monkeypatch):
    # SeedPSD can answer 204 for one narrow time window even though the day's
    # file processed fine, so the query covers the window's whole day instead.
    captured = {}
    def fake_get(url, params=None, **k):
        captured["params"] = params
        return DummyResp(status=200, text=CSV)
    monkeypatch.setattr(psd_mod.requests, "get", fake_get)
    psd_mod.psd_coverage("https://eida.example.org/fdsnws/", "HL", "ACHA", "HNZ",
                         "2024-06-02T12:00:00", "2024-06-02T12:10:00", loc="00")
    assert captured["params"]["start"] == "2024-06-02T00:00:00"
    assert captured["params"]["end"] == "2024-06-04T00:00:00"


def test_psd_day_query_is_24h_wherever_the_window_sits(monkeypatch):
    # A window minutes before midnight must still ask for its own whole day --
    # padding +-12h around the window would drift into the next day and could
    # miss a short record sitting early in this one.
    captured = {}
    monkeypatch.setattr(psd_mod.requests, "get",
                        lambda url, params=None, **k: captured.update(params=params) or DummyResp(status=200, text=CSV))
    psd_mod.psd_coverage("https://eida.example.org/fdsnws/", "HL", "ACHA", "HNZ",
                         "2024-06-02T23:50:00", "2024-06-02T23:59:00", loc="00")
    assert captured["params"]["start"] == "2024-06-02T00:00:00"
    assert captured["params"]["end"] == "2024-06-04T00:00:00"


def test_psd_day_query_end_clears_a_record_that_spills_past_midnight(monkeypatch):
    """The service matches by containment, not overlap.

    A day file runs a second or so past midnight, e.g. the real HL.VLI..HHZ
    record 2026-06-02T00:00:05.31Z -> 2026-06-03T00:00:02.50Z. Asking for
    exactly [Jun 2, Jun 3) excludes it and the day looks like it has no PSD.
    The end must clear the spill; the start still excludes the previous day.
    """
    captured = {}
    monkeypatch.setattr(psd_mod.requests, "get",
                        lambda url, params=None, **k: captured.update(params=params) or DummyResp(status=200, text=CSV))
    psd_mod.psd_coverage("https://eida.example.org/fdsnws/", "HL", "VLI", "HHZ",
                         "2026-06-02T12:00:00", "2026-06-02T12:10:00")
    lo, hi = captured["params"]["start"], captured["params"]["end"]
    rec_start, rec_end = "2026-06-02T00:00:05", "2026-06-03T00:00:02"
    assert lo <= rec_start and rec_end <= hi, "target day's record must be contained"
    prev_start = "2026-06-01T00:00:01"
    assert prev_start < lo, "previous day's record must still fall outside"


def test_psd_day_query_spans_both_days_across_midnight(monkeypatch):
    captured = {}
    monkeypatch.setattr(psd_mod.requests, "get",
                        lambda url, params=None, **k: captured.update(params=params) or DummyResp(status=200, text=CSV))
    psd_mod.psd_coverage("https://eida.example.org/fdsnws/", "HL", "ACHA", "HNZ",
                         "2024-06-02T23:55:00", "2024-06-03T00:05:00", loc="00")
    assert captured["params"]["start"] == "2024-06-02T00:00:00"
    assert captured["params"]["end"] == "2024-06-05T00:00:00"


def test_psd_coverage_timeout_is_transient(monkeypatch):
    def boom(*a, **k):
        raise psd_mod.requests.exceptions.Timeout("slow")
    monkeypatch.setattr(psd_mod.requests, "get", boom)
    monkeypatch.setattr(psd_mod.time, "sleep", lambda *_: None)
    res = psd_mod.psd_coverage("https://eida.example.org/fdsnws/", "HL", "ACHA", "HNZ",
                               "2024-06-02T12:00:00", "2024-06-02T12:10:00", max_attempts=2)
    assert res["success"] is False
    assert res["status"] != "Unsupported"
    assert res["day_covered"] is False


def test_psd_coverage_5xx_exhaustion_keeps_full_url_with_query(monkeypatch):
    monkeypatch.setattr(psd_mod.requests, "get",
                        lambda *a, **k: DummyResp(status=503, text="Service Unavailable"))
    monkeypatch.setattr(psd_mod.time, "sleep", lambda *_: None)
    res = psd_mod.psd_coverage("https://eida.example.org/fdsnws/", "HL", "ACHA", "HNZ",
                               "2024-06-02T12:00:00", "2024-06-02T12:10:00", max_attempts=3)
    assert res["success"] is False
    assert res["status"] != "Unsupported"
    assert "net=" in res["url"]
    assert "coverage?" in res["url"]
