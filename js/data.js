// FINN demo data.
// Tickers are real NSE symbols. Every price, filing, financial figure, profile and
// network contact below is INVENTED for the demo. Nothing here is market data.
// Live prices: scripts/fetch_prices.py. See docs/ARCHITECTURE.md.

const NOW = new Date('2026-11-16T09:00:00+05:30');
const DAY = 24 * 3600 * 1000;

// Investor's mock portfolio (15 names, mixed sectors and sizes).
const PORTFOLIO = [
  { ticker: 'RELIANCE',   name: 'Reliance Industries',      sector: 'Conglomerate',        size: 'Large' },
  { ticker: 'TCS',        name: 'Tata Consultancy Services', sector: 'IT Services',         size: 'Large' },
  { ticker: 'HDFCBANK',   name: 'HDFC Bank',                sector: 'Private Bank',        size: 'Large' },
  { ticker: 'INFY',       name: 'Infosys',                  sector: 'IT Services',         size: 'Large' },
  { ticker: 'SUNPHARMA',  name: 'Sun Pharmaceutical',       sector: 'Pharma',              size: 'Large' },
  { ticker: 'TATAMOTORS', name: 'Tata Motors',              sector: 'Autos',               size: 'Large' },
  { ticker: 'ASIANPAINT', name: 'Asian Paints',             sector: 'Consumer',            size: 'Large' },
  { ticker: 'PIDILITIND', name: 'Pidilite Industries',      sector: 'Specialty Chemicals', size: 'Large' },
  { ticker: 'ITC',        name: 'ITC',                      sector: 'FMCG',                size: 'Large' },
  { ticker: 'DIXON',      name: 'Dixon Technologies',       sector: 'Electronics Mfg',     size: 'Mid' },
  { ticker: 'PERSISTENT', name: 'Persistent Systems',       sector: 'IT Services',         size: 'Mid' },
  { ticker: 'AUBANK',     name: 'AU Small Finance Bank',    sector: 'Small Finance Bank',  size: 'Mid' },
  { ticker: 'DEEPAKNTR',  name: 'Deepak Nitrite',           sector: 'Specialty Chemicals', size: 'Mid' },
  { ticker: 'POLYCAB',    name: 'Polycab India',            sector: 'Cables',              size: 'Mid' },
  { ticker: 'SUZLON',     name: 'Suzlon Energy',            sector: 'Renewable Energy',    size: 'Small' },
];

// Ad-hoc research names outside the portfolio. Pull works for any ticker that has
// cached data; these three are the ones with demo data cached.
const ADHOC = [
  { ticker: 'DIVISLAB',   name: 'Divi\'s Laboratories',     sector: 'Pharma (API)',        size: 'Large' },
  { ticker: 'KAYNES',     name: 'Kaynes Technology',        sector: 'Electronics Mfg',     size: 'Mid' },
  { ticker: 'TRENT',      name: 'Trent',                    sector: 'Retail',              size: 'Mid' },
];

const COMPANIES = [...PORTFOLIO, ...ADHOC];
const nameOf = t => (COMPANIES.find(c => c.ticker === t) || { name: t }).name;

// Deterministic pseudo-random so the demo is stable across reloads.
function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
function seedOf(str) { let h = 2166136261; for (const c of str) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return h >>> 0; }

