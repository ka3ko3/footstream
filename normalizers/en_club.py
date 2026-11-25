# ---------------------------------------------------------------------------
# English Club Team Normalizer
# Handles English organizational noise stripping, modifier disambiguation,
# dynamic canonical synonyms, and slug generation for clubs.
# ---------------------------------------------------------------------------

import re
import unicodedata

# Organisational noise stripped before comparison — these carry no identity information
_ENGLISH_ORG_NOISE = re.compile(
    r'\b(?:1\.\s*fc|1\.\s*fsv|fc|cf|cfc|uc|afc|sc|ac|cd|sd|ud|tc|bsc|tsg|vfb|vfl|sv|ssv|fsv|rb|rsc|rc|cs|us|ogc'
    r'|bc|sk|jk|sfc|acb|ca|rcd|sl|as|ss|ssc|acf|losc|bvb|sco|hsc|aj|cr|se|deportivo|rasenballsport'
    r'|alsace|paulista|spvgg|kv|ksv|af|ea|sm|foot|praia|kulubu|balompie|amadora|fbpa|fr|ec|gd|pec|rkc|krc|kaa'
    r'|sad|va|eh|fk|fbc|sa|csd|scp|clube\s+de|sporting\s+clube\s+de'
    r'|balompie|sportive\s+de|club|football\s+club|de\s+f[uú]tbol|calcio|associazione\s+calcio|\d{2,4})\b',
    re.IGNORECASE
)

# Generic words that can appear as organizational prefixes but shouldn't alone distinguish a club
_GENERIC_ENGLISH_TOKENS = {
    "borussia", "eintracht", "olympique", "stade", "sporting", "real", "inter",
    "athletic", "atletico", "bayer", "bayern", "club", "de", "the", "al", "el",
    "sc", "ac", "fc", "cf", "san", "saint", "los", "las", "la", "le", "hotspur",
    "wanderers", "town", "albion", "city", "united", "casablanca",
    "tunis", "eindhoven", "rotterdam", "manchester", "hellas", "1909", "1899", "04", "05", "1846",
    "orient", "argyle", "county", "north", "end", "wednesday", "hove", "eagles", "stars", "crew",
    "galaxy", "red", "bulls", "plata", "almagro", "union", "sport", "rovers", "fortuna", "wehen",
    "lavallois", "quevilly", "rouen", "chaves", "sittard", "heracles", "waalwijk", "cleopatra",
    "gaish", "hodoud", "mahalla", "diaraf", "yaounde", "douala", "esperanca", "pr", "old", "boys",
    "kobe", "kawasaki", "hiroshima", "kashima", "nagoya", "machida", "niigata", "kashiwa", "kyoto",
    "pohang", "suwon", "tashkent", "namangan", "qarshi", "sydney", "melbourne", "brisbane",
    "adelaide", "wellington", "auckland", "dresden", "munster", "regensburg", "ferrara", "leonesa",
    "pescara", "delfino", "vicenza", "ceuta", "niort", "niortais", "chamois", "tilburg", "breda",
    "westerlo", "dender", "rizespor", "caykur", "gaziantep", "bodrum", "portland", "vancouver",
    "cultural", "ad", "lr", "preussen", "ssv", "jahn", "dynamo", "nac", "kvc", "fcv", "ts",
    "golden", "kano", "bendel", "fasil", "deportes", "universidad"
}

# If both names contain different words from any one of these pairs, they are DIFFERENT clubs.
_CONFLICTING_MODIFIER_PAIRS: set[frozenset] = {
    frozenset({"city", "united"}),
    frozenset({"city", "wanderers"}),
    frozenset({"city", "rovers"}),
    frozenset({"milan", "miami"}),
    frozenset({"milan", "inter"}),
    frozenset({"real", "atletico"}),
    frozenset({"madrid", "sociedad"}),
    frozenset({"madrid", "betis"}),
    frozenset({"madrid", "valladolid"}),
    frozenset({"madrid", "zaragoza"}),
    frozenset({"madrid", "salt"}),
    frozenset({"cp", "gijon"}),
    frozenset({"cp", "braga"}),
    frozenset({"cp", "kansas"}),
    frozenset({"lisbon", "braga"}),
    frozenset({"women", "castilla"}),
    frozenset({"women", "ii"}),
    frozenset({"castilla", "ii"}),
    frozenset({"femeni", "atletic"}),
    frozenset({"femenino", "castilla"}),
    frozenset({"rangers", "celtic"}),
    frozenset({"dortmund", "monchengladbach"}),
    frozenset({"leverkusen", "munchen"}),
    frozenset({"leverkusen", "munich"}),
    frozenset({"kyiv", "zagreb"}),
    frozenset({"kyiv", "moscow"}),
    frozenset({"kyiv", "houston"}),
    frozenset({"leipzig", "salzburg"}),
    frozenset({"leipzig", "york"}),
    frozenset({"barcelona", "guayaquil"}),
}

# Well-known short names / acronyms -> canonical normalized English name.
_CANONICAL_SYNONYMS: dict[str, str | None] = {}


def set_canonical_synonyms(synonyms: dict[str, str]):
    """Updates the in-memory canonical synonyms dictionary from the Google Sheets cache."""
    global _CANONICAL_SYNONYMS
    if synonyms:
        _CANONICAL_SYNONYMS = {k.strip().lower(): v for k, v in synonyms.items() if k and v}


