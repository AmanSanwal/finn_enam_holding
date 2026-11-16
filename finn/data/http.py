"""A polite, cached HTTP client.

Every external fetch in FINN goes through here so that we:
  * identify ourselves honestly (no browser spoofing),
  * respect robots.txt for each host,
  * rate-limit per host (default: one request every 3 seconds),
  * cache responses on disk so a rebuild never re-hits a source unnecessarily.
"""
from __future__ import annotations

import hashlib
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import requests

USER_AGENT = "FINN-prototype/0.1 (research prototype; low-volume, cached)"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
MIN_INTERVAL = {"default": 3.0}

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_last_hit: dict[str, float] = {}
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


class Disallowed(Exception):
    pass


def _robots_for(host: str, scheme: str):
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = _session.get(f"{scheme}://{host}/robots.txt", timeout=20)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            else:
                rp = None  # no robots.txt -> allowed
        except requests.RequestException:
            rp = None
        _robots[host] = rp
    return _robots[host]


def _throttle(host: str):
    gap = MIN_INTERVAL.get(host, MIN_INTERVAL["default"])
    wait = _last_hit.get(host, 0) + gap - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()


def get(url: str, *, max_age: float = 6 * 3600, binary: bool = False, params: dict | None = None):
    """GET with disk cache. Returns text (or bytes when binary=True), None on 404."""
    key_src = url + ("?" + "&".join(f"{k}={v}" for k, v in sorted(params.items())) if params else "")
    key = hashlib.sha1(key_src.encode()).hexdigest()
    path = CACHE_DIR / key[:2] / key
    if path.exists() and (time.time() - path.stat().st_mtime) < max_age:
        data = path.read_bytes()
        return data if binary else data.decode("utf-8", errors="replace")

    u = urlparse(url)
    rp = _robots_for(u.netloc, u.scheme)
    if rp is not None and not rp.can_fetch(USER_AGENT, url):
        raise Disallowed(f"robots.txt disallows {url}")

    _throttle(u.netloc)
    r = _session.get(url, params=params, timeout=45)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r.content if binary else r.content.decode("utf-8", errors="replace")
