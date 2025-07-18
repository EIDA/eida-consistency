def format_result(idx, url, available, ds_result, match):
    """
    Format the result of a single consistency check for logging output.

    Args:
        idx (int): Index number of the result (1, 2, 3...).
        url (str): Availability URL used for this check.
        available (bool): True if availability said data was present.
        ds_result (dict): Result from dataselect check.
        match (dict): Original metadata candidate from inventory.

    Returns:
        str: Multiline string formatted for printing to terminal/log.
    """
    net = match["network"]
    sta = match["station"]
    cha = match["channel"]
    loc = match.get("location", "")

    original_start = match.get("starttime", "?")
    original_end = match.get("endtime", "?")

    log = [f"{idx}. {url}"]
    log.append(f"    📡 Availability: {'✅' if available else '❌'}")
    log.append(f"    📥 Dataselect:   {'✅' if ds_result['success'] else f'❌ ({ds_result['status']})'}")

    consistent = (available == ds_result['success'])
    log.append(f"    🔁 Consistent:   {'✅' if consistent else '❌'}")
    log.append(f"    Station span:    {original_start} → {original_end}")

    # Include debug output from dataselect if available
    if "debug" in ds_result and ds_result["debug"].strip():
        log.append(ds_result["debug"].rstrip())

    return "\n".join(log)
