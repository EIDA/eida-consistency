# tests/test_formatter.py
import re
import eida_consistency.core.formatter as formatter


def test_format_result_success_consistent_with_debug():
    ds_result = {"success": True, "status": 200, "debug": "extra-info"}
    match = {
        "network": "XX",
        "station": "YY",
        "channel": "ZZ",
        "location": "00",
        "starttime": "2020-01-01",
        "endtime": "2020-01-02",
    }

    out = formatter.format_result(1, "http://url", True, ds_result, match)
    # Should contain ✅ for both availability and dataselect
    assert "Availability: ✅" in out
    assert "Dataselect:   ✅" in out
    assert "Consistent:   ✅" in out
    assert "extra-info" in out
    assert out.startswith("1. http://url")


def test_format_result_failure_inconsistent_without_debug():
    ds_result = {"success": False, "status": 500}  # no debug
    match = {
        "network": "NN",
        "station": "SS",
        "channel": "CC",
        # omit location and endtime to test fallbacks
        "starttime": "?", 
    }

    out = formatter.format_result(2, "http://bad", True, ds_result, match)
    # Availability says ✅ but dataselect failed => inconsistency
    assert "Availability: ✅" in out
    assert "Dataselect:   ❌ (500)" in out
    assert "Consistent:   ❌" in out
    assert "Station span: ? → ?" in out
    # Ensure no debug line
    assert "debug" not in out.lower()


def test_format_result_both_failures_consistent():
    ds_result = {"success": False, "status": 404}
    match = {"network": "A", "station": "B", "channel": "C"}
    out = formatter.format_result(3, "urlX", False, ds_result, match)
    # Both False → consistency
    assert "Availability: ❌" in out
    assert "Dataselect:   ❌ (404)" in out
    assert "Consistent:   ✅" in out


def test_format_result_regex_structure():
    """Sanity check for multiline format using regex."""
    ds_result = {"success": True, "status": 200}
    match = {"network": "N", "station": "S", "channel": "C"}
    out = formatter.format_result(4, "some-url", True, ds_result, match)

    # 5 lines minimum (idx/url, availability, dataselect, consistent, station span)
    lines = out.splitlines()
    assert len(lines) >= 5
    # first line begins with index and URL
    assert re.match(r"^4\. some-url$", lines[0])
