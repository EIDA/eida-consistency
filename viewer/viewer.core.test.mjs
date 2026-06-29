import { test } from 'node:test';
import assert from 'node:assert/strict';
import { queryTime, swapQueryTime, gapQueries, recordDirections, matchesFilter, timelineModel, summariseRequest, runRequest, renderSummary, renderResultsTable, renderDetail, sortRecords } from './viewer.core.js';

test('queryTime strips UTC suffix', () => {
  assert.equal(queryTime('2014-02-15T05:18:25.0069+00:00'), '2014-02-15T05:18:25.0069');
  assert.equal(queryTime('2014-02-15T05:18:25Z'), '2014-02-15T05:18:25');
});

test('swapQueryTime replaces only the named param', () => {
  const u = 'https://h/q?net=FR&start=2014-02-15T05:09:53&end=2014-02-15T05:19:53&format=text';
  assert.equal(
    swapQueryTime(u, 'start', '2014-02-15T05:18:25'),
    'https://h/q?net=FR&start=2014-02-15T05:18:25&end=2014-02-15T05:19:53&format=text');
});

test('gapQueries narrows both services to the gap window', () => {
  const rec = {
    url: 'https://h/availability/1/query?net=FR&start=2014-02-15T05:09:53&end=2014-02-15T05:19:53&format=text',
    dataselect_url: 'https://h/dataselect/1/query?net=FR&starttime=2014-02-15T05:09:53&endtime=2014-02-15T05:19:53&nodata=204',
  };
  const gap = { start: '2014-02-15T05:18:25+00:00', end: '2014-02-15T05:19:01+00:00' };
  const q = gapQueries(rec, gap);
  assert.match(q.availability, /start=2014-02-15T05:18:25&end=2014-02-15T05:19:01/);
  assert.match(q.dataselect, /starttime=2014-02-15T05:18:25&endtime=2014-02-15T05:19:01/);
});

test('gapQueries tolerates a missing base url', () => {
  assert.deepEqual(gapQueries({}, { start: 'a', end: 'b' }), { availability: null, dataselect: null });
});

const inc = {
  network: 'HT', station: 'KAVA', location: '', channel: 'HHE', consistent: false,
  mismatch: [{ who: 'dataselect' }, { who: 'dataselect' }],
};
const ok = { network: 'HL', station: 'PRK', location: '00', channel: 'HHZ', consistent: true, mismatch: [] };

test('recordDirections collects gap directions', () => {
  assert.deepEqual([...recordDirections(inc)], ['dataselect']);
  assert.deepEqual([...recordDirections(ok)], []);
});

test('onlyInconsistent hides consistent rows', () => {
  const f = { onlyInconsistent: true, direction: 'both', search: '' };
  assert.equal(matchesFilter(inc, f), true);
  assert.equal(matchesFilter(ok, f), false);
});

test('direction filter keeps matching gap direction', () => {
  assert.equal(matchesFilter(inc, { onlyInconsistent: true, direction: 'dataselect', search: '' }), true);
  assert.equal(matchesFilter(inc, { onlyInconsistent: true, direction: 'availability', search: '' }), false);
});

test('search matches NSLC case-insensitively', () => {
  const f = { onlyInconsistent: false, direction: 'both', search: 'kava' };
  assert.equal(matchesFilter(inc, f), true);
  assert.equal(matchesFilter(ok, f), false);
});

test('timelineModel classifies both/none/dataselect-only segments', () => {
  // window 0..600s; dataselect 60..180; availability empty
  const m = timelineModel(
    '2020-01-01T00:00:00', '2020-01-01T00:10:00',
    [], [['2020-01-01T00:01:00', '2020-01-01T00:03:00']], []);
  // expect a 'none' segment, a 'dataselect' segment, a 'none' segment
  const kinds = m.segments.map(s => s.kind);
  assert.deepEqual(kinds, ['none', 'dataselect', 'none']);
  assert.ok(Math.abs(m.segments[1].x0 - 0.1) < 1e-9);   // 60/600
  assert.ok(Math.abs(m.segments[1].x1 - 0.3) < 1e-9);   // 180/600
});

test('timelineModel emits a boundary between two gaps', () => {
  const m = timelineModel(
    '2020-01-01T00:00:00', '2020-01-01T00:10:00',
    [], [['2020-01-01T00:01:00','2020-01-01T00:02:00'], ['2020-01-01T00:06:00','2020-01-01T00:07:00']],
    [{ start: '2020-01-01T00:01:00+00:00', end: '2020-01-01T00:02:00+00:00', who: 'dataselect' },
     { start: '2020-01-01T00:06:00+00:00', end: '2020-01-01T00:07:00+00:00', who: 'dataselect' }]);
  assert.equal(m.boundaries.length, 1);
  assert.ok(m.boundaries[0] > 0.3 && m.boundaries[0] < 0.6);
});

