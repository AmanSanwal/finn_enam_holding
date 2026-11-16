"""Pull: on-demand research for ANY NSE ticker, grounded only in primary data.

Inputs: the company's filed financial statements (via screener.in's standardised tables)
and its concall transcripts (BSE-hosted PDFs). No news, no broker notes, no model priors.

Every section is computed deterministically first, so the research view works with no
model at all; the 'reason' tier (llm.py) is layered on top for promise-vs-delivery and
bull/bear, and every model output is cached per (symbol, latest call).
"""
from __future__ import annotations

import re

from urllib.parse import urlparse

from .. import llm
from ..data import screener
from . import network, results, transcripts


def _series(t: dict | None, *names, drop_ttm=True):
    if not t:
        return [], []
    for n in names:
        if n in t["rows"]:
            per, vals = t["periods"], t["rows"][n]
            if drop_ttm and per and per[-1] == "TTM":
                per, vals = per[:-1], vals[:-1]
            return per, vals
    return t["periods"], []


def _cagr(vals: list, years: int):
    v = [x for x in vals if x is not None]
    if len(v) <= years or not v[-1 - years] or v[-1 - years] <= 0 or v[-1] <= 0:
        return None
    return round(((v[-1] / v[-1 - years]) ** (1 / years) - 1) * 100, 1)


def _last(vals):
    v = [x for x in vals if x is not None]
    return v[-1] if v else None


def financial_snapshot(c: dict) -> dict:
    r = c["ratios"]
    per, sales = _series(c["annual"], "Sales", "Revenue", drop_ttm=False)
    _, pat = _series(c["annual"], "Net Profit", drop_ttm=False)
    _, opm = _series(c["annual"], "OPM %", "Financing Margin %", drop_ttm=False)
    _, borr = _series(c["balance_sheet"], "Borrowings", drop_ttm=False)
    _, eq = _series(c["balance_sheet"], "Equity Capital", drop_ttm=False)
    _, res = _series(c["balance_sheet"], "Reserves", drop_ttm=False)
    de = round(_last(borr) / (_last(eq) + _last(res)), 2) if borr and eq and res and (_last(eq) + _last(res)) else None
    return {"market_cap": r.get("Market Cap"), "price": r.get("Current Price"), "pe": r.get("Stock P/E"),
            "roce": r.get("ROCE"), "roe": r.get("ROE"), "div_yield": r.get("Dividend Yield"),
            "high_low": r.get("High / Low"), "ttm_revenue": _last(sales), "ttm_pat": _last(pat),
            "ttm_opm": _last(opm), "debt_equity": de, "period": per[-1] if per else None}


def trajectory(c: dict) -> dict:
    per, sales = _series(c["annual"], "Sales", "Revenue")
    _, op = _series(c["annual"], "Operating Profit", "Financing Profit")
    _, pat = _series(c["annual"], "Net Profit")
    _, opm = _series(c["annual"], "OPM %", "Financing Margin %")
    n = min(len(per), 8)
    out = {"periods": per[-n:], "revenue": sales[-n:], "ebitda": op[-n:], "pat": pat[-n:], "opm": opm[-n:],
           "rev_cagr_3y": _cagr(sales, 3), "rev_cagr_5y": _cagr(sales, 5),
           "pat_cagr_3y": _cagr(pat, 3), "pat_cagr_5y": _cagr(pat, 5)}
    calls = []
    if out["rev_cagr_3y"] is not None and out["rev_cagr_5y"] is not None:
        if out["rev_cagr_3y"] < out["rev_cagr_5y"] - 4:
            calls.append(f"Growth is decelerating: revenue CAGR {out['rev_cagr_3y']}% over 3y vs {out['rev_cagr_5y']}% over 5y")
        elif out["rev_cagr_3y"] > out["rev_cagr_5y"] + 4:
            calls.append(f"Growth is accelerating: revenue CAGR {out['rev_cagr_3y']}% over 3y vs {out['rev_cagr_5y']}% over 5y")
    om = [x for x in opm[-n:] if x is not None]
    if len(om) >= 4:
        if om[-1] < sum(om[:-1]) / len(om[:-1]) - 2:
            calls.append(f"Margins compressing: {om[-1]:.0f}% latest vs {sum(om[:-1]) / len(om[:-1]):.0f}% average of prior years")
        elif om[-1] > sum(om[:-1]) / len(om[:-1]) + 2:
            calls.append(f"Margins expanding: {om[-1]:.0f}% latest vs {sum(om[:-1]) / len(om[:-1]):.0f}% average of prior years")
    if out["pat_cagr_3y"] is not None and out["rev_cagr_3y"] is not None and out["pat_cagr_3y"] - out["rev_cagr_3y"] > 5:
        calls.append(f"Operating leverage: PAT compounding faster ({out['pat_cagr_3y']}%) than revenue ({out['rev_cagr_3y']}%)")
    out["calls"] = calls
    return out


