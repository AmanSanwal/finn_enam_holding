"""Corporate announcements from two public, exchange-originated sources.

1. NSE "Online announcements" RSS — the exchange's own feed of every filing, refreshed
   every ~5 min (ttl=5). In production a poller appends it to the filings store; it is
   the low-latency trigger for Push.
2. Per-company recent announcements listed on screener.in (sourced from BSE, with links
   to the BSE-hosted PDF). Gives per-company history so a 7/14-day digest is possible
   on day one, before the poller has accumulated history.

Both normalise to the same Filing dict and are de-duplicated on (symbol, day, subject).
"""
from __future__ import annotations

import hashlib
import html as htmlmod
import io
import re
from datetime import datetime

from rapidfuzz import fuzz

from . import http

NSE_RSS = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"


def _fid(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def _g(tag: str, it: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", it, re.S)
    return htmlmod.unescape(m.group(1)).strip() if m else ""


def nse_rss(name_to_symbol: dict[str, str]) -> list[dict]:
    """Parse the NSE feed and keep items for companies we track (matched by name or by symbol in the URL)."""
    xml = http.get(NSE_RSS, max_age=300)
    out = []
    norm = {re.sub(r"[^a-z0-9]", "", n.lower().replace("limited", "").replace("ltd", "")): s
            for n, s in name_to_symbol.items()}
    symbols = set(name_to_symbol.values())
    for it in re.findall(r"<item>(.*?)</item>", xml or "", re.S):
        title, desc, link, pub = _g("title", it), _g("description", it), _g("link", it), _g("pubDate", it)
        key = re.sub(r"[^a-z0-9]", "", title.lower().replace("limited", "").replace("ltd", ""))
        sym = norm.get(key)
        if not sym:
            m = re.search(r"/corporate/([A-Z0-9&]+)_\d{8}", link)
            sym = m.group(1) if m and m.group(1) in symbols else None
        if not sym:
            continue
        subject = desc.split("|SUBJECT:")[-1].strip() if "|SUBJECT:" in desc else ""
        body = desc.split("|SUBJECT:")[0].strip()
        body = re.sub(rf"^{re.escape(title)}\s+has informed the Exchanges?\s+(about|regarding)\s+", "", body, flags=re.I)
        body = re.sub(r"^.*?has informed the Exchanges?\s+(about|regarding)\s+", "", body, flags=re.I)
        try:
            ts = datetime.strptime(pub, "%d-%b-%Y %H:%M:%S").isoformat() + "+05:30"
        except ValueError:
            ts = None
        if link.endswith(".xml"):  # XBRL twin of a PDF filing — keep the human-readable one
            continue
        out.append({"id": _fid(sym, ts, subject, link), "symbol": sym, "ts": ts, "source": "NSE",
                    "title": subject or body[:80], "detail": body[0].upper() + body[1:] if body else "",
                    "url": link})
    return out


def screener_recent(company: dict) -> list[dict]:
    out = []
    for a in company["documents"]["announcements"]:
        out.append({"id": _fid(company["symbol"], a["ts"], a["title"], a["url"]), "symbol": company["symbol"],
                    "ts": a["ts"], "source": "BSE", "title": a["title"], "detail": a["detail"], "url": a["url"]})
    return out


def merge(*lists: list[dict], category=None) -> list[dict]:
    """Union with de-dup. The same filing reaches us from NSE and BSE with different wording, so:
    same company + same day + (same category, or similar text) => one filing, keeping the richer detail."""
    allf = sorted((f for lst in lists for f in lst if f.get("ts")), key=lambda f: f["ts"], reverse=True)
    kept: list[dict] = []
    for f in allf:
        dup = None
        for k in kept:
            if k["symbol"] != f["symbol"] or k["ts"][:10] != f["ts"][:10]:
                continue
            same_cat = category is not None and category(k) == category(f)
            sim = fuzz.token_set_ratio(k["title"] + " " + k["detail"], f["title"] + " " + f["detail"])
            if (same_cat and (k["source"] != f["source"] or sim > 50)) or sim > 72:
                dup = k
                break
        if dup is None:
            kept.append(f)
        else:
            # keep the more informative one-liner: specific beats boilerplate ("Intimation under Reg 30 ...")
            boiler = lambda d: bool(re.match(r"(intimation|disclosure|announcement) under|pursuant to|the appointment of|outcome of", d, re.I))
            better = (boiler(dup["detail"]) and not boiler(f["detail"])) or (boiler(dup["detail"]) == boiler(f["detail"]) and len(f["detail"]) > len(dup["detail"]))
            if better:
                dup["detail"] = f["detail"]
            dup.setdefault("also", []).append(f["url"])
    return kept


def pdf_text(url: str, max_pages: int = 12) -> str:
    """Extract text from a filing PDF (cached forever: filings are immutable)."""
    from pypdf import PdfReader
    try:
        b = http.get(url, binary=True, max_age=1e12)
        if not b or not b.startswith(b"%PDF"):
            return ""
        reader = PdfReader(io.BytesIO(b))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])
    except Exception:
        return ""
