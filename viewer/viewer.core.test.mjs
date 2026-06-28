import { test } from 'node:test';
import assert from 'node:assert/strict';
import { queryTime, swapQueryTime, gapQueries } from './viewer.core.js';

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
