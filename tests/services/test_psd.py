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


def test_psd_coverage_pads_window_by_one_day(monkeypatch):
    captured = {}
    def fake_get(url, params=None, **k):
        captured["params"] = params
        return DummyResp(status=200, text=CSV)
    monkeypatch.setattr(psd_mod.requests, "get", fake_get)
    psd_mod.psd_coverage("https://eida.example.org/fdsnws/", "HL", "ACHA", "HNZ",
                         "2024-06-02T12:00:00", "2024-06-02T12:10:00", loc="00")
    assert captured["params"]["start"] == "2024-06-01T12:00:00"  # t0 - 1 day
    assert captured["params"]["end"] == "2024-06-03T12:10:00"    # t1 + 1 day


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
