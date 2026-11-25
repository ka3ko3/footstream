# ---------------------------------------------------------------------------
# English National Team Normalizer
# Dynamic resolution against 211 FIFA nations using primary English names
# and dynamic Column D canonical synonyms loaded from _cache_national_teams.
# ---------------------------------------------------------------------------

import re
import unicodedata

# In-memory registry of 211 FIFA nations: normalized_en -> national team dict
_NATIONAL_TEAMS_EN: dict[str, dict] = {}


def strip_accents(text: str) -> str:
    """Removes accents and diacritics from Latin characters (e.g. Côte -> Cote)."""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def normalize_nation_en(name: str) -> str:
    """Produces a clean canonical lowercase string for English country comparison."""
    if not name:
        return ""
    t = strip_accents(name).lower().strip()
    t = re.sub(r"[.\-\u2010-\u2015\u2212_/|',–—]", " ", t)
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def register_national_teams_en(teams: list[dict] | dict[str, dict]):
    """
    Registers national teams loaded from '_cache_national_teams' worksheet.
    Maps normalized primary English names and Column D canonical synonyms to the team dictionary.
    """
    global _NATIONAL_TEAMS_EN
    team_list = teams.values() if isinstance(teams, dict) else teams

    for entry in team_list:
        if not isinstance(entry, dict):
            continue
        primary_en = entry.get("nameEn") or entry.get("name_en") or entry.get("primary_english_name", "")
        if primary_en and primary_en.strip().lower() not in ("unknown", "none"):
            norm_primary = normalize_nation_en(primary_en)
            if norm_primary:
                _NATIONAL_TEAMS_EN[norm_primary] = entry

        for syn in entry.get("canonical_synonyms", []):
            if syn and syn.strip().lower() not in ("unknown", "none"):
                norm_syn = normalize_nation_en(syn)
                if norm_syn:
                    _NATIONAL_TEAMS_EN[norm_syn] = entry


def _match_age_group_en(text: str) -> tuple[str, str] | None:
    """Matches English age group patterns like U23, U-23, Under 23, Sub 23."""
    m = re.search(r'\b(?:u|under|sub)[\s-]?(\d{1,2})\b', text, re.IGNORECASE)
    if m:
        age = m.group(1)
        remainder = (text[:m.start()] + " " + text[m.end():]).strip()
        return remainder, f"U{age}"
    return None


def _match_olympic_en(text: str) -> tuple[str, str] | None:
    """Matches English Olympic team keywords."""
    m = re.search(r'\b(?:olympic|olympics)\b', text, re.IGNORECASE)
    if m:
        remainder = (text[:m.start()] + " " + text[m.end():]).strip()
        return remainder, "Olympic"
    return None


def _match_women_en(text: str) -> tuple[str, str] | None:
    """Matches English women's team keywords."""
    m = re.search(r'(?:\b(?:women|women\'s|womens)\b|\(w\))', text, re.IGNORECASE)
    if m:
        remainder = (text[:m.start()] + " " + text[m.end():]).strip()
        return remainder, "Women"
    return None


def extract_nation_category_en(name: str) -> tuple[str, str | None]:
    """
    Extracts category and clean root country candidate from English string.
    Returns: (clean_root, canonical_suffix_en)
    If no category detected, returns (normalized_name, None).
    """
    if not name:
        return "", None

    cleaned = name.strip()
    for matcher in (_match_age_group_en, _match_olympic_en, _match_women_en):
        res = matcher(cleaned)
        if res:
            remainder, suffix_en = res
            clean_root = normalize_nation_en(remainder)
            return clean_root, suffix_en

    return normalize_nation_en(cleaned), None


def synthesize_youth_entry_en(mother_entry: dict, suffix_en: str) -> dict:
    """Synthesizes a virtual youth national team dictionary from mother entry in English."""
    mother_en = mother_entry.get("nameEn") or mother_entry.get("name_en") or mother_entry.get("primary_english_name", "")
    mother_ar = mother_entry.get("primary_arabic") or mother_entry.get("primary_arabic_name", "")
    code = mother_entry.get("code", "")
    logo_url = mother_entry.get("logo_url") or (f"https://flagcdn.com/{code.lower()}.svg" if code else "")

    return {
        "nameEn": f"{mother_en} {suffix_en}".strip(),
        "primary_arabic": f"{mother_ar} {suffix_en}".strip(),
        "code": code,
        "logo_url": logo_url,
        "sofascore_code": "",
        "type": "national",
        "is_youth_variant": True,
        "mother_team": mother_entry,
        "mother_row_num": mother_entry.get("row_num"),
        "sheet_name": "_cache_national_teams",
        "row_num": None,
        "arabic_aliases": [],
        "canonical_synonyms": [],
        "original_aliases_cell": "",
    }


def is_national_team_en(name: str) -> bool:
    """Returns True if the English name matches a registered 211 FIFA nation or youth variant."""
    if not name:
        return False
    return get_national_team_en(name) is not None


def get_national_team_en(name: str) -> dict | None:
    """
    Returns the national team dictionary if matched, or None.
    Checks direct registry first; if missing, extracts category and synthesizes from mother nation.
    """
    if not name:
        return None
    norm = normalize_nation_en(name)
    if not norm:
        return None

    # Step 1: Direct registry match
    if norm in _NATIONAL_TEAMS_EN:
        return _NATIONAL_TEAMS_EN[norm]

    # Step 2: Category decomposition and virtual synthesis
    root_cand, suffix_en = extract_nation_category_en(name)
    if suffix_en and root_cand:
        mother = _NATIONAL_TEAMS_EN.get(root_cand)
        if mother is not None:
            return synthesize_youth_entry_en(mother, suffix_en)

    return None


def are_nations_equivalent_en(name1: str, name2: str) -> bool:
    """
    Checks if two English country names represent the same national team.
    Deterministic with category isolation (Morocco U23 != Morocco Senior).
    """
    if not name1 or not name2:
        return False

    norm1 = normalize_nation_en(name1)
    norm2 = normalize_nation_en(name2)

    if not norm1 or not norm2:
        return False

    if norm1 == norm2:
        return True

    entry1 = get_national_team_en(name1)
    entry2 = get_national_team_en(name2)

    if entry1 is not None and entry2 is not None:
        en1 = (entry1.get("nameEn") or entry1.get("primary_english_name", "")).strip().lower()
        en2 = (entry2.get("nameEn") or entry2.get("primary_english_name", "")).strip().lower()
        if en1 and en2:
            return en1 == en2

    # Fallback decomposition comparison
    root1, cat1_en = extract_nation_category_en(name1)
    root2, cat2_en = extract_nation_category_en(name2)

    if (cat1_en or "") != (cat2_en or ""):
        return False

    return root1 == root2
