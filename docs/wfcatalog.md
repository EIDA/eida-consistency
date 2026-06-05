# WFCatalog Cross-check

An **advisory** third check that compares each tested epoch against the node's
[WFCatalog](https://github.com/EIDA/wfcatalog) service — the precomputed,
**daily** waveform-quality catalogue.

It answers a third question alongside the two standard checks:

| Service | Question | Path |
| :--- | :--- | :--- |
| `availability` | Does the node *declare* data here? | `…/fdsnws/availability/1/query` |
| `dataselect` | Can the bytes actually be *downloaded*? | `…/fdsnws/dataselect/1/query` |
| **`wfcatalog`** | Does the **quality catalogue** know about data here? | `…/eidaws/wfcatalog/1/query` |

> **It never affects the score.** WFCatalog is daily-granularity and optional, so
> it is reported as a separate, advisory signal — the score still comes from
> `availability` vs `dataselect` only.

## Usage

Add the `--with-wfcatalog` flag to a normal `consistency` run:

```bash
uv run eida-consistency --report-dir reports/example consistency \
    --node NOA --epochs 8 --duration 600 --seed 4242 --with-wfcatalog
```

### Flags used

| Flag | Scope | Meaning |
| :--- | :--- | :--- |
| `--report-dir <dir>` | group (before `consistency`) | Where to write reports |
| `--node <CODE>` | `consistency` | EIDA node code (e.g. `NOA`, `RESIF`) |
| `--epochs <n>` | `consistency` | Number of random epochs to test |
| `--duration <s>` | `consistency` | Epoch length in seconds (≥ 600) |
| `--seed <n>` | `consistency` | Random seed |
| `--with-wfcatalog` | `consistency` | **Enable the WFCatalog cross-check** (advisory) |

Without `--with-wfcatalog` the report is identical to before — zero footprint.

## The four verdicts

Each epoch gets one verdict (field `wfcatalog_verdict` in the JSON):

| Verdict | Meaning | When |
| :--- | :--- | :--- |
| `agree` | Catalogue matches dataselect | `has_data == dataselect_success` |
| `catalog-gap` | ⚠️ Data is served but the catalogue is **empty** | `dataselect=✓`, `wfcatalog=empty` |
| `day-partial` | Catalogue has data but dataselect returned none for the slice | `dataselect=✗`, `wfcatalog=✓` |
| `n/a` | Not comparable (service absent / HTTP 400 / transient) | not deployed, future date, etc. |

The `%` shown next to a verdict is the **day's** `percent_availability` from
WFCatalog (field `wfcatalog_percent`).

## How to read it

- **`agree (100%)` on an inconsistent row** (`Avail=N, DS=Y`) → dataselect *and*
  the catalogue confirm the data exists, so the fault is the **availability**
  service.
- **`catalog-gap`** → the node serves the waveform but never ingested it into
  WFCatalog (a collector/ingestion gap). This is the headline finding the
  cross-check exists to surface.
- **`day-partial (24%)`** → that day was only ~24% complete, so a 10-minute
  dataselect miss is expected — usually *not* a bug, just the daily granularity.

## Example output

Command:

```bash
uv run eida-consistency --report-dir reports/example consistency \
    --node NOA --epochs 8 --duration 600 --seed 4242 --with-wfcatalog
```

The console output is unchanged (no WFCatalog lines). WFCatalog appears only in
the report, in three places:

**1. The `WF` column of the inconsistencies table**

```
| Channel       | Window (UTC) | Avail | DS | Type        | Status | WF          |
| ME.NKME..HNZ  | 2024-02-24…  | N     | Y  | SingleTrace | OK     | catalog-gap |
```

**2. A one-line summary** (plus a `⚠️ catalog-gap` line naming the channels)

```
### WFCatalog (advisory): 7 agree · 1 catalog-gap
- ⚠️ catalog-gap: `ME.NKME..HNZ`
```

**3. One line per channel in *Detailed Results***

```
### ME.NKME..HNZ
- Availability: False
- Dataselect:   True
- Consistent:   ❌
- WFCatalog:    catalog-gap

### HL.SMTH..HHZ
- Availability: True
- Dataselect:   True
- Consistent:   ✔️
- WFCatalog:    agree (100.0%)
```

## JSON fields

When `--with-wfcatalog` is used, each result gains two fields:

```json
{
  "network": "ME", "station": "NKME", "channel": "HNZ",
  "available": false, "dataselect_success": true,
  "wfcatalog_verdict": "catalog-gap",
  "wfcatalog_percent": null
}
```

and the summary gains a compact block:

```json
"wfcatalog": {
  "counts": { "agree": 7, "catalog-gap": 1 },
  "catalog_gap_channels": ["ME.NKME..HNZ"]
}
```
