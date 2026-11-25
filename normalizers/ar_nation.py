# ---------------------------------------------------------------------------
# Arabic National Team Normalizer
# Strict, deterministic matching against 211 FIFA nations.
# Zero consonant shifting, zero vowel stripping, zero fuzzy ratio traps.
# ---------------------------------------------------------------------------

import re

# In-memory registry of 211 FIFA nations: normalized_ar -> national team dict
_NATIONAL_TEAMS_AR: dict[str, dict] = {}


def strip_arabic_diacritics_and_noise(text: str) -> str:
    """Strips tashkeel (diacritics), tatweel/kashida, and zero-width characters."""
    if not text:
        return ""
    t = re.sub(r'[\u064B-\u065F\u0670\u0640]', '', text)
    t = re.sub(r'[\u200B-\u200F\u202A-\u202E\uFEFF]', '', t)
    return t


def normalize_nation_ar(text: str) -> str:
    """
    Strict orthographic normalization for Arabic national team names.
    Normalizes character variants deterministically without vowel or consonant distortion.
    """
    if not text:
        return ""

    t = strip_arabic_diacritics_and_noise(text.strip())

    # Normalize alef variants (إ, أ, آ, ٱ -> ا)
    t = re.sub(r'[إأآٱ]', 'ا', t)

    # Normalize teh marbuta (ة -> ه)
    t = re.sub(r'ة', 'ه', t)

    # Normalize alif maksura and yaa forms (ى -> ي)
    t = re.sub(r'[ىي]', 'ي', t)

    # Normalize hamza on waw and yaa
    t = re.sub(r'ؤ', 'و', t)
    t = re.sub(r'ئ', 'ي', t)

    # Lowercase any Latin characters if present
    t = t.lower()

    # Collapse repeated whitespace and punctuation (including Unicode dashes)
    t = re.sub(r'[-\u2010-\u2015\u2212_/|,–—]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()

    return t


# Protected root nations where 'ال' is an inseparable part of the actual country name
_ROOT_AL_NATIONS = {"المانيا", "البانيا"}


def strip_al_prefix(norm_text: str) -> str:
    """
    Safely strips the Arabic definite article 'ال' (Al-) from tokens in a normalized nation string.
    Guards root-letter exceptions 'المانيا' (Germany) and 'البانيا' (Albania).
    """
    if not norm_text:
        return ""
    words = norm_text.split()
    stripped_words = []
    for w in words:
        if w in _ROOT_AL_NATIONS:
            stripped_words.append(w)
        elif w.startswith("ال") and len(w) > 3:
            stripped_words.append(w[2:])
        else:
            stripped_words.append(w)
    return " ".join(stripped_words)


def register_national_teams_ar(teams: list[dict] | dict[str, dict]):
    """
    Registers national teams loaded from '_cache_national_teams' worksheet.
    Maps normalized primary Arabic names, aliases, and AL-stripped variants to the team dictionary.
    """
    global _NATIONAL_TEAMS_AR
    team_list = teams.values() if isinstance(teams, dict) else teams

    for entry in team_list:
        if not isinstance(entry, dict):
            continue
        primary_ar = entry.get("primary_arabic") or entry.get("primary_arabic_name", "")
        if primary_ar:
            norm_primary = normalize_nation_ar(primary_ar)
            if norm_primary:
                _NATIONAL_TEAMS_AR[norm_primary] = entry
                stripped = strip_al_prefix(norm_primary)
                if stripped and stripped != norm_primary:
                    _NATIONAL_TEAMS_AR.setdefault(stripped, entry)

        for alias in entry.get("arabic_aliases", []):
            if alias:
                norm_alias = normalize_nation_ar(alias)
                if norm_alias:
                    _NATIONAL_TEAMS_AR[norm_alias] = entry
                    stripped = strip_al_prefix(norm_alias)
                    if stripped and stripped != norm_alias:
                        _NATIONAL_TEAMS_AR.setdefault(stripped, entry)


def _lookup_direct_nation_ar(norm: str) -> dict | None:
    """Helper to look up a nation strictly in the in-memory registry."""
    if not norm:
        return None
    if norm in _NATIONAL_TEAMS_AR:
        return _NATIONAL_TEAMS_AR[norm]
    stripped = strip_al_prefix(norm)
    if stripped in _NATIONAL_TEAMS_AR:
        return _NATIONAL_TEAMS_AR[stripped]
    return None


def strip_arabic_team_noise(text: str) -> str:
    """Strips common prefix/suffix noise words like منتخب, فريق, سنة, عام."""
    if not text:
        return ""
    t = re.sub(r'^(?:منتخب|فريق|اتحاد)\s+', '', text).strip()
    t = re.sub(r'\s+(?:سنة|سنه|عام)$', '', t).strip()
    return t


def _match_age_group_ar(text: str) -> tuple[str, str, str] | None:
    """Matches Arabic age group patterns (تحت, دون, أقل من, or Uxx)."""
    m = re.search(r'(?:تحت|دون|اقل من|أقل من)\s*(\d{1,2})', text)
    if m:
        age = m.group(1)
        remainder = (text[:m.start()] + " " + text[m.end():]).strip()
        return remainder, f"U{age}", f"تحت {age}"

    m = re.search(r'\b[uU][\s\-_]?(\d{1,2})\b', text)
    if m:
        age = m.group(1)
        remainder = (text[:m.start()] + " " + text[m.end():]).strip()
        return remainder, f"U{age}", f"تحت {age}"

    return None


def _match_olympic_ar(text: str) -> tuple[str, str, str] | None:
    """Matches Arabic Olympic team keywords."""
    m = re.search(r'\b(?:الاولمبي|الأولمبي|اولمبي|أولمبي|اولمبيك)\b', text)
    if m:
        remainder = (text[:m.start()] + " " + text[m.end():]).strip()
        return remainder, "Olympic", "الأولمبي"
    return None


def _match_youth_juniors_ar(text: str) -> tuple[str, str, str] | None:
    """Matches Arabic youth/juniors keywords mapping to U20 or U17."""
    m = re.search(r'\b(?:الشباب|للشباب|شباب)\b', text)
    if m:
        remainder = (text[:m.start()] + " " + text[m.end():]).strip()
        return remainder, "U20", "تحت 20"

    m = re.search(r'\b(?:الناشيين|الناشئين|للناشيين|للناشئين|ناشيين|ناشئين|شابات)\b', text)
    if m:
        remainder = (text[:m.start()] + " " + text[m.end():]).strip()
        return remainder, "U17", "تحت 17"

    return None


def _match_women_ar(text: str) -> tuple[str, str, str] | None:
    """Matches Arabic women/female team keywords."""
    m = re.search(r'\b(?:السيدات|سيدات|اناث|إناث|نساء|للسيدات)\b', text)
    if m:
        remainder = (text[:m.start()] + " " + text[m.end():]).strip()
        return remainder, "Women", "للسيدات"
    return None


def extract_nation_category_ar(raw_text: str) -> tuple[str, str | None, str | None]:
    """
    Extracts category and clean root country candidate from Arabic text.
    Returns: (clean_root, canonical_suffix_en, canonical_suffix_ar)
    If no category detected, returns (normalized_text, None, None).
    """
    if not raw_text:
        return "", None, None

    norm = normalize_nation_ar(raw_text)
    cleaned = strip_arabic_team_noise(norm)

    for matcher in (_match_age_group_ar, _match_olympic_ar, _match_youth_juniors_ar, _match_women_ar):
        res = matcher(cleaned)
        if res:
            remainder, suffix_en, suffix_ar = res
            clean_root = strip_arabic_team_noise(normalize_nation_ar(remainder))
            return clean_root, suffix_en, suffix_ar

    return cleaned, None, None


def synthesize_youth_entry_ar(mother_entry: dict, suffix_en: str, suffix_ar: str) -> dict:
    """Synthesizes a virtual youth national team dictionary from a mother nation entry."""
    mother_en = mother_entry.get("nameEn") or mother_entry.get("name_en") or mother_entry.get("primary_english_name", "")
    mother_ar = mother_entry.get("primary_arabic") or mother_entry.get("primary_arabic_name", "")
    code = mother_entry.get("code", "")
    logo_url = mother_entry.get("logo_url") or (f"https://flagcdn.com/{code.lower()}.svg" if code else "")

    return {
        "nameEn": f"{mother_en} {suffix_en}".strip(),
        "primary_arabic": f"{mother_ar} {suffix_ar}".strip(),
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


def is_national_team_ar(name: str) -> bool:
    """Returns True if the Arabic name matches a registered 211 FIFA nation or youth variant."""
    if not name:
        return False
    return get_national_team_ar(name) is not None


def get_national_team_ar(name: str) -> dict | None:
    """
    Returns the national team dictionary if matched, or None.
    Checks direct registry first; if missing, extracts category and synthesizes from mother nation.
    """
    if not name:
        return None
    norm = normalize_nation_ar(name)
    if not norm:
        return None

    # Step 1: Direct exact match (Senior nations or registered youth rows)
    direct = _lookup_direct_nation_ar(norm)
    if direct is not None:
        return direct

    # Step 2: Category decomposition and virtual zero-cost synthesis
    root_cand, suffix_en, suffix_ar = extract_nation_category_ar(name)
    if suffix_en and suffix_ar and root_cand:
        mother = _lookup_direct_nation_ar(normalize_nation_ar(root_cand))
        if mother is not None:
            return synthesize_youth_entry_ar(mother, suffix_en, suffix_ar)

    return None


def are_nations_equivalent_ar(name1: str, name2: str) -> bool:
    """
    Checks if two Arabic country names represent the same national team.
    Deterministic with category isolation (Morocco U23 != Morocco Senior).
    """
    if not name1 or not name2:
        return False

    norm1 = normalize_nation_ar(name1)
    norm2 = normalize_nation_ar(name2)

    if not norm1 or not norm2:
        return False

    if norm1 == norm2:
        return True

    entry1 = get_national_team_ar(name1)
    entry2 = get_national_team_ar(name2)

    if entry1 is not None and entry2 is not None:
        en1 = (entry1.get("nameEn") or entry1.get("primary_english_name", "")).strip().lower()
        en2 = (entry2.get("nameEn") or entry2.get("primary_english_name", "")).strip().lower()
        if en1 and en2:
            return en1 == en2

    # Fallback decomposition comparison
    root1, cat1_en, _ = extract_nation_category_ar(name1)
    root2, cat2_en, _ = extract_nation_category_ar(name2)

    # Categories must match
    if (cat1_en or "") != (cat2_en or ""):
        return False

    if root1 == root2:
        return True

    if strip_al_prefix(root1) == strip_al_prefix(root2):
        return True

    return False
