# EIDA Consistency Checker

Tool to evaluate consistency between EIDA `availability` and `dataselect` services.

## 🧠 Purpose
- Verify if waveform data declared in `/availability` is actually retrievable via `/dataselect`
- Generate JSON reports
- Compute consistency scores and failure types
- Enable reproducible reruns and score comparisons
- Export reports for further analysis or integration with Oculus

## 🚀 Main Commands

- `check` → Run random epoch tests and generate report
- `rerun` → Re-execute exact same tests from a previous report
- `compare` → Compare two reports (same config only)
- `export` → Export selected results to CSV/JSON
- `--delete-old` → Keep only the latest N reports per node

## 📄 Report Format

Each report includes:
- `node`, timestamp, config
- list of test results (one per epoch/channel)
- per-network summary and overall score

## 📁 Reports

Reports are saved under `reports/` using this format:
```
<node_short>_<YYYYMMDD>_<HHMM>.json
```
Example:
```
noa_20250706_1242.json
```

## ⚖️ Score

```
score = ok_matches / availability_claims
```
Only epochs with availability=true are counted.

## 🔄 Reproducibility

Each report includes all parameters, filters, so `rerun` can repeat the same test set.

## 📌 Notes


