"""People in filings: who changed, in what role, and who they are.

SEBI LODR (Reg. 30, Schedule III Part A) obliges a listed company to file a *brief profile*
of every newly appointed director / KMP / senior manager. So the bio FINN shows comes from
the company's own filing — a primary source — not from scraping LinkedIn. The profile is
then mined for employers and education (dictionary NER against the org registry, with an
optional cheap-model pass) and matched against the investor's network.
"""
from __future__ import annotations

import re

from . import network

HONORIFIC = r"(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?|Shri|Smt\.?|Prof\.?)"
NAME = r"([A-Z][a-zA-Z\.’']+(?:\s+[A-Z][a-zA-Z\.’']*){0,4})"
ROLE = (r"(Chief [A-Z][a-z]+ Officer(?: \([A-Z]+\))?(?:\s*-\s*Designate)?|Managing Director(?: (?:&|and) (?:Chief Executive Officer|CEO))?|"
        r"Whole[- ]?time Director|Executive Director|Company Secretary|Independent Director|Non-?Executive Director|"
        r"President(?: & CEO)?(?: - [A-Za-z ]+)?|Group Head[^,.;\n]{0,60}|Chairman(?: Emeritus)?|Promoter|CFO|CEO|CRO|MD & CEO)")


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def brief_profile(text: str) -> str:
    p = _brief_profile(text)
    p = re.sub(r"^\(?in case of appointment\)?\s*", "", p, flags=re.I)
    return "" if re.match(r"not applicable|n\.?a\.?$", p, re.I) else p


def _brief_profile(text: str) -> str:
    m = re.search(r"Brief profile[^\n]*?\)?\s*(.+?)(?:\n\s*\d+\s+Disclosure of relationship|Disclosure of relationship|\n\s*5\s|For [A-Z][A-Za-z &]+Limited)",
                  text, re.S | re.I)
    return _clean(m.group(1)) if m else ""


def action_of(text: str) -> str:
    t = text.lower()
    for a, pat in [("demise", r"demise|passed away"), ("re-appointed", r"re-?appoint"), ("resigned", r"resign"),
                   ("ceased", r"cessation|cease|superannuat|exit"), ("appointed", r"appoint|joined|designat")]:
        if re.search(pat, t):
            return a
    return "changed"


def extract(text: str, headline: str = "") -> list[dict]:
    """Return people mentioned as the subject of a management change, with role, action and (if any) profile."""
    blob = headline + "\n" + text
    people: dict[str, dict] = {}
    for m in re.finditer(HONORIFIC + r"\s+" + NAME, blob):
        name = _clean(m.group(1))
        name = re.sub(r"\s+(has|is|as|was|shall|who|will|from|to|the|of)\b.*$", "", name)
        if len(name.split()) < 2 or name.split()[-1] in ("Limited", "Bank", "Company"):
            continue
        window = blob[m.start(): m.start() + 400]
        r = re.search(ROLE, window)
        key = name.lower()
        if key not in people:
            people[key] = {"name": name, "role": _clean(r.group(1)) if r else None,
                           "action": action_of(blob[max(0, m.start() - 250): m.start() + 250])}
    profile = brief_profile(text)
    out = _dedupe(list(people.values()))
    # Keep the people the filing is *about*, not signatories (company secretary signing the letter).
    out = [p for p in out if not (p["role"] or "").lower().startswith("company secretary") or len(out) == 1]
    if profile and out:
        out[0]["profile"] = profile
        out[0]["career"] = [{"org": o, "role": _role_near(profile, o), "from": None, "to": None, "seniority": 3}
                            for o in network.find_orgs_in_text(profile)
                            if network.load()["org_by_id"][o]["industry"] != "edu"]
        out[0]["education"] = [{"org": o, "degree": None, "year": None} for o in network.find_orgs_in_text(profile)
                               if network.load()["org_by_id"][o]["industry"] == "edu"]
        out[0]["years_experience"] = _years(profile)
        out[0]["credentials"] = re.findall(r"\b(CAIIB|FRM|CFA|ACAMS|MBA|CA|CS|ICWA|PhD|M\.Sc\.|B\.Tech|MBBS|MS)\b", profile)
    return out[:3]


def _dedupe(ps: list[dict]) -> list[dict]:
    """PDF text is noisy ('Madhu Sasidha' / 'Madhu Sasidhar', 'Chandrakant V. Gogri' / 'Chandrakant Vallabhaji Gogri')."""
    from rapidfuzz import fuzz
    out: list[dict] = []
    rank = {"demise": 5, "resigned": 4, "ceased": 4, "re-appointed": 3, "appointed": 2, "changed": 1}
    for p in ps:
        toks = p["name"].replace(".", " ").split()
        for q in out:
            qt = q["name"].replace(".", " ").split()
            same = fuzz.ratio(p["name"], q["name"]) > 88 or (toks[0] == qt[0] and (toks[-1] == qt[-1] or fuzz.ratio(toks[-1], qt[-1]) > 85))
            if same:
                q["role"] = q["role"] or p["role"]
                if len(p["name"]) > len(q["name"]):
                    q["name"] = p["name"]
                if rank.get(p["action"], 0) > rank.get(q["action"], 0):
                    q["action"] = p["action"]
                break
        else:
            out.append(dict(p))
    return out


def _role_near(profile: str, org_id: str) -> str | None:
    org = network.load()["org_by_id"][org_id]
    for a in [org["name"], *org["aliases"]]:
        i = profile.find(a)
        if i >= 0:
            m = re.search(r"(?:as|served as|was)\s+([A-Z][A-Za-z &\-()]+?)\s+(?:at|with|in)\s*$", profile[max(0, i - 120):i])
            return m.group(1) if m else None
    return None


def _years(profile: str) -> int | None:
    m = re.search(r"(\d{1,2})\+?\s+years", profile)
    return int(m.group(1)) if m else None
