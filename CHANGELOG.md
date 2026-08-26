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

### Fixed — generated reports no longer carry a broken viewer link — #50

Every generated Markdown report opened with an *Interactive view* link built
from a hard-coded relative path (`../../viewer.html`). That path is only correct
if the viewer happens to sit two levels above the rendered report page, so on a
published site it was a 404 in every report. No link is written now: where a
viewer is published, and under what names reports are served, are facts only the
publishing site has, and a site that knows its own layout can emit the link
itself — it is an `<a>` with a `?report=` parameter.

### Changed — viewer readability and colour-blind safety — #50

- The PSD verdict moves out of the triangle cell into its own sortable **PSD**
  column, in words (`✖ must fix ≥2024`, `⚠ pre-2024 gap`, `PSD without data`,
  `consistent`). Sorting is by urgency rather than alphabetical.
- The PSD filter collapses from six options to **consistent** / **inconsistent**.
  An orphan PSD counts as inconsistent; `n/a` rows (no PSD service, or a skipped
  check) belong to neither and appear only under *PSD: all*.
- Palette fixes from a colour-vision audit: light `--warn` failed WCAG AA at
  2.95:1 and is now 6.41:1; dark `--ok`/`--bad` simulated to ΔE 3.1 under
  deuteranopia (indistinguishable) and now separate at 10.2. Coverage-timeline
  gap bands carry diagonal hatching as well as a red tint, so they survive
  red-green colour vision, which flattened the tint into the track grey.

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
