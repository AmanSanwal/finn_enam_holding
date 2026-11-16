"""Announcement taxonomy + materiality scoring.

Deterministic on purpose: the exchange subject line already carries the SEBI LODR
category, so a rules layer classifies ~95% of filings for free and instantly. A cheap
model is only consulted for the residual 'other' bucket (see llm.py), and its answer is
cached by subject line so each new subject string is classified once, ever.

Materiality = base score of the category, adjusted by what the text says
(who changed — a CFO vs a company secretary; how big — a ₹12 lakh penalty vs a plant
closure), and by user preferences (the categories you said you care about).
"""
from __future__ import annotations

import re

# (key, label, base score, how Push presents it)
CATEGORIES = {
    "results":    ("Results",              90, "results_card"),
    "management": ("Management change",    80, "person_card"),
    "mna":        ("M&A / JV / restructuring", 88, "event_card"),
    "litigation": ("Litigation / regulatory", 78, "event_card"),
    "capex":      ("Capacity / capex",     70, "event_card"),
    "fundraise":  ("Fund raise / capital", 62, "one_liner"),
    "orders":     ("Order win",            55, "one_liner"),
    "rating":     ("Credit rating",        40, "one_liner"),
    "disclosure": ("Investor material",    35, "one_liner"),
    "transcript": ("Concall transcript",   45, "one_liner"),
    "meet":       ("Analyst / investor meet", 8, "buried"),
    "admin":      ("Routine / administrative", 3, "buried"),
    "newspaper":  ("Newspaper publication", 3, "buried"),
    "other":      ("Other",                25, "one_liner"),
}

RULES = [
    ("transcript", r"transcript"),
    ("newspaper", r"newspaper"),
    ("meet", r"analyst|investor meet|institutional investor|con\.? ?call update|conference call|non-deal roadshow|investor conference|audio recording"),
    ("results", r"(?<!issued by )(financial results?|results for the quarter|integrated filing.?financial|un-?audited.*results|quarterly results)(?!.{0,40}issued by)"),
    ("mna", r"acqui|amalgamat|merger|scheme of arrangement|joint venture|\bjv\b|restructur|demerg|divest|sale or disposal|slump sale|share swap"),
    ("management", r"change in (management|directorate|directors|key|kmp|smp)|appointment|resignation|cessation|demise|superannuat|re-?appoint|managing director|\bceo\b|\bcfo\b|chief (executive|financial|risk|operating)"),
    ("litigation", r"litigation|dispute|penalt|\bclosure|pollution control|orders? passed|actions? (initiated|taken)|sebi order|\bfraud|\bdefault\b|arrest|show cause|clarification sought|rumou?r|news verification|\bnclt|\bnclat|insolvency|\bcirp\b|tax demand|\bsearch\b|seizure"),
    ("capex", r"capacity|commercial (production|operations)|commission|expansion|new plant|greenfield|brownfield|capex"),
    ("fundraise", r"\bqip\b|qualified institutions|preferential|warrant|rights issue|buy-?back|fund ?rais|alteration of capital|issue of securities|\bncds?\b|debenture|commercial paper"),
    ("orders", r"bagging|receiving of orders|award(ing)? of order|order win|wins? .* order|contract"),
    ("rating", r"credit rating|rating"),
    ("disclosure", r"press release|investor presentation|shareholders letter|media release|half yearly report"),
    ("admin", r"newspaper|trading window|esop|esos|esps|allotment|record date|registrar|\brta\b|share certificate|duplicate|postal ballot|shareholders? meeting|agm|egm|dematerial|book closure|security cover|redemption|interest payment|nav|loss of share|scrutinizer|reg\.? ?29|sast|74\(5\)|regulation 7\(|regulation 6\(|kfin|corporate office|address"),
]

SENIOR = r"\b(managing director|md ?& ?ceo|\bmd\b|chief executive|\bceo\b|chief financial|\bcfo\b|chairman|chairperson|promoter|whole-?time director|executive director|chief risk|\bcro\b|chief operating|\bcoo\b|president)"
JUNIOR = r"company secretary|compliance officer|independent director|non-?executive director|auditor|\bgm\b|general manager|vice president|head of|head -|senior management personnel"


