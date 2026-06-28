import { test } from 'node:test';
import assert from 'node:assert/strict';
import { queryTime, swapQueryTime, gapQueries, recordDirections, matchesFilter, timelineModel } from './viewer.core.js';

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
