# Report viewer

An interactive HTML view of the JSON reports produced by `eida-consistency`
(issue #50). One page, `viewer.html`, in two modes:

| Mode | What it is |
|---|---|
| `viewer.html` | **Landing page** — lists the reports found in the default reports directory, and takes a report by drag-drop, file picker, or pasted URL |
| `viewer.html?report=…` | **Report view** — score gauge, PSD summary, sortable and filterable table of findings, per-record timeline, and buttons that replay each finding's exact availability/dataselect request |

Reports produced before the PSD check render the same UI as current ones — same
columns, chip row and legend. The PSD chip reads *not checked*, every PSD cell
shows `▼ ▲ ?`, and the PSD filter is disabled rather than hidden.

## No framework, no build step

Plain ES modules and hand-written CSS. There is no React/Vue/Svelte, no
bundler, no `package.json`, and no CDN or external asset of any kind — the only
imports anywhere are `node:fs` and `node:path` in `make-index.mjs`, which runs
under Node rather than in the browser. Rendering is template-literal HTML
assigned to `innerHTML`; light/dark theming is CSS custom properties.

That keeps the viewer copy-and-serve deployable: drop the directory behind any
static web server and it works.

```
viewer.html            page shell (markup + CSS)
viewer.js              browser wiring — loading, events, state
viewer.core.js         pure render/filter/sort logic (no DOM), unit-tested
viewer.core.test.mjs   62 tests, Node's built-in test runner
sample-report.json     example report, including PSD fields
make-index.mjs         build index.json — the landing page's report list
```

## Setup

The page uses ES modules and `fetch()`, so it must be served over HTTP —
opening it as `file://` will not work. Any static server will do:

```bash
# from the repository root
python3 -m http.server 8777
```

Then open:

- <http://localhost:8777/viewer/viewer.html> — landing page
- `http://localhost:8777/viewer/viewer.html?report=sample-report.json` — the
  bundled example, the quickest way to see the PSD rendering
- `http://localhost:8777/viewer/viewer.html?report=../reports/<report>.json` —
  one of your own reports

The `report` parameter is a URL resolved relative to the page, so it can also
point at another host (see *CORS* below).

### The report list

`viewer.html` looks for an `index.json` next to itself and, if it finds one,
lists those reports on the landing page — name, node, score, timestamp and
inconsistency count, newest first. Build it from your reports directory:

```bash
node viewer/make-index.mjs reports ../reports/ viewer/index.json
```

Arguments are `<reportsDir> <urlPrefix> <outFile>`. The prefix is prepended to
each filename to form the URL the browser fetches, resolved relative to
`viewer.html` — `../reports/` above points back at the repository's `reports/`
directory, so nothing has to be copied. Re-run it after new reports are
generated. `viewer/index.json` is gitignored.

With no `index.json` present the landing page still works; it just shows the
upload/paste-a-URL form on its own.

### CORS

Reports hosted elsewhere load only if that host sends permissive CORS headers.
Oculus does, so `?report=https://eida-oculus.orfeus-eu.org/consistency/...json`
works from a local copy of the viewer. If a report fails to load from another
host, this is almost always why.

The "Run availability" / "Run dataselect" buttons issue live requests to the
node's FDSN services from the browser, and depend on those services' CORS
headers in the same way.

## Tests

```bash
node --test viewer/
```

No install needed — Node's built-in test runner. `viewer.core.js` holds the
logic worth testing (filtering, sorting, URL building, timeline geometry, HTML
rendering) and has no DOM dependency; `viewer.js` is the thin browser layer.
These tests run in CI on every push and pull request via the `viewer` job in
`.github/workflows/test.yml`.

## Deploying

Copy the directory onto any static host. Two useful placements:

- **Next to the reports** (e.g. on Oculus) — no CORS concerns, and `index.json`
  can be generated alongside the published reports.
- **On the docs site** — the viewer is reachable publicly and users paste a
  report URL into it.
