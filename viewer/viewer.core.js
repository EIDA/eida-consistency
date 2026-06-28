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
