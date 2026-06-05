from eida_consistency.core.consistency import (
    classify_wfcatalog,
    WF_AGREE,
    WF_CATALOG_GAP,
    WF_DAY_PARTIAL,
    WF_NA,
)


def _wf(deployed=True, has_data=True, status="OK", percent=100.0):
    return {
        "deployed": deployed,
        "has_data": has_data,
        "percent_availability": percent,
        "status": status,
    }


def test_not_deployed_is_na():
    v = classify_wfcatalog({"success": True}, _wf(deployed=False, has_data=None, status="NotDeployed"))
    assert v == WF_NA


def test_transient_is_na():
    v = classify_wfcatalog({"success": True}, _wf(has_data=None, status="HTTP 503"))
    assert v == WF_NA


def test_both_yes_is_agree():
    v = classify_wfcatalog({"success": True}, _wf(has_data=True))
    assert v == WF_AGREE


def test_both_no_is_agree():
    v = classify_wfcatalog({"success": False}, _wf(has_data=False, status="NoData", percent=None))
    assert v == WF_AGREE


def test_dataselect_yes_catalog_empty_is_gap():
    v = classify_wfcatalog({"success": True}, _wf(has_data=False, status="NoData", percent=None))
    assert v == WF_CATALOG_GAP


def test_dataselect_no_catalog_hasdata_is_day_partial():
    v = classify_wfcatalog({"success": False}, _wf(has_data=True, percent=24.0))
    assert v == WF_DAY_PARTIAL
