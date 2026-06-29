// viewer/viewer.js
import { renderSummary, renderResultsTable, renderDetail, renderIndex, runRequest, sortRecords } from './viewer.core.js';

const $ = sel => document.querySelector(sel);
const state = { report: null, filter: { onlyInconsistent: true, direction: 'both', search: '' }, sort: { key: 'gap', dir: 'desc' } };

function paint() {
  $('#summary').innerHTML = renderSummary(state.report.summary);
  $('#results').innerHTML = renderResultsTable(sortRecords(state.report.results, state.sort.key, state.sort.dir), state.filter, state.sort);
}

function setSort(key) {
  if (state.sort.key === key) state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
  else state.sort = { key, dir: key === 'gap' ? 'desc' : 'asc' };
  paint();
}

function wire() {
  $('#onlyInc').addEventListener('change', e => { state.filter.onlyInconsistent = e.target.checked; paint(); });
  $('#dir').addEventListener('change', e => { state.filter.direction = e.target.value; paint(); });
  $('#search').addEventListener('input', e => { state.filter.search = e.target.value; paint(); });
  $('#results').addEventListener('click', e => {
    const th = e.target.closest('th[data-sort]');
    if (th) { setSort(th.dataset.sort); return; }
    const tr = e.target.closest('tr[data-index]'); if (!tr) return;
    const rec = state.report.results.find(r => String(r.index) === tr.dataset.index);
    $('#detail').innerHTML = renderDetail(rec);
    tr.classList.add('sel');
    $('#results').querySelectorAll('tr.sel').forEach(o => { if (o !== tr) o.classList.remove('sel'); });
  });
  $('#detail').addEventListener('click', async e => {
    const copy = e.target.closest('button[data-copy]');
    if (copy) {
      try { await navigator.clipboard.writeText(copy.dataset.copy); copy.textContent = 'copied'; setTimeout(() => copy.textContent = 'copy', 1200); }
      catch { copy.textContent = 'copy failed'; }
      return;
    }
    const b = e.target.closest('button[data-kind]'); if (!b) return;
    b.textContent = '…';
    const r = await runRequest(b.dataset.kind, b.dataset.url, fetch);
    b.insertAdjacentHTML('afterend', `<span class="result"> ${r.summary}</span>`);
    b.textContent = `Run ${b.dataset.kind}`;
  });
}

function emptyForm(msg) {
  return `<section class="loader">
    <h1>EIDA consistency viewer</h1>
    <p>${msg}</p>
    <form id="loadForm"><input id="loadUrl" type="url" placeholder="paste a report .json URL (e.g. an Oculus report)" size="60">
      <button type="submit">Load</button></form>
  </section>`;
}

function wireLoader() {
  const form = $('#loadForm'); if (!form) return;
  form.addEventListener('submit', e => {
    e.preventDefault();
    const u = $('#loadUrl').value.trim();
    if (u) location.search = '?report=' + encodeURIComponent(u);
  });
}

async function showLanding() {
  $('#toolbar').style.display = 'none';
  try {
    const idx = await (await fetch('index.json')).json();
    const entries = Array.isArray(idx) ? idx : (idx.reports || []);
    $('#results').innerHTML = renderIndex(entries) + emptyForm('Or load any report by URL:');
  } catch {
    $('#results').innerHTML = emptyForm('No report selected. Open one from Oculus, or load it by URL.');
  }
  wireLoader();
}

async function main() {
  const url = new URLSearchParams(location.search).get('report');
  if (!url) { await showLanding(); return; }
  try {
    state.report = await (await fetch(url)).json();
  } catch { $('#results').innerHTML = emptyForm('Could not load that report. Check the URL (and CORS if it is on another host).'); wireLoader(); return; }
  $('#toolbar').style.display = '';
  wire(); paint();
}
main();
