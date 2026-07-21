// make-oculus-index.mjs — build the viewer manifest (index.json) of the LATEST
// consistency report per node, by crawling the public Oculus site.
//
// Oculus serves each report's JSON at the year level with open CORS:
//   <root>/<NODE>/<YEAR>/<NODE>_<DATE>_<seed>.json
// so the browser can load any entry cross-origin. This crawler only runs in
// Node (no CORS limits) to discover the latest report per node and read its
// summary for the landing list.
//
// Usage: node make-oculus-index.mjs [rootUrl] [outFile]
//   rootUrl  default https://eida-oculus.orfeus-eu.org/consistency
//   outFile  default index.json
import fs from 'node:fs';

const ROOT = (process.argv[2] || 'https://eida-oculus.orfeus-eu.org/consistency').replace(/\/$/, '');
const OUT = process.argv[3] || 'index.json';

async function links(url, re) {
  const res = await fetch(url);
  if (!res.ok) return [];
  const html = await res.text();
  const out = new Set();
  for (const m of html.matchAll(/href="([^"#?]+?)\/?"/g)) {
    const name = m[1].replace(/^\.?\//, '').replace(/\/$/, '');
    if (name && !name.includes('/') && re.test(name)) out.add(name);
  }
  return [...out];
}

const nodes = await links(`${ROOT}/`, /^[A-Z][A-Za-z0-9]+$/);
console.log(`nodes: ${nodes.join(', ')}`);

const entries = [];
for (const node of nodes) {
  const years = (await links(`${ROOT}/${node}/`, /^[0-9]{4}$/)).sort().reverse();
  if (!years.length) { console.log(`  ${node}: no years`); continue; }
  const year = years[0];
  const reports = (await links(`${ROOT}/${node}/${year}/`, new RegExp(`^${node}_[0-9].*$`))).sort().reverse();
  if (!reports.length) { console.log(`  ${node}: no reports in ${year}`); continue; }
  const id = reports[0];
  const url = `${ROOT}/${node}/${year}/${id}.json`;
  let s = {};
  try { const r = await fetch(url); if (r.ok) s = (await r.json()).summary || {}; } catch { /* keep bare entry */ }
  entries.push({
    name: node,
    report: id,
    url,
    node: null, // shown as the title already
    score: s.score ?? null,
    timestamp: s.timestamp ?? null,
    inconsistent: s.total_inconsistent ?? null,
  });
  console.log(`  ${node}: ${id} (score ${s.score ?? '?'})`);
}

entries.sort((a, b) => a.name.localeCompare(b.name));
fs.writeFileSync(OUT, JSON.stringify({ reports: entries }, null, 2) + '\n');
console.log(`wrote ${OUT} with ${entries.length} report(s)`);