test('timelineModel is safe on a degenerate window', () => {
  assert.deepEqual(timelineModel('x', 'x', [], [], []), { segments: [], boundaries: [] });
});

test('summariseRequest counts availability spans and dataselect bytes', () => {
  assert.match(summariseRequest('availability', 200, '#hdr\nA B\nC D\n', 0), /2 span/);
  assert.match(summariseRequest('dataselect', 204, '', 0), /no data/i);
  assert.match(summariseRequest('dataselect', 200, '', 4096), /4096 bytes/);
});

test('runRequest reports status and summary via injected fetch', async () => {
  const fakeFetch = async () => ({ status: 200, text: async () => '#h\nX Y\n', arrayBuffer: async () => new ArrayBuffer(8) });
  const r = await runRequest('availability', 'http://x', fakeFetch);
  assert.equal(r.ok, true);
  assert.equal(r.status, 200);
  assert.match(r.summary, /1 span/);
});

test('runRequest never throws on network error', async () => {
  const r = await runRequest('availability', 'http://x', async () => { throw new Error('net'); });
  assert.equal(r.ok, false);
  assert.equal(r.status, 0);
});

const rec = {
  index: 3, network: 'FR', station: 'MLS', location: '00', channel: 'HHN', consistent: false,
  starttime: '2014-02-15T05:09:53', endtime: '2014-02-15T05:19:53',
  url: 'https://h/availability/1/query?net=FR&start=2014-02-15T05:09:53&end=2014-02-15T05:19:53',
  dataselect_url: 'https://h/dataselect/1/query?net=FR&starttime=2014-02-15T05:09:53&endtime=2014-02-15T05:19:53&nodata=204',
  availability_status: 200, dataselect_status: 'OK',
  mismatch: [{ start: '2014-02-15T05:18:25+00:00', end: '2014-02-15T05:19:01+00:00', who: 'availability' }],
  coverage: { availability: [['2014-02-15T05:17:09','2014-02-15T05:19:01']], dataselect: [['2014-02-15T05:17:09','2014-02-15T05:18:25']] },
};

test('renderSummary shows score and counts', () => {
  const html = renderSummary({ node: 'NOA', score: 60, total_inconsistent: 8, total_consistent: 12 });
  assert.match(html, /NOA/); assert.match(html, /60/); assert.match(html, /8/); assert.match(html, /12/);
});

test('renderResultsTable respects the filter and tags rows by index', () => {
  const html = renderResultsTable([rec], { onlyInconsistent: true, direction: 'both', search: '' });
  assert.match(html, /data-index="3"/);
  assert.match(html, /FR\.MLS\.00\.HHN/);
});

test('renderDetail includes per-gap run buttons and a timeline payload', () => {
  const html = renderDetail(rec);
  assert.match(html, /data-kind="availability"/);
  assert.match(html, /start=2014-02-15T05:18:25/);          // per-gap narrowed query
  assert.match(html, /<pre class="tl">/);                   // ASCII timeline rendered
  assert.match(html, /Requests:/);
  assert.match(html, /start=2014-02-15T05:09:53/);          // full-window availability request present
});

test('renderDetail degrades when coverage/urls are absent', () => {
  const old = { index: 1, network: 'X', station: 'S', location: '', channel: 'BHZ', consistent: false };
  const html = renderDetail(old);
  assert.doesNotMatch(html, /class="tl"/);                 // no timeline without coverage
  assert.doesNotMatch(html, /data-kind=/);                 // no run buttons without urls
});

