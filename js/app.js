// FINN prototype: Push (digest + alerts), Pull (research), Network (who can help).
// All data is from js/data.js (synthetic demo). Logic below is the part that matters.

const state = {
  tab: 'push',
  windowHours: 24,
  alerts: loadAlerts(),
  netQuery: '',
};

// ---------- scoring ----------
// Priority per category, 0-100. This is the "what earns my attention" judgment.
const CATEGORY_WEIGHT = {
  'M&A': 88, 'Results': 85, 'Management change': 80, 'Litigation': 72,
  'Capex / Expansion': 66, 'Credit rating': 35, 'Board meeting': 25,
  'Shareholding': 12, 'Trading window': 8, 'Other': 20,
};
// Routine items collapse into a row instead of cards.
const ROUTINE_BELOW = 30;

function priority(a) {
  let p = CATEGORY_WEIGHT[a.category] ?? 20;
  if (a.fin) p += 5;                       // results carry numbers, so they rank higher
  if (state.alerts.categories.includes(a.category)) p += 5; // the investor said they care
  return Math.min(100, p);
}

// ---------- helpers ----------
const inr = n => '₹' + Math.round(n).toLocaleString('en-IN') + ' cr';
const pct = x => (x >= 0 ? '+' : '') + (x * 100).toFixed(1) + '%';
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const ago = h => h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;

function loadAlerts() {
  try { return { ...DEFAULT_ALERTS, ...JSON.parse(localStorage.getItem('finn-alerts') || '{}') }; }
  catch { return { ...DEFAULT_ALERTS }; }
}
function saveAlerts() { try { localStorage.setItem('finn-alerts', JSON.stringify(state.alerts)); } catch {} }

// ---------- network ----------
// Contacts who have a relation to a ticker (current, former, peer, supplier, customer).
function contactsFor(ticker) {
  return PEOPLE
    .map(p => ({ p, rel: p.companies.find(c => c.t === ticker) }))
    .filter(x => x.rel)
    .sort((a, b) => b.p.strength - a.p.strength);
}

// Given a person named in a filing, who in the network overlaps with them?
// Overlap = shared employer, shared school, or a direct link to someone who knows them.
function overlapsWith(person) {
  if (!person) return [];
  const employers = new Set(person.prior.map(x => x.org.toLowerCase()));
  const hits = [];
  for (const c of PEOPLE) {
    const reasons = [];
    const past = c.pastEmployers.map(s => s.toLowerCase());
    for (const e of employers) if (past.some(x => x.includes(e) || e.includes(x))) reasons.push(`worked at ${[...employers].find(e2 => past.some(x => x.includes(e2) || e2.includes(x)))}`);
    if (person.school && c.school === person.school) reasons.push(`studied at ${person.school}`);
    if (reasons.length) hits.push({ c, reasons, degree: 1 });
  }
  return hits;
}

// Best person to call about a material event at a company you have a link to.
function bestContactFor(ticker) {
  const list = contactsFor(ticker);
  if (!list.length) return null;
  const score = x => x.p.strength + (x.rel.rel.includes('current') ? 2 : 0) + (x.rel.rel.includes('former') ? 1 : 0);
  return list.sort((a, b) => score(b) - score(a))[0];
}

// ---------- push ----------
function visibleAnnouncements() {
  return ANNOUNCEMENTS
    .filter(a => a.hoursAgo <= state.windowHours)
    .filter(a => PORTFOLIO.some(c => c.ticker === a.ticker))
    .map(a => ({ ...a, score: priority(a) }))
    .sort((a, b) => b.score - a.score || a.hoursAgo - b.hoursAgo);
}

function renderResultsCard(a) {
  const f = a.fin;
  const row = (label, k) => {
    const [cur, prev, ya] = f[k];
    return `<tr><td>${label}</td><td>${inr(cur)}</td><td>${pct(cur / prev - 1)}</td><td>${pct(cur / ya - 1)}</td></tr>`;
  };
  return `<table class="fin"><thead><tr><th></th><th>${esc(f.period)}</th><th>QoQ</th><th>YoY</th></tr></thead><tbody>
    ${row('Revenue', 'rev')}${row('EBITDA', 'ebitda')}${row('PBT', 'pbt')}${row('PAT', 'pat')}
  </tbody></table><p class="muted small">Figures are synthetic demo values.</p>`;
}

function renderManagementCard(a) {
  const p = a.person;
  const hits = overlapsWith(p);
  const prior = p.prior.length
    ? p.prior.map(x => `<li>${esc(x.role)}, ${esc(x.org)} <span class="muted">(${esc(x.years)})</span></li>`).join('')
    : '<li class="muted">No prior history in the demo profile.</li>';
  const hitHtml = hits.length
    ? hits.map(h => `<li><b>${esc(h.c.name)}</b> — ${esc(h.reasons.join(', '))} <span class="muted">(${esc(h.c.met)})</span></li>`).join('')
    : '<li class="muted">No one in your network has worked with or studied with this person.</li>';
  return `<div class="bio"><div class="muted small">Incoming profile (demo)</div>
    <b>${esc(p.name)}</b> · ${esc(p.role)}${p.school ? ` · ${esc(p.school)}` : ''}
    <ul>${prior}</ul>
    <div class="label">In your network</div><ul>${hitHtml}</ul></div>`;
}

