# Report viewer

Browser view of the JSON reports `eida-consistency` produces: score, a findings
table with filters and sort, a per-record timeline, and buttons that replay a
finding's exact FDSN request.

Vanilla ES modules and hand-written CSS — no framework, no bundler, no
`package.json`, no CDN, no external asset of any kind.

## What deploys

```
viewer.html      page shell - all markup and all CSS
viewer.js        browser wiring - fetch, state, events
viewer.core.js   render / filter / sort logic
```

Those three, in the same directory. Where that directory is does not matter.
`dev/` is development-only and is not deployed.

Static page, no build step. It has to be served over HTTP rather than opened as
`file://`, because ES modules and `fetch()` do not work from the filesystem.

## Pointing it at a report

A report next to `viewer.html`, or by relative path:

```
viewer.html?report=noa_20260729_131402_471284.json
viewer.html?report=../reports/noa_20260729_131402_471284.json
```

By site-absolute path:

```
viewer.html?report=/consistency/NOA/2026/NOA_2026-08-23_140118_178556.json
```

From another host — needs CORS on that host. The paste-a-URL box builds this one
with `encodeURIComponent`, so `:` and `/` arrive as `%3A` and `%2F`:

```
viewer.html?report=https%3A%2F%2Feida-oculus.orfeus-eu.org%2Fconsistency%2FNOA%2F2026%2FNOA_2026-08-23_140118_178556.json
```

The unencoded form works too — both decode to the same URL — but the encoded one
is what appears in the address bar after using the form.

No parameter at all gives the landing page:

```
viewer.html
```

`?report=` is resolved against **viewer.html's own URL**, not against the page
the link was on. That is the one thing worth checking when a report 404s.

Reports produced before the PSD check render the same layout as current ones,
with the PSD column reading *not checked*.

## The landing page

With no `?report=`, the viewer looks for `index.json` beside itself and lists
what it finds, newest first:

```json
{ "reports": [
    { "name": "noa_20260729_131402_471284",
      "url": "../reports/noa_20260729_131402_471284.json",
      "node": "NOA", "score": 90,
      "timestamp": "2026-07-29T13:14:02.471284+00:00",
      "inconsistent": 3 }
] }
```

`url` is fetched relative to `viewer.html`. A bare array instead of
`{"reports": [...]}` also works. With no `index.json` the landing page still
works - it just shows its load-by-URL and drag-drop form alone.

`dev/make-index.mjs <reports-dir> <url-prefix> <out-file>` generates one from a
directory of reports.