test('renderResultsTable escapes hostile values (no attribute/tag breakout)', () => {
  const evil = { index: 1, network: 'X', station: `a"'<>`, location: '', channel: 'BHZ', consistent: false, mismatch: [{ who: 'dataselect' }] };
  const html = renderResultsTable([evil], { onlyInconsistent: false, direction: 'both', search: '' });
  assert.doesNotMatch(html, /a"'<>/);            // raw hostile string not present
  assert.match(html, /&quot;/); assert.match(html, /&#39;/); assert.match(html, /&lt;/); assert.match(html, /&gt;/);
});

const _sr = [
  { network:'B', station:'B', location:'', channel:'B', starttime:'2020-01-02T00:00:00', mismatch:[{start:'2020-01-01T00:00:00+00:00',end:'2020-01-01T00:01:00+00:00'}] },
  { network:'A', station:'A', location:'', channel:'A', starttime:'2020-01-01T00:00:00', mismatch:[{start:'2020-01-01T00:00:00+00:00',end:'2020-01-01T00:05:00+00:00'}] },
];
test('sortRecords by channel', () => { assert.equal(sortRecords(_sr,'channel')[0].network, 'A'); });
test('sortRecords by time', () => { assert.equal(sortRecords(_sr,'time')[0].starttime, '2020-01-01T00:00:00'); });
test('sortRecords by gap puts the largest gap first', () => { assert.equal(sortRecords(_sr,'gap')[0].network, 'A'); });
test('sortRecords does not mutate input', () => { const c = JSON.parse(JSON.stringify(_sr)); sortRecords(_sr,'channel'); assert.deepEqual(_sr, c); });

test('renderDetail refuses a javascript: open link but keeps safe https links', () => {
  const evil = { index:1, network:'X', station:'S', location:'', channel:'B', consistent:false,
    url:'javascript:alert(1)',
    dataselect_url:'https://h/dataselect/1/query?net=X&starttime=a&endtime=b',
    mismatch:[] };
  const html = renderDetail(evil);
  assert.doesNotMatch(html, /href="javascript:/);
  assert.match(html, /rel="noopener noreferrer"/);
});

test('renderSummary shows skipped + direction totals + timestamp and tolerates undefined', () => {
  const html = renderSummary({ node:'NOA', score:60, total_inconsistent:8, total_consistent:12,
    total_skipped:1, availability_yes_dataselect_no:2, availability_no_dataselect_yes:6, timestamp:'2026-06-28T15:00:00+00:00' });
  assert.match(html, /1 skipped/); assert.match(html, /▼ 2/); assert.match(html, /▲ 6/); assert.match(html, /2026-06-28/);
  assert.doesNotThrow(() => renderSummary(undefined));
});

import { timelineAscii } from './viewer.core.js';
test('timelineAscii renders fixed-width glyphs with a gap boundary', () => {
  const s = timelineAscii('2020-01-01T00:00:00', '2020-01-01T00:10:00', [],
    [['2020-01-01T00:01:00','2020-01-01T00:02:00'], ['2020-01-01T00:06:00','2020-01-01T00:07:00']],
    [{start:'2020-01-01T00:01:00+00:00',end:'2020-01-01T00:02:00+00:00'},{start:'2020-01-01T00:06:00+00:00',end:'2020-01-01T00:07:00+00:00'}]);
  assert.equal([...s].length, 58);
  assert.match(s, /▲/); assert.match(s, /·/); assert.match(s, /\|/);
  assert.doesNotMatch(s, /▼/);
});

import { fmtDuration, gapStats, renderIndex } from './viewer.core.js';

test('fmtDuration shows up to two largest units', () => {
  assert.equal(fmtDuration(0), '0s');
  assert.equal(fmtDuration(45), '45s');
  assert.equal(fmtDuration(95), '1m 35s');
  assert.equal(fmtDuration(3661), '1h 1m');
  assert.equal(fmtDuration(90000), '1d 1h');
});

test('gapStats counts gaps and the largest duration', () => {
  const s = gapStats({ mismatch: [
    { start: '2020-01-01T00:00:00+00:00', end: '2020-01-01T00:01:00+00:00' },
    { start: '2020-01-01T00:00:00+00:00', end: '2020-01-01T00:05:00+00:00' } ] });
  assert.equal(s.count, 2);
  assert.equal(s.maxGap, 300);
  assert.deepEqual(gapStats({}), { count: 0, maxGap: 0 });
});

test('renderResultsTable shows a gap-count badge, max gap, and sortable headers', () => {
  const html = renderResultsTable([rec], { onlyInconsistent: true, direction: 'both', search: '' }, { key: 'gap', dir: 'desc' });
  assert.match(html, /data-sort="gap"/);
  assert.match(html, /class="badge">1</);          // one gap on rec
  assert.match(html, /class="sortable active"/);   // active sorted column marked
});

test('renderIndex builds links that round-trip the report URL', () => {
  const html = renderIndex([{ name: 'NOA latest', url: 'https://x/a b/r.json', node: 'NOA', score: 76, inconsistent: 7 }]);
  assert.match(html, /NOA latest/);
  assert.match(html, /\?report=https%3A%2F%2Fx%2Fa%20b%2Fr\.json/);
  assert.match(html, /76%/);
  assert.match(html, /7 inconsistent/);
});

test('renderDetail shows per-gap duration and copy buttons', () => {
  const html = renderDetail(rec);
  assert.match(html, /class="gdur">36s</);         // 05:18:25 -> 05:19:01 = 36s
  assert.match(html, /data-copy=/);
});
