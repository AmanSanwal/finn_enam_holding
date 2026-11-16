/* FINN — mobile-first client. Vanilla JS, no build step. Reads data/snapshot.json (static mode) and,
   when the FINN API is reachable, does live research on any NSE ticker. */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n, d = 0) => (n == null || isNaN(n) ? "—" : Number(n).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }));
  const pct = (n, d = 0) => (n == null ? "—" : `${n > 0 ? "+" : ""}${fmt(n, d)}%`);
  const cls = (n) => (n == null ? "" : n >= 0 ? "d-up" : "d-down");
  const initials = (n) => n.replace(/^(Dr\.|Mr\.|Ms\.)\s*/, "").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const ICON = {
    gear: '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>',
    brief: '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round"><path d="M5 5h14M5 10h14M5 15h9M5 20h6"/></svg>',
    ask: '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg>',
    net: '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="2.5"/><circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="18" r="2"/><path d="M10.2 10.5L6.5 7.4M13.8 10.5l3.7-3.1M10.4 13.9L7.3 17.4M13.9 13.8l2.7 2.9"/></svg>',
    link: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><path d="M9 15l6-6M10 6.5l1.5-1.5a4.2 4.2 0 016 6L16 12.5M14 17.5L12.5 19a4.2 4.2 0 01-6-6L8 11.5"/></svg>',
  };
  const WINDOWS = [["24h", 1], ["3 days", 3], ["7 days", 7], ["14 days", 14], ["30 days", 30]];
  const CATS = [["results", "Results"], ["management", "Management"], ["mna", "M&A / JV"], ["litigation", "Litigation"], ["capex", "Capex"], ["fundraise", "Fund raise"], ["orders", "Orders"]];

  const S = {
    data: null, research: {}, live: false, window: 1, openWhy: new Set(), showRules: {},
    prefs: { vol_mult: 2, price_pct: 4, categories: ["results", "management", "mna", "litigation"] },
  };
  try { Object.assign(S.prefs, JSON.parse(localStorage.getItem("finn.prefs") || "{}")); } catch (e) { /* storage unavailable */ }
  try { S.window = Number(localStorage.getItem("finn.window")) || 1; } catch (e) { /* ignore */ }
  const save = () => { try { localStorage.setItem("finn.prefs", JSON.stringify(S.prefs)); localStorage.setItem("finn.window", S.window); } catch (e) { /* ignore */ } };

  /* ------------------------------------------------------------------ data */
  const asOf = () => new Date(S.data.as_of);
  const ago = (ts) => {
    if (!ts) return "";
    const h = (asOf() - new Date(ts)) / 36e5;
    if (h < 1) return "just now";
    if (h < 24) return `${Math.round(h)}h ago`;
    const d = Math.round(h / 24);
    return d === 1 ? "yesterday" : `${d}d ago`;
  };
  const inWindow = (ts) => ts && (asOf() - new Date(ts)) / 864e5 <= S.window + 0.01;
  const company = (sym) => S.data.portfolio.find((p) => p.symbol === sym) || { symbol: sym, name: sym };
  const contact = (id) => S.data.network.contacts.find((c) => c.id === id);
  const shortName = (n) => (n || "").replace(/\s+(Ltd|Limited|India|Industries|Technologies|Technology)\b.*$/i, "").replace(/^The\s+/, "");

  function rescore(e) {
    // user preferences shift priority live: a followed category gets +5, an unfollowed material one -10
    let s = e.score;
    const followed = S.prefs.categories.includes(e.category);
    if (["results", "management", "mna", "litigation", "capex", "fundraise", "orders"].includes(e.category)) s += followed ? 5 : -10;
    return Math.max(0, Math.min(99, s));
  }
  const tierOf = (s) => (s >= 75 ? "top" : s >= 30 ? "watch" : "buried");

  function priceAlerts() {
    const out = [];
    const days = S.window;
    const cutoff = new Date(asOf()); cutoff.setDate(cutoff.getDate() - days);
    for (const [sym, rows] of Object.entries(S.data.prices)) {
      for (let i = 21; i < rows.length; i++) {
        const [d, c, v] = rows[i];
        if (new Date(d + "T15:30:00+05:30") < cutoff) continue;
        const avg = rows.slice(i - 20, i).reduce((a, r) => a + r[2], 0) / 20;
        const chg = (c / rows[i - 1][1] - 1) * 100;
        const vm = avg ? v / avg : 0;
        const why = [];
        if (vm >= S.prefs.vol_mult) why.push(`volume ${fmt(vm, 1)}× 20-day avg`);
        if (Math.abs(chg) >= S.prefs.price_pct) why.push(`${pct(chg, 1)} on the day`);
        if (why.length) out.push({ sym, d, i, chg, vm, why, rows });
      }
    }
    return out.sort((a, b) => (b.d > a.d ? 1 : b.d < a.d ? -1 : Math.abs(b.chg) - Math.abs(a.chg)));
  }

  /* ------------------------------------------------------------------ small charts */
  function spark(rows, idx) {
    const seg = rows.slice(Math.max(0, idx - 40), idx + 1);
    const W = 112, H = 44, ps = seg.map((r) => r[1]), vs = seg.map((r) => r[2]);
    const lo = Math.min(...ps), hi = Math.max(...ps), vmax = Math.max(...vs);
    const x = (i) => (i / (seg.length - 1)) * (W - 4) + 2, y = (p) => 30 - ((p - lo) / (hi - lo || 1)) * 26;
    const line = ps.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join("");
    const bars = vs.map((v, i) => `<rect class="vb${i === seg.length - 1 ? " hot" : ""}" x="${(x(i) - 1).toFixed(1)}" y="${(H - (v / vmax) * 11).toFixed(1)}" width="2" height="${((v / vmax) * 11).toFixed(1)}"/>`).join("");
    return `<svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="40-day price and volume">${bars}<path class="ln" d="${line}"/><circle class="pt" cx="${x(seg.length - 1)}" cy="${y(ps[ps.length - 1])}" r="2.6"/></svg>`;
  }

  function barLine(periods, bars, line, { barLabel = "Revenue", lineLabel = "EBITDA margin %" } = {}) {
    const n = periods.length; if (!n) return "";
    const W = 340, H = 150, L = 6, R = 6, T = 14, B = 22, cw = (W - L - R) / n;
    const bmax = Math.max(1, ...bars.filter((v) => v != null).map(Math.abs));
    const lv = line.filter((v) => v != null), lmin = Math.min(...lv, 0), lmax = Math.max(...lv, 1);
    const by = (v) => T + (H - T - B) * (1 - Math.max(0, v) / bmax);
    const ly = (v) => T + 4 + (H - T - B - 8) * (1 - (v - lmin) / (lmax - lmin || 1));
    let g = `<line class="grid" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>`;
    periods.forEach((p, i) => {
      const v = bars[i]; const x = L + i * cw + cw * 0.18, w = cw * 0.64;
      if (v != null) g += `<rect class="${v < 0 ? "neg" : "bar"}" x="${x.toFixed(1)}" y="${by(Math.abs(v)).toFixed(1)}" width="${w.toFixed(1)}" height="${(H - B - by(Math.abs(v))).toFixed(1)}" rx="2"/>`;
      g += `<text x="${(L + i * cw + cw / 2).toFixed(1)}" y="${H - 7}" text-anchor="middle">${esc(String(p).replace(/^(\w{3}) 20(\d\d)$/, "$1 $2"))}</text>`;
    });
    const pts = line.map((v, i) => (v == null ? null : [L + i * cw + cw / 2, ly(v)])).filter(Boolean);
    if (pts.length > 1) {
      g += `<path class="lnA" d="${pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("")}"/>`;
      const last = pts[pts.length - 1]; const lastV = line.filter((v) => v != null).slice(-1)[0];
      g += `<circle cx="${last[0]}" cy="${last[1]}" r="3" fill="var(--signal)"/><text x="${Math.min(last[0], W - 24)}" y="${last[1] - 7}" text-anchor="middle" style="fill:var(--signal)">${fmt(lastV)}%</text>`;
    }
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(barLabel)} bars and ${esc(lineLabel)} line">${g}</svg>
      <div class="legend"><span><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:color-mix(in srgb,var(--accent) 70%,transparent)"></i> ${esc(barLabel)} (₹ cr)</span><span style="color:var(--signal)">— ${esc(lineLabel)}</span></div>`;
  }

  /* ------------------------------------------------------------------ cards */
  const metaLine = (e) => `<div class="meta"><span class="co">${esc(shortName(e.name))}</span><span class="pill ${e.tierNow === "top" ? "sig" : ""}">${esc(e.label)}</span><span>${ago(e.ts)}</span></div>`;
  const whyBtn = (e) => `<button class="why" data-why="${e.id}">Why this?</button>${S.openWhy.has(e.id) ? `<div class="whybox">Priority ${e.scoreNow}/100 · ${esc(e.label)}${e.why && e.why.length ? " · " + e.why.map(esc).join(" · ") : ""}${S.prefs.categories.includes(e.category) ? "" : " · not a category you follow"}. Source: ${esc(e.source)}${e.synthetic ? " (dated by the first results-related filing)" : ""}.</div>` : ""}`;
  const fileLink = (e) => (e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">Open filing ↗</a>` : "");

  function threadPeople(list, title = "Who can help") {
    if (!list || !list.length) return "";
    return `<div class="thread"><div class="lbl">${ICON.net}${esc(title)}</div>${list.map((w) => {
      const c = contact(w.contact);
      return `<div class="person-row" data-contact="${w.contact}"><div class="avatar net">${initials(w.name)}</div><div><b>${esc(w.name)}</b><small>${esc(w.why || w.evidence || "")}</small>${w.would_know ? `<small style="color:var(--muted)">Would know: ${esc(w.would_know)}</small>` : ""}</div><div title="Tie strength"><div class="meter"><i style="width:${Math.round((w.tie || c?.tie || 0) * 100)}%"></i></div></div></div>`;
    }).join("")}</div>`;
  }

  function personCard(e) {
    const ppl = (e.people || []).filter((p) => p.name);
    const lead = ppl[0];
    let body = "";
    if (lead) {
      const act = { appointed: "Appointed", resigned: "Resigned", ceased: "Exiting", demise: "Passed away", "re-appointed": "Re-appointed", changed: "Change" }[lead.action] || "Change";
      body += `<div class="person"><div class="avatar">${initials(lead.name)}</div><div><div class="nm">${esc(lead.name)} <span class="pill ${lead.action === "appointed" ? "" : "sig"}">${act}</span></div><div class="rl">${esc(lead.role || "")}${lead.years_experience ? ` · ${lead.years_experience} yrs experience` : ""}</div>
        ${lead.profile ? `<div class="quote clamp" data-clamp>${esc(lead.profile)}</div><div class="meta" style="font-size:11.5px">From the company's filing (SEBI-mandated brief profile) · tap to expand</div>` : ""}
        ${lead.credentials && lead.credentials.length ? `<div class="creds">${[...new Set(lead.credentials)].map((c) => `<span class="pill">${esc(c)}</span>`).join("")}</div>` : ""}</div></div>`;
      if (lead.links && lead.links.length) {
        const best = lead.links[0];
        body += `<div class="thread"><div class="lbl">${ICON.net}Your way in</div>
          <div class="path"><span class="node you">You</span><span class="edge${best.tie < 0.5 ? " weak" : ""}"></span><span class="node" data-contact="${best.contact}">${esc(best.name)}</span><span class="edge weak"></span><span class="node">${esc(lead.name)}</span></div>
          <div class="ev">${esc(best.name)} — ${esc(best.evidence)}. You last spoke ${ago(best.last_contact + "T12:00:00+05:30")}. <span class="pill net">inferred</span></div>
          ${lead.links.slice(1, 3).map((l) => `<div class="ev" style="margin-top:4px">Also: <a href="#" data-contact="${l.contact}">${esc(l.name)}</a> — ${esc(l.evidence)}</div>`).join("")}</div>`;
      } else if (lead.profile === undefined || !lead.career || !lead.career.length) {
        body += threadPeople(e.who_to_call, lead.action === "resigned" ? "Who'd know why" : "Closest to this company");
      }
      if (lead.ask) body += `<ul class="asks">${lead.ask.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>`;
      if (ppl.length > 1) body += `<div class="meta" style="margin-top:8px">Also in this filing: ${ppl.slice(1).map((p) => `${esc(p.name)}${p.role ? ` (${esc(p.role)})` : ""}`).join(", ")}</div>`;
    } else {
      body += threadPeople(e.who_to_call, "Closest to this company");
    }
    return `<article class="card is-top">${metaLine(e)}<h3>${esc(e.headline)}</h3>${body}<div class="actions">${fileLink(e)}<a href="#research-${e.symbol}">Research ${esc(e.symbol)}</a>${whyBtn(e)}</div></article>`;
  }

  function resultsTable(h) {
    if (!h) return "";
    const rows = h.metrics.map((m) => `<tr><td>${esc(m.label)}</td><td>${fmt(m.cur)}</td><td class="${cls(m.qoq)}">${pct(m.qoq)}</td><td class="${cls(m.yoy)}">${pct(m.yoy)}</td></tr>`).join("");
    const mg = h.margin ? `<tr><td>EBITDA margin</td><td>${fmt(h.margin.cur, 1)}%</td><td class="${cls(h.margin.qoq_bps)}">${h.margin.qoq_bps > 0 ? "+" : ""}${fmt(h.margin.qoq_bps)} bps</td><td class="${cls(h.margin.yoy_bps)}">${h.margin.yoy_bps > 0 ? "+" : ""}${fmt(h.margin.yoy_bps)} bps</td></tr>` : "";
    return `<table class="tbl"><thead><tr><th>${esc(h.period)} · ₹ cr</th><th>Actual</th><th>QoQ</th><th>YoY</th></tr></thead><tbody>${rows}${mg}</tbody></table>${h.read ? `<div class="read">${esc(h.read)}</div>` : ""}`;
  }

  const resultsCard = (e) => `<article class="card${e.tierNow === "top" ? " is-top" : ""}">${metaLine(e)}<h3>${esc(e.title)}</h3>${resultsTable(e.results)}${threadPeople(e.who_to_call, "Who to call about the quarter")}<div class="actions">${fileLink(e)}<a href="#research-${e.symbol}">Research ${esc(e.symbol)}</a>${whyBtn(e)}</div></article>`;

  const eventCard = (e) => `<article class="card is-top">${metaLine(e)}<h3>${esc(e.headline)}</h3>${e.facts && e.facts.length ? `<ul class="facts">${e.facts.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}${threadPeople((e.who_to_call || []).slice(0, 2), "Best person to call")}<div class="actions">${fileLink(e)}<a href="#research-${e.symbol}">Research ${esc(e.symbol)}</a>${whyBtn(e)}</div></article>`;

  const rowItem = (e) => `<div class="row"><div class="t"><b>${esc(shortName(e.name))}</b> · ${esc(e.headline)} <span class="pill">${esc(e.label)}</span></div><div class="tm">${ago(e.ts)}${e.url ? ` · <a href="${esc(e.url)}" target="_blank" rel="noopener">filing</a>` : ""}</div></div>`;

  function alertCard(a) {
    const co = company(a.sym);
    const near = S.data.events.filter((e) => e.symbol === a.sym && e.ts && Math.abs(new Date(e.ts) - new Date(a.d + "T15:30:00+05:30")) / 864e5 <= 2.6 && !["meet", "admin", "newspaper"].includes(e.category)).sort((x, y) => y.score - x.score);
    return `<article class="card"><div class="alert"><div><div class="meta"><span class="co">${esc(shortName(co.name))}</span><span class="pill ${a.chg >= 0 ? "up" : "down"}">${pct(a.chg, 1)}</span><span>${new Date(a.d).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span></div>
      <h3>${esc(a.why.join(" · "))}</h3><p style="font-size:13px">Close ₹${fmt(a.rows[a.i][1], 1)}${near.length ? ` · around the same time: <b>${esc(near[0].label.toLowerCase())}</b> — ${esc(near[0].headline.slice(0, 90))}` : " · no filing explains it — worth a look"}</p></div>${spark(a.rows, a.i)}</div></article>`;
  }

  /* ------------------------------------------------------------------ views */
  function viewBrief() {
    const evs = S.data.events.filter((e) => inWindow(e.ts)).map((e) => { const s = rescore(e); return { ...e, scoreNow: s, tierNow: tierOf(s) }; });
    const top = evs.filter((e) => e.tierNow === "top").sort((a, b) => b.scoreNow - a.scoreNow);
    const watch = evs.filter((e) => e.tierNow === "watch").sort((a, b) => b.scoreNow - a.scoreNow);
    const buried = evs.filter((e) => e.tierNow === "buried");
    const cos = new Set(evs.map((e) => e.symbol)).size;
    const alerts = priceAlerts();
    const total = evs.length || 1;
    const wl = WINDOWS.find((w) => w[1] === S.window)[0];
    const groups = {}; buried.forEach((e) => { groups[e.label] = (groups[e.label] || 0) + 1; });
    const nudges = S.data.network.nudges.slice(0, 3);

    const card = (e) => (e.category === "results" ? resultsCard(e) : e.card === "person_card" || e.category === "management" ? personCard(e) : eventCard(e));
    const heat = [...S.data.portfolio].filter((p) => p.results).sort((a, b) => (b.surprise || 0) - (a.surprise || 0));
    const hcell = (v, unit = "%", scale = 30) => {
      if (v == null) return `<span class="cell">—</span>`;
      const a = Math.min(1, Math.abs(v) / scale) * 0.85 + 0.08;
      const col = v >= 0 ? "var(--up)" : "var(--down)";
      return `<span class="cell" style="background:color-mix(in srgb, ${col} ${Math.round(a * 32)}%, transparent);color:${col}">${v > 0 ? "+" : ""}${fmt(v)}${unit}</span>`;
    };

    return `
      <section class="hero">
        <h1>${top.length ? `<em>${top.length} ${top.length === 1 ? "thing needs" : "things need"} you</em>` : "Quiet window"} out of ${evs.length} filings.</h1>
        <p>${wl === "24h" ? "In the last 24 hours" : `Over the last ${wl}`}, ${cos} of your ${S.data.portfolio.length} companies filed. FINN read all ${evs.length} and buried ${buried.length}.${alerts.length ? ` ${alerts.length} unusual ${alerts.length === 1 ? "move" : "moves"} by your rules.` : ""}</p>
        <div class="triage" aria-hidden="true"><span class="t" style="width:${(top.length / total) * 100}%"></span><span class="w" style="width:${(watch.length / total) * 100}%"></span><span class="b" style="width:${(buried.length / total) * 100}%"></span></div>
        <div class="legend"><span><b>${top.length}</b> need you</span><span><b>${watch.length}</b> worth a glance</span><span><b>${buried.length}</b> buried</span></div>
      </section>
      <div class="chips" role="tablist" aria-label="Time window">${WINDOWS.map(([l, d]) => `<button class="chip${S.window === d ? " on" : ""}" data-win="${d}" role="tab" aria-selected="${S.window === d}">${l}</button>`).join("")}</div>

      ${top.length ? `<div class="sec"><h2>Needs you</h2><span class="n">${top.length}</span></div>${top.map(card).join("")}` : ""}

      <div class="sec"><h2>Unusual moves</h2><span class="n">${alerts.length}</span><span class="sp"></span><button class="link" data-open="rules">Volume ≥ ${fmt(S.prefs.vol_mult, 1)}× · move ≥ ${fmt(S.prefs.price_pct, 1)}%</button></div>
      ${alerts.length ? alerts.slice(0, 6).map(alertCard).join("") : `<div class="rows"><div class="empty">Nothing crossed your thresholds in this window.</div></div>`}

      ${watch.length ? `<div class="sec"><h2>Worth a glance</h2><span class="n">${watch.length}</span></div><div class="rows">${watch.map(rowItem).join("")}</div>` : ""}

      ${buried.length ? `<div class="sec"><h2>Buried</h2><span class="n">${buried.length}</span></div>
      <details class="rows buried"><summary><b>${buried.length}</b> routine filings, hidden so you don't have to read them <span style="margin-left:auto">Show</span></summary>
        <div class="groups">${Object.entries(groups).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<span class="pill">${esc(k)} · ${v}</span>`).join("")}</div>${buried.map(rowItem).join("")}</details>` : ""}

      <div class="sec"><h2>Results season · latest quarter</h2><span class="n">${heat.length}</span></div>
      <div class="rows" style="padding:8px 12px;overflow-x:auto"><table class="heat"><thead><tr><th>Sorted by surprise</th><th>Rev YoY</th><th>Margin</th><th>PAT YoY</th></tr></thead><tbody>
        ${heat.map((p) => { const m = Object.fromEntries(p.results.metrics.map((x) => [x.key, x])); return `<tr class="clk" data-go="research-${p.symbol}"><td>${esc(shortName(p.name))}</td><td>${hcell(m.revenue?.yoy)}</td><td>${p.results.margin ? hcell(p.results.margin.yoy_bps / 100, " pt", 10) : '<span class="cell">—</span>'}</td><td>${hcell(m.pat?.yoy, "%", 60)}</td></tr>`; }).join("")}
      </tbody></table></div>

      ${nudges.length ? `<div class="sec"><h2>Reasons to reconnect</h2><span class="n">${nudges.length}</span></div>
      <div class="thread" style="margin-top:0">${nudges.map((n) => `<div class="person-row" data-contact="${n.contact}"><div class="avatar net">${initials(n.name)}</div><div><b>${esc(n.name)}</b><small>Quiet for ${Math.round(n.days_quiet / 30)} months · ${esc(n.relation)} ${esc(n.symbol)}: ${esc(n.event.slice(0, 80))}</small></div><div></div></div>`).join("")}</div>` : ""}

      <p class="note">Data: ${esc(S.data.stats.sources.join(" · "))}. As of ${asOf().toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })} IST. ${S.data.stats.filings_scanned} filings scanned across ${S.data.stats.companies} companies.</p>`;
  }

  function viewAsk(q = "") {
    const idx = S.data.research_index || [];
    const port = idx.filter((r) => r.in_portfolio), other = idx.filter((r) => !r.in_portfolio);
    return `<section class="hero"><h1>Ask about any company.</h1><p>Research grounded only in filings and concall transcripts — no news, no broker notes. Or ask who in your network can help.</p></section>
      <form class="ask" id="askform" autocomplete="off">${ICON.ask}<input id="askq" placeholder="PIIND, Kaynes, or “who knows Punjab & Sind Bank?”" value="${esc(q)}" aria-label="Ask FINN"></form>
      <div id="askout"></div>
      <div class="sec"><h2>Research set</h2><span class="n">${other.length}</span></div>
      <div class="sugg">${other.map((r) => `<button data-go="research-${r.symbol}"><b>${esc(r.symbol)}</b> ${esc(shortName(r.name))}<small>outside portfolio</small></button>`).join("")}</div>
      <div class="sec"><h2>Your portfolio</h2><span class="n">${port.length}</span></div>
      <div class="chips" style="flex-wrap:wrap">${port.map((r) => `<button class="chip" data-go="research-${r.symbol}">${esc(r.symbol)}</button>`).join("")}</div>
      <p class="note">${S.live ? "Live mode: any NSE ticker works — FINN fetches filings and transcripts on demand (≈20 s, then cached)." : "Static demo: the companies above are pre-computed. Run the FINN API (see README) and any NSE ticker works."}</p>`;
  }

  function answerAsk(q) {
    const out = $("#askout"); if (!out) return;
    const t = q.trim(); if (!t) { out.innerHTML = ""; return; }
    const idx = S.data.research_index || [];
    const sym = t.toUpperCase().replace(/[^A-Z0-9&-]/g, "");
    const hit = idx.find((r) => r.symbol === sym) || idx.find((r) => r.name.toLowerCase().includes(t.toLowerCase()));
    const isWho = /\b(who|know|knows|call|expert|network|introduc)\b/i.test(t);
    if (hit && !isWho) { location.hash = `research-${hit.symbol}`; return; }
    if (isWho || !hit) {
      const words = t.toLowerCase().replace(/\b(who|knows?|do|i|in|my|network|can|call|about|the|at|expert|on|for|help|me|understand|with|a|an)\b/g, " ").split(/\s+/).filter((w) => w.length > 2);
      const res = S.data.network.contacts.map((c) => {
        const hay = [c.name, c.headline, c.notes, ...c.tags, ...c.career_named.map((j) => `${j.org_name} ${j.role}`), ...c.education_named.map((e) => e.org_name)].join(" ").toLowerCase();
        const hits = words.filter((w) => hay.includes(w));
        return { c, n: hits.length, hits };
      }).filter((r) => r.n).sort((a, b) => b.n - a.n || b.c.tie - a.c.tie).slice(0, 5);
      if (res.length) {
        out.innerHTML = `<div class="thread" style="margin:0 0 8px"><div class="lbl">${ICON.net}From your network</div>${res.map(({ c, hits }) => {
          const j = c.career_named.find((j) => hits.some((h) => (j.org_name + " " + j.role).toLowerCase().includes(h))) || c.career_named[c.career_named.length - 1];
          return `<div class="person-row" data-contact="${c.id}"><div class="avatar net">${initials(c.name)}</div><div><b>${esc(c.name)}</b><small>${esc(j.role)} · ${esc(j.org_name)} (${j.from}–${j.to || "now"})</small></div><div><div class="meter"><i style="width:${Math.round(c.tie * 100)}%"></i></div></div></div>`;
        }).join("")}</div>`;
        return;
      }
      if (/^[A-Z0-9&-]{2,15}$/.test(sym) && !isWho) { location.hash = `research-${sym}`; return; }
      out.innerHTML = `<div class="rows"><div class="empty">No match in your research set or network. Try a ticker (e.g. SRF) or a theme (e.g. “rural lending”).</div></div>`;
    }
  }

  async function loadResearch(sym) {
    if (S.research[sym]) return S.research[sym];
    let r = null;
    try { const res = await fetch(`data/research/${encodeURIComponent(sym)}.json`); if (res.ok) r = await res.json(); } catch (e) { /* fall through */ }
    if (!r && S.live) { const res = await fetch(`/api/research/${encodeURIComponent(sym)}`); if (res.ok) r = await res.json(); else throw new Error((await res.json()).detail || "Not found"); }
    if (!r) throw new Error(`${sym} isn't in the static demo. Run the FINN API for live research on any NSE ticker.`);
    S.research[sym] = r; return r;
  }

  function viewResearch(r) {
    const s = r.snapshot, t = r.trajectory, b = r.balance_sheet, c = r.cash;
    const inPort = S.data.portfolio.some((p) => p.symbol === r.symbol);
    const pv = r.promise_verdict;
    const rules = r.promises || [];
    const showRules = S.showRules[r.symbol] || !pv;
    const li = (x) => `<li class="${/compress|deceler|stretch|rising|weak|negative|missed/i.test(x) ? "bad" : /expand|acceler|leverage|strong|debt-free/i.test(x) ? "good" : ""}">${esc(x)}</li>`;
    const pvItem = (p) => `<div class="item"><div class="h"><span class="st ${p.status}">${esc(p.status.replace("_", " "))}</span><span>${esc(p.given_in)}</span></div><div class="pr">${esc(p.promise)}</div><div class="ac">${esc(p.actual || "")}</div>${p.quote ? `<div class="quote">“${esc(p.quote)}”${p.source ? ` <a href="${esc(p.source)}" target="_blank" rel="noopener">transcript ↗</a>` : ""}</div>` : ""}</div>`;
    const ts = r.token_savings || {};
    return `
      <div class="rhead"><div class="meta"><span class="pill ${inPort ? "sig" : ""}">${inPort ? "In your portfolio" : "Research"}</span><span>${esc(r.symbol)}</span>${r.consolidated ? "<span>Consolidated</span>" : "<span>Standalone</span>"}</div>
        <h1>${esc(r.name)}</h1>
        <div class="sub"><span class="num">₹${fmt(s.price, 0)}</span><span>Mcap ₹${fmt(s.market_cap)} cr</span><span>P/E ${fmt(s.pe, 1)}</span><span>ROCE ${fmt(s.roce, 1)}%</span></div></div>
      <nav class="secnav">${[["biz", "Business"], ["num", "Numbers"], ["traj", "Trajectory"], ["bs", "Balance sheet"], ["cash", "Cash"], ["pvd", "Promises"], ["bb", "Bull / Bear"], ["who", "Who to call"]].map(([id, l]) => `<button class="chip" data-jump="${id}">${l}</button>`).join("")}</nav>

      <div class="sec" id="s-biz"><h2>Business</h2></div>
      ${r.business.in_their_words ? `<div class="quote clamp" data-clamp>“${esc(r.business.in_their_words)}”</div><div class="meta" style="font-size:12px">Management, latest earnings call · <a href="${esc(r.business.in_their_words_source)}" target="_blank" rel="noopener">transcript ↗</a></div>` : ""}
      ${r.business.about ? `<p style="font-size:13.5px;color:var(--ink-2)">${esc(r.business.about.replace(/\s*\[\d+\]/g, ""))}</p>` : ""}

      <div class="sec" id="s-num"><h2>Numbers</h2><span class="n">TTM · ₹ cr</span></div>
      <div class="tiles"><div class="tile"><span>Revenue</span><b>${fmt(s.ttm_revenue)}</b></div><div class="tile"><span>EBITDA margin</span><b>${fmt(s.ttm_opm)}%</b></div><div class="tile"><span>PAT</span><b>${fmt(s.ttm_pat)}</b></div>
        <div class="tile"><span>Debt / equity</span><b>${fmt(s.debt_equity, 2)}</b></div><div class="tile"><span>ROE</span><b>${fmt(s.roe, 1)}%</b></div><div class="tile"><span>52w range</span><b style="font-size:14px">${s.high_low ? `${fmt(s.high_low[1])}–${fmt(s.high_low[0])}` : "—"}</b></div></div>
      ${r.results ? `<div class="card" style="margin-top:10px"><div class="meta"><span class="co">Latest quarter</span><span>vs ${esc(r.results.vs_qoq)} and ${esc(r.results.vs_yoy)}</span></div>${resultsTable(r.results)}</div>` : ""}

      <div class="sec" id="s-traj"><h2>Trajectory</h2><span class="n">Rev CAGR 3y ${pct(t.rev_cagr_3y, 1)} · 5y ${pct(t.rev_cagr_5y, 1)}</span></div>
      <div class="card">${barLine(t.periods, t.revenue, t.opm, { lineLabel: r.results?.is_bank ? "Financing margin %" : "EBITDA margin %" })}<ul class="calls">${t.calls.map(li).join("") || "<li>Steady — no strong trend signal.</li>"}</ul></div>

      <div class="sec" id="s-bs"><h2>Balance sheet</h2></div>
      <div class="card"><table class="tbl"><thead><tr><th>Year</th>${b.periods.slice(-5).map((p) => `<th>${esc(p.replace(/^\w+ /, "FY").replace(/FY20(\d\d)/, "FY$1"))}</th>`).join("")}</tr></thead><tbody>
        <tr><td>Borrowings</td>${b.borrowings.slice(-5).map((v) => `<td>${fmt(v)}</td>`).join("")}</tr>
        <tr><td>Debt / equity</td>${b.debt_equity.slice(-5).map((v) => `<td>${fmt(v, 2)}</td>`).join("")}</tr>
        ${b.ccc.length ? `<tr><td>Cash cycle (days)</td>${b.ccc.slice(-5).map((v) => `<td>${fmt(v)}</td>`).join("")}</tr>` : ""}
        ${b.roce.length ? `<tr><td>ROCE %</td>${b.roce.slice(-5).map((v) => `<td>${fmt(v)}</td>`).join("")}</tr>` : ""}
      </tbody></table><ul class="calls">${b.calls.map(li).join("")}</ul></div>

      <div class="sec" id="s-cash"><h2>Cash quality</h2>${c.conversion_5y != null ? `<span class="n">CFO/PAT 5y ${fmt(c.conversion_5y, 2)}×</span>` : ""}</div>
      <div class="card">${barLine(c.periods, c.cfo, [], { barLabel: "Operating cash flow", lineLabel: "" }).replace(/<span style="color:var\(--signal\)">— <\/span>/, "")}
        <table class="tbl"><thead><tr><th>Year</th>${c.periods.slice(-5).map((p) => `<th>${esc(p.replace(/^\w+ 20/, "FY"))}</th>`).join("")}</tr></thead><tbody>
        <tr><td>Op. cash flow</td>${c.cfo.slice(-5).map((v) => `<td class="${v < 0 ? "d-down" : ""}">${fmt(v)}</td>`).join("")}</tr>
        <tr><td>Profit (PAT)</td>${c.pat.slice(-5).map((v) => `<td>${fmt(v)}</td>`).join("")}</tr>
        <tr><td>Free cash flow</td>${c.fcf.slice(-5).map((v) => `<td class="${v < 0 ? "d-down" : ""}">${fmt(v)}</td>`).join("")}</tr></tbody></table>
        <ul class="calls">${c.calls.map(li).join("")}</ul></div>

      <div class="sec" id="s-pvd"><h2>Promised vs delivered</h2><span class="n">last 4 calls</span></div>
      ${pv ? `<div class="card"><div class="meta"><span class="pill ${pv.credibility === "high" ? "up" : pv.credibility === "low" ? "down" : "sig"}">Credibility: ${esc(pv.credibility)}</span></div><p class="verdict">${esc(pv.verdict)}</p>
        <div class="pvd">${pv.rows.map(pvItem).join("")}</div><div class="prov">Reasoning tier · ${esc(r.promise_verdict_by || "model")} · inputs: ${fmt(ts.sent_to_model_chars)} chars of extracted quotes (from ${fmt(ts.transcript_chars)} chars of transcripts) + reported numbers. Cached per call.</div>
        <div class="actions"><button data-rules="${r.symbol}">${showRules ? "Hide" : "Show"} the rules-only first pass</button></div></div>` : ""}
      ${showRules ? `<div class="card"><div class="meta"><span class="pill">Rules-only first pass</span><span>free · deterministic · no model</span></div>
        <p style="font-size:13px">Every quantified, forward-looking statement by management, tested against what was reported afterwards.${pv ? "" : " A reasoning model refines this when an API key is configured."}</p>
        <div class="pvd">${rules.length ? rules.map((p) => pvItem({ ...p, promise: p.promise })).join("") : `<div class="empty">${!(r.guidance || []).length && (r.transcripts_unreachable || []).length ? `This company hosts its transcripts on its own site (${esc(r.transcripts_unreachable.join(", "))}), which this demo's sandbox couldn't reach. A normal deployment fetches them like any other source.` : "No quantified, forward-looking guidance found in recent calls."}</div>`}</div></div>` : ""}

      <div class="sec" id="s-bb"><h2>Bull vs bear</h2><span class="n">${r.bull_bear_by === "model" ? "reasoning tier" : "from computed signals"}</span></div>
      <div class="bb"><div class="bull"><h3>Bull</h3><ul>${r.bull_bear.bull.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div><div class="bear"><h3>Bear</h3><ul>${r.bull_bear.bear.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>

      <div class="sec" id="s-who"><h2>Who to call</h2></div>
      ${r.who_to_call && r.who_to_call.length ? threadPeople(r.who_to_call, "From your network") : `<div class="rows"><div class="empty">No one in your network has worked at ${esc(shortName(r.name))}, a competitor or a partner.</div></div>`}

      <div class="sec"><h2>Sources</h2></div>
      <div class="rows">${(r.guidance || []).map((g) => `<div class="row"><div class="t"><b>${esc(g.call)} call</b> · quarter ended ${esc(g.quarter)} · ${g.items.length} guidance lines extracted</div><div class="tm"><a href="${esc(g.url)}" target="_blank" rel="noopener">transcript ↗</a></div></div>`).join("")}
        ${(r.sources.annual_reports || []).map((a) => `<div class="row"><div class="t"><b>Annual report ${esc(a.year)}</b></div><div class="tm"><a href="${esc(a.url)}" target="_blank" rel="noopener">PDF ↗</a></div></div>`).join("")}
        <div class="row"><div class="t">Financial statements (exchange filings, standardised)</div><div class="tm"><a href="${esc(r.source_url)}" target="_blank" rel="noopener">screener ↗</a></div></div></div>
      <p class="note">Fetched ${esc(r.fetched_at)}. Pull uses only primary sources; network suggestions are your private data.</p>`;
  }

  function viewNetwork() {
    const N = S.data.network;
    return `<section class="hero"><h1>Your network, <em style="color:var(--net)">working</em>.</h1><p>Who knows what, who has worked where, and who is worth a call this week. Private to you.</p></section>
      <div class="netstats"><span><b>${N.contacts.length}</b>people</span><span><b>${new Set(N.contacts.flatMap((c) => c.career.map((j) => j.org))).size}</b>organisations</span><span><b>${N.contacts.filter((c) => c.days_quiet > 90).length}</b>gone quiet</span></div>
      <form class="ask" id="netform" autocomplete="off">${ICON.ask}<input id="netq" placeholder="A company, a theme, or a person" aria-label="Search your network"></form>
      <div id="askout"></div>
      ${N.nudges.length ? `<div class="sec"><h2>Reasons to reconnect</h2><span class="n">${N.nudges.length}</span></div>
      <div class="thread" style="margin-top:0">${N.nudges.map((n) => `<div class="person-row" data-contact="${n.contact}"><div class="avatar net">${initials(n.name)}</div><div><b>${esc(n.name)}</b><small>${Math.round(n.days_quiet / 30)} months quiet · ${esc(n.relation)} ${esc(n.symbol)} just filed</small><small style="color:var(--muted)">“${esc(n.opener)}”</small></div><div></div></div>`).join("")}</div>` : ""}
      <div class="sec"><h2>Expertise map</h2><span class="n">go-to people by theme</span></div>
      <div class="rows">${N.expertise.map((t) => `<div class="theme" data-theme="${esc(t.theme)}"><div><div class="tn">${esc(t.theme)}</div></div><div class="faces">${t.people.slice(0, 4).map((p) => `<span class="avatar net" title="${esc(p.name)}">${initials(p.name)}</span>`).join("")}</div><div class="ts">${t.people.slice(0, 2).map((p) => `${esc(p.name)} (${p.years}y: ${esc(p.evidence.slice(0, 2).join(", "))})`).join(" · ")}</div></div>`).join("")}</div>
      <div class="sec"><h2>Network map</h2><span class="n">tap a person</span></div>
      <div class="mapwrap">${netMap()}<div class="maplegend"><span><i style="background:var(--net)"></i>You</span><span><i style="background:var(--net-bg);border:1px solid var(--net)"></i>Contact (closer = stronger tie)</span><span><i style="background:var(--signal-bg);border:1px solid var(--signal)"></i>Your portfolio</span><span><i style="background:var(--sunk);border:1px solid var(--muted)"></i>Other organisation</span></div></div>
      <p class="note">${esc(N.provenance)}</p>`;
  }

  function netMap() {
    const g = S.data.network.graph, W = 360, H = 360, cx = W / 2, cy = H / 2;
    const contacts = g.nodes.filter((n) => n.type === "contact"), orgs = g.nodes.filter((n) => n.type === "org");
    const portSyms = new Set(S.data.portfolio.map((p) => p.symbol));
    const pos = { you: [cx, cy] };
    orgs.forEach((o, i) => { const a = (i / orgs.length) * Math.PI * 2 - Math.PI / 2; pos[o.id] = [cx + Math.cos(a) * 160, cy + Math.sin(a) * 160]; });
    contacts.forEach((c) => {
      const links = g.edges.filter((e) => e.s === c.id).map((e) => pos[e.t]).filter(Boolean);
      const ax = links.reduce((s, p) => s + p[0], 0) / (links.length || 1) - cx, ay = links.reduce((s, p) => s + p[1], 0) / (links.length || 1) - cy;
      const a = Math.atan2(ay, ax), r = 48 + (1 - c.tie) * 70;
      pos[c.id] = [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
    });
    // light relaxation so contact dots don't sit on top of each other
    for (let k = 0; k < 40; k++) for (let i = 0; i < contacts.length; i++) for (let j = i + 1; j < contacts.length; j++) {
      const p = pos[contacts[i].id], q = pos[contacts[j].id]; const dx = q[0] - p[0], dy = q[1] - p[1], d = Math.hypot(dx, dy) || 1;
      if (d < 22) { const m = (22 - d) / 2 / d; p[0] -= dx * m; p[1] -= dy * m; q[0] += dx * m; q[1] += dy * m; }
    }
    let s = "";
    g.edges.forEach((e) => { const a = pos[e.s], b = pos[e.t]; if (a && b) s += `<line class="${e.s === "you" ? "e" : "e2"}" x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}" x2="${b[0].toFixed(1)}" y2="${b[1].toFixed(1)}" stroke-width="${e.s === "you" ? (0.4 + e.w * 1.6).toFixed(2) : 0.7}"/>`; });
    orgs.forEach((o) => { const [x, y] = pos[o.id]; const port = portSyms.has(o.id); const lx = x + (x > cx ? 7 : -7);
      s += `<circle class="o${port ? " port" : ""}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${port ? 5 : 3.5}"/><text class="org" x="${lx.toFixed(1)}" y="${(y + 3).toFixed(1)}" text-anchor="${x > cx ? "start" : "end"}">${esc(o.label.replace(/ (India|International|Technologies|Technology|Industries|Laboratories|Industrial Solutions|& Industrial Solutions|Company|Pharmaceutical|Systems)\b.*$/, ""))}</text>`; });
    contacts.forEach((c) => { const [x, y] = pos[c.id]; s += `<g data-contact="${c.id}" role="button" aria-label="${esc(c.label)}"><circle class="c" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="8"/><text x="${x.toFixed(1)}" y="${(y + 3).toFixed(1)}" text-anchor="middle" style="font-size:7.5px;font-weight:600;fill:var(--net)">${initials(c.label)}</text></g>`; });
    s += `<circle class="you" cx="${cx}" cy="${cy}" r="13"/><text x="${cx}" y="${cy + 3.5}" text-anchor="middle" style="fill:var(--surface);font-weight:600">You</text>`;
    return `<svg class="map" viewBox="-60 0 ${W + 120} ${H}" role="img" aria-label="Map of your network">${s}</svg>`;
  }

  /* ------------------------------------------------------------------ sheets */
  function openSheet(html) {
    closeSheet();
    const scrim = document.createElement("div"); scrim.className = "scrim"; scrim.addEventListener("click", closeSheet);
    const sh = document.createElement("div"); sh.className = "sheet"; sh.setAttribute("role", "dialog"); sh.innerHTML = `<div class="in"><div class="grab"></div>${html}</div>`;
    document.body.append(scrim, sh);
    sh.addEventListener("click", onClick);
    sh.addEventListener("input", onInput);
  }
  function closeSheet() { document.querySelectorAll(".scrim,.sheet").forEach((n) => n.remove()); }

  function rulesSheet() {
    return `<h2>Alert rules</h2><p class="note" style="margin-top:6px">You decide what “unusual” means; FINN watches end-of-day data for it. Changes apply instantly.</p>
      <div class="field"><label for="volr">Volume spike <b id="volv">${fmt(S.prefs.vol_mult, 1)}× 20-day avg</b></label><input id="volr" type="range" min="1.5" max="5" step="0.1" value="${S.prefs.vol_mult}"><small>Flags days when traded volume is at least this multiple of the trailing 20-session average.</small></div>
      <div class="field"><label for="pxr">Price move <b id="pxv">±${fmt(S.prefs.price_pct, 1)}% in a day</b></label><input id="pxr" type="range" min="1" max="10" step="0.5" value="${S.prefs.price_pct}"><small>Close-to-close change, either direction.</small></div>
      <div class="field"><label>Announcement types you follow</label><div class="toggles">${CATS.map(([k, l]) => `<button class="chip${S.prefs.categories.includes(k) ? " on" : ""}" data-cat="${k}">${l}</button>`).join("")}</div><small>Followed types rank higher; unfollowed material types drop a tier. Routine filings are always buried.</small></div>`;
  }

  function contactSheet(id) {
    const c = contact(id); if (!c) return "";
    const rel = S.data.events.filter((e) => c.career.some((j) => j.org === e.symbol) && e.tier !== "buried").slice(0, 3);
    const linkedIn = S.data.events.filter((e) => (e.people || []).some((p) => (p.links || []).some((l) => l.contact === id)));
    return `<div class="meta"><span class="pill net">tie ${Math.round(c.tie * 100)}/100</span><span>last spoke ${c.days_quiet} days ago · ${c.touchpoints_12m} touchpoints in 12 months</span></div>
      <h2 style="margin-top:8px">${esc(c.name)}</h2><p style="margin:4px 0;color:var(--ink-2)">${esc(c.headline)}</p>
      <p class="note" style="margin:6px 0">${esc(c.how_met)}${c.notes ? ` · ${esc(c.notes)}` : ""}</p>
      ${linkedIn.length ? `<div class="thread"><div class="lbl">${ICON.net}Why FINN surfaced them</div>${linkedIn.map((e) => { const p = e.people.find((p) => (p.links || []).some((l) => l.contact === id)); const l = p.links.find((l) => l.contact === id); return `<div class="ev">Linked to <b>${esc(p.name)}</b> (${esc(p.role || "")}, ${esc(e.symbol)}): ${esc(l.evidence)}</div>`; }).join("")}</div>` : ""}
      <div class="sec"><h2>Career</h2></div><ul class="timeline">${c.career_named.map((j) => `<li><span>${j.from}–${j.to || "now"}</span><div><b>${esc(j.org_name)}</b><br><span style="color:var(--muted);font-family:var(--f-ui);font-size:13px">${esc(j.role)}</span></div></li>`).join("")}${c.education_named.map((e) => `<li><span>${e.year || ""}</span><div>${esc(e.org_name)} · ${esc(e.degree || "")}</div></li>`).join("")}</ul>
      ${rel.length ? `<div class="sec"><h2>Recent filings at their companies</h2></div><div class="rows">${rel.map(rowItem).join("")}</div>` : ""}
      ${c.introduces.length ? `<div class="sec"><h2>Can introduce you to</h2></div><div class="chips" style="flex-wrap:wrap">${c.introduces.map((k) => `<button class="chip" data-contact="${k.contact}">${esc(k.name)}</button>`).join("")}</div>` : ""}
      <div class="sec"><h2>Expertise</h2></div><div class="chips" style="flex-wrap:wrap">${c.tags.map((t) => `<span class="pill net">${esc(t)}</span>`).join("")}</div>`;
  }

  function themeSheet(name) {
    const t = S.data.network.expertise.find((x) => x.theme === name); if (!t) return "";
    return `<h2>${esc(t.theme)}</h2><p class="note" style="margin-top:6px">${t.depth} people in your network have worked in this space. Ranked by years in the industry and how warm the relationship is.</p>
      <div class="thread">${t.people.map((p) => `<div class="person-row" data-contact="${p.contact}"><div class="avatar net">${initials(p.name)}</div><div><b>${esc(p.name)}</b><small>${p.years} yrs · ${esc(p.evidence.join(", "))}</small></div><div><div class="meter"><i style="width:${Math.round(p.tie * 100)}%"></i></div></div></div>`).join("")}</div>`;
  }

  /* ------------------------------------------------------------------ router + events */
  async function render() {
    const h = location.hash.replace("#", "") || "brief";
    const main = $("#main");
    document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("on", h.startsWith(a.dataset.tab) || (a.dataset.tab === "ask" && h.startsWith("research"))));
    if (h.startsWith("research-")) {
      const sym = h.slice(9);
      main.innerHTML = `<div class="loading">Reading ${esc(sym)}'s filings and transcripts…</div>`;
      try { const r = await loadResearch(sym); main.innerHTML = viewResearch(r); }
      catch (e) { main.innerHTML = `${viewAsk(sym)}`; $("#askout").innerHTML = `<div class="rows"><div class="empty">${esc(e.message)}</div></div>`; }
    } else if (h === "ask") main.innerHTML = viewAsk();
    else if (h === "network") main.innerHTML = viewNetwork();
    else main.innerHTML = viewBrief();
    window.scrollTo(0, 0);
  }

  function onClick(ev) {
    const t = ev.target.closest("[data-win],[data-why],[data-go],[data-contact],[data-open],[data-cat],[data-theme],[data-jump],[data-rules],[data-clamp]");
    if (!t) return;
    if (t.dataset.win) { S.window = Number(t.dataset.win); save(); render(); }
    else if (t.dataset.why) { S.openWhy.has(t.dataset.why) ? S.openWhy.delete(t.dataset.why) : S.openWhy.add(t.dataset.why); const y = scrollY; render().then(() => scrollTo(0, y)); }
    else if (t.dataset.go) { closeSheet(); location.hash = t.dataset.go; }
    else if (t.dataset.contact) { ev.preventDefault(); openSheet(contactSheet(t.dataset.contact)); }
    else if (t.dataset.open === "rules") openSheet(rulesSheet());
    else if (t.dataset.cat) { const k = t.dataset.cat; S.prefs.categories = S.prefs.categories.includes(k) ? S.prefs.categories.filter((x) => x !== k) : [...S.prefs.categories, k]; t.classList.toggle("on"); save(); if (!location.hash.startsWith("#research")) { const y = scrollY; render().then(() => scrollTo(0, y)); } }
    else if (t.dataset.theme) openSheet(themeSheet(t.dataset.theme));
    else if (t.dataset.jump) { const el = document.getElementById("s-" + t.dataset.jump); if (el) scrollTo({ top: el.getBoundingClientRect().top + scrollY - 110, behavior: "smooth" }); }
    else if (t.dataset.rules) { S.showRules[t.dataset.rules] = !S.showRules[t.dataset.rules]; const y = scrollY; render().then(() => scrollTo(0, y)); }
    else if (t.hasAttribute("data-clamp")) t.classList.toggle("clamp");
  }

  let rt;
  function onInput(ev) {
    if (ev.target.id === "volr" || ev.target.id === "pxr") {
      S.prefs.vol_mult = Number($("#volr").value); S.prefs.price_pct = Number($("#pxr").value);
      $("#volv").textContent = `${fmt(S.prefs.vol_mult, 1)}× 20-day avg`; $("#pxv").textContent = `±${fmt(S.prefs.price_pct, 1)}% in a day`;
      save(); clearTimeout(rt); rt = setTimeout(() => { if (!location.hash.startsWith("#research")) { const y = scrollY; render().then(() => scrollTo(0, y)); } }, 120);
    }
  }

  document.addEventListener("click", onClick);
  document.addEventListener("submit", (ev) => { if (ev.target.id === "askform" || ev.target.id === "netform") { ev.preventDefault(); answerAsk(ev.target.querySelector("input").value); } });
  document.addEventListener("input", (ev) => { if (ev.target.id === "netq") answerAsk(ev.target.value + " who"); });
  window.addEventListener("hashchange", () => { closeSheet(); render(); });

  async function boot() {
    $("#gear").innerHTML = ICON.gear;
    document.querySelectorAll(".tabs a").forEach((a) => { a.insertAdjacentHTML("afterbegin", ICON[a.dataset.tab === "brief" ? "brief" : a.dataset.tab === "ask" ? "ask" : "net"]); });
    $("#gear").addEventListener("click", () => openSheet(rulesSheet()));
    try {
      const res = await fetch("data/snapshot.json");
      S.data = await res.json();
    } catch (e) { $("#main").innerHTML = `<div class="loading">Couldn't load FINN's data. ${esc(e.message)}</div>`; return; }
    // probe for the live API only where one can exist (local dev / self-hosted), never on static hosts
    if (location.protocol.startsWith("http") && !/claude\.ai|claudeusercontent|github\.io|netlify|vercel/.test(location.hostname)) {
      try { const h = await fetch("/api/health", { cache: "no-store" }); S.live = h.ok && (await h.json()).ok; } catch (e) { S.live = false; }
    }
    $("#asof").textContent = `${asOf().toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })} · ${S.live ? "live" : "snapshot"}`;
    render();
  }
  boot();
})();
