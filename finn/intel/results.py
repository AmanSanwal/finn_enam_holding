"""Quarterly results: first cut of the headline numbers.

Revenue, EBITDA, PBT, PAT for the latest quarter vs last quarter (QoQ) and the same
quarter last year (YoY), plus margin moves in basis points, and a deterministic one-line
read ("the weakest EBITDA margin in 13 quarters") so the card says something even with no
LLM in the loop.

Numbers come from the exchange-filed quarterly results as standardised by screener.in
(row labels differ for banks: Revenue/Financing Profit — handled below). The card links
to the actual results filing PDF on the exchange.
"""
from __future__ import annotations

ROWMAP = {
    "revenue": ["Sales", "Revenue"],
    "ebitda": ["Operating Profit", "Financing Profit"],
    "pbt": ["Profit before tax"],
    "pat": ["Net Profit"],
}
LABEL = {"revenue": "Revenue", "ebitda": "EBITDA", "pbt": "PBT", "pat": "PAT"}


def _row(q: dict, key: str):
    for name in ROWMAP[key]:
        if name in q["rows"]:
            return q["rows"][name], name
    return None, None


def _pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round((a / b - 1) * 100 if b > 0 else (a - b) / abs(b) * 100, 1)


def headline(company: dict) -> dict | None:
    q = company.get("quarters")
    if not q or len(q["periods"]) < 5:
        return None
    n = len(q["periods"])
    i, p, y = n - 1, n - 2, n - 5
    is_bank = "Financing Profit" in q["rows"]
    metrics = []
    for k in ("revenue", "ebitda", "pbt", "pat"):
        vals, src = _row(q, k)
        if k == "ebitda" and is_bank and "Revenue" in q["rows"] and "Interest" in q["rows"]:
            # Banks have no EBITDA. Net interest income (interest earned − interest expended) is the analogue.
            vals = [(a - b) if a is not None and b is not None else None for a, b in zip(q["rows"]["Revenue"], q["rows"]["Interest"])]
            src = "Revenue − Interest"
        if not vals:
            continue
        cur, prev, ly = vals[i], vals[p], vals[y]
        metrics.append({"key": k, "label": ("NII" if (k == "ebitda" and is_bank) else LABEL[k]),
                        "source_row": src, "cur": cur, "qoq": _pct(cur, prev), "yoy": _pct(cur, ly),
                        "series": vals[-9:]})
    rev = _row(q, "revenue")[0]
    eb = _row(q, "ebitda")[0]
    margin = None
    if rev and eb and rev[i] and rev[y] and rev[p]:
        m = lambda j: eb[j] / rev[j] * 100 if rev[j] else None
        margin = {"cur": round(m(i), 1), "qoq_bps": round((m(i) - m(p)) * 100), "yoy_bps": round((m(i) - m(y)) * 100),
                  "series": [round(m(j), 1) if rev[j] else None for j in range(max(0, n - 9), n)]}
    pdf = q["pdfs"][i] if q.get("pdfs") and len(q["pdfs"]) > i else None
    return {"period": q["periods"][i], "vs_qoq": q["periods"][p], "vs_yoy": q["periods"][y], "is_bank": is_bank,
            "metrics": metrics, "margin": margin, "read": read(metrics, margin, q, i, is_bank), "pdf": pdf,
            "periods": q["periods"][-9:], "unit": "₹ cr"}


def read(metrics: list[dict], margin: dict | None, q: dict, i: int, is_bank: bool) -> str:
    """One deterministic sentence: the single most decision-relevant fact in the numbers."""
    by = {m["key"]: m for m in metrics}
    parts = []
    r, pat = by.get("revenue"), by.get("pat")
    if r and r["yoy"] is not None:
        parts.append(f"Revenue {r['yoy']:+.0f}% YoY")
    if margin and not is_bank:
        hist = [x for x in margin["series"] if x is not None]
        tag = ""
        if hist and margin["cur"] <= min(hist):
            tag = f" — the lowest in {len(hist)} quarters"
        elif hist and margin["cur"] >= max(hist):
            tag = f" — the highest in {len(hist)} quarters"
        direction = "expanded" if margin["yoy_bps"] > 0 else "compressed"
        if abs(margin["yoy_bps"]) >= 100 or tag:
            parts.append(f"EBITDA margin {direction} {abs(margin['yoy_bps'])} bps YoY to {margin['cur']:.0f}%{tag}")
    if pat and pat["yoy"] is not None:
        if r and r["yoy"] is not None and pat["yoy"] - r["yoy"] > 15:
            parts.append(f"PAT {pat['yoy']:+.0f}% — profits outran sales")
        elif r and r["yoy"] is not None and r["yoy"] - pat["yoy"] > 15:
            parts.append(f"PAT {pat['yoy']:+.0f}% — sales growth didn't reach the bottom line")
        else:
            parts.append(f"PAT {pat['yoy']:+.0f}% YoY")
    return "; ".join(parts) + "." if parts else ""


def surprise_score(h: dict) -> float:
    """How much this print deviates from the company's own recent pattern (for ranking the results heatmap)."""
    by = {m["key"]: m for m in h["metrics"]}
    s = 0.0
    for k, w in (("revenue", 1.0), ("ebitda", 1.2), ("pat", 1.0)):
        if k in by and by[k]["yoy"] is not None:
            s += w * min(abs(by[k]["yoy"]), 80) / 80
    if h["margin"]:
        s += min(abs(h["margin"]["yoy_bps"]), 1500) / 1500
    return round(s, 3)