def _matches(text: str) -> list[str]:
    out = []
    for key, pat in RULES:
        if re.search(pat, text):
            # an auditor/RTA appointment is admin, not a management change
            if key == "management" and re.search(r"auditor|registrar|\brta\b", text) and not re.search(SENIOR, text):
                key = "admin"
            if key not in out:
                out.append(key)
    return out


def labels(title: str, detail: str = "") -> list[str]:
    """All categories a filing touches (a board outcome can be results + JV + a CEO exit)."""
    t = f"{title} {detail}".lower()
    title_cats = _matches(title.lower())
    if title_cats and title_cats[0] == "newspaper":
        return ["admin"]                            # newspaper ads repeat what was already filed
    if title_cats and title_cats[0] in ("meet", "transcript"):
        return title_cats[:1]                       # explicit, unambiguous subject lines
    if re.search(r"\besop|\besos|\besps|employee stock", t):
        return ["admin"]
    cats = [c for c in _matches(t) if c not in ("admin", "other", "newspaper")]
    return cats or title_cats or ["other"]


def classify(title: str, detail: str = "") -> str:
    """Primary category = the most material label. Results lose ties to events because the
    quarterly numbers already get their own card from the results pipeline."""
    labs = labels(title, detail)
    if len(labs) > 1 and "results" in labs:
        labs = [l for l in labs if l != "results"]
    return max(labs, key=lambda c: score(c, title, detail)[0])


def _amount_crore(text: str) -> float | None:
    """Biggest rupee amount mentioned, in crore (handles lakh/crore/million/billion)."""
    best = None
    for m in re.finditer(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(lakh|crore|cr|million|mn|billion|bn)?", text.lower()):
        v = float(m.group(1).replace(",", ""))
        unit = m.group(2) or "crore"
        v = {"lakh": v / 100, "crore": v, "cr": v, "million": v / 10, "mn": v / 10, "billion": v * 100, "bn": v * 100}[unit]
        best = max(best or 0, v)
    return best


def score(category: str, title: str, detail: str, prefs: dict | None = None, mcap_cr: float | None = None) -> tuple[int, list[str]]:
    """Return (0-100 materiality, reasons). Reasons are shown to the user: FINN explains its triage."""
    base = CATEGORIES[category][1]
    t = f"{title} {detail}".lower()
    why = []
    if category == "management":
        if re.search(r"demise|death", t):
            base, _ = 88, why.append("Promoter/leader passed away — succession and control questions")
        elif re.search(r"re-?appoint", t) and not re.search(r"\bnew\b", t):
            base, _ = 45, why.append("Re-appointment — continuity, not change")
        elif re.search(SENIOR, t):
            base, _ = 92, why.append("C-suite / board-level change")
        elif re.search(JUNIOR, t):
            base, _ = 42, why.append("Below the C-suite")
        if re.search(r"resign", t) and re.search(r"\bcfo\b|chief financial", t):
            base, _ = 95, why.append("CFO resignations are the classic early-warning signal")
    if category in ("litigation", "fundraise", "orders", "mna", "capex"):
        amt = _amount_crore(t)
        if amt is not None and mcap_cr:
            frac = amt / mcap_cr
            if frac < 0.001:
                base = min(base, 25)
                why.append(f"Small relative to size (₹{amt:,.2f} cr vs ₹{mcap_cr:,.0f} cr market cap)")
            elif frac > 0.02:
                base = min(99, base + 10)
                why.append(f"Large relative to size (~{frac*100:.1f}% of market cap)")
        if category == "fundraise" and re.search(r"commercial paper|\(cp\)|redeem|redemption", t):
            base, _ = 15, why.append("Routine treasury")
        if re.search(r"\bclosure|\bstay(ed)?\b|\bhalt|\bban\b|suspen", t) and category == "litigation":
            base, _ = max(base, 85), why.append("Operations at risk")
    if category == "rating" and re.search(r"downgrad|negative|watch", t):
        base, _ = 75, why.append("Rating action is negative")
    if prefs and prefs.get("categories") and category in prefs["categories"]:
        base = min(99, base + 5)
        why.append("A category you follow")
    return int(base), why


def tier(score_: int) -> str:
    """Three tiers: what you must see, what you may want, what FINN buries."""
    if score_ >= 75:
        return "top"
    if score_ >= 30:
        return "watch"
    return "buried"
