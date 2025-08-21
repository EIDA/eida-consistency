# EIDA Consistency Checker
[![Run Tests](https://github.com/EIDA/eida-consistency/actions/workflows/test.yml/badge.svg)](https://github.com/EIDA/eida-consistency/actions/workflows/test.yml)
![Coverage](badges/coverage.svg)
---
A tool to evaluate the consistency between EIDA nodes' **availability** and **dataselect** web services. Designed for use in quality control and monitoring tasks across the European Integrated Data Archive (EIDA).

---

## 🔍 Features

- Fetch random epochs from the **availability** service
- Validate if corresponding waveform data is accessible via **dataselect**
- Save results as:
  - `JSON` reports (machine-readable)
  - `Markdown` summaries (human-readable)
- Compare two reports from the same seed to track changes/improvements
- Support for `MultiTrace`, `NoData`, `SingleTrace`, etc.

---

## 📦 Installation


---

## 🚀 Usage

### 1. Run Consistency Check

```bash
uv run eida-consistency consistency --node RESIF --epochs 10 --duration 60
```

Options:
- `--node`: EIDA node code (e.g. `RESIF`, `NOA`, `ETH`)
- `--epochs`: Number of random epochs to check (default: 10)
- `--duration`: Duration of each epoch in seconds (default: 600)
- `--seed`: Optional seed for reproducibility
- `--delete-old`: Optionally delete old reports

---

### 2. Compare Reports

```bash
uv run eida-consistency compare reports/RESIF_123456_10.json reports/RESIF_123456_10_v2.json
```

Outputs a markdown comparison between the two reports, showing improved or regressed entries.

---

## 📂 Output

Reports are saved in the `./reports/` folder:

- JSON reports: `reports/NOA_123456_10.json`
- Markdown reports: `reports/NOA_123456_10.md`
- Comparison summaries: `reports/compare_NOA_123456_10_vs_v2.md`

---

## 🧪 Example

```bash
uv run eida-consistency consistency --node NOA --epochs 5
uv run eida-consistency compare reports/NOA_1234_5.json reports/NOA_1234_5_v2.json
```

---

## 🧠 Notes

- `MultiTrace` responses from dataselect are considered **successful**, but marked separately.
- The same seed will always select the same candidate epochs.
- Comparison only works between reports with the same seed.

---

