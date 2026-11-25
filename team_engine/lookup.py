# ---------------------------------------------------------------------------
# Team Engine: In-Memory Cache Lookup & Matching
# Multi-step ladder search with strict match-type isolation (nations vs clubs).
# ---------------------------------------------------------------------------

from normalization import (
    get_national_team_ar,
    get_national_team_en,
    are_nations_equivalent_ar,
    are_nations_equivalent_en,
    are_clubs_equivalent_ar,
    are_clubs_equivalent_en,
)


def find_existing_translation(name: str, team_translations: dict, is_national: bool | None = None) -> dict | None:
    """
    Looks up a team name in the translation cache with match-type isolation.
    If is_national is True, searches strictly against national teams.
    If is_national is False, searches strictly against club teams.
    """
    if not team_translations or not name:
        return None

    def _is_valid(entry: dict) -> bool:
        return entry.get("nameEn") not in ("Unknown", "", None)

    def _matches_type(entry: dict) -> bool:
        if is_national is None:
            return True
        entry_is_nat = (entry.get("type") == "national")
        return entry_is_nat == is_national

    # Step 0: Canonical 211 FIFA nations registry direct lookup
    if is_national:
        nat_entry = get_national_team_ar(name)
        if nat_entry is not None and _is_valid(nat_entry):
            if not nat_entry.get("is_youth_variant"):
                return nat_entry

    # Step 1: Direct exact primary name match
    if name in team_translations:
        entry = team_translations[name]
        if _is_valid(entry) and _matches_type(entry):
            return entry

    # Step 2: Exact alias lookup
    for v in team_translations.values():
        if not _is_valid(v) or not _matches_type(v):
            continue
        aliases = v.get("arabic_aliases", [])
        if name in aliases:
            return v

    # Step 3: Arabic equivalence matching (strict national or club-specific)
    best_candidate = None
    for v in team_translations.values():
        if not _matches_type(v):
            continue
        all_ar_names = [v["primary_arabic"]] + v.get("arabic_aliases", [])
        is_nat = (v.get("type") == "national")
        for alias in all_ar_names:
            eq = are_nations_equivalent_ar(name, alias) if is_nat else are_clubs_equivalent_ar(name, alias)
            if eq:
                if _is_valid(v):
                    return v
                if best_candidate is None:
                    best_candidate = v

    # Step 4: English canonical name / synonyms matching
    for v in team_translations.values():
        if not _is_valid(v) or not _matches_type(v):
            continue
        name_en = v.get("nameEn", "")
        is_nat = (v.get("type") == "national")
        if name_en:
            eq = are_nations_equivalent_en(name, name_en) if is_nat else are_clubs_equivalent_en(name, name_en)
            if eq:
                return v
        for syn in v.get("canonical_synonyms", []):
            eq = are_nations_equivalent_en(name, syn) if is_nat else are_clubs_equivalent_en(name, syn)
            if eq:
                return v

    # Step 5: Fallback if untranslated placeholder entry exists
    if name in team_translations:
        entry = team_translations[name]
        if _matches_type(entry):
            return entry

    return best_candidate


def _find_matching_cached_team(name_en: str, team_translations: dict, is_national: bool = False) -> dict | None:
    """
    Searches for an existing team in cache that matches the newly translated English team name.
    Strictly type-isolated: if is_national is True, matches 211 nations; if False, matches clubs.
    """
    if not team_translations or not name_en:
        return None

    clean_en = name_en.strip().lower()

    def _is_valid_entry(v: dict) -> bool:
        return v.get("nameEn") not in ("Unknown", "", None)

    if is_national:
        nat_entry = get_national_team_en(name_en)
        if nat_entry is not None:
            return nat_entry
        for v in team_translations.values():
            if not _is_valid_entry(v) or v.get("type") != "national":
                continue
            if v.get("nameEn", "").strip().lower() == clean_en:
                return v
            if any(syn.strip().lower() == clean_en for syn in v.get("canonical_synonyms", [])):
                return v
        return None

    # Club matching:
    for v in team_translations.values():
        if not _is_valid_entry(v) or v.get("type") == "national":
            continue
        if v.get("nameEn", "").strip().lower() == clean_en:
            return v
        if any(syn.strip().lower() == clean_en for syn in v.get("canonical_synonyms", [])):
            return v

    for v in team_translations.values():
        if not _is_valid_entry(v) or v.get("type") == "national":
            continue
        if are_clubs_equivalent_en(name_en, v.get("nameEn", "")):
            return v

    return None