function renderMaterialEventCard(a) {
  const c = bestContactFor(a.ticker);
  if (!c) return '';
  return `<div class="callout"><b>Call ${esc(c.p.name)}</b> — ${esc(c.rel.rel)} at ${esc(nameOf(a.ticker))}. ${esc(c.p.now)}. Themes: ${esc(c.p.themes.join(', '))}.</div>`;
}

function renderItem(a) {
  const extra =
    a.category === 'Results' && a.fin ? renderResultsCard(a)
    : a.category === 'Management change' && a.person ? renderManagementCard(a)
    : ['M&A', 'Litigation', 'Capex / Expansion'].includes(a.category) ? renderMaterialEventCard(a)
    : '';
  return `<article class="card">
    <header><span class="tag">${esc(a.category)}</span><span class="muted small">${esc(a.ticker)} · ${ago(a.hoursAgo)}</span></header>
    <h3>${esc(a.title)}</h3>
    <p>${esc(a.summary)}</p>
    ${extra}
  </article>`;
}

function renderPush() {
  const items = visibleAnnouncements();
  const main = items.filter(a => a.score >= ROUTINE_BELOW);
  const routine = items.filter(a => a.score < ROUTINE_BELOW);
  const alerts = computeAlerts();
  return `
    <div class="seg">${[24, 72, 168, 720].map(h => `<button data-win="${h}" class="${state.windowHours === h ? 'on' : ''}">${{ 24: '24h', 72: '3d', 168: '7d', 720: '30d' }[h]}</button>`).join('')}</div>
    <h2>Alerts</h2>
    ${alerts.length ? alerts.map(x => `<div class="alert ${x.kind}"><b>${esc(x.ticker)}</b> ${x.text}</div>`).join('') : '<p class="muted">No alerts fired at your thresholds.</p>'}
    <h2>Digest <span class="muted small">${items.length} filings</span></h2>
    ${main.length ? main.map(renderItem).join('') : '<p class="muted">Nothing material in this window.</p>'}
    ${routine.length ? `<details class="routine"><summary>${routine.length} routine filings collapsed</summary>
      ${routine.map(a => `<div class="row"><span class="muted small">${esc(a.ticker)}</span> ${esc(a.title)}</div>`).join('')}</details>` : ''}
  `;
}

// ---------- alerts ----------
function computeAlerts() {
  const out = [];
  for (const c of PORTFOLIO) {
    const h = priceHistory(c.ticker);
    const last = h[h.length - 1];
    const prev = h[h.length - 2];
    const baseVol = avgVol(h.slice(0, -1));
    const volRatio = last.volume / baseVol;
    const move = last.close / prev.close - 1;
    if (volRatio >= state.alerts.volMult)
      out.push({ ticker: c.ticker, kind: 'vol', text: `volume ${volRatio.toFixed(1)}× its 30-day average (threshold ${state.alerts.volMult}×)` });
    if (Math.abs(move) * 100 >= state.alerts.pctMove)
      out.push({ ticker: c.ticker, kind: 'px', text: `moved ${pct(move)} today (threshold ±${state.alerts.pctMove}%)` });
  }
  return out;
}

function renderAlertSettings() {
  const a = state.alerts;
  const cats = Object.keys(CATEGORY_WEIGHT).map(c => `<label class="chk"><input type="checkbox" data-cat="${esc(c)}" ${a.categories.includes(c) ? 'checked' : ''}> ${esc(c)}</label>`).join('');
  return `<h2>Your thresholds</h2>
    <label class="slider">Volume above <b id="vm">${a.volMult.toFixed(1)}</b>× average
      <input type="range" id="volMult" min="1.2" max="4" step="0.1" value="${a.volMult}"></label>
    <label class="slider">Price move beyond ±<b id="pm">${a.pctMove.toFixed(1)}</b>%
      <input type="range" id="pctMove" min="1" max="10" step="0.5" value="${a.pctMove}"></label>
    <p class="muted small">Announcement types that trigger a push alert:</p>
    <div class="chks">${cats}</div>`;
}