def balance_sheet(c: dict) -> dict:
    per, borr = _series(c["balance_sheet"], "Borrowings", drop_ttm=False)
    _, eq = _series(c["balance_sheet"], "Equity Capital", drop_ttm=False)
    _, res = _series(c["balance_sheet"], "Reserves", drop_ttm=False)
    _, cwip = _series(c["balance_sheet"], "CWIP", drop_ttm=False)
    _, fa = _series(c["balance_sheet"], "Fixed Assets", drop_ttm=False)
    eff_per, ccc = _series(c["efficiency"], "Cash Conversion Cycle", drop_ttm=False)
    _, debtor = _series(c["efficiency"], "Debtor Days", drop_ttm=False)
    _, inv = _series(c["efficiency"], "Inventory Days", drop_ttm=False)
    _, roce = _series(c["efficiency"], "ROCE %", drop_ttm=False)
    n = min(len(per), 6)
    de = [round(b / (e + r), 2) if None not in (b, e, r) and (e + r) else None for b, e, r in zip(borr, eq, res)]
    calls = []
    if de and de[-1] is not None:
        calls.append("Virtually debt-free" if de[-1] < 0.1 else f"Debt/equity {de[-1]:.2f}" + (" — rising" if len(de) > 3 and de[-4] is not None and de[-1] > de[-4] + 0.15 else ""))
    if len(ccc) >= 4 and None not in (ccc[-1], ccc[-4]) and ccc[-1] - ccc[-4] > 20:
        calls.append(f"Working capital stretching: cash-conversion cycle {ccc[-4]:.0f} → {ccc[-1]:.0f} days in 3 years")
    if cwip and fa and _last(cwip) and _last(fa) and _last(cwip) / _last(fa) > 0.15:
        calls.append(f"Heavy capex under way: CWIP is {_last(cwip) / _last(fa) * 100:.0f}% of fixed assets")
    return {"periods": per[-n:], "borrowings": borr[-n:], "net_worth": [(e or 0) + (r or 0) for e, r in zip(eq, res)][-n:],
            "debt_equity": de[-n:], "cwip": cwip[-n:], "eff_periods": eff_per[-6:], "ccc": ccc[-6:],
            "debtor_days": debtor[-6:], "inventory_days": inv[-6:], "roce": roce[-6:], "calls": calls}


def cash_quality(c: dict) -> dict:
    per, cfo = _series(c["cash_flow"], "Cash from Operating Activity")
    _, fcf = _series(c["cash_flow"], "Free Cash Flow")
    ap, pat = _series(c["annual"], "Net Profit")
    pat_by = dict(zip(ap, pat))
    n = min(len(per), 6)
    pairs = [(p, f, pat_by.get(p)) for p, f in zip(per[-5:], cfo[-5:])]
    s_cfo = sum(x[1] for x in pairs if x[1] is not None and x[2] is not None)
    s_pat = sum(x[2] for x in pairs if x[1] is not None and x[2] is not None)
    conv = round(s_cfo / s_pat, 2) if s_pat else None
    calls = []
    if conv is not None:
        calls.append(f"{'Strong' if conv >= 0.9 else 'Weak' if conv < 0.7 else 'Adequate'} cash conversion: "
                     f"5-yr operating cash flow is {conv:.2f}× reported profit")
    neg_fcf = sum(1 for x in fcf[-5:] if x is not None and x < 0)
    if neg_fcf >= 3:
        calls.append(f"Free cash flow negative in {neg_fcf} of the last 5 years")
    return {"periods": per[-n:], "cfo": cfo[-n:], "fcf": fcf[-n:], "pat": [pat_by.get(p) for p in per[-n:]],
            "conversion_5y": conv, "calls": calls}


