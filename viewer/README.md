# EIDA Consistency — HTML report viewer

A self-contained, dependency-free web page that turns one consistency
**`report.json`** into an interactive view: filter/sort the streams, see a
graphical timeline of where availability and dataselect disagree, and replay the
underlying FDSN requests live from the browser.

There is **no backend, no build step, no framework**. It is plain HTML + CSS +
ES-module JavaScript. Oculus (or any static host) serves the files as-is.

---

## 1. What problem it solves

The consistency checker emits two artifacts per run: a Markdown report (rendered
to HTML by Oculus) and a machine-readable `report.json`. The Markdown is static.
Issue #50 asked for a *dynamic* presentation — filtering, "play the requests",
etc. This viewer is that dynamic layer: it reads the JSON the tool already
produces and renders it interactively, entirely client-side.

Key facts that make the no-backend design work:

- **Oculus publishes the JSON.** Each report's JSON is served at the year level,
  e.g. `…/consistency/<NODE>/<YEAR>/<NODE>_<DATE>_<seed>.json`, with
  `Access-Control-Allow-Origin: *`. So the browser can load any report
  cross-origin.
- **FDSN nodes send open CORS too.** So the in-browser "Run" can fetch the
  availability/dataselect URLs directly and report what came back.

---

## 2. Files

| File | Role |
|------|------|
| `viewer.html` | The shell: `<head>` with all CSS, and four mount points (`#summary`, `#toolbar`, `#results`, `#detail`). Loads `viewer.js` as a module. |
| `viewer.core.js` | **All pure logic.** Functions that take data and return HTML strings or values — no DOM, no network. This is what the tests exercise. |
| `viewer.js` | **DOM glue.** Reads the URL, fetches JSON, mounts HTML into the page, and wires events (clicks, filters, file drops, Run buttons). Imports from `viewer.core.js`. |
| `viewer.core.test.mjs` | `node:test` suite over the pure functions (run with `node --test`). |
| `make-index.mjs` | Generator: build `index.json` from a **local** directory of report JSONs. |
| `make-oculus-index.mjs` | Generator: crawl the public **Oculus** site and build `index.json` of the latest report per node. |
| `index.json` | The landing manifest (generated; git-ignored). |
| `sample-report.json` | A real report checked in for offline demos/tests. |

**Why core/glue are split:** the render functions return strings, so they can be
unit-tested in Node without a browser or DOM. `viewer.js` is the only file that
touches `document`, `fetch`, or `location`.

---

## 3. Lifecycle (what happens on load)

`viewer.js` → `main()`:

1. `wireDragAndDrop()` — makes the whole window a drop target for a `.json` file.
2. Read `?report=` from the URL.
   - **No `?report=`** → `showLanding()`: fetch `index.json`; if present render the
     report list (`renderIndex`), then always show the loader (URL box + file
     picker). If there's no manifest, just the loader.
   - **`?report=<url>`** → `fetch()` it, then `showReport()`.
3. `showReport(report)` stores the parsed object in `state`, reveals the toolbar,
   calls `wire()` (attach event handlers once), and `paint()`.
4. `paint()` re-renders the summary header and the results table from the current
   `state.filter` and `state.sort`. It runs on every filter/sort change.

`state` holds: the parsed `report`, the `filter` (only-inconsistent, direction,
search text), and the `sort` (`{key, dir}`).

The report URL is treated as an **opaque string** — the viewer never parses the
filename or seed, so changes to report filenames never affect it.

---

## 4. The data it reads (report JSON)

Everything is driven off the schema the tool emits:

- `summary`: `node`, `score`, `total_consistent` / `total_inconsistent` /
  `total_skipped`, the two direction totals
  (`availability_yes_dataselect_no`, `availability_no_dataselect_yes`),
  `timestamp`.
- `results[]`, one per stream/epoch:
  `network`/`station`/`location`/`channel`, `starttime`/`endtime`,
  `consistent`, `dataselect_status`, `url` (availability),
  `dataselect_url`, `mismatch[] {start, end, who}`,
  `coverage {availability[], dataselect[]}`.

**Graceful degradation is a hard rule.** Older reports lack
`coverage`/`dataselect_url`/`who`. The viewer renders whatever is present and
hides what it can't build — it must never crash on a missing field. Two concrete
examples:

- No `coverage` → it draws the single-track "request window with gaps" timeline
  instead of the two-lane chart (see §6).
- No `dataselect_url` → it **derives** one from the availability `url` (see §7).

---

## 5. The components (in `viewer.core.js`)

### Summary header — `renderSummary(summary)`
An SVG **score gauge** (a stroked circle whose dash-offset encodes the percent,
coloured green/amber/red by threshold), the node name, status chips
(inconsistent / consistent / skipped), the timestamp, and two **direction bars**
(`▲ data-only`, `▼ avail-only`) scaled to the larger of the two counts.

### Toolbar — wired in `viewer.js`
- **only inconsistent** (checkbox) — `matchesFilter` hides consistent rows.
- **direction** (select) — both / `▲` dataselect-only / `▼` availability-only.
- **search** — substring match on `NET.STA.LOC.CHA`.
- Sorting is by **clicking a column header** (see below), not a dropdown.

### Results table — `renderResultsTable(results, filter, sort)`
Columns: Channel, Window, Dir, Gaps (count badge), Max gap, Status. Sortable
headers carry `data-sort`; the active one shows ▲/▼. `sortRecords(results, key,
dir)` does the ordering (`gap` defaults to largest-first). `gapStats(record)`
computes the gap count and longest gap; `fmtDuration(seconds)` formats it
("1h 1m", "36s").

