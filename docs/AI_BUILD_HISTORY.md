# AI build history

**Read this first.** This file records one session: the one in which this prototype was
drafted, with Claude (Anthropic) doing the code and document drafting under direction.
It is not a complete record of everything used to build FINN. Before you submit, add the
other sessions you actually ran (Claude Code, Cursor, ChatGPT, and so on) and export or link
them. Edit this file so it matches what you did. Do not submit anything here you did not do.

## Session 1: scope, data, and first build (single session, drafted with Claude)

**1. Problem breakdown.** I asked for the full brief to be turned into a deliverable list
(prototype, repo, build history, covering email). I flagged that the deadline in the brief was
15 Nov 2026 and today was 16 Nov, and asked whether to proceed. I chose to proceed.

**2. Scope cut.** The brief says thin-but-working beats broad-but-broken. I cut the live
data feeds and kept the three layers as working views over synthetic data. I chose a static
mobile-first page.

**3. Data design.** Named the tickers (15 portfolio, 3 ad-hoc), wrote the synthetic price
history with a seeded generator so the demo is stable, and planted a few spikes so the alert
engine has something to find. Wrote the network as ten invented people with employers,
schools, and relations to companies.

**4. Rules before models.** Chose rule-based scoring for filings, alerts and network overlap,
with a plan for a small model later. Reason: keeps it free, offline and explainable.

**5. Check.** Ran a syntax check and a smoke test of each view in Node with a stub DOM. The
first pass had a dead helper and an incoming-CFO profile that did not match anyone in the
network, so I changed the profile's school to match a contact so the overlap appears. Flag
this kind of fix in your own notes too.

**6. Not verified.** The price-fetch script has not been run against Yahoo. The app has not
been tested on a real phone.

## What I would add from my own sessions

- [ ] Session with the first prompt and how I broke the problem down
- [ ] A place where the model's output was wrong, and how I corrected it
- [ ] A place where I rewrote code myself instead of accepting it, and why
- [ ] Any session on the pipeline or the network matching logic
- [ ] Links or exports for each session
