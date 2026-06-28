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
