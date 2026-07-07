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
*   `--upload`: Upload the report to the configured S3 bucket.

### compare

Compare two existing JSON reports.

```bash
eida-consistency compare report_A.json report_B.json
```

### explore

Explore the boundaries of inconsistent data found in a report.

```bash
eida-consistency explore --index 0
```

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

### list-nodes

List all configured EIDA nodes.

```bash
eida-consistency list-nodes
```
