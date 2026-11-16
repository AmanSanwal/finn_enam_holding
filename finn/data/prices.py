"""End-of-day price & volume from Yahoo Finance (yfinance), NSE tickers as SYMBOL.NS."""
from __future__ import annotations

import math

import yfinance as yf


def fetch_eod(symbols: list[str], period: str = "1y") -> dict[str, list[dict]]:
    """Return {symbol: [{d, o, h, l, c, v}, ...]} oldest first. One batched request for all symbols."""
    tickers = [f"{s}.NS" for s in symbols]
    df = yf.download(tickers, period=period, interval="1d", group_by="ticker",
                     auto_adjust=False, progress=False, threads=True)
    out: dict[str, list[dict]] = {}
    for s, t in zip(symbols, tickers):
        try:
            sub = df[t] if len(tickers) > 1 else df
        except KeyError:
            continue
        rows = []
        for idx, r in sub.iterrows():
            c = r.get("Close")
            if c is None or (isinstance(c, float) and math.isnan(c)):
                continue
            rows.append({
                "d": idx.strftime("%Y-%m-%d"),
                "o": round(float(r["Open"]), 2), "h": round(float(r["High"]), 2),
                "l": round(float(r["Low"]), 2), "c": round(float(c), 2),
                "v": int(r["Volume"]) if not math.isnan(r["Volume"]) else 0,
            })
        if rows:
            out[s] = rows
    return out


def unusual_moves(series: list[dict], *, vol_mult: float = 2.0, price_pct: float = 4.0,
                  lookback: int = 20, days: int = 30) -> list[dict]:
    """Days in the last `days` sessions where volume > vol_mult x trailing-avg or |move| > price_pct.

    The thresholds are user settings — FINN watches for what *you* call unusual.
    """
    alerts = []
    start = max(lookback + 1, len(series) - days)
    for i in range(start, len(series)):
        today, prev = series[i], series[i - 1]
        window = series[i - lookback:i]
        avg_v = sum(x["v"] for x in window) / max(1, len(window))
        chg = (today["c"] / prev["c"] - 1) * 100 if prev["c"] else 0
        vm = today["v"] / avg_v if avg_v else 0
        reasons = []
        if vm >= vol_mult:
            reasons.append("volume")
        if abs(chg) >= price_pct:
            reasons.append("price")
        if reasons:
            alerts.append({"d": today["d"], "chg": round(chg, 2), "vol_mult": round(vm, 2),
                           "close": today["c"], "reasons": reasons})
    return alerts