// ---------- pull ----------
function renderPull(ticker) {
  const co = COMPANIES.find(c => c.ticker === ticker);
  if (!co) return `<p class="muted">Type a NSE ticker above, e.g. TCS or DIVISLAB.</p>`;
  const d = PULL_DATA[ticker];
  const g = GUIDANCE_CHECK[ticker];
  const h = priceHistory(ticker);
  const last = h[h.length - 1];
  const spark = sparkline(h.map(x => x.close));
  const fin = ANNOUNCEMENTS.filter(a => a.ticker === ticker && a.fin)[0];
  const cached = !!d;
  return `<h2>${esc(co.name)} <span class="muted small">${esc(ticker)} · ${esc(co.sector)}</span></h2>
    <div class="px"><b>₹${last.close.toLocaleString('en-IN')}</b> ${spark}</div>
    ${cached ? `
      <section><h3>Business snapshot</h3><p>${esc(d.business)}</p></section>
      ${fin ? `<section><h3>Financial snapshot</h3>${renderResultsCard(fin)}</section>` : ''}
      ${g ? `<section><h3>Numbers vs. narrative <span class="muted small">last four quarters</span></h3>
        <table class="fin"><thead><tr><th>Qtr</th><th>Promised</th><th>Delivered</th><th>Verdict</th></tr></thead><tbody>
        ${g.map(r => `<tr><td>${esc(r.quarter)}</td><td>${esc(r.promised)}</td><td>${esc(r.delivered)}</td><td>${esc(r.verdict)}</td></tr>`).join('')}
        </tbody></table></section>` : ''}
      <section><h3>Bull vs. bear</h3>
        <div class="bull"><b>Bull</b> ${esc(d.bull)}</div>
        <div class="bear"><b>Bear</b> ${esc(d.bear)}</div></section>
      <section><h3>Who can help</h3>${contactsFor(ticker).map(x => `<div class="row"><b>${esc(x.p.name)}</b> · ${esc(x.rel.rel)} · <span class="muted">${esc(x.p.now)}</span></div>`).join('') || '<p class="muted">No one in your network is linked to this company.</p>'}</section>
    ` : `<p class="muted">No cached fundamentals for ${esc(ticker)} in this build. Run <code>scripts/fetch_fundamentals.py ${esc(ticker)}</code> to pull annual reports and transcripts. Until then FINN will not guess.</p>`}`;
}

function sparkline(vals) {
  const w = 120, hh = 32;
  const min = Math.min(...vals), max = Math.max(...vals);
  const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * w},${hh - ((v - min) / (max - min || 1)) * hh}`).join(' ');
  return `<svg width="${w}" height="${hh}" class="spark"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>`;
}

// ---------- network tab ----------
function renderNetwork() {
  const q = state.netQuery.toLowerCase();
  const people = PEOPLE.filter(p => !q || (p.name + p.now + p.themes.join(' ') + p.companies.map(c => c.t).join(' ')).toLowerCase().includes(q));
  const themes = {};
  for (const p of PEOPLE) for (const t of p.themes) (themes[t] ||= []).push(p.name.split(' ')[0]);
  return `<input class="search" id="netq" placeholder="Search: a name, company or theme" value="${esc(state.netQuery)}">
    <h2>Expertise map</h2>
    <div class="chips">${Object.entries(themes).map(([t, names]) => `<span class="chip">${esc(t)} <span class="muted">${names.join(', ')}</span></span>`).join('')}</div>
    <h2>Who can help <span class="muted small">${people.length} people</span></h2>
    ${people.map(p => `<article class="card">
      <header><b>${esc(p.name)}</b><span class="muted small">strength ${p.strength}/5</span></header>
      <div class="muted small">${esc(p.now)} · ${esc(p.school)}</div>
      <div class="small">Met: ${esc(p.met)}</div>
      <div class="small">Worked at: ${esc(p.pastEmployers.join(', '))}</div>
      <div class="small">Can speak to: ${p.companies.map(c => `${esc(c.t)} (${esc(c.rel)})`).join(', ')}</div>
    </article>`).join('')}`;
}

// ---------- shell ----------
function render() {
  const app = document.getElementById('view');
  const tabs = [['push', 'Push'], ['pull', 'Pull'], ['network', 'Network'], ['settings', 'Alerts']];
  let body = '';
  if (state.tab === 'push') body = renderPush();
  if (state.tab === 'pull') body = `<div class="search-row"><input id="tkr" list="tickers" placeholder="Ticker, e.g. TCS" value="${esc(state.ticker || '')}"><button id="go">Research</button></div>
    <datalist id="tickers">${COMPANIES.map(c => `<option value="${c.ticker}">${esc(c.name)}</option>`).join('')}</datalist>
    ${renderPull(state.ticker || '')}`;
  if (state.tab === 'network') body = renderNetwork();
  if (state.tab === 'settings') body = renderAlertSettings();
  app.innerHTML = body;
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('on', b.dataset.tab === state.tab));
  document.querySelectorAll('[data-win]').forEach(b => b.onclick = () => { state.windowHours = +b.dataset.win; render(); });
  const go = document.getElementById('go');
  if (go) go.onclick = () => { state.ticker = document.getElementById('tkr').value.trim().toUpperCase(); render(); };
  const nq = document.getElementById('netq');
  if (nq) nq.oninput = e => { state.netQuery = e.target.value; render(); document.getElementById('netq').focus(); };
  document.querySelectorAll('[data-cat]').forEach(c => c.onchange = () => {
    const cat = c.dataset.cat;
    state.alerts.categories = c.checked ? [...new Set([...state.alerts.categories, cat])] : state.alerts.categories.filter(x => x !== cat);
    saveAlerts(); render();
  });
  for (const id of ['volMult', 'pctMove']) {
    const el = document.getElementById(id);
    if (el) el.oninput = e => { state.alerts[id] = +e.target.value; saveAlerts(); render(); };
  }
}

document.querySelectorAll('nav button').forEach(b => b.onclick = () => { state.tab = b.dataset.tab; render(); });
render();
