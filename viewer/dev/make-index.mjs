// make-index.mjs — build a viewer manifest (index.json) from a directory of report JSONs.
// Usage: node make-index.mjs <reportsDir> <urlPrefix> <outFile>
//   reportsDir  directory containing *.json reports
//   urlPrefix   prepended to each filename to form the URL the viewer fetches
//               (e.g. "reports/" or "../reports/" or "https://host/path/")
//   outFile     where to write the manifest
// Lists every report, newest first (by summary.timestamp, falling back to mtime).
import fs from 'node:fs';
import path from 'node:path';

const [, , dir = 'reports', prefix = 'reports/', out = 'index.json'] = process.argv;

const entries = [];
for (const file of fs.readdirSync(dir)) {
  if (!file.endsWith('.json') || file === 'index.json') continue;
  const full = path.join(dir, file);
  let summary = {};
  try { summary = (JSON.parse(fs.readFileSync(full, 'utf8')).summary) || {}; }
  catch { continue; } // skip unreadable / non-report JSON
  entries.push({
    name: file.replace(/\.json$/, ''),
    url: prefix + file,
    node: summary.node ?? null,
    score: summary.score ?? null,
    timestamp: summary.timestamp ?? null,
    inconsistent: summary.total_inconsistent ?? null,
    _sort: Date.parse(summary.timestamp || '') || fs.statSync(full).mtimeMs,
  });
}
entries.sort((a, b) => b._sort - a._sort); // newest first
for (const e of entries) delete e._sort;

fs.writeFileSync(out, JSON.stringify({ reports: entries }, null, 2) + '\n');
console.log(`wrote ${out} with ${entries.length} report(s)`);
