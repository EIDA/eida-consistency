from eida_consistency.core.consistency import classify_consistency, is_transient_dataselect_failure


def test_is_transient_dataselect_failure_connection_error():
    assert is_transient_dataselect_failure(False, "ConnectionError") is True


def test_is_transient_dataselect_failure_timeout_family():
    assert is_transient_dataselect_failure(False, "ReadTimeout") is True


def test_is_transient_dataselect_failure_nodata_is_not_transient():
    assert is_transient_dataselect_failure(False, "NoData") is False


def test_classify_consistency_marks_transient_failure_as_skipped():
    result = classify_consistency(True, {"success": False, "status": "ConnectionError"})
    assert result["consistent"] is None
    assert result["scoreable"] is False
    assert result["status"] == "Skipped"


def test_classify_consistency_marks_real_mismatch_as_inconsistent():
    result = classify_consistency(True, {"success": False, "status": "NoData"})
    assert result["consistent"] is False
    assert result["scoreable"] is True
    assert result["status"] == "Inconsistent"


def test_is_transient_dataselect_failure_more_variants():
    assert is_transient_dataselect_failure(False, "HTTP 503 Service Unavailable") is True
    assert is_transient_dataselect_failure(False, "HTTP Error 500") is True
    assert is_transient_dataselect_failure(False, "ProxyError") is True
    assert is_transient_dataselect_failure(False, "SSLError") is True
    assert is_transient_dataselect_failure(False, "Remote end closed connection without response") is True
    assert is_transient_dataselect_failure(False, "Internal Server Error") is True