// 30 trading-day OHLCV history per ticker, with a planted spike on the last day for
// a few names so the alert engine has something to find.
const SPIKES = {
  SUZLON:  { vol: 2.6, pct: 6.2 },
  DIXON:   { vol: 1.4, pct: -4.8 },
  AUBANK:  { vol: 3.1, pct: 1.1 },
  TCS:     { vol: 1.1, pct: -0.6 },
};
function priceHistory(ticker) {
  const r = rng(seedOf(ticker));
  let px = 200 + r() * 2400;
  const rows = [];
  for (let i = 29; i >= 0; i--) {
    const drift = (r() - 0.5) * 0.024;
    px = Math.max(5, px * (1 + drift));
    const vol = Math.round((800000 + r() * 1200000) * (0.8 + r() * 0.4));
    rows.push({ date: new Date(NOW.getTime() - i * DAY).toISOString().slice(0, 10), close: +px.toFixed(2), volume: vol });
  }
  const sp = SPIKES[ticker];
  if (sp) {
    const last = rows[rows.length - 1];
    const prev = rows[rows.length - 2];
    last.close = +(prev.close * (1 + sp.pct / 100)).toFixed(2);
    last.volume = Math.round(avgVol(rows.slice(0, -1)) * sp.vol);
  }
  return rows;
}
function avgVol(rows) { return rows.reduce((a, b) => a + b.volume, 0) / rows.length; }

const CONTACTS_AS_OF = '2026-11-01';

// Investor's network. Each contact: who they are, where they worked, who they know,
// and which companies they can speak to (and how). Synthetic.
const PEOPLE = [
  { id: 'p1', name: 'Rohan Iyer',     now: 'Head of Strategy, Tata Consultancy Services', school: 'IIT Madras', pastEmployers: ['Accenture', 'McKinsey'], strength: 5, met: 'Ex-colleague, 2019–2021', companies: [{ t: 'TCS', rel: 'current employer' }, { t: 'INFY', rel: 'competitor' }, { t: 'PERSISTENT', rel: 'peer' }], themes: ['IT services', 'deal pricing'], knows: ['p4', 'p7'] },
  { id: 'p2', name: 'Meera Kapoor',   now: 'Vice President, Treasury, HDFC Bank', school: 'IIM Ahmedabad', pastEmployers: ['ICICI Bank', 'Kotak'], strength: 4, met: 'Classmate, IIM-A 2014', companies: [{ t: 'HDFCBANK', rel: 'current employer' }, { t: 'AUBANK', rel: 'competitor' }], themes: ['private banking', 'liquidity'], knows: ['p6'] },
  { id: 'p3', name: 'Vikram Desai',   now: 'Co-founder, Gridline Cables', school: 'BITS Pilani', pastEmployers: ['Polycab India', 'KEI Industries'], strength: 4, met: 'Met at a supplier summit, 2024', companies: [{ t: 'POLYCAB', rel: 'former employer' }, { t: 'SUZLON', rel: 'supplier' }], themes: ['cables', 'copper cost'], knows: ['p5'] },
  { id: 'p4', name: 'Sanjana Rao',    now: 'Principal, Equity Research, Stellar Capital', school: 'NMIMS', pastEmployers: ['Infosys', 'Nomura'], strength: 3, met: 'Former colleague, 2017', companies: [{ t: 'INFY', rel: 'former employer' }, { t: 'TCS', rel: 'peer' }], themes: ['IT services', 'mid-cap research'], knows: ['p1'] },
  { id: 'p5', name: 'Arjun Nair',     now: 'Chief Operating Officer, Renewvolt Energy', school: 'IIT Kanpur', pastEmployers: ['Suzlon Energy', 'Vestas'], strength: 5, met: 'College friend, IIT Kanpur 2008', companies: [{ t: 'SUZLON', rel: 'former employer' }, { t: 'TATAMOTORS', rel: 'customer (EV fleets)' }], themes: ['wind energy', 'project execution'], knows: ['p3'] },
  { id: 'p6', name: 'Priya Menon',    now: 'Partner, Vantage Capital', school: 'IIM Bangalore', pastEmployers: ['Kotak Institutional Equities', 'HDFC Bank'], strength: 3, met: 'Conference panel, 2025', companies: [{ t: 'HDFCBANK', rel: 'former employer' }, { t: 'AUBANK', rel: 'peer' }], themes: ['banking', 'NBFC credit'], knows: ['p2', 'p8'] },
  { id: 'p7', name: 'Kunal Shah',     now: 'Director, Supply Chain, Asian Paints', school: 'IIT Bombay', pastEmployers: ['Hindustan Unilever', 'Pidilite Industries'], strength: 2, met: 'Met at a supply-chain meetup, 2023', companies: [{ t: 'ASIANPAINT', rel: 'current employer' }, { t: 'PIDILITIND', rel: 'former employer' }, { t: 'DEEPAKNTR', rel: 'supplier' }], themes: ['specialty chemicals', 'raw-material cost'], knows: ['p1', 'p9'] },
  { id: 'p8', name: 'Ananya Sethi',   now: 'Senior Analyst, Lotus Wealth', school: 'Delhi School of Economics', pastEmployers: ['Motilal Oswal'], strength: 2, met: 'Former classmate, 2016', companies: [{ t: 'ITC', rel: 'peer' }], themes: ['FMCG', 'valuations'], knows: ['p6'] },
  { id: 'p9', name: 'Dev Malhotra',   now: 'Head of Specialty Chemicals, Crescent Industries', school: 'IIT Delhi', pastEmployers: ['Deepak Nitrite', 'Aarti Industries'], strength: 4, met: 'Ex-colleague, 2018–2020', companies: [{ t: 'DEEPAKNTR', rel: 'former employer' }, { t: 'PIDILITIND', rel: 'customer' }], themes: ['specialty chemicals', 'capacity expansion'], knows: ['p7'] },
  { id: 'p10', name: 'Neha Varghese', now: 'Head of Retail Ops, Lakeside Malls', school: 'XLRI', pastEmployers: ['Trent', 'Shoppers Stop'], strength: 3, met: 'Former colleague, 2020', companies: [{ t: 'TRENT', rel: 'former employer' }], themes: ['organised retail', 'store expansion'], knows: ['p8'] },
];

