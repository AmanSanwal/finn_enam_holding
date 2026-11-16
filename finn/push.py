"""Push: turn raw filings + prices into a ranked, enriched brief.

Every filing is classified and scored (classify.py). Then only the ones that earn it get
enriched — and the enrichment is specific to the type:
  * management change -> who the person is (from the filing's own SEBI-mandated profile)
                         + who in your network is linked to them, and how strongly
  * results           -> Revenue / EBITDA / PBT / PAT, QoQ and YoY, plus a one-line read
  * M&A, litigation, capex -> key facts pulled from the filing + the best person to call
Everything else gets its exchange one-liner at the right priority, or is buried.
"""
from __future__ import annotations

import re

from .data.filings import pdf_text
from .intel import classify as C
from .intel import network, people, results

ASK = {
    "resigned": ["Was this planned, or sudden? Notice period suggests which.", "Any disagreement on accounting, provisioning or guidance?",
                 "Is there an internal successor, or is this an outside search?"],
    "appointed": ["What mandate was this person hired with?", "What did they change in their last role, and what broke?",
                  "Who did they replace, and why did that person leave?"],
    "ceased": ["Why now — tenure end, or performance?", "Who runs the business day-to-day in the interim?",
               "Does this change the strategy the outgoing person was associated with?"],
    "demise": ["Is the promoter shareholding transmission clear (will, family arrangement)?", "Does board or management control change?",
               "Was this person still involved in day-to-day decisions?"],
}


def _facts(text: str) -> list[str]:
    """Cheap, high-precision fact extraction from the covering letter (not the attached financials)."""
    facts = []
    t = re.sub(r"\s+", " ", text)
    cut = re.search(r"(Independent Auditor'?s? (Limited )?Review Report|Review Report to the Board|Statement of Un-?audited (Standalone|Consolidated))", t, re.I)
    t = t[: cut.start()] if cut else t[:6000]
    for m in re.finditer(r"((?:for|to) (?:establish|establishing|undertake|set up|setting up|acquire|acquiring)[^.]{25,200})", t, re.I):
        facts.append(m.group(1).strip()[0].upper() + m.group(1).strip()[1:])
    for m in re.finditer(r"([^.]{0,90}?(?:approx\.?|about|around)?\s*\d+(?:\.\d+)?\s*%\s*of (?:the )?(?:company'?s )?(?:annual |total )?(?:consolidated )?(?:revenue|turnover|sales)[^.]{0,40})", t, re.I):
        facts.append(m.group(1).strip().rstrip(",") )
    for m in re.finditer(r"((?:returnable|hearing|next date|listed)[^.]{0,30}?\d{1,2}(?:st|nd|rd|th)? \w+ 20\d{2})", t, re.I):
        facts.append(m.group(1).strip())
    for m in re.finditer(r"([^.]{0,60}(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d+)?\s*(?:crore|cr|lakh|million|billion)[^.]{0,60})", t, re.I):
        facts.append(m.group(1).strip())
    out = []
    for f in facts:
        if len(f) > 20 and f not in out:
            out.append(f if len(f) <= 220 else f[:220].rsplit(" ", 1)[0] + "…")
    return out[:3]


def _results_events(companies: dict, filings: list[dict]) -> list[dict]:
    """One results event per company, dated by the earliest results-related filing we can see."""
    out = []
    for sym, comp in companies.items():
        h = results.headline(comp)
        if not h:
            continue
        rel = [f for f in filings if f["symbol"] == sym and re.search(r"result|transcript|investor presentation", f["title"] + " " + f["detail"], re.I)]
        rel.sort(key=lambda f: f["ts"])
        if not rel:
            continue
        f0 = rel[0]
        out.append({"id": f"res-{sym}-{h['period'].replace(' ', '')}", "symbol": sym, "ts": f0["ts"], "source": f0["source"],
                    "title": f"Results — quarter ended {h['period']}", "detail": h["read"], "url": f0["url"],
                    "category": "results", "synthetic": True})
    return out


def build_events(companies: dict, filings: list[dict], prefs: dict | None = None, *, enrich_pdfs: bool = True) -> list[dict]:
    events = []
    for f in filings:
        cat = C.classify(f["title"], f["detail"])
        if cat == "results":  # results are represented once, by the results pipeline below
            continue
        comp = companies.get(f["symbol"], {})
        sc, why = C.score(cat, f["title"], f["detail"], prefs, (comp.get("ratios") or {}).get("Market Cap"))
        events.append({**f, "category": cat, "labels": C.labels(f["title"], f["detail"]), "score": sc, "why": why})
    for r in _results_events(companies, filings):
        h = results.headline(companies[r["symbol"]])
        surprise = results.surprise_score(h)
        sc = 45 + int(surprise * 15)            # a routine quarter is 'worth a glance'; a big move 'needs you'
        by = {m["key"]: m for m in h["metrics"]}
        if (by.get("pat", {}).get("yoy") or 0) <= -30 or (h["margin"] and h["margin"]["yoy_bps"] <= -300):
            sc += 18                            # downside surprises matter more than upside ones
        sc = min(95, sc)
        events.append({**r, "labels": ["results"], "score": sc, "why": ["Quarterly results — numbers below"],
                       "results": h})

    for e in events:
        comp = companies.get(e["symbol"], {})
        e["name"] = comp.get("name", e["symbol"])
        e["tier"] = C.tier(e["score"])
        e["card"] = C.CATEGORIES[e["category"]][2] if e["tier"] != "buried" else "buried"
        e["label"] = C.CATEGORIES[e["category"]][0]
        e["headline"] = e["detail"] if len(e["detail"]) > 12 else e["title"]
        if e["tier"] != "top" or not enrich_pdfs:
            continue
        text = pdf_text(e["url"]) if e.get("url", "").lower().endswith(".pdf") or "AnnPdfOpen" in e.get("url", "") else ""
        if e["category"] == "management":
            ps = people.extract(text, e["detail"])
            # the person the headline is about leads; drop role-less bystanders (signatories, scrutinisers)
            ps.sort(key=lambda p: (p["name"].split()[-1].lower()[:5] not in e["detail"].lower(), p["role"] is None))
            ps = [p for i, p in enumerate(ps) if i == 0 or p["role"] or p["name"].split()[-1].lower()[:5] in e["detail"].lower()]
            for p in ps:
                p["links"] = network.links_to_person(p) if p.get("career") or p.get("education") else []
                p["ask"] = ASK.get(p["action"], ASK["appointed"])
            e["people"] = ps
            topic = "finance cfo controller" if re.search(r"cfo|financial", e["detail"], re.I) else \
                    "risk credit" if re.search(r"risk|cro", e["detail"], re.I) else e["detail"]
            e["who_to_call"] = network.who_to_call(e["symbol"], topic=topic, limit=3)
        elif e["category"] in ("mna", "litigation", "capex", "fundraise"):
            e["facts"] = _facts(text)
            e["who_to_call"] = network.who_to_call(e["symbol"], topic=f"{e['title']} {e['detail']}", limit=3)
        elif e["category"] == "results":
            e["who_to_call"] = network.who_to_call(e["symbol"], limit=2)
    events.sort(key=lambda x: (x["ts"] or ""), reverse=True)
    return events
