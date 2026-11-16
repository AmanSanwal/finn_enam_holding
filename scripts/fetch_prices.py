"""Fetch end-of-day NSE prices and volume for any ticker and cache them as JSON.

Usage:
    pip install yfinance
    python scripts/fetch_prices.py TCS RELIANCE DIVISLAB
    python scripts/fetch_prices.py --portfolio        # the 15 demo names

Writes data/prices/<TICKER>.json. The web app reads that folder when it exists.
Indian tickers use the .NS suffix (NSE). Anything yfinance returns works.

Status: written but NOT yet run end to end against Yahoo from this build.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

PORTFOLIO = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "SUNPHARMA", "TATAMOTORS", "ASIANPAINT",
    "PIDILITIND", "ITC", "DIXON", "PERSISTENT", "AUBANK", "DEEPAKNTR", "POLYCAB", "SUZLON",
]
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "prices"


def fetch(ticker: str, days: int = 40) -> dict:
    import yfinance as yf  # imported here so the rest of the repo works without it

    symbol = ticker if ticker.endswith((".NS", ".BO")) else f"{ticker}.NS"
    hist = yf.Ticker(symbol).history(period=f"{days}d", interval="1d", auto_adjust=False)
    if hist.empty:
        raise RuntimeError(f"no price data for {symbol}")
    rows = [
        {
            "date": idx.strftime("%Y-%m-%d"),
            "close": round(float(r["Close"]), 2),
            "volume": int(r["Volume"]),
        }
        for idx, r in hist.iterrows()
    ]
    return {
        "ticker": ticker,
        "symbol": symbol,
        "source": "yfinance (Yahoo Finance)",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*")
    ap.add_argument("--portfolio", action="store_true")
    args = ap.parse_args()
    tickers = PORTFOLIO if args.portfolio else [t.upper() for t in args.tickers]
    if not tickers:
        ap.error("give tickers or --portfolio")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failed = []
    for t in tickers:
        try:
            payload = fetch(t)
            (OUT_DIR / f"{t}.json").write_text(json.dumps(payload, indent=1))
            print(f"ok   {t}: {len(payload['rows'])} sessions")
        except Exception as exc:  # keep going; one bad ticker should not stop the run
            failed.append(t)
            print(f"fail {t}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
