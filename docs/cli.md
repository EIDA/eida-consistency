# CLI Reference

The `eida-consistency` tool can be used directly from the command line.

## Basic Usage

```bash
eida-consistency --help
```

## commands

### consistency

Run the main consistency check.

```bash
eida-consistency consistency --node NOA --epochs 10 --duration 600
```

**Options:**

*   `--node TEXT`: EIDA node code (e.g., NOA, RESIF). [Required]
*   `--epochs INTEGER`: Number of random time to check. [Default: 10]
*   `--duration INTEGER`: Duration of each check in seconds (>= 600). [Default: 600]
*   `--psd / --no-psd`: Also check PSD (`eidaws/psd`) coverage vs dataselect. [Default: on]
*   `--report-dir PATH`: Directory to store reports. Accepted before the
    subcommand (`eida-consistency --report-dir DIR consistency …`) or after it
    (`eida-consistency consistency … --report-dir DIR`). [Default: `reports/`]
*   `--upload`: Upload the report to the configured S3 bucket.

### compare

Compare two existing JSON reports.

```bash
eida-consistency compare report_A.json report_B.json
```

### explore

Re-check **only the inconsistencies** of a report, drilling down day-by-day to
find their exact boundaries. Pass a report file, or omit it to use the newest
report in the report directory.

```bash
# re-check every inconsistency in the latest report
eida-consistency explore

# re-check only specific inconsistencies in a given report
eida-consistency explore reports/noa_20260621_140111_113496.json --index 0 --index 3
```

**Options:**

*   `--index INTEGER`: Index of an inconsistency to explore (repeatable; default: all).
*   `--days INTEGER`: Maximum days to explore backward/forward. [Default: 30]
*   `--verbose`: Print query URLs while exploring.
*   `--json`: Emit discovered fixes as JSON on stdout (logs stay on stderr).
*   `--report-dir PATH`: Directory to load reports from (same placement rules as above).

### rerun

Re-verify the inconsistencies of a report against the live services — no
boundary walk, no dmtri commands. Reports a verdict per row: `PERSISTS` (still
inconsistent), `RESOLVED` (now consistent), `SKIPPED` (transient dataselect
failure), plus `CONSISTENT` / `REGRESSED` when `--all` re-checks
previously-consistent rows.

```bash
eida-consistency rerun reports/noa_latest.json      # all inconsistent rows
eida-consistency rerun -i 15 reports/noa_latest.json # one specific row
eida-consistency rerun --all reports/noa_latest.json # every row
eida-consistency rerun --json reports/noa_latest.json # machine-readable stdout
```

**Options:**

*   `REPORT`: Report `.json` path or URL. Omitted → latest report in the report dir.
*   `--index, -i INTEGER`: Result index to re-run (repeatable; overrides scope).
*   `--all`: Re-verify every row, not just the inconsistent ones.
*   `--json`: Emit verdicts as JSON to stdout (logs stay on stderr).
*   `--verbose`: Print query URLs while re-running.

## Re-run & Re-verify

There are three ways to "run it again", depending on intent:

*   **Re-verify a report's findings** — replay each recorded inconsistency's exact
    window: `eida-consistency rerun <report.json>` (plain re-check), or
    `eida-consistency explore <report.json>` (drills day-by-day to the boundary).
    Use `--index` to target specific findings.
*   **Re-check a single stream/window** — `eida-consistency check --node … --net …
    --sta … --cha … --start … --end …`.
*   **Fresh sampled run** — `eida-consistency consistency --node …` (samples new
    windows; does not reproduce a specific past finding).

### list-nodes

List all configured EIDA nodes.

```bash
eida-consistency list-nodes
```
