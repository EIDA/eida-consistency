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

### list-nodes

List all configured EIDA nodes.

```bash
eida-consistency list-nodes
```
