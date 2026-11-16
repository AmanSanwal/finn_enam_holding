**To:** assessment@enam.com
**Subject:** IIT Kanpur – Founding AI Engineer - 2027

Hello,

Please find my FINN prototype below. The app runs in a phone browser, and the source is in a public repository.

- Prototype: `<deployed link>`
- Repository: `<github link>`
- AI build history: attached (`AI_BUILD_HISTORY.md`)

**What I built.** I built the three layers the brief asked for, at a small scope. Push is a
windowed digest of portfolio filings, sorted by priority, with routine items collapsed. It also
has threshold alerts for volume and price moves, which the investor can change. Pull is a research
view for a ticker. It includes a business snapshot, a financial snapshot, a numbers-versus-narrative
table, and a bull-versus-bear view. The Network sits inside both. It appears when a management
change is filed, showing who in the investor's network worked with or studied with the incoming
person. It also appears when a material event hits a company the investor knows people at. The
network tab adds an expertise map and a searchable list of who can speak to which company.

**Honest scope.** The demo runs on invented data. Every price, filing, financial figure, profile,
and contact is synthetic. Tickers are real NSE symbols, and the price script is written to fetch
live data, but I have not yet run it end to end. Pull only renders a worked example for the
companies I cached. For any other ticker it says the data is not cached, rather than guessing.

**Key decisions and tradeoffs.**
- I chose a static, mobile-first page over a native app. It is fast to try on a phone, and nothing
  needs installing.
- I used rules for classification and scoring, not a model. That keeps the prototype offline and
  free, and makes every ranking explainable. The next step is a small model for summaries, with
  rules kept as the override.
- The network matches on exact name, then employer, then school. I show a fuzzy name match as
  "possible, confirm" rather than merging it silently.

**Architecture.** The full write-up is in `docs/ARCHITECTURE.md`. In short: a scheduled pipeline
fetches prices, filings, and fundamentals, and writes JSON. The browser reads only that JSON. Model
calls happen only in the pipeline, behind a cache keyed by document hash. Data for each investor's
network stays owned by that investor. Each contact has a consent record and a retention rule. In a
real deployment I would fetch profile data only from sources whose terms allow it.

**Models and cost.** The prototype uses no model calls, so it costs nothing to run. The planned
routing is a small, cheap model for bulk filing summaries, a mid-tier model for profile extraction,
and the strongest model only for guidance-versus-delivery reasoning.

**What I deliberately left out.** Live scraping of NSE/BSE filings, multi-user accounts, voice,
and any buy or sell recommendation. I also left out broker notes and news, because the brief asks
for primary sources on the Pull side.

**Where I would take it next.** Run the price and filing pipeline on a schedule for a real
portfolio. Add retrieval over annual reports and transcripts, with a citation for every claim. Add
an on-phone digest that sends a push notification when a threshold fires.

**AI use.** I used Claude to help build this. The build history shows how I broke the problem down,
where I changed the model's output, and what I rewrote myself.

Thank you for the time.

Best regards,
<name>
<phone / email>
