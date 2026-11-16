**To:** assessment@enam.com
**Subject:** IIT Kanpur – Founding AI Engineer - 2027

Hello,

Here is my submission for the FINN build challenge.

- **Prototype (open on a phone):** https://claude.ai/artifact/Dfh6QNxQofXTVbhyLEroLq
- **Repository:** https://github.com/AmanSanwal/finn_enam_holding
- **AI build history:** https://claude.ai/code/session_017oHiQR28zEu9dwviCMcKnN (plus `docs/BUILD_LOG.md` in the repo)

**What I built**

FINN is a mobile web app with three tabs. The network runs through all of them as a violet thread.

- **Brief (Push).** Every exchange filing across a 19-stock portfolio for the window you pick (24h to 30
  days). FINN triages each one into *needs you*, *worth a glance* or *buried*, and shows its reasoning
  ("Why this?"). Each type of event gets its own card:
  - *Management change*: the person's bio, taken from the filing's SEBI-mandated brief profile, and
    "your way in" through a contact.
  - *Results*: Revenue / EBITDA / PBT / PAT, QoQ and YoY, plus a one-line read.
  - *Material event*: facts pulled from the PDF and the best person to call.

  Price and volume alerts use thresholds you set with sliders, and there's a results-season heatmap.
- **Ask (Pull).** Research on any NSE ticker, built only from filed financials and concall transcripts:
  snapshot, trajectory, balance sheet, cash quality, *promised vs delivered* over the last four calls,
  bull/bear, and who to call.
- **Network.** The contacts' expertise map, reasons to reconnect (someone gone quiet whose former
  employer just filed something material), a network map and contact sheets. It also answers inside the
  other tabs.

All of it runs on real data as of 16 Nov 2026. A few examples from that data:
- Equitas SFB's new CRO (filed that day) is linked to a contact who was Chief Credit Officer at his
  previous bank. FINN labels it a *possible overlap* because the filing gives no dates.
- Subex's CFO resignation is scored 95. With no successor named, FINN points to "who'd know why".
- CG Power's plant-closure order surfaces the contact who ran that exact plant.
- Kaynes's FY26 guidance went ₹4,500 cr → ₹4,000 cr → ₹3,626 cr delivered.

**Key decisions and trade-offs**
- **A brief, not a feed.** The hero sentence says how many things need you out of how many filings, and
  routine filings are counted and folded away. My view is that the product's value is judgment shown
  transparently, not aggregation.
- **Bios from filings, not scraping.** SEBI requires a brief profile of every appointed KMP or director,
  so the bio is a primary source. Employers are pulled out with dictionary NER against an org registry.
  Links to the network are inferred from career overlap and weighted sceptically: overlapping years,
  seniority, and company size (a shared stint at a 3,000-person firm counts; at a 300,000-person firm it
  barely does). Every link is labelled *inferred*.
- **Deterministic first, model second.** Classification, scoring, results, network matching and a
  rules-based promise check all run with no model. Speaker segmentation cuts a 50-page transcript to
  about 10 candidate guidance lines, roughly 98% fewer tokens, before any model sees it.
- **Model routing.** Claude Haiku 5.5 handles bulk extraction. Claude Opus 5.5 only handles promised vs
  delivered and bull/bear, cached per company per call. The router is opt-in, keeps a cost ledger, and
  falls back to the rules path with no key.
- **Data sources.**
  - Free, public, and fetched politely: robots.txt respected, 3 s per host, cached forever where the
    data is immutable.
  - BSE's JSON API rejects bots, so I used NSE's official RSS feed for live filings and BSE filing
    history via screener.in.
  - Production would use a licensed exchange feed.

**Architecture** (diagram and detail in the README)
- **Pipelines:** a Python job (EOD, plus the 5-minute RSS poller in production) writes a snapshot. A
  FastAPI service does live research for any ticker.
- **Privacy:**
  - The network lives in a separate per-user store with row-level security and encryption.
  - FINN stores only what the investor imports plus interaction metadata (dates and counts, never
    content), deletable on request. People-in-filings data is limited to what the company published.
  - Network matching is code, not a model, so contact data never goes to an LLM by default.
  - Sharing with a team is a per-contact opt-in.
- **Cloud:** Cloud Run jobs and API, Cloud SQL, object storage for PDFs, and FCM/APNs for push.

**Being upfront about what's real**
- **Network:** the 30 contacts are synthetic. The companies and filings are real.
- **Model outputs:** I had no API key while building. The reasoning-tier outputs for PI Industries and
  Kaynes were written in the coding-agent session from the same extracted inputs. They are cached and
  labelled as such, and every number is checked against the filed tables. Every other company shows the
  rules-only pass.

**Deliberately left out:** chat, segment revenue mix (needs annual-report table parsing), real push
notifications, auth and multi-user, and gross-margin checks (FINN marks those *unverifiable* rather than
guessing).

**Next:**
1. Results-day autopilot: extract line items from the results PDF, reconcile them against a second
   source, check them against last call's guidance, and push within minutes.
2. A tool-using research agent for multi-hop questions across the portfolio and the network.
3. A "draft the intro" action on person cards.
4. Per-investor relevance learning from "not useful" swipes.

Thank you for the interesting problem.

Best regards,
<Your name>
