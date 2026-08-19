# Changelog

## Unreleased

### Added — `rerun` command — #55

Re-verify the inconsistencies of a report against the live services, without the
boundary walk or dmtri output that `explore` produces:

```
eida-consistency rerun [REPORT] [-i N ...] [--all] [--json] [--verbose]
```

Defaults to the latest report and its inconsistent rows; `--all` re-checks every
row. Reports a verdict per row — `PERSISTS` / `RESOLVED` / `SKIPPED`, plus
`CONSISTENT` / `REGRESSED` under `--all`. Read-only (`--json` for machine
output). The report loader and window-check core are now shared with `explore`
(`reverify.py`); `explore`'s behavior is unchanged.

### Removed — seeds (breaking) — #52

The seed mechanism is removed entirely. A seed could never reliably reproduce a
run: the node's live inventory drifts over time, so the same seed selects
different channels later. Reproduce a finding instead by replaying its exact
window with `explore` or `check` (deterministic).

- `--seed` is removed from the `consistency` command. Passing it now errors
  (`No such option: --seed`) instead of warning.
- `run_consistency_check()` no longer accepts a `seed` argument.
- Reports no longer carry `summary.seed`. Use `summary.timestamp` as the audit
  anchor.
- Report filenames change the trailing seed slot to microseconds:
  `{node}_{YYYYMMDD}_{HHMMSS}_{ffffff}.{ext}`. The 4-part underscore shape and a
  numeric final field are preserved, so filename parsers keep working. The
  `.json` and `.md` of one run still share a stem (both derived from the report
  timestamp).

Old reports that still contain a `seed` field continue to load everywhere;
`compare`, `explore`, and the viewer never read it, and the multi-report
markdown regenerator shows the legacy seed only when present.

> **Note:** downstream consumers (Oculus crawler, dmtri) may parse `summary.seed`
> or the filename's seed field. Confirm with the Oculus admins before releasing.
