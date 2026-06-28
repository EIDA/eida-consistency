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
