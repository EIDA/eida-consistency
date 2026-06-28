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

function _sec(iso, t0) { return (Date.parse(iso) - t0) / 1000; }

export function timelineModel(windowStart, windowEnd, avail, ds, mismatch) {
  const t0 = Date.parse(windowStart), t1 = Date.parse(windowEnd);
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
  const gaps = [...(mismatch || [])].sort((m, n) => String(m.start).localeCompare(String(n.start)));
  const boundaries = [];
  for (let i = 0; i < gaps.length - 1; i++) {
    const e = _sec(gaps[i].end, t0), s = _sec(gaps[i + 1].start, t0);
    boundaries.push(((e + s) / 2) / total);
  }
  return { segments, boundaries };
}
