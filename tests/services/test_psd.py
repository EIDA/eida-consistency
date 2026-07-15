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
