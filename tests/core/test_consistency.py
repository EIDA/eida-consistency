from eida_consistency.core.consistency import (
    classify_consistency, is_transient_dataselect_failure, classify_psd,
)

WINDOW = ("2020-01-09T23:55:00", "2020-01-10T00:05:00")


def span(start, end, sr="100.0"):
    return {"start": start, "end": end, "samplerate": sr}


# --- transient detection unchanged ---
def test_is_transient_connection_error():
    assert is_transient_dataselect_failure(False, "ConnectionError") is True

def test_is_transient_nodata_is_not_transient():
    assert is_transient_dataselect_failure(False, "NoData") is False

def test_is_transient_more_variants():
    assert is_transient_dataselect_failure(False, "HTTP 503 Service Unavailable") is True
    assert is_transient_dataselect_failure(False, "HTTP Error 500") is True
    assert is_transient_dataselect_failure(False, "ProxyError") is True
    assert is_transient_dataselect_failure(False, "SSLError") is True
    assert is_transient_dataselect_failure(False, "Internal Server Error") is True


# --- classification (scenarios 2,3,6,8,12,13) ---
def test_transient_failure_skipped():                         # scenario 12
    r = classify_consistency([], {"success": False, "status": "ConnectionError", "segments": []}, WINDOW)
    assert r["consistent"] is None
    assert r["scoreable"] is False
    assert r["status"] == "Skipped"

def test_identical_midnight_split_is_consistent():            # scenario 2 (#41)
    spans = [span("2020-01-09T23:55:00", "2020-01-09T23:59:59"),
             span("2020-01-10T00:00:00", "2020-01-10T00:05:00")]
    ds = {"success": True, "status": "OK", "segments": [
        ("2020-01-09T23:55:00", "2020-01-09T23:59:59", 100.0),
        ("2020-01-10T00:00:00", "2020-01-10T00:05:00", 100.0)]}
    r = classify_consistency(spans, ds, WINDOW)
    assert r["consistent"] is True
    assert r["status"] == "Consistent"
    assert r["mismatch"] == []

def test_big_shared_gap_is_consistent():                      # scenario 3
    spans = [span("2020-01-09T23:55:00", "2020-01-09T23:58:00"),
             span("2020-01-10T00:01:00", "2020-01-10T00:05:00")]
    ds = {"success": True, "status": "OK", "segments": [
        ("2020-01-09T23:55:00", "2020-01-09T23:58:00", 100.0),
        ("2020-01-10T00:01:00", "2020-01-10T00:05:00", 100.0)]}
    assert classify_consistency(spans, ds, WINDOW)["consistent"] is True

def test_availability_has_data_dataselect_empty_is_inconsistent():  # scenario 8
    spans = [span("2020-01-09T23:55:00", "2020-01-10T00:05:00")]
    ds = {"success": False, "status": "NoData", "segments": []}
    r = classify_consistency(spans, ds, WINDOW)
    assert r["consistent"] is False
    assert r["status"] == "Inconsistent"
    assert len(r["mismatch"]) == 1

def test_both_empty_is_consistent():                          # scenario 6 / restricted (16)
    r = classify_consistency([], {"success": False, "status": "NoData", "segments": []}, WINDOW)
    assert r["consistent"] is True

def test_dataselect_hole_records_location():                  # scenario 4
    spans = [span("2020-01-09T23:55:00", "2020-01-10T00:05:00")]
    ds = {"success": True, "status": "OK", "segments": [
        ("2020-01-09T23:55:00", "2020-01-09T23:58:00", 100.0),
        ("2020-01-10T00:01:00", "2020-01-10T00:05:00", 100.0)]}
    r = classify_consistency(spans, ds, WINDOW)
    assert r["consistent"] is False
    assert r["mismatch"][0]["start"].startswith("2020-01-09T23:58:00")
    assert r["mismatch"][0]["end"].startswith("2020-01-10T00:01:00")


