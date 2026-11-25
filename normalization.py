# ---------------------------------------------------------------------------
# Arabic & International Team Name Normalization and Matching Module
# Unified facade routing between strict national and robust club normalizers.
# ---------------------------------------------------------------------------

from normalizers import ar_nation
from normalizers import en_nation
from normalizers import ar_club
from normalizers import en_club


def register_national_teams(teams: list[dict] | dict[str, dict]):
    """Registers national teams in both Arabic and English national engines."""
    ar_nation.register_national_teams_ar(teams)
    en_nation.register_national_teams_en(teams)


def set_canonical_synonyms(synonyms: dict[str, str]):
    """Registers dynamic canonical synonyms for clubs from Google Sheets."""
    en_club.set_canonical_synonyms(synonyms)


def is_national_team_ar(name: str) -> bool:
    """Checks if the Arabic name matches a registered 211 FIFA nation."""
    return ar_nation.is_national_team_ar(name)


def is_national_team_en(name: str) -> bool:
    """Checks if the English name matches a registered 211 FIFA nation or its synonyms."""
    return en_nation.is_national_team_en(name)


def get_national_team_ar(name: str) -> dict | None:
    """Returns the national team dictionary if matched by Arabic name, or None."""
    return ar_nation.get_national_team_ar(name)


def get_national_team_en(name: str) -> dict | None:
    """Returns the national team dictionary if matched by English name, or None."""
    return en_nation.get_national_team_en(name)


def detect_match_type(t1_name: str, t2_name: str) -> bool:
    """
    Determines match type by checking if either team is a known 211 FIFA nation.
    Returns True for national match, False for club.
    """
    return is_national_team_ar(t1_name) or is_national_team_ar(t2_name)


def normalize_nation_ar(text: str) -> str:
    """Strict orthographic normalization for Arabic national team names."""
    return ar_nation.normalize_nation_ar(text)


def normalize_nation_en(name: str) -> str:
    """Canonical lowercase normalization for English country names."""
    return en_nation.normalize_nation_en(name)


def are_nations_equivalent_ar(name1: str, name2: str) -> bool:
    """Checks if two Arabic country names represent the same national team."""
    return ar_nation.are_nations_equivalent_ar(name1, name2)


def are_nations_equivalent_en(name1: str, name2: str) -> bool:
    """Checks if two English country names represent the same national team."""
    return en_nation.are_nations_equivalent_en(name1, name2)


def normalize_club_ar(text: str, aggressive: bool = False) -> str:
    """Standardizes Arabic club strings with noise/affix stripping."""
    return ar_club.normalize_club_ar(text, aggressive=aggressive)


def normalize_club_en(name: str) -> str:
    """Canonical lowercase token string for English club name comparison."""
    return en_club.normalize_club_en(name)


def are_clubs_equivalent_ar(name1: str, name2: str) -> bool:
    """Determines if two Arabic club names represent the same team."""
    return ar_club.are_clubs_equivalent_ar(name1, name2)


def are_clubs_equivalent_en(name1: str, name2: str) -> bool:
    """Checks if two English club names refer to the same club."""
    return en_club.are_clubs_equivalent_en(name1, name2)


def are_arabic_names_equivalent(name1: str, name2: str, is_national: bool | None = None) -> bool:
    """
    Context-aware Arabic equivalence check.
    If is_national is True, routes strictly to national engine.
    If is_national is False, routes strictly to club engine.
    If is_national is None, checks national registry first before falling back to club engine.
    """
    if not name1 or not name2:
        return False

    if is_national is True:
        return are_nations_equivalent_ar(name1, name2)
    elif is_national is False:
        return are_clubs_equivalent_ar(name1, name2)

    # Automatic context detection:
    if is_national_team_ar(name1) or is_national_team_ar(name2):
        return are_nations_equivalent_ar(name1, name2)

    return are_clubs_equivalent_ar(name1, name2)


def are_english_teams_equivalent(name1: str, name2: str, is_national: bool | None = None) -> bool:
    """
    Context-aware English equivalence check.
    If is_national is True, routes strictly to national engine.
    If is_national is False, routes strictly to club engine.
    If is_national is None, checks national registry first before falling back to club engine.
    """
    if not name1 or not name2:
        return False

    if is_national is True:
        return are_nations_equivalent_en(name1, name2)
    elif is_national is False:
        return are_clubs_equivalent_en(name1, name2)

    # Automatic context detection:
    if is_national_team_en(name1) or is_national_team_en(name2):
        return are_nations_equivalent_en(name1, name2)

    return are_clubs_equivalent_en(name1, name2)


def extract_nation_category_ar(text: str) -> tuple[str, str | None, str | None]:
    """Extracts category and clean root country candidate from Arabic text."""
    return ar_nation.extract_nation_category_ar(text)


def extract_nation_category_en(name: str) -> tuple[str, str | None]:
    """Extracts category and clean root country candidate from English string."""
    return en_nation.extract_nation_category_en(name)


def slugify_team_name(name: str) -> str:
    """Converts an English team name into a URL-safe slug."""
    return en_club.slugify_team_name(name)


__all__ = [
    "register_national_teams",
    "set_canonical_synonyms",
    "is_national_team_ar",
    "is_national_team_en",
    "get_national_team_ar",
    "get_national_team_en",
    "extract_nation_category_ar",
    "extract_nation_category_en",
    "detect_match_type",
    "normalize_nation_ar",
    "normalize_nation_en",
    "are_nations_equivalent_ar",
    "are_nations_equivalent_en",
    "normalize_club_ar",
    "normalize_club_en",
    "are_clubs_equivalent_ar",
    "are_clubs_equivalent_en",
    "are_arabic_names_equivalent",
    "are_english_teams_equivalent",
    "slugify_team_name",
]
