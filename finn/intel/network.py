"""The Network layer: turns the investor's contacts into answers to "who can help me understand this?"

Model
-----
A small property graph, rebuilt in-process from the investor's private network file:
  you ──knows(strength)──> contact ──worked_at(org, years, seniority)──> org
                                    └─studied_at(org, year)──> institution
  person-in-filing ──worked_at / studied_at──> org          (parsed from the filing itself)

Edges between a contact and a filing person are *inferred* from career overlap and are
always labelled as such, with the evidence. Link strength is deliberately sceptical:
overlapping at a 3,000-person company is a real link; overlapping at a 300,000-person
company mostly isn't.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

NET = Path(__file__).resolve().parents[2] / "data" / "network" / "network.json"
TODAY = date(2026, 11, 16)


@lru_cache(maxsize=1)
def load(path: str = str(NET)) -> dict:
    d = json.load(open(path))
    d["org_by_id"] = {o["id"]: o for o in d["orgs"]}
    d["contact_by_id"] = {c["id"]: c for c in d["contacts"]}
    d["alias"] = {}
    for o in d["orgs"]:
        for a in [o["name"], *o["aliases"]] + ([o["symbol"]] if o["symbol"] else []):
            d["alias"][_norm(a)] = o["id"]
    d["theme_of_industry"] = {ind: t for t, inds in d["themes"].items() for ind in inds}
    return d


def _norm(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"\b(ltd|limited|pvt|private|india|the|co|company|inc)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def resolve_org(text: str) -> str | None:
    """Entity resolution for organisations: exact alias, then fuzzy (≥90) — conservative on purpose."""
    d = load()
    n = _norm(text)
    if n in d["alias"]:
        return d["alias"][n]
    m = process.extractOne(n, list(d["alias"].keys()), scorer=fuzz.token_sort_ratio)
    return d["alias"][m[0]] if m and m[1] >= 90 else None


def find_orgs_in_text(text: str) -> list[str]:
    """Dictionary NER over free text (e.g. a filing's 'brief profile'). Longest alias first."""
    d = load()
    found, t = [], " " + _norm(text) + " "
    for alias in sorted(d["alias"], key=len, reverse=True):
        if len(alias) < 3:
            continue
        if f" {alias} " in t:
            oid = d["alias"][alias]
            if oid not in found:
                found.append(oid)
            t = t.replace(f" {alias} ", " ")
    return found


# ---------------------------------------------------------------- strengths

def tie_strength(c: dict) -> float:
    """You → contact. Recency and frequency of real interaction (calendar/email metadata, with consent)."""
    days = (TODAY - date.fromisoformat(c["last_contact"])).days
    recency = math.exp(-days / 240)                       # ~0.6 at 4 months, ~0.2 at a year
    freq = min(1.0, math.log1p(c["touchpoints_12m"]) / math.log1p(12))
    close = 0.15 if re.search(r"batchmate|ex-colleague|friend", c["how_met"], re.I) else 0
    return round(min(1.0, 0.25 + 0.4 * freq + 0.35 * recency + close), 2)


def _size_factor(org: dict) -> float:
    n = org.get("employees") or 0
    if n == 0:
        return 0.5
    return 1.0 if n < 3000 else 0.8 if n < 15000 else 0.6 if n < 80000 else 0.4


def overlap(job_a: dict, job_b: dict) -> tuple[float, str] | None:
    """Strength + evidence that two people overlapped at the same org."""
    if job_a["org"] != job_b["org"]:
        return None
    org = load()["org_by_id"][job_a["org"]]
    a0, a1 = job_a.get("from"), job_a.get("to") or TODAY.year
    b0, b1 = job_b.get("from"), job_b.get("to") or TODAY.year
    if a0 is None or b0 is None:  # dates unknown for one side (typical for filing bios)
        return round(0.55 * _size_factor(org), 2), f"both at {org['name']} (dates not disclosed — possible overlap)"
    yrs = min(a1, b1) - max(a0, b0)
    if yrs < 0:
        return round(0.15 * _size_factor(org), 2), f"both alumni of {org['name']}, different eras"
    senior = 1.15 if min(job_a.get("seniority", 2), job_b.get("seniority", 2)) >= 3 else 1.0
    s = min(0.95, (0.45 + 0.15 * min(yrs, 3)) * _size_factor(org) * senior)
    return round(s, 2), f"overlapped at {org['name']} {max(a0, b0)}–{min(a1, b1)} (~{max(yrs, 1)} yr)"


def edu_overlap(ea: dict, eb: dict) -> tuple[float, str] | None:
    if ea["org"] != eb["org"]:
        return None
    name = load()["org_by_id"][ea["org"]]["name"]
    if ea.get("year") and eb.get("year") and abs(ea["year"] - eb["year"]) <= 1:
        return 0.5, f"{name} batch of {ea['year']}" if ea["year"] == eb["year"] else f"{name}, a year apart"
    return 0.2, f"{name} alumni"


def links_to_person(person: dict) -> list[dict]:
    """All inferred links from your contacts to a person (e.g. an incoming CRO parsed from a filing)."""
    d = load()
    out = []
    for c in d["contacts"]:
        best = None
        for ja in c["career"]:
            for jb in person.get("career", []):
                r = overlap(ja, jb)
                if r and (best is None or r[0] > best[0]):
                    best = r
        for ea in c["education"]:
            for eb in person.get("education", []):
                r = edu_overlap(ea, eb)
                if r and (best is None or r[0] > best[0]):
                    best = r
        if best:
            t = tie_strength(c)
            out.append({"contact": c["id"], "name": c["name"], "headline": c["headline"], "tie": t,
                        "link": best[0], "evidence": best[1], "path_strength": round(t * best[0], 2),
                        "last_contact": c["last_contact"], "inferred": True})
    return sorted(out, key=lambda x: -x["path_strength"])


def _role_knowledge(role: str) -> str:
    r = role.lower()
    for pat, what in [
        (r"plant|operations|manufactur", "how the plants actually run — capacity, compliance, local regulators"),
        (r"risk|credit", "risk culture, underwriting standards and how the board treats risk"),
        (r"cfo|financ|controller|treasury", "financial controls, the close process and the finance bench"),
        (r"sales|marketing|channel|merchand", "demand, pricing and the channel"),
        (r"supply chain|procure", "suppliers, input costs and lead times"),
        (r"strategy|planning|corporate", "how decisions get made at the top, family/board dynamics"),
        (r"program|product|delivery|project", "execution on large programmes and the customer roster"),
        (r"quality|regulat", "regulatory standing and inspection history"),
        (r"business head|regional|zonal", "branch-level reality: collections, attrition, competition"),
        (r"ecm|capital market", "who's buying the paper and at what price"),
    ]:
        if re.search(pat, r):
            return what
    return "the organisation from the inside"


STOP = set("""regulation regulations announcement intimation disclosure disclosures listing obligations requirements
update updates company limited board meeting approved approval effective november october december group head
officer chief director management appointment business pursuant schedule exchange informed""".split())


def _topic_words(topic: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{5,}", topic.lower()) if w not in STOP}


def who_to_call(symbol: str, *, topic: str = "", limit: int = 5) -> list[dict]:
    """Rank contacts for a company: worked there > competitor/value-chain > theme expertise."""
    d = load()
    org = d["org_by_id"].get(symbol) or d["org_by_id"].get(resolve_org(symbol) or "")
    if not org:
        return []
    chain = {v["to"]: v for v in d["value_chain"] if v["from"] == org["id"]}
    chain.update({v["from"]: v for v in d["value_chain"] if v["to"] == org["id"]})
    theme = d["theme_of_industry"].get(org["industry"])
    res = []
    for c in d["contacts"]:
        t = tie_strength(c)
        best = None
        for j in c["career"]:
            jo = d["org_by_id"][j["org"]]
            yrs_ago = TODAY.year - (j["to"] or TODAY.year)
            fresh = max(0.55, 1 - yrs_ago / 20)
            if j["org"] == org["id"]:
                cur = j["to"] is None
                s = (0.9 if not cur else 0.75) * fresh * (1.1 if j.get("seniority", 2) >= 3 else 1)
                why = f"{'Currently' if cur else 'Was'} {j['role']} at {org['name']} ({j['from']}–{j['to'] or 'now'})"
                kind = "insider" if cur else "alumnus"
            elif j["org"] in chain:
                v = chain[j["org"]]
                s = 0.55 * fresh
                why = f"{j['role']} at {jo['name']} — {v['rel'].replace('_', ' ')} ({v['note']})"
                kind = v["rel"]
            elif jo["industry"] == org["industry"]:
                s = 0.5 * fresh
                why = f"{j['role']} at {jo['name']}, a direct competitor"
                kind = "competitor"
            else:
                continue
            hits = [w for w in _topic_words(topic) if re.search(rf"\b{w}", j["role"].lower())]
            if hits:  # e.g. the event names the Waluj plant and this person ran the Waluj plant
                s += 0.3
                why += f" — directly relevant ({hits[0].title()})"
            if best is None or s > best[0]:
                best = (s, why, kind, _role_knowledge(j["role"]))
        if best is None and theme and any(d["org_by_id"][j["org"]]["industry"] in d["themes"][theme] for j in c["career"]):
            best = (0.3, f"Go-to person for {theme.lower()}", "expert", "the sector's economics")
        tagwords = set(re.findall(r"[a-z]+", " ".join(c["tags"]).lower()))
        if best is None and topic and _topic_words(topic) & tagwords:
            best = (0.45, f"Specialist: {', '.join(c['tags'][:2])}", "expert", "the specific issue at hand")
        if best:
            res.append({"contact": c["id"], "name": c["name"], "headline": c["headline"], "kind": best[2],
                        "why": best[1], "would_know": best[3], "tie": t, "score": round(best[0] * (0.5 + t / 2), 3),
                        "last_contact": c["last_contact"]})
    return sorted(res, key=lambda x: -x["score"])[:limit]


def expertise_map() -> list[dict]:
    """Theme → go-to people, with evidence (years in the industry, seniority, recency)."""
    d = load()
    out = []
    for theme, inds in d["themes"].items():
        people = []
        for c in d["contacts"]:
            yrs, ev = 0, []
            for j in c["career"]:
                o = d["org_by_id"][j["org"]]
                if o["industry"] in inds:
                    span = (j["to"] or TODAY.year) - j["from"]
                    yrs += span
                    ev.append(f"{o['name']} ({span}y)")
            if yrs:
                people.append({"contact": c["id"], "name": c["name"], "years": yrs, "evidence": ev,
                               "tie": tie_strength(c), "score": round(min(yrs, 15) / 15 * 0.7 + tie_strength(c) * 0.3, 2)})
        people.sort(key=lambda p: -p["score"])
        if people:
            out.append({"theme": theme, "people": people[:5], "depth": len(people)})
    return sorted(out, key=lambda t: -t["depth"])


def nudges(events: list[dict], *, quiet_days: int = 90) -> list[dict]:
    """Keep the network warm: someone you haven't spoken to lately + a fresh, relevant reason to call."""
    d = load()
    out = []
    for c in d["contacts"]:
        days = (TODAY - date.fromisoformat(c["last_contact"])).days
        if days < quiet_days:
            continue
        orgs = {j["org"]: j for j in c["career"]}
        for e in sorted(events, key=lambda x: -x.get("score", 0)):
            if e.get("score", 0) < 60:   # only a material event is a natural reason to call
                break
            if e["symbol"] in orgs:
                j = orgs[e["symbol"]]
                rel = "current employer" if j["to"] is None else "former employer"
                out.append({"contact": c["id"], "name": c["name"], "days_quiet": days, "symbol": e["symbol"],
                            "event": e["headline"], "event_id": e["id"], "relation": rel,
                            "opener": f"Saw {d['org_by_id'][e['symbol']]['name']}'s news — {e['headline'][:90].rstrip('.')}. "
                                      f"Would love your read given your years there."})
                break
    return sorted(out, key=lambda x: -x["days_quiet"])[:8]


def contact_card(cid: str) -> dict:
    d = load()
    c = dict(d["contact_by_id"][cid])
    c["tie"] = tie_strength(c)
    c["career_named"] = [{**j, "org_name": d["org_by_id"][j["org"]]["name"]} for j in c["career"]]
    c["education_named"] = [{**e, "org_name": d["org_by_id"][e["org"]]["name"]} for e in c["education"]]
    c["days_quiet"] = (TODAY - date.fromisoformat(c["last_contact"])).days
    # second-degree: who this contact can introduce you to (explicit) + shared employers with other contacts
    c["introduces"] = [{"contact": k["person"], "name": d["contact_by_id"][k["person"]]["name"], "strength": k["strength"]}
                       for k in c.get("knows", []) if k["person"] in d["contact_by_id"]]
    return c


def graph() -> dict:
    """Nodes/edges for the network map (you, contacts, orgs) — only listed or relevant orgs."""
    d = load()
    nodes = [{"id": "you", "label": "You", "type": "you"}]
    edges = []
    seen = set()
    for c in d["contacts"]:
        nodes.append({"id": c["id"], "label": c["name"], "type": "contact", "tie": tie_strength(c), "tags": c["tags"][:2]})
        edges.append({"s": "you", "t": c["id"], "w": tie_strength(c)})
        for j in c["career"]:
            o = d["org_by_id"][j["org"]]
            if o["industry"] in ("edu", "fund") or not o["symbol"]:
                continue   # the map shows listed companies only; private employers stay in the contact card
            if o["id"] not in seen:
                nodes.append({"id": o["id"], "label": o["name"].split(" (")[0], "type": "org", "listed": bool(o["symbol"])})
                seen.add(o["id"])
            edges.append({"s": c["id"], "t": o["id"], "w": 0.5, "current": j["to"] is None})
    return {"nodes": nodes, "edges": edges}
