import eida_consistency.core.formatter as formatter


def make_match():
    return {
        "network": "XX",
        "station": "AAA",
        "channel": "HHZ",
        "location": "00",
        "starttime": "2020-01-01T00:00:00",
        "endtime": "2020-01-02T00:00:00",
    }


def test_format_result_consistent_ok():
    url = "http://fake/query"
    ds_result = {"success": True, "status": "OK", "debug": "extra-debug"}
    out = formatter.format_result(1, url, True, ds_result, make_match())

    assert url in out
    assert "Availability: ✅" in out
    assert "Dataselect:   ✅" in out
    assert "Consistent:   ✅" in out
    assert "Epoch span: 2020-01-01T00:00:00 → 2020-01-02T00:00:00" in out
    assert "extra-debug" in out


def test_format_result_inconsistent_avail_yes_ds_no():
    url = "http://fake/query"
    ds_result = {"success": False, "status": "NoData", "debug": ""}
    out = formatter.format_result(2, url, True, ds_result, make_match())

    assert "Availability: ✅" in out
    assert "Dataselect:   ❌ (NoData)" in out
    assert "Consistent:   ❌" in out


def test_format_result_inconsistent_avail_no_ds_yes():
    url = "http://fake/query"
    ds_result = {"success": True, "status": "OK", "debug": ""}
    out = formatter.format_result(3, url, False, ds_result, make_match())

    assert "Availability: ❌" in out
    assert "Dataselect:   ✅" in out
    assert "Consistent:   ❌" in out


def test_format_result_with_missing_location_and_times():
    url = "http://fake/query"
    ds_result = {"success": False, "status": "Error", "debug": ""}
    match = {
        "network": "YY",
        "station": "BBB",
        "channel": "EHN",
        # no location, no endtime
        "starttime": "2020-05-01T00:00:00",
    }
    out = formatter.format_result(4, url, False, ds_result, match)

    assert "Epoch span: 2020-05-01T00:00:00 → ?" in out
    assert "Availability: ❌" in out
    assert "Dataselect:   ❌ (Error)" in out


def test_format_result_with_matched_span_includes_start_end():
    """Ensure matched_span start/end are appended when present in match dict."""
    url = "http://fake/query"
    ds_result = {"success": True, "status": "OK", "debug": ""}
    match = make_match()
    match["matched_span"] = {
        "start": "2020-01-01T01:00:00",
        "end": "2020-01-01T02:00:00",
    }

    out = formatter.format_result(5, url, True, ds_result, match)

    assert "2020-01-01T01:00:00" in out
    assert "2020-01-01T02:00:00" in out