def shareholding(c: dict) -> dict | None:
    t = c.get("shareholding")
    if not t:
        return None
    out = {"periods": t["periods"][-6:]}
    for k in ("Promoters", "FIIs", "DIIs", "Public"):
        if k in t["rows"]:
            out[k.lower()] = t["rows"][k][-6:]
    return out


# ---------------------------------------------------------------- promise vs delivery

def _q_index(periods: list[str], q: str):
    return periods.index(q) if q in periods else None


def check_promises(c: dict, calls: list[dict]) -> list[dict]:
    """Deterministic first pass: test each quantified promise against what was reported afterwards."""
    q = c["quarters"]
    per = q["periods"]
    rev = q["rows"].get("Sales") or q["rows"].get("Revenue") or []
    opm = q["rows"].get("OPM %") or []
    rows = []
    for call in calls[:4]:
        i = _q_index(per, call["quarter"])
        for g in call["candidates"]:
            ql = g["quote"].lower()
            if g["low"] is None or g["metric"] not in ("revenue_growth", "margin", "capex"):
                continue
            # rules pass keeps only forward-looking company statements: drop past facts, tax rates, industry/market forecasts
            if not re.search(r"\b(will|expect|guid|target|should|plan|aim|going forward|next year|commit|maintain|trajectory)", ql):
                continue
            if re.search(r"\b(etr|tax rate)\b", ql) or (g["metric"] == "revenue_growth" and re.search(r"\b(industry|market|gdp|globally|global)\b", ql)):
                continue
            if re.search(r"\b(delivered|reported|registered|grew|achieved)\b", ql) and not re.search(r"\b(will|expect|guid)", ql):
                continue
            row = {"given_in": call["call"], "quarter": call["quarter"], "metric": g["metric"], "quote": g["quote"],
                   "speaker": g["speaker"], "source": call["url"], "promise": _fmt_promise(g)}
            after = list(range(i + 1, len(per))) if i is not None else []
            if g["metric"] == "margin":
                if any(k in g["quote"].lower() for k in ("gross", "gp ", "gp margin", "contribution")):
                    row.update(status="unverifiable", actual="Gross margin isn't in the standardised P&L — needs the filing's notes")
                elif not after:
                    row.update(status="too_early", actual="No quarter reported since")
                elif opm:
                    vals = [opm[j] for j in after if opm[j] is not None]
                    avg = sum(vals) / len(vals) if vals else None
                    row["actual"] = f"EBITDA margin since: {', '.join(f'{v:.0f}%' for v in vals)}"
                    row["status"] = ("delivered" if avg >= g["low"] - 1 else "partly" if avg >= g["low"] - 4 else "missed") if avg is not None else "unverifiable"
            elif g["metric"] == "revenue_growth":
                if g["unit"] != "%" or g["low"] > 60:
                    continue  # absolute ₹ targets / segment anecdotes aren't company-level growth guidance
                if not after:
                    row.update(status="too_early", actual="No quarter reported since")
                else:
                    yoy = [(rev[j] / rev[j - 4] - 1) * 100 for j in after if j >= 4 and rev[j] and rev[j - 4]]
                    avg = sum(yoy) / len(yoy) if yoy else None
                    row["actual"] = f"Revenue YoY since: {', '.join(f'{v:+.0f}%' for v in yoy)}"
                    row["status"] = ("delivered" if avg >= g["low"] - 1 else "partly" if avg >= g["low"] * 0.5 else "missed") if avg is not None else "unverifiable"
            elif g["metric"] == "capex":
                row.update(status="tracking", actual="Annual capex is reported yearly — checked at year end")
            rows.append(row)
    return rows[:10]