// Corporate announcements. Synthetic. Category set is our own (the brief's reference
// categories were not supplied); see docs/ARCHITECTURE.md for the taxonomy.
// hoursAgo drives the time window.
const ANNOUNCEMENTS = [
  { id: 'a1', ticker: 'TCS', hoursAgo: 5, category: 'Results', title: 'Q2 FY27 quarterly results and dividend declared', fin: { period: 'Q2 FY27', rev: [64200, 63100, 60800], ebitda: [17300, 16900, 16100], pbt: [16000, 15600, 14900], pat: [12100, 11800, 11250] }, summary: 'Board approved standalone and consolidated results for the quarter.' },
  { id: 'a2', ticker: 'SUZLON', hoursAgo: 2, category: 'Capex / Expansion', title: 'Board approves new blade manufacturing capacity', summary: 'Plan to add blade capacity in Tamil Nadu; capex amount disclosed.' },
  { id: 'a3', ticker: 'INFY', hoursAgo: 9, category: 'Management change', title: 'Appointment of new Chief Financial Officer', person: { name: 'Anjali Mehta', role: 'Chief Financial Officer (incoming)', prior: [{ org: 'Wipro', role: 'VP Finance', years: '2016–2021' }, { org: 'Deloitte', role: 'Director, Transaction Advisory', years: '2011–2016' }], school: 'IIM Bangalore' }, summary: 'Outgoing CFO steps down; successor effective 1 December.' },
  { id: 'a4', ticker: 'DIXON', hoursAgo: 14, category: 'M&A', title: 'Acquisition of a majority stake in a display module maker', summary: 'Stake acquisition to add display module capability. Deal value disclosed.' },
  { id: 'a5', ticker: 'HDFCBANK', hoursAgo: 20, category: 'Board meeting', title: 'Intimation of board meeting to consider financials', summary: 'Routine notice of a board meeting date.' },
  { id: 'a6', ticker: 'TATAMOTORS', hoursAgo: 30, category: 'Litigation', title: 'Disclosure of tax demand order received', summary: 'Company received an order under a tax dispute and plans to appeal.' },
  { id: 'a7', ticker: 'SUNPHARMA', hoursAgo: 40, category: 'Shareholding', title: 'Shareholding pattern for the quarter', summary: 'Routine filing.' },
  { id: 'a8', ticker: 'ITC', hoursAgo: 52, category: 'Trading window', title: 'Closure of trading window', summary: 'Routine compliance notice.' },
  { id: 'a9', ticker: 'PIDILITIND', hoursAgo: 70, category: 'Credit rating', title: 'Credit rating reaffirmed', summary: 'Rating agency reaffirmed the existing rating.' },
  { id: 'a10', ticker: 'AUBANK', hoursAgo: 96, category: 'Results', title: 'Q2 FY27 quarterly results', fin: { period: 'Q2 FY27', rev: [5200, 5050, 4300], ebitda: [2100, 2050, 1700], pbt: [1480, 1420, 1120], pat: [1090, 1050, 840] }, summary: 'Quarterly results filed.' },
  { id: 'a11', ticker: 'DEEPAKNTR', hoursAgo: 120, category: 'Capex / Expansion', title: 'Capex plan for a new nitro-aromatics unit', summary: 'Disclosed capex for a new unit. Commissioning timeline given.' },
  { id: 'a12', ticker: 'POLYCAB', hoursAgo: 150, category: 'Other', title: 'Investor presentation uploaded', summary: 'Presentation filed ahead of the earnings call.' },
  { id: 'a13', ticker: 'PERSISTENT', hoursAgo: 200, category: 'Management change', title: 'Resignation of Head of Delivery', person: { name: 'Sameer Joshi', role: 'Head of Delivery (outgoing)', prior: [], school: '' }, summary: 'Executive resigned; a replacement is being searched for.' },
  { id: 'a14', ticker: 'ASIANPAINT', hoursAgo: 260, category: 'Results', title: 'Q2 FY27 quarterly results', fin: { period: 'Q2 FY27', rev: [8400, 8600, 8200], ebitda: [1700, 1820, 1690], pbt: [1200, 1350, 1210], pat: [900, 1010, 920] }, summary: 'Results filed; margins under pressure.' },
];

