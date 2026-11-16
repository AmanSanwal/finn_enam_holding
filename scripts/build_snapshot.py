"""End-of-day pipeline: fetch → classify → enrich → write the snapshot the app reads.

    python scripts/build_snapshot.py            # full build (portfolio + research set)
    python scripts/build_snapshot.py --quick    # skip transcripts/research

Runs in ~6–8 minutes cold (polite 3 s/request to each source), seconds warm (disk cache).
In production this is a scheduled job (EOD for prices/fundamentals, 5-minutely for the
NSE announcements feed), writing to a database instead of JSON files.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finn.data import filings as F  # noqa: E402
from finn.data import prices, screener  # noqa: E402
from finn.intel import network, research, results  # noqa: E402
from finn.intel.classify import classify  # noqa: E402
from finn.push import build_events  # noqa: E402
from finn.universe import PORTFOLIO, RESEARCH  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "data"
DEFAULT_PREFS = {"categories": ["results", "management", "mna", "litigation"], "vol_mult": 2.0, "price_pct": 4.0}


def main(quick: bool = False):
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "research").mkdir(exist_ok=True)
    syms = [p[0] for p in PORTFOLIO]
    meta = {p[0]: {"sector": p[1], "size": p[2]} for p in PORTFOLIO}

    print("· fundamentals")
    companies = {}
    for s in syms + [r for r in RESEARCH if r not in syms]:
        c = screener.fetch_company(s)
        if c:
            companies[s] = c
            (ROOT / "data" / "companies").mkdir(parents=True, exist_ok=True)
            json.dump(c, open(ROOT / "data" / "companies" / f"{s}.json", "w"), indent=1)
    port = {s: companies[s] for s in syms if s in companies}

    print("· filings")
    names = {c["name"]: s for s, c in port.items()}
    allf = F.merge(F.nse_rss(names), *[F.screener_recent(c) for c in port.values()],
                   category=lambda f: classify(f["title"], f["detail"]))

    print("· prices")
    px = prices.fetch_eod(syms, period="1y")

    print("· events")
    events = build_events(port, allf, DEFAULT_PREFS)

    as_of = max((e["ts"] for e in events if e.get("ts")), default=None)
    portfolio = []
    for s in syms:
        c = port.get(s)
        if not c:
            continue
        series = px.get(s, [])
        last, prev = (series[-1], series[-2]) if len(series) > 1 else (None, None)
        h = results.headline(c)
        portfolio.append({"symbol": s, "name": c["name"], **meta[s], "mcap": c["ratios"].get("Market Cap"),
                          "pe": c["ratios"].get("Stock P/E"), "close": last and last["c"], "date": last and last["d"],
                          "chg": round((last["c"] / prev["c"] - 1) * 100, 2) if last and prev else None,
                          "results": h, "surprise": h and results.surprise_score(h)})

    top_events = [e for e in events if e["tier"] in ("top", "watch")]
    snapshot = {
        "as_of": as_of, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "prefs": DEFAULT_PREFS, "portfolio": portfolio, "events": events,
        "prices": {s: [[r["d"], r["c"], r["v"]] for r in v[-130:]] for s, v in px.items()},
        "network": {"you": network.load()["you"],
                    "contacts": [network.contact_card(c["id"]) for c in network.load()["contacts"]],
                    "expertise": network.expertise_map(), "graph": network.graph(),
                    "nudges": network.nudges(top_events), "provenance": network.load()["_provenance"]},
        "research_set": RESEARCH,
        "stats": {"filings_scanned": len(allf), "companies": len(port), "sources": ["NSE RSS", "BSE (via screener.in)", "screener.in", "Yahoo Finance"]},
    }

    if not quick:
        print("· research (portfolio + research set)")
        idx = []
        for s, c in companies.items():
            try:
                r = research.build(s, company=c)
            except Exception as ex:  # one bad company must not break the brief
                print("  research failed", s, ex)
                continue
            json.dump(r, open(OUT / "research" / f"{s}.json", "w"), default=str, ensure_ascii=False)
            idx.append({"symbol": s, "name": c["name"], "in_portfolio": s in port})
        snapshot["research_index"] = idx
    else:
        prev = OUT / "snapshot.json"
        snapshot["research_index"] = json.load(open(prev)).get("research_index", []) if prev.exists() else []

    json.dump(snapshot, open(OUT / "snapshot.json", "w"), default=str, ensure_ascii=False)
    print(f"done in {time.time() - t0:.0f}s · {len(events)} events · {len(snapshot['research_index'])} research files")


if __name__ == "__main__":
    main(quick="--quick" in sys.argv)
