# EIDA Consistency Checker
[![Run Tests](https://github.com/EIDA/eida-consistency/actions/workflows/test.yml/badge.svg)](https://github.com/EIDA/eida-consistency/actions/workflows/test.yml)
![Coverage](badges/coverage.svg)
[![Docs](https://img.shields.io/badge/docs-online-blue)](https://EIDA.github.io/eida-consistency/)

---

A tool to evaluate the consistency between EIDA nodes' **availability** and **dataselect** web services.  
Designed for use in quality control and monitoring tasks across the European Integrated Data Archive (EIDA).

📖 **Full documentation:** <https://EIDA.github.io/eida-consistency/>

---

## 🚀 Installation & Quick Start

You can use `eida-consistency` in two ways:

### Option 1: Using `uvx`

```bash
uvx eida-consistency <command> [options]
```

### Option 2: Global install

```bash
uv tool install eida-consistency
```

Now it’s available globally:

```bash
eida-consistency <command> [options]
```

Update it with:

```bash
uv tool upgrade eida-consistency
```

---

## 🔍 CLI Commands

### Run Consistency Check

Check if **availability spans** align with **dataselect** results:


```bash
uvx eida-consistency consistency --node RESIF --epochs 10 --duration 600
# OR check 5% of available stations:
uvx eida-consistency consistency --node RESIF --epochs "5%"
```

Options:
- `--node`: Node code (e.g. `RESIF`, `NOA`, `ETH`)
- `--epochs`: Number of random test epochs (default: 10) OR percentage (e.g., `"5%"`, `0.05`)
- `--duration`: Epoch length in seconds (≥600)
- `--psd` / `--no-psd`: Also check PSD (`eidaws/psd`) coverage vs dataselect (default: on)
- `--delete-old`: Keep only the most recent report
- `--stdout`: Print JSON report to stdout
- `--report-dir`: Save reports to a custom folder (default: `reports/`); works before or after the subcommand
- `--log-level`: Control verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`)

### Compare Reports

Compare two report files (e.g. a before/after pair for the same node):

```bash
uvx eida-consistency compare reports/resif_run1.json reports/resif_run2.json
```

### Explore Inconsistencies

Re-check **only the inconsistencies** of a report, drilling down day-by-day to
find their exact boundaries. With no report argument it uses the newest report;
`--index` (repeatable) targets specific findings.

```bash
uvx eida-consistency explore                 # newest report, all inconsistencies
uvx eida-consistency explore reports/noa_20260621_140111_113496.json --index 7
```

See [Re-run & Re-verify](#-re-run--re-verify) for when to use this vs `check` vs a fresh run.

### Manage Node List

Reload routing cache:

```bash
uvx eida-consistency reload-nodes
```

List currently cached nodes:

```bash
uvx eida-consistency list-nodes
```

---

## 📂 Reports

Reports are stored in `./reports/` by default, or in a custom folder using `--report-dir`.

- JSON reports: `reports/<node>_<YYYYMMDD>_<HHMMSS>_<microseconds>.json`
- Markdown reports: `reports/<node>_<YYYYMMDD>_<HHMMSS>_<microseconds>.md`
- Global summary: [`summary.md`](https://github.com/EIDA/eida-consistency/blob/main/reports/summary.md)

---

## 📚 Library Usage

You can also use `eida-consistency` as a Python library to run checks programmatically or build custom tools.

### Check a Single Candidate

```python
from eida_consistency.core.checker import check_candidate

# Define a candidate (network, station, channel, starttime)
candidate = {
    "network": "GR",
    "station": "ATH",
    "channel": "BHZ",
    "starttime": "2023-01-01T00:00:00",
}

# Run the check
results, stats = check_candidate(
    base_url="http://node.eida.eu/fdsnws",
    candidate=candidate,
    epochs=5,
    duration=600
)

for res in results:
    url, available, start, end, loc, span = res
    print(f"Time: {start} -> Available: {available}")
```

### Run a Full Consistency Check

```python
from eida_consistency.runner import run_consistency_check

# Run check for a specific node and get the report path
report_path = run_consistency_check(
    node="NOA",
    epochs=10,
    duration=600
)
print(f"Report generated at: {report_path}")
```

For full API documentation, please visit our [Documentation Site](https://EIDA.github.io/eida-consistency/) or run:

```bash
uv run mkdocs serve
```

---

## 🔁 Re-run & Re-verify

There are three distinct ways to "run it again", depending on what you want:

1. **Re-verify the findings of an existing report** — re-check only the
   inconsistencies that a report recorded, replaying each one's exact window.
   This is the right way to confirm a node-side fix:

   ```bash
   uvx eida-consistency explore reports/noa_20260621_140111_113496.json
   ```

   Add `--index N` (repeatable) to re-check specific inconsistencies only.

2. **Re-check a single stream/window** — for a one-off, targeted check:

   ```bash
   uvx eida-consistency check --node NOA --net HP --sta SERG --loc "" --cha HHZ \
       --start 2016-09-20 --end 2016-10-19
   ```

3. **Run a fresh sampled check** — draw a new random set of streams for a node:

   ```bash
   uvx eida-consistency consistency --node NOA --epochs 20 --duration 600
   ```

   > ⚠️ Passing the same `--seed` does **not** reproduce an older run once the
   > node's live inventory changes. To reproduce a *specific* finding, use option
   > 1 or 2 above, which replay the exact window rather than re-sampling.

   > ℹ️ A fresh run **cannot be limited to only inconsistent streams** — a
   > stream isn't known to be inconsistent until it's tested. Instead, the
   > report already lists them on their own under the **"Detected
   > Inconsistencies"** table, and option 1 (`explore`) re-checks **only** those
   > inconsistent streams.

---

## 🧪 Example Workflow

```bash
# 1. Run a check (reports land in reports/test_noa/)
uvx eida-consistency consistency --node NOA --epochs 20 --report-dir reports/test_noa

# 2. Re-check the inconsistencies it found (day-by-day boundaries)
uvx eida-consistency explore --report-dir reports/test_noa

# 3. Fix them at node level, then re-verify by replaying the exact windows
#    (verdict per row: PERSISTS / RESOLVED / SKIPPED; add --all for CONSISTENT/REGRESSED)
uvx eida-consistency rerun reports/test_noa/<report>.json

# 4. Compare before/after
uvx eida-consistency compare reports/test_noa/old.json reports/test_noa/new.json
```

---

## 📊 Global Consistency Summary

| Node | Epochs Requested | Epochs Usable | Total Checks | Consistent | Inconsistent | Score |
|------|------------------|---------------|--------------|------------|--------------|-------|
| [BGR](https://github.com/EIDA/eida-consistency/blob/main/reports/nodes/bgr/bgr_214412_20250908_170139.md) | 20 | 20 | 20 | 15 | 5 | 75.0 % |
| [BGS](https://github.com/EIDA/eida-consistency/blob/main/reports/nodes/bgs/bgs_173308_20250908_171621.md) | 20 | 11 | 11 | 6 | 5 | 54.55 % |
| [ETH](https://github.com/EIDA/eida-consistency/blob/main/reports/nodes/eth/eth_332194_20250908_165337.md) | 20 | 20 | 20 | 19 | 1 | 95.0 % |
| [GEOFON](https://github.com/EIDA/eida-consistency/blob/main/reports/nodes/geofon/geofon_193844_20250908_165204.md) | 20 | 20 | 20 | 20 | 0 | 100.0 % |
| [KOERI](https://github.com/EIDA/eida-consistency/blob/main/reports/nodes/koeri/koeri_859306_20250908_172726.md) | 20 | 20 | 20 | 10 | 10 | 50.0 % |
| [LMU](https://github.com/EIDA/eida-consistency/blob/main/reports/nodes/lmu/lmu_674788_20250908_170016.md) | 20 | 20 | 20 | 20 | 0 | 100.0 % |
| [NIEP](https://github.com/EIDA/eida-consistency/blob/main/reports/nodes/niep/niep_330643_20250908_171207.md) | 20 | 20 | 20 | 15 | 5 | 75.0 % |
| [NOA](https://github.com/EIDA/eida-consistency/blob/main/reports/nodes/noa/noa_596334_20250908_170412.md) | 20 | 20 | 20 | 16 | 4 | 80.0 % |
| [RESIF](https://github.com/EIDA/eida-consistency/blob/main/reports/nodes/resif/resif_478857_20250908_165731.md) | 20 | 20 | 20 | 20 | 0 | 100.0 % |
| [UIB-NORSAR](https://github.com/EIDA/eida-consistency/blob/main/reports/nodes/uib-norsar/uib-norsar_493182_20250908_173000.md) | 20 | 20 | 20 | 18 | 2 | 90.0 % |

📖 Full details: [summary.md](reports/summary.md)

---
