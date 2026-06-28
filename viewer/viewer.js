// viewer/viewer.js
import { renderSummary, renderResultsTable, renderDetail, runRequest, sortRecords } from './viewer.core.js';

const $ = sel => document.querySelector(sel);
const state = { report: null, filter: { onlyInconsistent: true, direction: 'both', search: '' }, sort: 'time' };

function paint() {
  $('#summary').innerHTML = renderSummary(state.report.summary);
  $('#results').innerHTML = renderResultsTable(sortRecords(state.report.results, state.sort), state.filter);
}

function wire() {
  $('#onlyInc').addEventListener('change', e => { state.filter.onlyInconsistent = e.target.checked; paint(); });
  $('#dir').addEventListener('change', e => { state.filter.direction = e.target.value; paint(); });
  $('#search').addEventListener('input', e => { state.filter.search = e.target.value; paint(); });
  $('#sort').addEventListener('change', e => { state.sort = e.target.value; paint(); });
  $('#results').addEventListener('click', e => {
    const tr = e.target.closest('tr[data-index]'); if (!tr) return;
    const rec = state.report.results.find(r => String(r.index) === tr.dataset.index);
    $('#detail').innerHTML = renderDetail(rec);
    tr.classList.add('sel');
    $('#results').querySelectorAll('tr.sel').forEach(o => { if (o !== tr) o.classList.remove('sel'); });
  });
  $('#detail').addEventListener('click', async e => {
    const b = e.target.closest('button[data-kind]'); if (!b) return;
    b.textContent = '…';
    const r = await runRequest(b.dataset.kind, b.dataset.url, fetch);
    b.insertAdjacentHTML('afterend', `<span class="result"> ${r.summary}</span>`);
    b.textContent = `Run ${b.dataset.kind}`;
  });
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
