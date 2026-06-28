export function queryTime(iso) {
  return String(iso ?? '').replace('+00:00', '').replace('Z', '');
}

export function swapQueryTime(url, key, value) {
  const re = new RegExp(`([?&]${key}=)[^&]*`);
  return url.replace(re, (_, p1) => p1 + value);
}

export function gapQueries(record, gap) {
  const gs = queryTime(gap.start), ge = queryTime(gap.end);
  const av = record.url
    ? swapQueryTime(swapQueryTime(record.url, 'start', gs), 'end', ge) : null;
  const ds = record.dataselect_url
    ? swapQueryTime(swapQueryTime(record.dataselect_url, 'starttime', gs), 'endtime', ge) : null;
  return { availability: av, dataselect: ds };
}

export function recordDirections(record) {
  const s = new Set();
  for (const m of record.mismatch || []) if (m.who) s.add(m.who);
  return s;
}

export function matchesFilter(record, filter) {
  if (filter.onlyInconsistent && record.consistent !== false) return false;
  if (filter.direction && filter.direction !== 'both') {
    if (!recordDirections(record).has(filter.direction)) return false;
  }
  if (filter.search) {
    const nslc = `${record.network}.${record.station}.${record.location}.${record.channel}`.toLowerCase();
    if (!nslc.includes(filter.search.toLowerCase())) return false;
  }
  return true;
}

function _parseUTC(iso) { return Date.parse(/[Z+]/.test(iso) ? iso : iso + 'Z'); }

function _sec(iso, t0) { return (_parseUTC(iso) - t0) / 1000; }

export function timelineModel(windowStart, windowEnd, avail, ds, mismatch) {
  const t0 = _parseUTC(windowStart), t1 = _parseUTC(windowEnd);
  if (!(t1 > t0)) return { segments: [], boundaries: [] };
  const total = (t1 - t0) / 1000;
  const toIv = arr => (arr || []).map(([a, b]) => [_sec(a, t0), _sec(b, t0)]).filter(([a, b]) => b > a);
  const A = toIv(avail), D = toIv(ds);
  const cov = (iv, x) => iv.some(([a, b]) => a <= x && x < b);
  const pts = new Set([0, total]);
  for (const [a, b] of [...A, ...D]) { if (a > 0 && a < total) pts.add(a); if (b > 0 && b < total) pts.add(b); }
  const sorted = [...pts].sort((p, q) => p - q);
  const segments = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    const a = sorted[i], b = sorted[i + 1], mid = (a + b) / 2;
    const inA = cov(A, mid), inD = cov(D, mid);
    const kind = inA && inD ? 'both' : inA ? 'availability' : inD ? 'dataselect' : 'none';
    segments.push({ x0: a / total, x1: b / total, kind });
  }
  const gaps = [...(mismatch || [])].sort((m, n) => _parseUTC(m.start) - _parseUTC(n.start));
  const boundaries = [];
  for (let i = 0; i < gaps.length - 1; i++) {
    const e = _sec(gaps[i].end, t0), s = _sec(gaps[i + 1].start, t0);
    const b = ((e + s) / 2) / total;
    if (b >= 0 && b <= 1) boundaries.push(b);
  }
  return { segments, boundaries };
}

export function timelineAscii(windowStart, windowEnd, avail, ds, mismatch, width = 58) {
  const t0 = _parseUTC(windowStart), t1 = _parseUTC(windowEnd);
  if (!(t1 > t0)) return '';
  const total = (t1 - t0) / 1000;
  const toIv = arr => (arr || []).map(([a, b]) => [_sec(a, t0), _sec(b, t0)]).filter(([a, b]) => b > a);
  const A = toIv(avail), D = toIv(ds);
  const cov = (iv, i) => { const cs = i * total / width, ce = (i + 1) * total / width; return iv.some(([a, b]) => Math.max(cs, a) < Math.min(ce, b) - 1e-9); };
  const out = [];
  for (let i = 0; i < width; i++) { const a = cov(A, i), d = cov(D, i); out.push(a && d ? '█' : a ? '▼' : d ? '▲' : '·'); }
  const gaps = [...(mismatch || [])].sort((m, n) => _parseUTC(m.start) - _parseUTC(n.start));
  for (let i = 0; i < gaps.length - 1; i++) {
    const e = _sec(gaps[i].end, t0), s = _sec(gaps[i + 1].start, t0);
    const cell = Math.min(width - 1, Math.max(0, Math.floor(((e + s) / 2) / total * width)));
    out[cell] = '|';
  }
  return out.join('');
}

export function summariseRequest(kind, status, bodyText, byteLength) {
  if (kind === 'availability') {
    const n = (bodyText || '').split('\n').filter(l => l && !l.startsWith('#')).length;
    return `HTTP ${status} — ${n} span${n === 1 ? '' : 's'}`;
  }
  if (status === 204) return `HTTP 204 — no data`;
  return `HTTP ${status} — ${byteLength} bytes`;
}