def _fmt_promise(g):
    if g["high"] is None:
        return f"{g['metric'].replace('_', ' ')} ≥ {g['low']:g}{g['unit'] or ''}"
    if g["high"] == g["low"]:
        return f"{g['metric'].replace('_', ' ')} ~{g['low']:g}{g['unit'] or ''}"
    return f"{g['metric'].replace('_', ' ')} {g['low']:g}–{g['high']:g}{g['unit'] or ''}"


def bull_bear_signals(snap, traj, bs, cash, h, share, promises) -> dict:
    bull, bear = [], []
    if traj["rev_cagr_5y"] is not None:
        (bull if traj["rev_cagr_5y"] >= 12 else bear if traj["rev_cagr_5y"] < 6 else []).append(
            (abs(traj["rev_cagr_5y"] - 9), f"Revenue compounded {traj['rev_cagr_5y']}% a year over 5 years"))
    if snap.get("roce") is not None:
        (bull if snap["roce"] >= 20 else bear if snap["roce"] < 12 else []).append(
            (abs(snap["roce"] - 16) / 2, f"ROCE {snap['roce']:.0f}%"))
    if cash["conversion_5y"] is not None:
        (bull if cash["conversion_5y"] >= 0.9 else bear if cash["conversion_5y"] < 0.7 else []).append(
            (abs(cash["conversion_5y"] - 0.8) * 20, f"Operating cash flow is {cash['conversion_5y']:.2f}× profit over 5 years"))
    if bs["debt_equity"] and bs["debt_equity"][-1] is not None and not h.get("is_bank"):
        de = bs["debt_equity"][-1]
        (bull if de < 0.1 else bear if de > 1 else []).append((3 if de < 0.1 else de * 3, "Virtually debt-free balance sheet" if de < 0.1 else f"Debt/equity at {de:.2f}"))
    if h and h["margin"]:
        m = h["margin"]
        hist = [x for x in m["series"] if x is not None]
        if m["yoy_bps"] <= -300:
            bear.append((abs(m["yoy_bps"]) / 150, f"EBITDA margin down {abs(m['yoy_bps'])} bps YoY to {m['cur']:.0f}%" + (" — a 9-quarter low" if hist and m["cur"] <= min(hist) else "")))
        elif m["yoy_bps"] >= 300:
            bull.append((m["yoy_bps"] / 150, f"EBITDA margin up {m['yoy_bps']} bps YoY to {m['cur']:.0f}%"))
    if h:
        by = {x["key"]: x for x in h["metrics"]}
        if "revenue" in by and by["revenue"]["yoy"] is not None:
            y = by["revenue"]["yoy"]
            (bull if y >= 15 else bear if y < 0 else []).append((abs(y) / 5, f"Latest quarter revenue {y:+.0f}% YoY"))
    if share and share.get("promoters") and len(share["promoters"]) >= 4 and None not in (share["promoters"][-1], share["promoters"][0]):
        d = share["promoters"][-1] - share["promoters"][0]
        if d <= -2:
            bear.append((abs(d), f"Promoter holding down {abs(d):.1f} pts over 6 quarters"))
    if share and share.get("fiis") and len(share["fiis"]) >= 4 and None not in (share["fiis"][-1], share["fiis"][0]):
        d = share["fiis"][-1] - share["fiis"][0]
        if abs(d) >= 2:
            (bull if d > 0 else bear).append((abs(d) / 2, f"FII holding {'up' if d > 0 else 'down'} {abs(d):.1f} pts over 6 quarters"))
    for calls_ in (traj["calls"], bs["calls"]):
        for t in calls_:
            if "stretching" in t or "compressing" in t or "decelerating" in t or "rising" in t:
                bear.append((2.5, t))
            elif "accelerating" in t or "expanding" in t or "leverage" in t:
                bull.append((2.5, t))
    hit = sum(1 for p in promises if p.get("status") == "delivered")
    miss = sum(1 for p in promises if p.get("status") == "missed")
    if hit >= 2 and hit > miss:
        bull.append((hit, f"Delivered {hit} of {hit + miss} checkable promises from recent calls"))
    if miss >= 2 and miss >= hit:
        bear.append((miss * 1.5, f"Missed {miss} of {hit + miss} checkable promises from recent calls"))
    top = lambda xs: [t for _, t in sorted(xs, key=lambda x: -x[0])[:3]]
    return {"bull": top(bull), "bear": top(bear)}


