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
*   `--seed INTEGER`: Random seed for the candidate sampling. It does **not**
    reliably reproduce an older run (a seed only selects the same streams while
    the node's inventory is unchanged); to re-verify a past finding use
    `explore`/`check`. See [Re-run & Re-verify](#re-run-re-verify).
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

## Re-run & Re-verify

There are three ways to "run it again", depending on intent:

*   **Re-verify a report's findings** — replay each recorded inconsistency's exact
    window: `eida-consistency explore <report.json>` (only inconsistencies; use
    `--index` to target specific ones).
*   **Re-check a single stream/window** — `eida-consistency check --node … --net …
    --sta … --cha … --start … --end …`.
*   **Fresh sampled run** — `eida-consistency consistency --node …`. Note that
    `--seed` does not reproduce an older run once the node's inventory changes.

### list-nodes

List all configured EIDA nodes.

```bash
eida-consistency list-nodes
```
