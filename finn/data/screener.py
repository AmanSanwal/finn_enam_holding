"""Company fundamentals from screener.in public company pages.

One page per company gives us, for any NSE ticker:
  * profile text, headline ratios
  * quarterly results (13 quarters) incl. links to the exchange results PDFs
  * annual P&L, balance sheet, cash flow, efficiency ratios, shareholding
  * links to annual reports and concall transcripts (primary sources, hosted on BSE)
  * the 5 most recent exchange announcements

Parsing is label-driven (not position-driven) so it survives banks/NBFCs, whose
tables use different row names (Revenue / Financing Profit instead of Sales / OPM).
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from . import http

BASE = "https://www.screener.in"


def _num(s: str):
    s = (s or "").strip().replace(",", "").replace("%", "").replace("₹", "")
    if s in ("", "-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _label(td) -> str:
    t = td.get_text(" ", strip=True)
    return re.sub(r"\s*\+\s*$", "", t).strip()


def _table(section) -> dict | None:
    """Parse a screener data table into {periods: [...], rows: {label: [values]}, pdfs: [...]}."""
    if section is None:
        return None
    table = section.find("table", class_="data-table")
    if table is None:
        return None
    head = [re.sub(r"\s+", " ", th.get_text(" ", strip=True)).replace(" (S)", "").strip() for th in table.select("thead th")][1:]
    rows: dict[str, list] = {}
    pdfs: list[str | None] = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        label = _label(tds[0])
        if label.lower().startswith("raw pdf"):
            for td in tds[1:]:
                a = td.find("a")
                pdfs.append(BASE + a["href"] if a and a.get("href", "").startswith("/") else (a["href"] if a else None))
            continue
        rows[label] = [_num(td.get_text()) for td in tds[1:]]
    return {"periods": head, "rows": rows, "pdfs": pdfs}


def _ratios(soup) -> dict:
    out = {}
    for li in soup.select("#top-ratios li"):
        name = li.select_one(".name")
        val = li.select_one(".value")
        if not name or not val:
            continue
        nums = [_num(n.get_text()) for n in val.select(".number")]
        out[name.get_text(" ", strip=True)] = nums[0] if len(nums) == 1 else nums
    return out


def _documents(soup) -> dict:
    doc = soup.select_one("#documents")
    res = {"announcements": [], "annual_reports": [], "concalls": []}
    if doc is None:
        return res
    for block in doc.find_all("div", class_="documents"):
        h = block.find("h3")
        title = h.get_text(" ", strip=True).lower() if h else ""
        if title.startswith("announcements"):
            for li in block.select("ul.list-links li"):
                a = li.find("a")
                t = li.find("time")
                if not a:
                    continue
                head = a.contents[0].strip() if a.contents and isinstance(a.contents[0], str) else a.get_text(" ", strip=True)
                sub = li.select_one(".ink-600")
                detail = sub.get_text(" ", strip=True) if sub else ""
                detail = re.sub(r"^\d{1,2} \w{3}( \d{4})?\s*-\s*", "", detail)
                res["announcements"].append({
                    "title": re.sub(r"^Announcement under Regulation 30 \(LODR\)-", "", head),
                    "detail": detail,
                    "ts": t.get("datetime") if t else None,
                    "url": a.get("href"),
                })
        elif title.startswith("annual reports"):
            for li in block.select("ul.list-links li"):
                a = li.find("a")
                if not a:
                    continue
                m = re.search(r"(\d{4})", a.get_text())
                res["annual_reports"].append({"year": int(m.group(1)) if m else None, "url": a.get("href")})
        elif "concalls" in (block.get("class") or []) or title.startswith("concalls"):
            for li in block.select("ul.list-links li"):
                when = li.find("div")
                item = {"period": when.get_text(" ", strip=True) if when else None, "transcript": None, "ppt": None}
                for a in li.find_all("a"):
                    label = a.get_text(" ", strip=True).lower()
                    if label == "transcript":
                        item["transcript"] = a.get("href")
                    elif label == "ppt":
                        item["ppt"] = a.get("href")
                res["concalls"].append(item)
    return res


def _profile(soup) -> dict:
    name = soup.select_one("h1")
    about = soup.select_one(".company-profile .about") or soup.select_one(".about")
    key_points = soup.select_one(".company-profile .commentary") or soup.select_one(".commentary")
    hrefs = [a.get("href") or "" for a in soup.find_all("a", href=True)]
    bse_code = nse_symbol = None
    for href in hrefs:
        if bse_code is None and "bseindia.com/stock-share-price/" in href:
            m = re.search(r"/(\d{6})/", href)
            bse_code = m.group(1) if m else None
        if nse_symbol is None and "nseindia.com/get-quotes/equity" in href:
            m = re.search(r"symbol=([A-Z0-9&\-]+)", href)
            nse_symbol = m.group(1) if m else None
    website = None
    for a in soup.select("#top a[target=_blank]"):
        h = a.get("href") or ""
        if h.startswith("http") and not any(x in h for x in ("bseindia", "nseindia", "screener")):
            website = h
            break
    return {
        "name": name.get_text(" ", strip=True) if name else None,
        "about": about.get_text(" ", strip=True) if about else "",
        "key_points": key_points.get_text(" ", strip=True)[:1500] if key_points else "",
        "bse_code": bse_code,
        "nse_symbol": nse_symbol,
        "website": website,
    }


def fetch_company(symbol: str, consolidated: bool = True) -> dict | None:
    """Fetch and parse a company. Falls back to standalone when no consolidated accounts exist."""
    symbol = symbol.upper().strip()
    url = f"{BASE}/company/{symbol}/" + ("consolidated/" if consolidated else "")
    html = http.get(url)
    if html is None:
        return None
    soup = BeautifulSoup(html, "lxml")
    quarters = _table(soup.select_one("#quarters"))
    stale = bool(quarters and quarters["periods"]) and int(quarters["periods"][-1][-4:]) < datetime.now().year - 1
    if consolidated and (quarters is None or not quarters["rows"] or stale):
        return fetch_company(symbol, consolidated=False)
    data = {
        "symbol": symbol,
        "source_url": url,
        "consolidated": consolidated,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        **_profile(soup),
        "ratios": _ratios(soup),
        "quarters": quarters,
        "annual": _table(soup.select_one("#profit-loss")),
        "balance_sheet": _table(soup.select_one("#balance-sheet")),
        "cash_flow": _table(soup.select_one("#cash-flow")),
        "efficiency": _table(soup.select_one("#ratios")),
        "shareholding": _table(soup.select_one("#quarterly-shp")) or _table(soup.select_one("#shareholding")),
        "documents": _documents(soup),
    }
    return data
