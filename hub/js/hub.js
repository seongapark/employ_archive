import { loadJson } from '../core/shell.js';
import { DOMAINS, domainState, updatedLabel } from './state.js';

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

async function render() {
  const list = document.getElementById('domains');
  if (!list) return;

  for (const d of DOMAINS) {
    const lastRun = await loadJson(`./${d.slug}/data/last_run.json`);
    const ready = domainState(lastRun) === 'ready';

    const el = document.createElement(ready ? 'a' : 'div');
    el.className = ready ? 'domain' : 'domain domain--pending';
    if (ready) el.href = `./${d.slug}/`;
    el.innerHTML = `
      <div class="domain__name">${esc(d.name)}</div>
      <div class="domain__desc">${esc(d.desc)}</div>
      <div class="domain__meta num">${esc(updatedLabel(lastRun))}</div>`;
    list.appendChild(el);
  }
}

render();
