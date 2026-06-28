// viewer/viewer.js
import { renderSummary, renderResultsTable, renderDetail, runRequest } from './viewer.core.js';

const $ = sel => document.querySelector(sel);
const state = { report: null, filter: { onlyInconsistent: true, direction: 'both', search: '' } };

function paint() {
  $('#summary').innerHTML = renderSummary(state.report.summary);
  $('#results').innerHTML = renderResultsTable(state.report.results, state.filter);
}

function wire() {
  $('#onlyInc').addEventListener('change', e => { state.filter.onlyInconsistent = e.target.checked; paint(); });
  $('#dir').addEventListener('change', e => { state.filter.direction = e.target.value; paint(); });
  $('#search').addEventListener('input', e => { state.filter.search = e.target.value; paint(); });
  $('#results').addEventListener('click', e => {
    const tr = e.target.closest('tr[data-index]'); if (!tr) return;
    const rec = state.report.results.find(r => String(r.index) === tr.dataset.index);
    $('#detail').innerHTML = renderDetail(rec);
    $('#detail').querySelectorAll('.timeline').forEach(drawTimeline);
  });
  $('#detail').addEventListener('click', async e => {
    const b = e.target.closest('button[data-kind]'); if (!b) return;
    b.textContent = '…';
    const r = await runRequest(b.dataset.kind, b.dataset.url, fetch);
    b.insertAdjacentHTML('afterend', `<span class="result"> ${r.summary}</span>`);
    b.textContent = `Run ${b.dataset.kind}`;
  });
}

function drawTimeline(el) {
  const model = JSON.parse(el.dataset.timeline);
  const color = { both: '#2e7d32', availability: '#c62828', dataselect: '#1565c0', none: 'transparent' };
  el.innerHTML = model.segments.map(s =>
    `<i style="left:${s.x0 * 100}%;width:${(s.x1 - s.x0) * 100}%;background:${color[s.kind]}"></i>`).join('')
    + model.boundaries.map(x => `<b style="left:${x * 100}%"></b>`).join('');
}

async function main() {
  const url = new URLSearchParams(location.search).get('report');
  if (!url) { $('#results').textContent = 'No ?report=… given.'; return; }
  try {
    state.report = await (await fetch(url)).json();
  } catch { $('#results').textContent = 'Could not load report JSON.'; return; }
  wire(); paint();
}
main();
