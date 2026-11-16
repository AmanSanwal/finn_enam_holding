"""Model router with a persistent, content-addressed cache.

Routing (cheapest model that can do the job):
  tier "extract" -> claude-haiku-5-5 : bulk extraction/classification ($0.10/$0.50 per MTok)
  tier "reason"  -> claude-opus-5-5  : promise-vs-delivery, bull/bear (on demand, cached)
Most of FINN runs with no model at all (rules + parsing); the model is the exception.

Cache: results are keyed by a *semantic* key (task:symbol:period) plus a hash of the
prompt, so a filing or a quarter is processed once, ever — re-opening a company is free.
Safety: calls are opt-in via FINN_ANTHROPIC_API_KEY so the app never silently picks up
ambient credentials; with no key the router serves cached results or returns None and
the caller falls back to its deterministic path.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

CACHE = Path(__file__).resolve().parents[1] / "data" / "llm_cache"
MODELS = {"extract": "claude-haiku-5-5", "reason": "claude-opus-5-5"}
EFFORT = {"extract": "low", "reason": "high"}
LEDGER = CACHE / "_ledger.jsonl"


def _path(key: str) -> Path:
    safe = key.replace("/", "_").replace(":", "__")
    return CACHE / f"{safe}.json"


def cached(key: str):
    p = _path(key)
    return json.loads(p.read_text()) if p.exists() else None


def put(key: str, output, *, producer: str, prompt_hash: str = "", usage: dict | None = None):
    CACHE.mkdir(parents=True, exist_ok=True)
    _path(key).write_text(json.dumps({"key": key, "producer": producer, "prompt_hash": prompt_hash,
                                      "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "usage": usage,
                                      "output": output}, indent=1, ensure_ascii=False))


def complete(key: str, *, tier: str, system: str, user: str, schema: dict, max_tokens: int = 4000):
    """Return structured JSON for `key`, from cache or the routed model; None if unavailable."""
    ph = hashlib.sha256((MODELS[tier] + system + user + json.dumps(schema, sort_keys=True)).encode()).hexdigest()[:16]
    hit = cached(key)
    if hit is not None:
        return hit["output"]
    api_key = os.environ.get("FINN_ANTHROPIC_API_KEY")
    if not api_key:
        return None
    import anthropic
    client = anthropic.Anthropic(api_key=api_key, base_url="https://api.anthropic.com")
    params = dict(
        model=MODELS[tier], max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],  # stable prefix -> cache reads
        messages=[{"role": "user", "content": user}],
        output_config={"effort": EFFORT[tier], "format": {"type": "json_schema", "schema": schema}},
    )
    try:
        if tier == "reason":
            resp = client.beta.messages.create(**params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        else:
            resp = client.messages.create(**params)
    except anthropic.RateLimitError:
        return None
    except anthropic.APIStatusError:
        return None
    except anthropic.APIConnectionError:
        return None
    if resp.stop_reason in ("refusal", "max_tokens"):
        return None
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if text is None:
        return None
    out = json.loads(text)
    usage = {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens,
             "cache_read": getattr(resp.usage, "cache_read_input_tokens", 0)}
    put(key, out, producer=resp.model, prompt_hash=ph, usage=usage)
    with open(LEDGER, "a") as f:
        f.write(json.dumps({"key": key, "model": resp.model, **usage}) + "\n")
    return out


# ------------------------------------------------------------------ task prompts (stable => cacheable)

GUIDANCE_SYSTEM = """You extract management guidance from Indian listed-company earnings-call excerpts.
Use ONLY the sentences provided. Never use outside knowledge of the company.
A guidance item is an explicit, forward-looking statement about a headline number
(revenue/AUM growth, EBITDA margin, capex, order book, asset quality).
Return numbers exactly as stated; if a range, give low and high; if 'double digit', low=10, high=null."""

GUIDANCE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["metric", "low", "high", "unit", "horizon", "quote"],
        "properties": {"metric": {"type": "string", "enum": ["revenue_growth", "margin", "capex", "orders", "asset_quality", "other"]},
                       "low": {"type": ["number", "null"]}, "high": {"type": ["number", "null"]},
                       "unit": {"type": ["string", "null"]}, "horizon": {"type": "string"}, "quote": {"type": "string"}}}}},
}

VERDICT_SYSTEM = """You are a sceptical buy-side analyst. You are given (a) management's guidance from the last
four earnings calls, verbatim, with the quarter each was given in, and (b) the reported quarterly numbers.
For each promise, decide: delivered, partly, missed, or too early — and cite the numbers.
Then write a 2-sentence verdict on management credibility. Use only the data given."""

VERDICT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["rows", "verdict", "credibility"],
    "properties": {
        "rows": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                 "required": ["given_in", "promise", "actual", "status", "quote"],
                 "properties": {"given_in": {"type": "string"}, "promise": {"type": "string"}, "actual": {"type": "string"},
                                "status": {"type": "string", "enum": ["delivered", "partly", "missed", "too_early"]},
                                "quote": {"type": "string"}}}},
        "verdict": {"type": "string"},
        "credibility": {"type": "string", "enum": ["high", "mixed", "low"]}},
}

BULLBEAR_SYSTEM = """Write a tight bull case and bear case (3 points each, <= 22 words per point) for an Indian
listed company using ONLY the computed signals and management quotes provided. Every point must
cite a number or a quote from the input. No outside knowledge, no news, no broker views."""

BULLBEAR_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["bull", "bear"],
    "properties": {"bull": {"type": "array", "items": {"type": "string"}}, "bear": {"type": "array", "items": {"type": "string"}}},
}
