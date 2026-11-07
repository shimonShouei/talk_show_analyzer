"""Canonical person records: Hebrew name is the key, English is display only.

Persons used to be looked up by ``name_en``, so every transliteration variant
("Avishai Samberg" / "Avishag Semberg") created a new person. We now key on a
normalised Hebrew name (titles, quotes and geresh variants stripped) and fall
back to the English name only when no Hebrew match exists.
"""

from __future__ import annotations

import re
from typing import Optional

from talk_show_analyzer.models import Person

_TITLES = r"(?:פרופ['׳]?|פרופסור|ד[\"״']?ר|דוקטור|דר['׳]?|עו[\"״]ד|השר|השרה|ח[\"״]כ|חבר הכנסת|חברת הכנסת|רב|הרב|תא[\"״]ל|אלוף|ניצב)"
_TITLE_RE = re.compile(rf"^(?:{_TITLES}\s+)+")
_GENERIC = {
    "unknown", "מגיש", "מגישה", "מנחה", "קריין", "קריינית", "שדרן", "שדרנית",
    "announcer", "host", "narrator", "מאזין", "מאזינה", "מתקשר", "מתקשרת",
}


def normalize_he(name: str | None) -> str:
    n = (name or "").strip()
    n = n.replace("״", '"').replace("׳", "'").replace("`", "'")
    n = _TITLE_RE.sub("", n)
    n = re.sub(r"[\"'.,()\-–—]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def is_generic_name(name_he: str | None, name_en: str | None = None) -> bool:
    """Role words ("מגיש/מנחה", "Announcer") are not people."""
    for n in (name_he, name_en):
        if not n:
            continue
        parts = re.split(r"[/\s]+", n.strip().lower())
        if parts and all(p in _GENERIC for p in parts if p):
            return True
    return False


def get_or_create_person(session, name_he: str, name_en: str, role: str) -> Optional[Person]:
    """Find a person by normalised Hebrew name (then English); create if missing."""
    if is_generic_name(name_he, name_en) or (name_en or "Unknown") == "Unknown":
        return None
    key = normalize_he(name_he)
    if key and key != "Unknown":
        for p in session.query(Person).all():
            if normalize_he(p.name_he) == key:
                return p
    person = session.query(Person).filter_by(name_en=name_en).first()
    if person:
        return person
    person = Person(name_he=name_he, name_en=name_en, role=role)
    session.add(person)
    session.flush()
    return person


def upgrade_partial_names(resolved: dict, full_names: list[str]) -> dict:
    """Expand first-name-only / surname-only speakers to a unique full name.

    Candidates are ``full_names`` (e.g. scheduled hosts) plus full names already
    given to other labels in the same episode. A partial name is upgraded only if
    exactly one candidate starts with it (first name) or ends with it (surname),
    so "יוני" → "יוני הללי" but an ambiguous "משה" stays as is.
    Returns {label: (old_name_he, new_name_he)} for the labels changed.
    """
    candidates = {normalize_he(n) for n in full_names if len(normalize_he(n).split()) >= 2}
    candidates |= {
        normalize_he(rs.name_he) for rs in resolved.values()
        if rs.name_he != "Unknown" and len(normalize_he(rs.name_he).split()) >= 2
    }
    changed = {}
    for label, rs in resolved.items():
        cur = normalize_he(rs.name_he)
        if rs.name_he == "Unknown" or len(cur.split()) != 1:
            continue
        matches = [c for c in candidates if c.split()[0] == cur or c.split()[-1] == cur]
        if len(matches) == 1:
            changed[label] = (rs.name_he, matches[0])
            rs.name_he = matches[0]
    return changed
