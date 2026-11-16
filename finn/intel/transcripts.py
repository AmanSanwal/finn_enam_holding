"""Concall transcripts → management's guidance, as structured, checkable claims.

Two-stage, cost-aware pipeline:
  Stage 1 (free, deterministic): segment the transcript into speaker turns, keep only
          management's turns, score every sentence for "forward-looking + quantified",
          and tag it with a metric (revenue growth, margin, capex, ...) and a parsed
          numeric target ("15-18%", "mid-teens", "double digit").  A 50-page transcript
          becomes ~10 candidate sentences — ~97% fewer tokens for any model that follows.
  Stage 2 (optional, cheap model): turn candidates into clean guidance JSON. Only runs
          when an API key is configured; results are cached by (symbol, call).
"""
from __future__ import annotations

import re

from ..data.filings import pdf_text

FWD = r"\b(expect|guid|target|aim|anticipat|outlook|going forward|next (year|quarter|few)|should (be|see|grow)|will (be|grow|see|reach|deliver|come|achieve)|plan to|we see|confident|aspire|trajectory|by fy|in fy|fy ?\d{2}|h2|second half|full year|medium term|ambition|on track)"
NUM = r"(\d+(?:\.\d+)?\s*(?:%|per ?cent|bps|basis points|crore|cr\b|x\b)|double[- ]digit|single[- ]digit|mid[- ]teens?|high[- ]teens?|low[- ]teens?|twenties)"
METRIC = [
    ("margin", r"margin|ebitda %|profitability"),
    ("revenue_growth", r"revenue|top ?line|sales|growth|grow|aum|loan book|advances|disbursement|income"),
    ("capex", r"capex|capital expenditure|invest(ing|ment)? of|capacity|plant|commission"),
    ("orders", r"order book|order inflow|pipeline|deal win|tcv"),
    ("asset_quality", r"credit cost|gnpa|npa|slippage|collection efficiency|par ?\d+"),
]
WORDS = {"double digit": (10, None), "double-digit": (10, None), "mid teens": (13, 17), "mid-teens": (13, 17), "mid teen": (13, 17),
         "high teens": (17, 19), "high-teens": (17, 19), "low teens": (10, 13), "low-teens": (10, 13),
         "high single digit": (7, 9), "high single-digit": (7, 9), "low single digit": (1, 3), "lower single digit": (1, 3),
         "mid single digit": (4, 6), "mid-single digit": (4, 6), "twenties": (20, 29)}


def call_quarter(period: str) -> str:
    """'Nov 2026' (call month) -> 'Sep 2026' (the quarter it discusses)."""
    mon, yr = period.split()[0][:3], int(period.split()[-1])
    m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(mon) + 1
    if m <= 3:
        return f"Dec {yr - 1}"
    return {2: "Mar", 3: "Jun", 4: "Sep"}[(m - 1) // 3 + 1] + f" {yr}"


def turns(text: str) -> list[tuple[str, str]]:
    text = re.sub(r"Page \d+ of \d+", " ", text)
    parts = re.split(r"\n\s*([A-Z][A-Za-z\.\s']{2,40}?)\s*:\s", "\n" + text)
    out = []
    for i in range(1, len(parts) - 1, 2):
        out.append((parts[i].strip(), re.sub(r"\s+", " ", parts[i + 1]).strip()))
    return out


def management_speakers(ts: list[tuple[str, str]], text: str) -> set[str]:
    analysts = set(m.strip() for m in re.findall(r"(?:line of|question (?:is )?from)\s+([A-Z][A-Za-z\.\s]{2,40}?)\s+(?:from|of|with)\s", text))
    words = {}
    for sp, body in ts:
        words[sp] = words.get(sp, 0) + len(body.split())
    mgmt = {sp for sp, w in words.items() if w > 150 and sp not in analysts and not re.search(r"moderator|operator", sp, re.I)}
    return mgmt


def parse_target(s: str):
    sl = s.lower()
    for w, (lo, hi) in WORDS.items():
        if w in sl:
            return lo, hi, "%"
    m = re.search(r"(\d+(?:\.\d+)?)\s*%?\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*%", sl)
    if m:
        return float(m.group(1)), float(m.group(2)), "%"
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(\+|plus|or more|and above)?", sl)
    if m:
        v = float(m.group(1))
        return v, (None if m.group(2) else v), "%"
    m = re.search(r"(?:rs\.?|₹|inr)?\s*([\d,]+(?:\.\d+)?)\s*(?:-|–|to)\s*(?:rs\.?|₹|inr)?\s*([\d,]+(?:\.\d+)?)\s*(crore|cr\b)", sl)
    if m:
        return float(m.group(1).replace(",", "")), float(m.group(2).replace(",", "")), "₹ cr"
    m = re.search(r"(?:rs\.?|₹|inr)?\s*([\d,]+(?:\.\d+)?)\s*(crore|cr\b)", sl)
    if m:
        v = float(m.group(1).replace(",", ""))
        return v, v, "₹ cr"
    return None, None, None


def candidates(text: str, limit: int = 10) -> list[dict]:
    ts = turns(text)
    mgmt = management_speakers(ts, text)
    out = []
    for sp, body in ts:
        if sp not in mgmt:
            continue
        for sent in re.split(r"(?<=[\.\?!])\s+", body):
            s = sent.strip()
            if not (40 <= len(s) <= 420):
                continue
            fwd = len(re.findall(FWD, s, re.I))
            num = len(re.findall(NUM, s, re.I))
            if not fwd or not num:
                continue
            metric = next((k for k, pat in METRIC if re.search(pat, s, re.I)), "other")
            lo, hi, unit = parse_target(s)
            score = fwd + 1.5 * num + (1 if metric != "other" else 0) + (1 if lo is not None else 0)
            out.append({"speaker": sp, "quote": s, "metric": metric, "low": lo, "high": hi, "unit": unit, "score": score})
    out.sort(key=lambda x: -x["score"])
    seen, res = set(), []
    for c in out:  # diversity: at most 4 per metric
        k = c["metric"]
        if sum(1 for r in res if r["metric"] == k) >= 4 or c["quote"][:60] in seen:
            continue
        seen.add(c["quote"][:60])
        res.append(c)
        if len(res) >= limit:
            break
    return res


def guidance_history(company: dict, n_calls: int = 5) -> list[dict]:
    """For the last n calls: the quarter discussed + stage-1 guidance candidates (+ source link)."""
    calls = []
    for c in company["documents"]["concalls"]:
        if not c.get("transcript") or not c.get("period"):
            continue
        text = pdf_text(c["transcript"], max_pages=40)
        if not text:
            continue
        calls.append({"call": c["period"], "quarter": call_quarter(c["period"]), "url": c["transcript"],
                      "chars": len(text), "candidates": candidates(text), "opening": opening_remarks(text)})
        if len(calls) >= n_calls:
            break
    return calls


def opening_remarks(text: str, max_chars: int = 900) -> str:
    """Management's own description of the business — first substantial management turn."""
    ts = turns(text)
    mgmt = management_speakers(ts, text)
    for sp, body in ts:
        if sp in mgmt and len(body) > 400 and not re.search(r"joined by|senior members of the management|welcome", body[:400], re.I):
            sents = [s for s in re.split(r"(?<=[\.\?!])\s+", body)
                     if re.search(r"\b(we are|our (business|portfolio|segments?)|segment|platform|leading|largest|share of)\b", s, re.I)
                     and not re.search(r"forward-looking|disclaimer|thank", s, re.I)]
            return " ".join(sents)[:max_chars]
    return ""