// Quarterly guidance vs. delivered (worked example). Synthetic. Built from the filings
// above only, not from outside knowledge.
const GUIDANCE_CHECK = {
  TCS: [
    { quarter: 'Q3 FY26', promised: 'Revenue growth in the low single digits', delivered: 'Revenue growth in the low single digits', verdict: 'Met' },
    { quarter: 'Q4 FY26', promised: 'Margin in a stated band', delivered: 'Margin near the lower end of the band', verdict: 'Partly met' },
    { quarter: 'Q1 FY27', promised: 'Deal wins to stabilise', delivered: 'Deal wins rose, pricing pressure noted', verdict: 'Met (volume), missed (price)' },
    { quarter: 'Q2 FY27', promised: 'Margin recovery in H2', delivered: 'Margin held flat quarter on quarter', verdict: 'Not yet' },
  ],
};

// Business snapshot / bull vs bear, per cached ticker. Synthetic.
const PULL_DATA = {
  TCS: {
    business: 'IT services. Segments: BFSI, Retail, Manufacturing, Life Sciences. Revenue mostly from large enterprise contracts.',
    bull: 'Large deal book and steady dividend payout; margin recovery if pricing stabilises.',
    bear: 'Slow volume growth and pricing pressure; margins flat for two quarters.',
  },
  DIXON: {
    business: 'Contract electronics manufacturing for consumer and industrial brands. Growing into display modules.',
    bull: 'Scale in contract manufacturing and new module capability add to the revenue mix.',
    bear: 'Thin margins; acquisitions add integration and funding risk.',
  },
  SUZLON: {
    business: 'Wind turbine manufacturer and project developer. Revenue depends on order execution.',
    bull: 'Capacity expansion in blades supports execution on a growing order book.',
    bear: 'Working capital and project-timing risk keep cash conversion uncertain.',
  },
};

// Alert thresholds the investor can change in the UI.
const DEFAULT_ALERTS = { volMult: 2.0, pctMove: 4.0, categories: ['Results', 'M&A', 'Management change', 'Litigation', 'Capex / Expansion'] };
