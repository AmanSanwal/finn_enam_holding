"""FINN API — serves the app and does live research on any NSE ticker.

    uvicorn finn.api:app --port 8000      # then open http://localhost:8000

The static app works from web/data/snapshot.json alone; when this API is reachable the
app also gets live research for tickers outside the snapshot.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .intel import network, research

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
app = FastAPI(title="FINN", version="0.1")


@app.get("/api/health")
def health():
    return {"ok": True, "live_research": True}


@app.get("/api/research/{symbol}")
def research_for(symbol: str):
    symbol = symbol.upper().strip()
    if not re.fullmatch(r"[A-Z0-9&\-]{1,20}", symbol):
        raise HTTPException(400, "Not an NSE symbol")
    cached = WEB / "data" / "research" / f"{symbol}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    try:
        r = research.build(symbol)
    except LookupError:
        raise HTTPException(404, f"No filings data found for {symbol}")
    cached.write_text(json.dumps(r, default=str, ensure_ascii=False))
    return r


@app.get("/api/network/who")
def who(symbol: str, topic: str = ""):
    return network.who_to_call(symbol.upper(), topic=topic, limit=6)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")