# --- each mismatch is tagged with which side has the data ("who") ---
def test_mismatch_who_is_availability_when_dataselect_empty():
    spans = [span("2020-01-09T23:55:00", "2020-01-10T00:05:00")]
    ds = {"success": False, "status": "NoData", "segments": []}
    r = classify_consistency(spans, ds, WINDOW)
    assert r["mismatch"][0]["who"] == "availability"

def test_mismatch_who_is_dataselect_when_availability_missing():
    spans = []  # availability has nothing
    ds = {"success": True, "status": "OK", "segments": [
        ("2020-01-09T23:56:00", "2020-01-10T00:04:00", 100.0)]}
    r = classify_consistency(spans, ds, WINDOW)
    assert r["consistent"] is False
    assert r["mismatch"][0]["who"] == "dataselect"


def test_classify_returns_clipped_coverage_for_timeline():
    spans = [span("2020-01-09T23:55:00", "2020-01-10T00:05:00")]
    ds = {"success": True, "status": "OK", "segments": [
        ("2020-01-09T23:56:00", "2020-01-10T00:04:00", 100.0)]}
    r = classify_consistency(spans, ds, WINDOW)
    assert r["coverage"]["availability"][0][0].startswith("2020-01-09T23:55:00")
    assert r["coverage"]["availability"][0][1].startswith("2020-01-10T00:05:00")
    assert r["coverage"]["dataselect"][0][0].startswith("2020-01-09T23:56:00")
    assert r["coverage"]["dataselect"][0][1].startswith("2020-01-10T00:04:00")


# --- classify_psd (dataselect vs PSD day-coverage) ---
W2024 = ("2024-06-02T12:00:00", "2024-06-02T12:10:00")
W2015 = ("2015-06-02T12:00:00", "2015-06-02T12:10:00")


def ds(success=True, status="OK", segs=1):
    return {"success": success, "status": status,
            "segments": [("2024-06-02T12:00:00", "2024-06-02T12:10:00", 200.0)] * segs}


def psd(status="OK", success=True, day=True):
    return {"success": success, "status": status, "day_covered": day, "records": []}


def test_classify_psd_consistent_when_data_and_psd_present():
    r = classify_psd(ds(), psd(day=True), W2024)
    assert r["consistent"] is True
    assert r["status"] == "Consistent"
    assert r["d_present"] is True and r["p_present"] is True
    assert r["psd_required"] is True


def test_classify_psd_inconsistent_data_but_no_psd():
    r = classify_psd(ds(), psd(day=False), W2024)
    assert r["consistent"] is False
    assert r["status"] == "Inconsistent"


def test_classify_psd_psd_only_is_not_a_fault():
    # dataselect empty (ground truth), psd present -> nothing to fault
    r = classify_psd(ds(success=False, status="NoData", segs=0), psd(day=True), W2024)
    assert r["consistent"] is True


def test_classify_psd_unsupported():
    r = classify_psd(ds(), psd(status="Unsupported", success=False), W2024)
    assert r["status"] == "Unsupported"
    assert r["scoreable"] is False
    assert r["consistent"] is None


def test_classify_psd_transient_is_skipped():
    r = classify_psd(ds(), psd(status="Timeout", success=False), W2024)
    assert r["status"] == "Skipped"
    assert r["scoreable"] is False


def test_classify_psd_required_flag_false_pre_2024():
    r = classify_psd(ds(), psd(day=False), W2015)
    assert r["psd_required"] is False
    assert r["consistent"] is False  # still reported, scoring deferred


def test_classify_psd_unknown_failure_is_skipped_not_a_finding():
    # Exotic non-transient, non-Unsupported PSD failure (e.g. requests' InvalidURL)
    # must not be reported as a data-but-no-PSD inconsistency.
    r = classify_psd(ds(), psd(status="InvalidURL", success=False, day=False), W2024)
    assert r["status"] == "Skipped"
    assert r["scoreable"] is False
    assert r["consistent"] is None