def build(symbol: str, *, company: dict | None = None, n_calls: int = 5) -> dict:
    c = company or screener.fetch_company(symbol)
    if not c:
        raise LookupError(f"No data for {symbol}")
    snap = financial_snapshot(c)
    traj = trajectory(c)
    bs = balance_sheet(c)
    cash = cash_quality(c)
    h = results.headline(c)
    share = shareholding(c)
    calls = transcripts.guidance_history(c, n_calls=n_calls)
    promises = check_promises(c, calls)
    latest = calls[0]["call"] if calls else "na"
    bb = bull_bear_signals(snap, traj, bs, cash, h or {}, share, promises)

    # Reasoning tier (cached; live only with an API key). Inputs are the extracted numbers + verbatim quotes only.
    actuals = {"periods": c["quarters"]["periods"][-6:],
               "revenue": (c["quarters"]["rows"].get("Sales") or c["quarters"]["rows"].get("Revenue"))[-6:],
               "ebitda_margin_pct": (c["quarters"]["rows"].get("OPM %") or [None] * 6)[-6:],
               "pat": c["quarters"]["rows"]["Net Profit"][-6:]}
    guidance_in = [{"call": x["call"], "quarter": x["quarter"], "quotes": [g["quote"] for g in x["candidates"]]} for x in calls[:4]]
    pvd = llm.complete(f"promise_delivery:{symbol}:{latest}", tier="reason", system=llm.VERDICT_SYSTEM,
                       user=f"GUIDANCE:\n{guidance_in}\n\nREPORTED (₹ cr, quarterly):\n{actuals}", schema=llm.VERDICT_SCHEMA)
    bb_llm = llm.complete(f"bull_bear:{symbol}:{latest}", tier="reason", system=llm.BULLBEAR_SYSTEM,
                          user=f"SIGNALS: {bb}\nTRAJECTORY: {traj['calls']}\nBALANCE SHEET: {bs['calls']}\nCASH: {cash['calls']}\n"
                               f"RESULTS: {h and h['read']}\nQUOTES: {guidance_in[:2]}", schema=llm.BULLBEAR_SCHEMA)
    pvd_meta = llm.cached(f"promise_delivery:{symbol}:{latest}")
    return {
        "symbol": c["symbol"], "name": c["name"], "source_url": c["source_url"], "fetched_at": c["fetched_at"],
        "consolidated": c["consolidated"], "bse_code": c["bse_code"],
        "business": {"about": c["about"], "in_their_words": calls[0]["opening"] if calls else "",
                     "in_their_words_source": calls[0]["url"] if calls else None},
        "snapshot": snap, "results": h, "trajectory": traj, "balance_sheet": bs, "cash": cash, "shareholding": share,
        "guidance": [{"call": x["call"], "quarter": x["quarter"], "url": x["url"], "chars": x["chars"],
                      "items": x["candidates"][:6]} for x in calls],
        "promises": promises,
        "promise_verdict": pvd, "promise_verdict_by": pvd_meta and pvd_meta["producer"],
        "bull_bear": bb_llm or bb, "bull_bear_by": "model" if bb_llm else "rules",
        "who_to_call": network.who_to_call(c["symbol"], limit=4),
        "sources": {"annual_reports": c["documents"]["annual_reports"][:3], "concalls": [x["url"] for x in calls]},
        "transcripts_unreachable": sorted({urlparse(x["transcript"]).netloc for x in c["documents"]["concalls"][:5]
                                           if x.get("transcript") and x["transcript"] not in [y["url"] for y in calls]}),
        "token_savings": {"transcript_chars": sum(x["chars"] for x in calls),
                          "sent_to_model_chars": sum(len(q) for x in guidance_in for q in x["quotes"])},
    }