### Detail view — `renderDetail(record)`
Rendered when a row is clicked. Contains, in order:

1. **Timeline** (graphical + ASCII) — see §6.
2. **Requests: full-window** — Run / open / copy for availability and dataselect.
3. **Gaps** — one block per `mismatch` entry: start → end, duration, the
   direction label, and per-gap Run / open / copy buttons narrowed to that gap's
   time window (`gapQueries`).

### Landing list — `renderIndex(entries)`
One row per report: node (link), colour-coded score, timestamp, inconsistent
count. Each link is `?report=<encodeURIComponent(url)>`, so clicking reloads the
viewer pointed at that report (local path or absolute Oculus URL).

---

## 6. The timeline

Three renderers, all pure, all returning SVG/text strings:

- **`timelineSVG(start, end, avail, ds, mismatch)`** — the rich view. Two lanes
  over the request window: a green **Availability** lane and a blue **Dataselect**
  lane, each filled where that service reports data, with mismatch regions
  shaded red and `<title>` hover tooltips showing exact times. Used when the
  record has `coverage`.
- **`timelineGapsSVG(start, end, mismatch)`** — the fallback for reports without
  `coverage`: a single "Window" track with the gap regions marked solid red.
- **`timelineAscii(start, end, avail, ds, mismatch)`** — the text timeline
  (`█` both · `·` neither · `▲` dataselect-only · `▼` availability-only · `|` gap
  boundary), kept beneath the SVG when coverage exists. Mirrors the CLI/Markdown
  output.

`timelineModel(...)` is the shared segment math (also unit-tested); `_segs(...)`
converts `[start,end]` pairs into clamped 0–1 fractions of the window.

---

## 7. Replaying requests ("Run")

Each request shows three actions:

- **open** — a normal link to the FDSN URL (new tab).
- **copy** — copies the URL to the clipboard.
- **Run** — fetches it from the browser and shows the result inline.

`runRequest(kind, url, fetchImpl)` performs the fetch and returns
`{ok, status, hasData, summary}`:

- availability → counts non-comment lines (spans); `hasData` = `200` and spans>0.
- dataselect → reads bytes; `hasData` = `200` with bytes (`204` = no data).

`viewer.js` turns that into a coloured pill next to the button — green **HAS
DATA**, red **NO DATA**, grey **FAILED** — plus the HTTP/size summary. Re-running
replaces the previous result rather than stacking.

**Deriving dataselect** — `buildDataselectUrl(record)`: if `dataselect_url` is
stored, use it; otherwise rebuild from the availability `url` by swapping
`/availability/` → `/dataselect/`, renaming `start`/`end` →
`starttime`/`endtime`, narrowing `location=*` to the record's stream, and adding
`nodata=204`. This is why old Oculus reports still get a working "Run dataselect".

---

## 8. Loading reports (three ways)

- **By URL** — `?report=<url>` or the URL box. Any reachable `report.json`
  (local path or an Oculus URL).
- **By file** — the file picker; `readFile` validates it's a report
  (`summary` + `results`) before rendering.
- **By drag-and-drop** — drop a `.json` anywhere on the page.

The landing list itself is just whatever `index.json` contains, so Oculus can
own the "latest reports" page simply by publishing a manifest.

---

## 9. Security

The report could be untrusted (loaded by URL), so all rendering is escaped:

- **`esc(s)`** — HTML-escapes `& < > " '` on every interpolated value.
- **`safeUrl(u)`** — only `http(s)` URLs become `href`s; anything else (e.g.
  `javascript:`) yields no link. "open" links also carry
  `rel="noopener noreferrer"`.

These are covered by dedicated tests (hostile NSLC values, `javascript:` URLs).

---

## 10. The manifest generators

`index.json` is a **generated artifact** (git-ignored), shaped
`{ "reports": [ {name, url, node, score, timestamp, inconsistent}, … ] }`.

- **Local:** `node make-index.mjs <reportsDir> <urlPrefix> <outFile>` — lists
  every report in a directory, newest first.
- **Oculus:** `node make-oculus-index.mjs [rootUrl] [outFile]` — crawls the
  public Oculus tree, picks the latest report per node, reads each summary, and
  writes absolute year-level JSON URLs (which the browser loads cross-origin).

Either can be re-run on a schedule, or replaced by an `index.json` that Oculus
emits itself.

---

## 11. Running it

Serve the `viewer/` directory with any static server and open `viewer.html`:

```bash
cd viewer
python3 -m http.server 8800
# then:
#   http://127.0.0.1:8800/viewer.html                      (landing)
#   http://127.0.0.1:8800/viewer.html?report=sample-report.json
#   http://127.0.0.1:8800/viewer.html?report=<any oculus report .json url>
```

Run the tests:

```bash
node --test viewer/viewer.core.test.mjs
```

---

## 12. How Oculus integrates

1. Serve `viewer.html`, `viewer.js`, `viewer.core.js` as static assets.
2. (Optional) publish an `index.json` next to them for the landing list — either
   by running `make-oculus-index.mjs` on a cron, or by emitting the manifest as
   part of the report build.
3. The report generator already adds a `🔍 Interactive view` link to each
   report's Markdown pointing at `viewer.html?report=<that-report>.json`, so
   users never type a URL by hand.

Nothing else is required — no plugin, no theme override, no database.

---

## 13. Extending it

- **New render piece:** add a pure function to `viewer.core.js` that returns an
  HTML string, add a `node:test`, then call it from `renderDetail`/`paint` and
  mount it in `viewer.js`. Keep DOM/network out of the core.
- **New report field:** read it defensively (assume it may be absent) and hide
  the UI when it's missing — never assume a field exists.
