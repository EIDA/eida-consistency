# Report viewer

An interactive HTML view of the JSON reports produced by `eida-consistency`
(issue #50). Two pages, both reading the same report format:

| Page | What it shows |
|---|---|
| `viewer.html` | Report browser — score gauge, sortable/filterable table of findings, per-record timeline, and buttons that replay each finding's exact availability/dataselect request |
| `dashboard.html` | Compact instrument panel — A/D and PSD scores, per-day timeline, and the Availability/Dataselect/PSD consistency triangle |

## No framework, no build step

Plain ES modules and hand-written CSS. There is no React/Vue/Svelte, no
bundler, no `package.json`, and no CDN or external asset of any kind — the only
imports anywhere are `node:fs` and `node:path` in the two manifest builders,
which run under Node rather than in the browser. Rendering is template-literal
HTML assigned to `innerHTML`; light/dark theming is CSS custom properties.

That keeps the viewer copy-and-serve deployable: drop the directory behind any
static web server and it works.

```
viewer.html            page shell (markup + CSS) for the report browser
viewer.js              browser wiring — loading, events, state
viewer.core.js         pure render/filter/sort logic (no DOM), unit-tested
viewer.core.test.mjs   61 tests, Node's built-in test runner
dashboard.html         self-contained PSD dashboard (inline CSS + JS)
sample-report.json     example report; the dashboard's default input
make-index.mjs         build index.json from a local directory of reports
make-oculus-index.mjs  build index.json by crawling the public Oculus site
```

## Setup

The pages use ES modules and `fetch()`, so they must be served over HTTP —
opening them as `file://` will not work. Any static server will do:

```bash
# from the repository root
python3 -m http.server 8777
```

Then open one of:

- <http://localhost:8777/viewer/viewer.html> — landing page. Drag a report
  `.json` onto it, pick a file, or paste a report URL.
- `http://localhost:8777/viewer/viewer.html?report=../reports/<report>.json` —
  open a specific report directly.
- `http://localhost:8777/viewer/dashboard.html?report=../reports/<report>.json`
  — the PSD dashboard. Without `?report=` it loads `sample-report.json`.

The `report` parameter is a URL resolved relative to the page, so it can also
point at another host (see *CORS* below).

### Listing several reports

`viewer.html` looks for an `index.json` next to itself and, if it finds one,
renders it as a list of reports on the landing page. Build it from a directory
of reports:

```bash
mkdir -p viewer/reports
cp reports/*.json viewer/reports/
node viewer/make-index.mjs viewer/reports reports/ viewer/index.json
```

Arguments are `<reportsDir> <urlPrefix> <outFile>`. The prefix is prepended to
each filename to form the URL the browser fetches, resolved relative to
`viewer.html` — so `reports/` above matches the `viewer/reports/` directory.
Entries are sorted newest first by `summary.timestamp`. Both `viewer/index.json`
and `viewer/reports/` are gitignored.

To list the latest published report per node instead, crawl Oculus:

```bash
node viewer/make-oculus-index.mjs \
  https://eida-oculus.orfeus-eu.org/consistency viewer/index.json
```

Arguments are `[rootUrl] [outFile]`, defaulting to the URL above and
`index.json` in the current directory — pass `viewer/index.json` explicitly when
running from the repository root. The crawl runs in Node (no CORS restrictions)
and only reads each report's summary.

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

No install needed — Node 20's built-in test runner. `viewer.core.js` holds the
logic worth testing (filtering, sorting, URL building, timeline geometry, HTML
rendering) and has no DOM dependency; `viewer.js` is the thin browser layer.
These tests run in CI on every push and pull request via the `viewer` job in
`.github/workflows/test.yml`.

## Deploying

Copy the directory onto any static host. Two useful placements:

- **Next to the reports** (e.g. on Oculus) — no CORS concerns, and `index.json`
  can be generated alongside the published reports.
- **On the docs site** — the viewer is reachable publicly and users paste an
  Oculus report URL into it.
