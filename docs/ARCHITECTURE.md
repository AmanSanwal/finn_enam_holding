# FINN — architecture

Status legend: **built** = in this repo and runs. **planned** = designed, not wired.

## 1. Shape of the system

```
          ┌──────────────── Push ────────────────┐   ┌──────────── Pull ────────────┐
          │ digest · threshold alerts · people   │   │ snapshot · numbers vs. words  │
          └──────────────┬───────────────────────┘   └───────────────┬──────────────┘
                         │                                           │
                         ▼                                           ▼
                 ┌──────────────── Network (overlap + relevance engine) ────────────┐
                 └──────────────────────────────┬───────────────────────────────────┘
                                                │
        ┌───────────────┬──────────────┬────────┴───────┬─────────────────┐
        ▼               ▼              ▼                ▼                 ▼
   prices (EOD)   filings (NSE/BSE)  fundamentals    profiles          investor's
   yfinance       announcements      screener.in     (public / synth)   network (private)
```

The browser app is a static page. It reads JSON that the pipeline writes. It never calls a
market or model API directly, so a phone never holds a key.

## 2. Data pipelines

| Source | Method | Refresh | Storage | Status |
|---|---|---|---|---|
| Price and volume | yfinance, `.NS` suffix, 40 sessions | after market close | `data/prices/<T>.json` | **built** (script; not yet run live) |
| Filings | NSE/BSE announcement feeds, classified into our category set | every 30 min in market hours | `data/filings/` | planned; demo data used |
| Fundamentals | annual report and transcript links from screener.in or IR site, parsed to text | on new filing | `data/docs/<T>/` | planned |
| Profiles | public professional profile, public dataset, or synthetic | weekly, or on demand | `data/people.json` | **built** as synthetic |

**Linking a name in a filing to a person in the network.** A filing names a person
("Anjali Mehta, CFO"). We normalise the name, then score candidates against the network on
exact name match, then employer overlap, then school overlap. Anything under a confidence
threshold is shown as "possible match — confirm" and never silently merged. Names alone are
not an identity key.

**Refresh.** Each source keeps its own timestamp. The app shows the age of every number.

## 3. Push: what earns attention

- Each filing gets a category weight (M&A and results rank highest; trading-window notices
  rank lowest). Results with numbers get a small bonus. A category the investor has chosen
  for alerts gets a small bonus too.
- Items below a cut-off collapse into a "routine" list rather than disappearing.
- **Built:** rule-based scoring. **Planned:** a small model reads each filing and proposes a
  category and a one-line summary, and a human-written rule can override it.

**Alerts.** The volume rule compares the latest session with the mean of the prior 30
sessions. The price rule compares the close with the previous close. Both thresholds are set
by the investor in the app.

## 4. Pull: grounding

Pull answers only from the annual report and the transcripts. Broker notes, news and the
model's own memory of the company are not inputs. Each claim in a Pull view cites its page.
**Built:** the demo renders a worked example from synthetic data. **Planned:** retrieval over
the cached documents, with citations.

**Numbers vs. narrative.** Guidance sentences are extracted from transcripts (guidance
statements are a bounded set: growth, margin, capex). Each is matched to the reported figure
in the following quarters, and a verdict is attached: met, partly met, missed, or not yet.

## 5. Security and privacy

- **What we store about people.** Name, public role, employer history, school, and the
  investor's own notes on each relationship. We do not store contact details, personal
  social media, or anything from a private account.
- **Where the network lives.** The network is per investor. Records carry an owner ID and
  are readable only by that owner. Nothing is shared across investors.
- **Retention.** Public profile snapshots are refreshed and expire after 90 days without
  access. The investor's own notes stay until they delete them.
- **Consent and access (real deployment).** Each contact would have a consent record, and the
  investor could delete a contact and its derived links in one action. Profile data would be
  fetched only from sources the platform's terms allow. Any contact who asks to be removed
  would be removed from every derived view.
- **Demo.** All people, companies' people, and profiles in this repo are invented.

## 6. LLMs and agents

| Step | Model class | Why |
|---|---|---|
| Filing classification and one-line summary | small, cheap model | bulk, short, many items per day |
| Management-change bio (from public profile) | mid-tier model | needs careful extraction and name matching |
| Numbers vs. narrative (guidance matching) | strongest model available | long context, reasoning across quarters |
| Caching | results keyed by document hash | a filing is processed once |

**Agents.** Only the Pull research path would use an agent loop. It plans a short list of
checks (fetch report, fetch transcript, extract guidance, match, verify), calls tools for
each, and stops when every claim has a citation. Push does not act on its own. It only
surfaces items and proposes a contact.

**Built today:** no model calls. Every category and score is rule-based, so the prototype
runs offline and costs nothing.

## 7. Cloud

- **Static front end** on any free static host (the app is one HTML file plus two scripts).
- **Pipeline** as a scheduled job (cron or a free-tier scheduled function), writing JSON.
- **Model calls** only from the pipeline, behind a cache, never from the browser.
- **Why:** the phone app stays cheap and fast, and secrets and personal data stay on the
  server side.

## 8. What we left out, on purpose

- Live filings scraping. It is fragile and the demo does not need it to be judged.
- Any login or multi-user accounts. One investor, one device.
- Voice. The interaction is text plus cards for now.
- Trading or any recommendation to buy or sell.
