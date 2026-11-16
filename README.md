# FINN — financial investment agent (prototype)

A mobile-first prototype for the ENAM Founding AI Engineer challenge. It has three layers:

- **Push**: a windowed digest of portfolio filings, prioritised, plus threshold alerts.
- **Pull**: a research view for any ticker, grounded in primary sources.
- **Network**: who in the investor's own network can help, woven into Push and Pull.

> All data in this build is synthetic. Tickers are real NSE symbols. Prices, filings,
> financials, profiles and contacts are invented for the demo.

## Run it

Open `index.html` in a browser, or serve the folder:

```bash
python3 -m http.server 8080      # then open http://localhost:8080 on a phone on the same network
```

No build step and no dependencies.

## Live prices (optional)

```bash
pip install yfinance
python scripts/fetch_prices.py --portfolio     # writes data/prices/<TICKER>.json
```

The script is written but not yet verified end to end against Yahoo.

## Layout

```
index.html          app shell (mobile-first, responsive)
js/data.js          synthetic demo data: portfolio, filings, financials, people, guidance
js/app.js           scoring, alerts, network matching, rendering
scripts/            data pipeline (prices; fundamentals and filings are planned)
docs/ARCHITECTURE.md  pipelines, security and privacy, LLMs and agents, cloud
docs/WRITEUP_EMAIL.md covering note for the submission
docs/AI_BUILD_HISTORY.md how the build was done with AI tools
```

## What works

- Push digest with a 1-day, 3-day, 7-day and 30-day window. Routine filings collapse.
- Management change: an incoming-person card, plus network overlaps (employer or school).
- Quarterly results: revenue, EBITDA, PBT and PAT, QoQ and YoY.
- Material events: the best-placed contact and why.
- Alerts: volume and price thresholds the investor sets. Announcement types that alert are
  configurable.
- Pull: business snapshot, financial snapshot, numbers vs. narrative, bull vs. bear, and who
  can help. Tickers without cached data say so instead of guessing.
- Network: searchable contacts, expertise map by theme.

## What is not built yet

- Live NSE/BSE filings feed and screener.in fundamentals.
- Retrieval and citations over annual reports and transcripts.
- Model calls. The current build is entirely rule-based.
