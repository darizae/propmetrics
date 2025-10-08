const qs = sel => document.querySelector(sel);
const qsa = sel => Array.from(document.querySelectorAll(sel));

const state = {
  lastSpec: null,     // QuerySpec used for /aggregate and for /download
  lastEcho: null,     // filters_echo from response
  lastRows: [],       // data[]
  lastRowCount: 0,    // row_count
};

function showSpinner(on) { qs('#spinner').classList.toggle('hidden', !on); }

function clearErrors() { qs('#errors').textContent = ''; }
function showError(err) {
  const out = typeof err === 'string' ? {message: err} : err;
  qs('#errors').textContent = JSON.stringify(out, null, 2);
}

function setDownloadEnabled(on) { qs('#download').disabled = !on; }

function parseCSVFileName(spec) {
  const g = spec.groupby || 'none';
  const start = spec.date_range?.start || 'start';
  const end = spec.date_range?.end || 'end';
  return `aggregate_${g}_${start}_${end}.csv`.replace(/[^\w\.\-]+/g, '_');
}

function specFromAdvanced() {
  if (!qs('#adv').open) return null;
  const start = qs('#start').value || '2011-01-01';
  const end = qs('#end').value || '2030-12-31';
  const parseList = (s) => {
    const v = (s || '').split(',').map(x => x.trim()).filter(Boolean);
    return v.length ? v : null;
  };
  const muni = parseList(qs('#municipality').value);
  const lu = parseList(qs('#land_use').value);
  const plz = parseList(qs('#plz').value);
  const groupby = qs('#groupby').value || 'none';
  return { date_range: { start, end }, groupby, ...(muni ? {municipality: muni} : {}), ...(lu ? {land_use: lu} : {}), ...(plz ? {plz} : {}) };
}

function specFromEcho(echo) {
  if (!echo || !echo.date_range) return null;
  const out = {
    date_range: { start: echo.date_range.start, end: echo.date_range.end },
    groupby: echo.groupby || 'none'
  };
  if (echo.municipality) out.municipality = echo.municipality;
  if (echo.land_use) out.land_use = echo.land_use;
  if (echo.plz) out.plz = echo.plz;
  return out;
}

async function postJSON(path, payload) {
  const r = await fetch(path, { method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify(payload) });
  const ct = r.headers.get('content-type') || '';
  if (!r.ok) {
    let detail = {};
    try { detail = ct.includes('application/json') ? await r.json() : {text: await r.text()}; } catch(e) {}
    throw { status: r.status, path, detail };
  }
  return ct.startsWith('application/json') ? await r.json() : await r.text();
}

function renderEcho(obj) {
  qs('#echo').textContent = JSON.stringify(obj || {}, null, 2);
}

function renderMeta(rowCount, headers) {
  const parts = [`rows: ${rowCount}`];
  if (headers) {
    const xc = headers.get('x-cache');
    if (xc) parts.push(`cache: ${xc}`);
  }
  qs('#meta').textContent = parts.join(' · ');
}

function renderTable(rows) {
  const mount = qs('#result');
  if (!rows || !rows.length) {
    mount.innerHTML = '<p>No rows</p>';
    return;
  }
  const cols = [...new Set(rows.flatMap(r => Object.keys(r)))];
  const thead = `<thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead>`;
  const tbody = `<tbody>${rows.map(r => `<tr>${cols.map(c => `<td>${r[c] ?? ''}</td>`).join('')}</tr>`).join('')}</tbody>`;
  mount.innerHTML = `<table>${thead}${tbody}</table>`;
}

async function runQuery() {
  clearErrors();
  setDownloadEnabled(false);
  showSpinner(true);
  try {
    // Manual advanced spec takes precedence
    const adv = specFromAdvanced();
    if (adv) {
      const res = await fetch('/aggregate', { method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify(adv) });
      const body = await res.json();
      state.lastSpec = adv;
      state.lastEcho = body.filters_echo || null;
      state.lastRows = body.data || [];
      state.lastRowCount = body.row_count || 0;
      renderEcho(adv);
      renderMeta(state.lastRowCount, res.headers);
      renderTable(state.lastRows);
      setDownloadEnabled(true);
      return;
    }

    // NL mode: Parser or LLM front
    const prompt = qs('#prompt').value || '';
    const mode = qsa('input[name="mode"]').find(x => x.checked).value;

    if (mode === 'parser') {
      const pr = await fetch('/intent/parse', { method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify({ text: prompt }) });
      const p = await pr.json();
      const spec = p.spec || { date_range: { start: '2011-01-01', end: '2030-12-31' }, groupby: 'none' };
      renderEcho(spec);
      const ar = await fetch('/aggregate', { method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify(spec) });
      const body = await ar.json();
      state.lastSpec = spec;
      state.lastEcho = body.filters_echo || null;
      state.lastRows = body.data || [];
      state.lastRowCount = body.row_count || 0;
      renderMeta(state.lastRowCount, ar.headers);
      renderTable(state.lastRows);
      setDownloadEnabled(true);
      return;
    } else {
      const lr = await fetch('/llm/ask', { method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify({ text: prompt }) });
      if (!lr.ok) throw { status: lr.status, path: '/llm/ask', detail: await lr.json().catch(() => ({})) };
      const body = await lr.json();
      state.lastEcho = body.filters_echo || null;
      state.lastRows = body.data || [];
      state.lastRowCount = body.row_count || 0;
      // Reconstruct a valid QuerySpec for downloads from filters_echo
      const spec = specFromEcho(state.lastEcho) || { date_range: { start: '2011-01-01', end: '2030-12-31' }, groupby: 'none' };
      state.lastSpec = spec;
      renderEcho(body.filters_echo || {});
      renderMeta(state.lastRowCount, lr.headers);
      renderTable(state.lastRows);
      setDownloadEnabled(true);
      return;
    }
  } catch (e) {
    showError(e);
  } finally {
    showSpinner(false);
  }
}

async function downloadCSV() {
  clearErrors();
  const spec = state.lastSpec || specFromAdvanced() || specFromEcho(state.lastEcho);
  if (!spec) { showError('No spec to download'); return; }
  try {
    const r = await fetch('/download', { method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify(spec) });
    if (!r.ok) throw { status: r.status, path: '/download', detail: await r.text() };
    const blob = await r.blob();
    const a = document.createElement('a');
    const url = URL.createObjectURL(blob);
    a.href = url;
    a.download = parseCSVFileName(spec);
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    showError(e);
  }
}

function wire() {
  qs('#run').addEventListener('click', (e) => { e.preventDefault(); runQuery(); });
  qs('#download').addEventListener('click', (e) => { e.preventDefault(); downloadCSV(); });
  // Improve UX: hitting Enter in prompt triggers Run
  qs('#prompt').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); runQuery(); }});
}

document.addEventListener('DOMContentLoaded', wire);