def _strip_accents(text: str) -> str:
    """Removes accents and diacritics from Latin characters (e.g. Ferencváros -> Ferencvaros)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def normalize_club_en(name: str) -> str:
    """
    Produces a canonical lowercase token string for English club name comparison.
    Strips org-noise abbreviations, accents, punctuation, and applies known synonyms.
    """
    if not name:
        return ""
    raw_clean = _strip_accents(name).lower().strip()
    synonym_raw = _CANONICAL_SYNONYMS.get(raw_clean)
    if synonym_raw is not None:
        name = synonym_raw

    t = _strip_accents(name).lower().strip()
    # Normalize abbreviations: utd -> united
    t = re.sub(r'\butd\b', 'united', t)
    # Normalize dotted acronyms: U.D. -> ud, F.C. -> fc, A.F.C. -> afc, 1. FC -> fc
    t = re.sub(r'\b1\.\s*', '', t)
    t = re.sub(r'\b([a-z])\.([a-z])\.(?:([a-z])\.)?', r'\1\2\3', t)
    t = re.sub(r"[.\-\u2010-\u2015\u2212_/|',–—]", " ", t)
    t = re.sub(r'\s+', ' ', t).strip()

    # Apply synonym lookup on normalized phrase
    synonym = _CANONICAL_SYNONYMS.get(t)
    if synonym is not None:
        t = synonym

    # Strip organizational noise
    t = _ENGLISH_ORG_NOISE.sub('', t)
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()

    # Re-apply synonym lookup after noise strip
    synonym_after = _CANONICAL_SYNONYMS.get(t)
    if synonym_after is not None:
        return synonym_after
    return t


def _has_conflicting_modifiers(tokens1: set[str], tokens2: set[str], raw1: str = "", raw2: str = "") -> bool:
    """
    Returns True if the two token sets each contain a different word from any conflicting pair.
    """
    r1 = (raw1 or "").strip().lower()
    r2 = (raw2 or "").strip().lower()

    # Guard against Barcelona (Spain) vs Barcelona SC (Ecuador)
    is_ec1 = "barcelona sc" in r1 or "guayaquil" in r1
    is_ec2 = "barcelona sc" in r2 or "guayaquil" in r2
    if is_ec1 and not is_ec2 and "barcelona" in r2.split():
        return True
    if is_ec2 and not is_ec1 and "barcelona" in r1.split():
        return True

    # Guard against Dundee FC vs Dundee United
    if ("dundee fc" in r1 and "dundee united" in r2) or \
       ("dundee fc" in r2 and "dundee united" in r1):
        return True

    # Prevent Real Madrid vs Atletico Madrid
    has_real1 = "real" in tokens1 or "real" in r1.split()
    has_real2 = "real" in tokens2 or "real" in r2.split()
    has_atm1 = "atletico" in tokens1 or "atletico" in r1.split() or "atlético" in r1.split()
    has_atm2 = "atletico" in tokens2 or "atletico" in r2.split() or "atlético" in r2.split()
    if (has_real1 and has_atm2) or (has_real2 and has_atm1):
        return True

    # Prevent AC Milan vs Inter Milan
    has_inter1 = "inter" in tokens1 or "internazionale" in tokens1 or "inter" in r1.split()
    has_inter2 = "inter" in tokens2 or "internazionale" in tokens2 or "inter" in r2.split()
    has_milan1 = "milan" in tokens1
    has_milan2 = "milan" in tokens2
    if (has_milan1 and has_milan2) and (has_inter1 != has_inter2):
        return True

    # Prevent standalone generic word matching specific club (e.g. Manchester vs Manchester City)
    for g in ("manchester", "inter", "real", "sporting", "atletico", "athletic"):
        if (g in tokens1 and len(tokens1) == 1 and len(tokens2) > 1) or \
           (g in tokens2 and len(tokens2) == 1 and len(tokens1) > 1):
            return True

    for pair in _CONFLICTING_MODIFIER_PAIRS:
        pair_list = list(pair)
        a, b = pair_list[0], pair_list[1]
        if (a in tokens1 and b in tokens2 and a not in tokens2) or \
           (b in tokens1 and a in tokens2 and b not in tokens2):
            return True
    return False


def are_clubs_equivalent_en(name1: str, name2: str) -> bool:
    """
    Checks if two English team names refer to the same club.
    """
    if not name1 or not name2:
        return False

    # Level 0: exact match
    if name1.strip().lower() == name2.strip().lower():
        return True

    norm1 = normalize_club_en(name1)
    norm2 = normalize_club_en(name2)

    tokens1 = set(norm1.split()) if norm1 else set()
    tokens2 = set(norm2.split()) if norm2 else set()

    # Level 1: conflict detection MUST precede equality check
    if _has_conflicting_modifiers(tokens1, tokens2, name1, name2):
        return False

    # Level 2: normalized strings are identical
    if norm1 and norm2 and norm1 == norm2:
        return True

    # Level 3: full set equality of all tokens
    if tokens1 and tokens2 and tokens1 == tokens2:
        if any(len(tok) >= 3 for tok in tokens1):
            return True

    # Level 4: distinctive non-generic tokens set equality
    distinct1 = {t for t in tokens1 if t not in _GENERIC_ENGLISH_TOKENS}
    distinct2 = {t for t in tokens2 if t not in _GENERIC_ENGLISH_TOKENS}
    if distinct1 and distinct2 and distinct1 == distinct2:
        if any(len(tok) >= 3 for tok in distinct1):
            return True

    return False


def slugify_team_name(name: str) -> str:
    """
    Converts an English team name into a URL-safe slug for use as part of event_id.
    'Manchester City' -> 'manchester-city', 'Paris Saint-Germain' -> 'paris-saint-germain'.
    """
    if not name or name.strip().lower() in ("unknown", ""):
        return "unk"
    t = _strip_accents(name).lower().strip()
    t = re.sub(r"[.\-\u2010-\u2015\u2212_/|',–—]", " ", t)
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', '-', t).strip('-')
    return t or "unk"