export async function runRequest(kind, url, fetchImpl) {
  try {
    const res = await fetchImpl(url);
    if (kind === 'availability') {
      const text = await res.text();
      return { ok: true, status: res.status, summary: summariseRequest(kind, res.status, text, 0) };
    }
    const buf = await res.arrayBuffer();
    return { ok: true, status: res.status, summary: summariseRequest(kind, res.status, '', buf.byteLength) };
  } catch {
    return { ok: false, status: 0, summary: 'request failed' };
  }
}

const DIR_LABEL = {
  availability: '▼ Availability: data · Dataselect: NO DATA',
  dataselect: '▲ Availability: NO DATA · Dataselect: data',
};
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safeUrl = u => (/^https?:\/\//i.test(String(u ?? '')) ? String(u) : '');

export function renderSummary(s) {
  s = s || {};
  return `<header class="summary"><h1>${esc(s.node)}</h1>
    <span class="score">Score ${esc(s.score)}%</span>
    <span>${esc(s.total_inconsistent)} inconsistent / ${esc(s.total_consistent)} consistent / ${esc(s.total_skipped ?? 0)} skipped</span>
    <span class="dirtotals">▼ ${esc(s.availability_yes_dataselect_no ?? 0)} · ▲ ${esc(s.availability_no_dataselect_yes ?? 0)}</span>
    <span class="ts">${esc(s.timestamp ?? '')}</span></header>`;
}

export function renderResultsTable(results, filter) {
  const rows = (results || []).filter(r => matchesFilter(r, filter)).map(r => {
    const nslc = `${r.network}.${r.station}.${r.location}.${r.channel}`;
    const dir = r.consistent === false ? [...recordDirections(r)].map(w => DIR_LABEL[w] ? DIR_LABEL[w][0] : '').join('') : '✔';
    return `<tr data-index="${esc(r.index)}"><td>${esc(nslc)}</td>
      <td>${esc(r.starttime)} → ${esc(r.endtime)}</td><td>${esc(dir)}</td>
      <td>${esc(r.dataselect_status ?? '')}</td></tr>`;
  }).join('');
  return `<table class="results"><thead><tr><th>Channel</th><th>Window</th><th>Dir</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function _maxGap(record) {
  let max = 0;
  for (const m of record.mismatch || []) {
    const d = (_parseUTC(m.end) - _parseUTC(m.start)) / 1000;
    if (d > max) max = d;
  }
  return max;
}

export function sortRecords(results, key) {
  const arr = [...(results || [])];
  const nslc = r => `${r.network}.${r.station}.${r.location}.${r.channel}`;
  if (key === 'channel') arr.sort((a, b) => nslc(a).localeCompare(nslc(b)));
  else if (key === 'gap') arr.sort((a, b) => _maxGap(b) - _maxGap(a)); // largest gap first
  else arr.sort((a, b) => String(a.starttime).localeCompare(String(b.starttime))); // 'time'
  return arr;
}

export function renderDetail(record) {
  const parts = [];
  const cov = record.coverage;
  if (cov && (cov.availability || cov.dataselect)) {
    const tl = timelineAscii(record.starttime, record.endtime, cov.availability || [], cov.dataselect || [], record.mismatch || []);
    parts.push(`<pre class="tl">${esc(tl)}</pre><div class="legend">▲ Data YES / Avail NO &nbsp; ▼ Avail YES / Data NO &nbsp; █ both &nbsp; · none &nbsp; | gap boundary</div>`);
  }
  const full = ['availability', 'dataselect'].map(k => {
    const u = k === 'availability' ? record.url : record.dataselect_url;
    const link = safeUrl(u) ? ` <a href="${esc(safeUrl(u))}" target="_blank" rel="noopener noreferrer">open</a>` : '';
    return u ? `<button data-kind="${k}" data-url="${esc(u)}">Run ${k}</button>${link}` : '';
  }).filter(Boolean).join(' ');
  if (full) parts.push(`<div class="req full">Requests: ${full}</div>`);
  for (const m of record.mismatch || []) {
    const q = gapQueries(record, m);
    const btns = ['availability', 'dataselect'].filter(k => q[k]).map(k => {
      const link = safeUrl(q[k]) ? ` <a href="${esc(safeUrl(q[k]))}" target="_blank" rel="noopener noreferrer">open</a>` : '';
      return `<button data-kind="${k}" data-url="${esc(q[k])}">Run ${k}</button>${link}`;
    }).join(' ');
    parts.push(`<div class="gap">${esc(m.start)} → ${esc(m.end)} ${esc(DIR_LABEL[m.who] || '')}<div class="req">${btns}</div></div>`);
  }
  return `<section class="detail">${parts.join('')}</section>`;
}
