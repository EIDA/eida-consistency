"""Formatter module for logging consistency-check results."""

from __future__ import annotations


def format_result(idx, url, available, ds_result, match, classification):
    original_start = match.get("starttime", "?")
    original_end = match.get("endtime", "?")

    log = [f"{idx}. {url}"]

    if available:
        line = "     Availability: ✅ (timespan covered)"
        matched_span = match.get("matched_span")
        if matched_span:
            line += f" → {matched_span['start']} → {matched_span['end']}"
        log.append(line)
    else:
        log.append("     Availability: ❌ (No availability in this timespan)")

    dataselect_status = "✅" if ds_result["success"] else f"❌ ({ds_result['status']})"
    log.append(f"     Dataselect:   {dataselect_status}")

    if classification["consistent"] is True:
        consistency_status = "✅"
    elif classification["consistent"] is False:
        consistency_status = "❌"
    else:
        consistency_status = f"⚪ ({classification['status']}: {ds_result['status']})"
    log.append(f"     Consistent:   {consistency_status}")

    for m in classification.get("mismatch", []):
        log.append(f"     Gap mismatch: {m['start']} → {m['end']}")

    log.append(f"     Epoch span: {original_start} → {original_end}")

    debug = ds_result.get("debug", "").strip()
    if debug:
        log.append(debug)

    return "\n".join(log)
