# How FINN was built (with an AI coding agent)

Built in a single Claude Code session (cloud). The full transcript is the primary record; this is the
short version of how the problem was broken down, and where the agent's first attempt was wrong and got
corrected.

## Sequence
1. **Read the brief, then probe reality before designing.** The sandbox blocked every finance host. I
   allowlisted exactly the eight hosts the brief names (Yahoo, NSE, BSE, screener.in), then tested each.
   - Yahoo and screener worked. NSE's RSS feed worked. BSE's JSON API returned *Access Denied* to
     non-browser clients.
   - **Decision:** don't spoof headers to get around a bot block. Use NSE's official RSS (live) plus BSE
     filing history via screener.in, and say so in the writeup.
   - The user explicitly approved polite fetching: robots.txt, 3 s per host, cache.
2. **Pick the portfolio from real events.** I fetched about 40 candidates, listed their last five filings,
   and chose 19 holdings that had real management changes, M&A, litigation and results in the window,
   while keeping a sector and size mix.
3. **Insight that shaped the Network design.** Reading the Equitas filing showed that SEBI LODR requires a
   *brief profile* of every appointed KMP. So bios come from the primary source, and LinkedIn scraping is
   unnecessary.
4. **Build bottom-up, testing each layer on real filings:** http, then screener parser, filings, classifier,
   people, network, results, transcripts, research, push, snapshot, UI.

## Course-corrections (model output that was wrong and got fixed)
- **Classifier false positives found on real data:**
  - "Disclosure" matched `closure`, which flagged an RBI approval as *operations at risk*.
  - "Researchers" matched `search`, which made the Infosys Prize announcement *litigation*.
  - Suzuki Motor's results were counted as Maruti's results.
  - A generic "Allotment" title hid a ₹5,800 cr warrant issue.

  Fixed with word boundaries, multi-label classification and a materiality-based primary label.
- **De-duplication:** the same filing arrives from NSE and BSE with different wording, so fuzzy text
  matching alone missed it. It now matches on same company + same day + same category. It also prefers
  the specific one-liner over NSE's "Intimation under Reg 30…" boilerplate.
- **Name extraction:** noisy PDF text ("Madhu Sasidha" / "Madhu Sasidhar", "Chandrakant V. Gogri" /
  "Chandrakant Vallabhaji Gogri"), plus an apostrophe that cut "D'Souza". Fixed with fuzzy de-duplication
  and by putting the person named in the headline first.
- **Network ranking:** a contact who ran CG Power's Waluj plant ranked below a competitor's COO.
  - Alumni now decay more slowly.
  - Event text naming the plant boosts the person who ran it.
  - "finance" no longer matches "microfinance".
  - A theme-expert bug (`"it" in "capital markets"`) was fixed.
- **Results flooding "needs you":** every quarter scored top priority. Results are now *worth a glance*
  unless the move is large, and downside moves weigh more.
- **The rules-only promise checker was noisy.** It treated past facts ("Pharma delivered 40% growth"),
  tax rates and industry forecasts as promises. I added filters, and kept the rules pass visible
  alongside the reasoning-tier verdict, since showing the gap is the point.
- **UI:** the card class `.top` collided with the header's sticky flex `.top`, so cards laid out as
  columns. Caught in the first phone screenshot and renamed.
- **Bank metrics:** screener's "Financing Profit" is not EBITDA or PPOP. FINN now shows NII
  (Revenue − Interest) for banks.

## What was accepted vs rewritten
- **Accepted:** the parsing scaffolds, the CSS token system, and the SVG chart helpers.
- **Rewritten after reading real data:** classification rules, the de-dup policy, people extraction,
  network scoring, results scoring, and the promise filters. Every one of those changed after looking at
  actual filings, not before.
