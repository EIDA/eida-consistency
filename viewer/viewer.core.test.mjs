import { test } from 'node:test';
import assert from 'node:assert/strict';
import { queryTime, swapQueryTime, gapQueries, recordDirections, matchesFilter, timelineModel, summariseRequest, runRequest, renderSummary, renderResultsTable, renderDetail, sortRecords, recordVerdict, explainRecord } from './viewer.core.js';

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

test('runRequest reports status, hasData and summary via injected fetch', async () => {
  const fakeFetch = async () => ({ status: 200, text: async () => '#h\nX Y\n', arrayBuffer: async () => new ArrayBuffer(8) });
  const r = await runRequest('availability', 'http://x', fakeFetch);
  assert.equal(r.ok, true);
  assert.equal(r.status, 200);
  assert.equal(r.hasData, true);
  assert.match(r.summary, /1 span/);
});

test('runRequest flags no-data for empty availability and 204 dataselect', async () => {
  const emptyAvail = await runRequest('availability', 'http://x', async () => ({ status: 200, text: async () => '#header only\n', arrayBuffer: async () => new ArrayBuffer(0) }));
  assert.equal(emptyAvail.hasData, false);
  const ds200 = await runRequest('dataselect', 'http://x', async () => ({ status: 200, text: async () => '', arrayBuffer: async () => new ArrayBuffer(512) }));
  assert.equal(ds200.hasData, true);
  const ds204 = await runRequest('dataselect', 'http://x', async () => ({ status: 204, text: async () => '', arrayBuffer: async () => new ArrayBuffer(0) }));
  assert.equal(ds204.hasData, false);
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

test('recordVerdict states the result in words', () => {
  assert.equal(recordVerdict({ consistent: false }).text, 'Inconsistent');
  assert.equal(recordVerdict({ consistent: true }).text, 'Consistent');
  assert.equal(recordVerdict({ consistent: null }).text, 'Skipped');
});

test('renderResultsTable shows a word verdict and a labelled disagreement tag (not a bare glyph)', () => {
  const html = renderResultsTable([rec], { onlyInconsistent: true, direction: 'both', search: '' });
  assert.match(html, /class="verdict bad">Inconsistent</);   // result in words, not "OK"
  assert.match(html, /class="tag /);                          // labelled pill...
  assert.match(html, /Avail only|Data only/);                 // ...with a readable label
});

test('explainRecord gives a plain single-gap sentence', () => {
  const html = explainRecord({
    consistent: false,
    mismatch: [{ start: '2014-02-15T05:18:25+00:00', end: '2014-02-15T05:19:01+00:00', who: 'availability' }],
  }).text;
  assert.match(html, /Inconsistency/);
  assert.match(html, /availability reported data but dataselect returned none/);
  assert.match(html, /05:18:25/);
});

test('explainRecord summarises multiple gaps and marks consistent rows', () => {
  const multi = explainRecord({
    consistent: false,
    mismatch: [
      { start: '2014-02-15T05:18:25+00:00', end: '2014-02-15T05:19:01+00:00', who: 'availability' },
      { start: '2014-02-15T05:20:00+00:00', end: '2014-02-15T05:21:00+00:00', who: 'dataselect' },
    ],
  }).text;
  assert.match(multi, /across 2 intervals/);
  assert.match(explainRecord({ consistent: true }).text, /Consistent/);
});

test('renderDetail leads with the plain-language explanation', () => {
  const html = renderDetail(rec);
  assert.match(html, /class="explain bad">/);
  assert.match(html, /Inconsistency/);
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

import { timelineSVG } from './viewer.core.js';
test('timelineSVG draws both lanes, a gap band, and time labels', () => {
  const svg = timelineSVG('2020-01-01T00:00:00', '2020-01-01T00:10:00',
    [['2020-01-01T00:00:00', '2020-01-01T00:06:00']],            // availability has data 0-6m
    [['2020-01-01T00:00:00', '2020-01-01T00:04:00']],            // dataselect has data 0-4m
    [{ start: '2020-01-01T00:04:00+00:00', end: '2020-01-01T00:06:00+00:00', who: 'availability' }]);
  assert.match(svg, /^<svg class="tlsvg"/);
  assert.match(svg, /class="tl-av"/);
  assert.match(svg, /class="tl-ds"/);
  assert.match(svg, /class="tl-gap"/);
  assert.match(svg, /<title>Availability: 2020-01-01 00:00:00/);
  assert.match(svg, /2020-01-01 00:10:00<\/text>/);             // end label
});
test('timelineSVG is empty on a degenerate window', () => {
  assert.equal(timelineSVG('x', 'x', [], [], []), '');
});
test('renderDetail embeds the SVG timeline alongside the ASCII line', () => {
  const html = renderDetail(rec);
  assert.match(html, /<svg class="tlsvg"/);
  assert.match(html, /<pre class="tl">/);
});

import { timelineGapsSVG } from './viewer.core.js';
test('timelineGapsSVG marks gaps on a single window track', () => {
  const svg = timelineGapsSVG('2009-01-09T04:51:00', '2009-01-09T05:01:00',
    [{ start: '2009-01-09T04:55:00+00:00', end: '2009-01-09T04:57:00+00:00' }]);
  assert.match(svg, /class="tl-gap-solid"/);
  assert.match(svg, /<title>gap: 2009-01-09 04:55:00/);
});
test('timelineGapsSVG is empty without a window or gaps', () => {
  assert.equal(timelineGapsSVG('x', 'x', [{ start: 'a', end: 'b' }]), '');
  assert.equal(timelineGapsSVG('2009-01-09T04:51:00', '2009-01-09T05:01:00', []), '');
});
test('renderDetail falls back to a gaps-only graph when coverage is absent', () => {
  const old = { index: 2, network: 'HL', station: 'X', location: '', channel: 'HHZ', consistent: false,
    starttime: '2009-01-09T04:51:07', endtime: '2009-01-09T05:01:07',
    mismatch: [{ start: '2009-01-09T04:55:00+00:00', end: '2009-01-09T04:57:00+00:00' }] };
  const html = renderDetail(old);
  assert.match(html, /class="tl-gap-solid"/);
  assert.doesNotMatch(html, /class="tl-av"/);   // no two-lane chart without coverage
});

import { buildDataselectUrl } from './viewer.core.js';
test('buildDataselectUrl returns the stored url when present', () => {
  assert.equal(buildDataselectUrl({ url: 'https://h/availability/1/query?x', dataselect_url: 'https://h/ds?y' }), 'https://h/ds?y');
});
test('buildDataselectUrl derives dataselect from an availability url', () => {
  const ds = buildDataselectUrl({
    url: 'https://eida.gein.noa.gr/fdsnws/availability/1/query?network=HP&station=EFP&location=*&channel=HHE&start=2015-04-29T21:29:38&end=2015-04-29T21:39:38&format=text',
    network: 'HP', station: 'EFP', location: '', channel: 'HHE',
    starttime: '2015-04-29T21:29:38', endtime: '2015-04-29T21:39:38' });
  assert.match(ds, /\/fdsnws\/dataselect\/1\/query\?/);
  assert.match(ds, /network=HP&station=EFP&location=&channel=HHE/);
  assert.match(ds, /starttime=2015-04-29T21:29:38&endtime=2015-04-29T21:39:38&nodata=204/);
});
test('buildDataselectUrl returns null without a usable url', () => {
  assert.equal(buildDataselectUrl({}), null);
  assert.equal(buildDataselectUrl({ url: 'https://h/other/1/query?x' }), null);
});
test('renderDetail offers a dataselect run button for coverage-less reports', () => {
  const old = { index: 9, network: 'HP', station: 'EFP', location: '', channel: 'HHE', consistent: false,
    url: 'https://eida.gein.noa.gr/fdsnws/availability/1/query?network=HP&station=EFP&location=*&channel=HHE&start=2015-04-29T21:29:38&end=2015-04-29T21:39:38&format=text',
    starttime: '2015-04-29T21:29:38', endtime: '2015-04-29T21:39:38',
    mismatch: [{ start: '2015-04-29T21:29:38+00:00', end: '2015-04-29T21:39:38+00:00' }] };
  const html = renderDetail(old);
  assert.match(html, /data-kind="dataselect"/);
  assert.match(html, /\/fdsnws\/dataselect\/1\/query/);
});

// ── PSD triangle (Availability / Dataselect / PSD) ────────────────────────
import { psdChecked, psdVerdict, psdTriad, psdCounts } from './viewer.core.js';

const psdViolation = {
  index: 9, network: 'IV', station: 'CESX', location: '', channel: 'HHZ',
  available: true, dataselect_success: true, consistent: true, mismatch: [],
  psd_status: 'Inconsistent', psd_present: false, psd_required: true, psd_consistent: false,
  starttime: '2025-01-05T05:55:50', endtime: '2025-01-05T06:05:50',
  coverage: { availability: [], dataselect: [] },
};
const psdPregap = { ...psdViolation, index: 10, psd_required: false,
  starttime: '2011-01-01T00:00:00', endtime: '2011-01-01T00:10:00' };
const psdOk = { ...psdViolation, index: 11, psd_present: true, psd_consistent: true,
  psd_status: 'Consistent',
  coverage: { availability: [], dataselect: [], psd: [['2025-01-05T00:00:00Z', '2025-01-06T00:00:01Z']] } };
const noPsd = { index: 12, network: 'HL', station: 'X', location: '', channel: 'HHZ',
  available: true, dataselect_success: true, consistent: true, mismatch: [] };

test('psdChecked true only when psd_status present', () => {
  assert.equal(psdChecked(psdOk), true);
  assert.equal(psdChecked(noPsd), false);
});

test('psdVerdict distinguishes violation, pre-2024 gap, consistent, none', () => {
  assert.equal(psdVerdict(psdViolation).cls, 'bad');
  assert.match(psdVerdict(psdViolation).text, /violation/);
  assert.equal(psdVerdict(psdPregap).cls, 'warn');
  assert.match(psdVerdict(psdPregap).text, /pre-2024/);
  assert.equal(psdVerdict(psdOk).cls, 'ok');
  assert.equal(psdVerdict(noPsd), null);
});

test('psdTriad renders filled/hollow triangles', () => {
  assert.equal(psdTriad(psdViolation), '▼ ▲ ▷');  // avail+data present, PSD absent
  assert.equal(psdTriad(psdOk), '▼ ▲ ▶');
});

test('psdCounts rolls up the PSD dimension', () => {
  const c = psdCounts([psdViolation, psdPregap, psdOk, noPsd]);
  assert.equal(c.checked, 3);
  assert.equal(c.violations, 1);
  assert.equal(c.pregaps, 1);
  assert.equal(c.consistent, 1);
});

test('renderSummary shows PSD chips when records carry PSD', () => {
  const html = renderSummary({ node: 'IV', score: 70 }, [psdViolation, psdPregap, psdOk]);
  assert.match(html, /1 violations/);
  assert.match(html, /pre-2024 gaps/);
});

test('renderSummary omits PSD chips for pre-PSD reports', () => {
  const html = renderSummary({ node: 'X', score: 80 }, [noPsd]);
  assert.doesNotMatch(html, /PSD/);
});

test('renderResultsTable adds a PSD column with the triad when data present', () => {
  const html = renderResultsTable([psdViolation], { onlyInconsistent: false, direction: 'both', search: '' });
  assert.match(html, /PSD/);
  assert.match(html, /▼ ▲ ▷/);
});

test('renderResultsTable has no PSD column for pre-PSD reports', () => {
  const html = renderResultsTable([noPsd], { onlyInconsistent: false, direction: 'both', search: '' });
  assert.doesNotMatch(html, /PSD/);
});

test('renderDetail shows the PSD line when checked', () => {
  const html = renderDetail(psdOk);
  assert.match(html, /psd-line/);
  assert.match(html, /PSD consistent/);
});

import { psdLegend } from './viewer.core.js';

test('matchesFilter psd=violation shows >=2024 data-without-PSD even when A-D consistent', () => {
  const f = { onlyInconsistent: true, direction: 'both', psd: 'violation', search: '' };
  assert.equal(matchesFilter(psdViolation, f), true);
  assert.equal(matchesFilter(psdPregap, f), false);
  assert.equal(matchesFilter(psdOk, f), false);
});

test('matchesFilter psd=pregap / psd=consistent select their categories', () => {
  assert.equal(matchesFilter(psdPregap, { psd: 'pregap' }), true);
  assert.equal(matchesFilter(psdViolation, { psd: 'pregap' }), false);
  assert.equal(matchesFilter(psdOk, { psd: 'consistent' }), true);
  assert.equal(matchesFilter(psdViolation, { psd: 'consistent' }), false);
});

test('matchesFilter psd=all keeps the normal onlyInconsistent behavior', () => {
  assert.equal(matchesFilter(psdOk, { onlyInconsistent: true, psd: 'all' }), false);
  assert.equal(matchesFilter(psdOk, { onlyInconsistent: false, psd: 'all' }), true);
});

test('renderResultsTable includes the PSD legend when data present, omits it otherwise', () => {
  const withPsd = renderResultsTable([psdViolation], { onlyInconsistent: false, direction: 'both', search: '' });
  assert.match(withPsd, /psd-legend/);
  assert.match(withPsd, /PSD triangle/);
  const without = renderResultsTable([noPsd], { onlyInconsistent: false, direction: 'both', search: '' });
  assert.doesNotMatch(without, /psd-legend/);
});

test('psdLegend explains the glyphs', () => {
  const l = psdLegend();
  assert.match(l, /Availability/);
  assert.match(l, /Dataselect/);
  assert.match(l, /filled = has data/);
});
