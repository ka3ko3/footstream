# ---------------------------------------------------------------------------
# Arabic Club Team Normalizer
# Handles Arabic club prefix/suffix stripping, regional conflict guards,
# dialectal shifts, and controlled club fuzzy matching.
# ---------------------------------------------------------------------------

import re
import difflib

# Common prefixes and noise words found in Arabic club names
_ARABIC_PREFIXES = [
    r'^(?:النادي|نادي)\s+',
    r'^(?:الفريق|فريق)\s+',
    r'^(?:الجمعية|جمعية)\s+',
    r'^(?:ستاد|استاد)\s+',
    r'^(?:إيه|ايه|اي|أيه)\s+(?:أف|اف|ف)\s+(?:سي|س)\s+',
    r'^(?:إف|اف|ف)\s+(?:سي|س)\s+',
    r'^(?:إيه|ايه|اي|أيه)\s+(?:إس|اس|س)\s+',
    r'^(?:إس|اس|س)\s+(?:سي|س)\s+',
    r'^(?:إيه|ايه|اي|أيه)\s+(?:سي|س)\s+',
    r'^(?:سي|س)\s+(?:دي|د)\s+',
    r'^(?:سي|س)\s+(?:إف|اف|ف)\s+',
    r'^(?:fc|afc|cf|sc|ac|cd|sd|as|sk|fk|bsc|tsg|vfb|vfl|sv|ssv|fsv|rb|rsc|rc|cs|us|ogc)\s+',
]

# Common suffixes and internal noise words found in Arabic club names
_ARABIC_SUFFIXES = [
    r'\s+(?:إف|اف|ف)\s+(?:سي|س)$',
    r'\s+(?:إس|اس|س)\s+(?:سي|س)$',
    r'\s+(?:تي|ت)\s+(?:سي|س)$',
    r'\s+(?:الرياضي|الرياضية|رياضي|البيضاوي|بيضاوي|القاهري|قاهري|البورسعيدي|بورسعيدي|الرباطي|رباطي|الجزائر|الجزاير|العاصمة|العاصمه|العراقي|التونسي|المصري|مصري|السعودي|سعودي|القطري|قطري|تيزي\s+وزو|للألعاب\s+الرياضية|للالعاب\s+الرياضيه)$',
    r'\s+(?:fc|afc|cf|sc|ac|cd|sd|tc|athletic|city|united|town|rovers|wanderers|albion)$',
]

# Generic noise words in Arabic that shouldn't be the sole basis for a match
_GENERIC_CLUB_WORDS = {
    "نادي", "فريق", "جمعية", "اولمبيك", "أولمبيك", "لوكوموتيف", "سسكا", "سبارتاك", "ريد بول", "رد بول", "ستاد", "استاد"
}

# Generic Latin affixes transcribed into Arabic: يونايتد, هوتسبير, سيتي, ريال
_AR_LATIN_GENERICS = {
    "يوناتد", "يونايتد", "رال", "ريال", "هوسبر", "هوتسبر", "هوتسبير", "ستي", "سيتي", "سبورتنج", "سبورتينج", "سبورتينغ"
}

# Arabic country / regional qualifiers that differentiate clubs sharing a common name
_ARABIC_CONFLICTING_PAIRS: set[frozenset] = {
    frozenset({"السعودي", "السوداني"}),
    frozenset({"السعودي", "المصري"}),
    frozenset({"السعودي", "الليبي"}),
    frozenset({"السعودي", "القطري"}),
    frozenset({"السعودي", "الكويتي"}),
    frozenset({"السعودي", "الاماراتي"}),
    frozenset({"السعودي", "السوري"}),
    frozenset({"السعودي", "العماني"}),
    frozenset({"المصري", "الليبي"}),
    frozenset({"المصري", "القطري"}),
    frozenset({"المصري", "السوداني"}),
    frozenset({"السكندري", "السعودي"}),
    frozenset({"السكندري", "الليبي"}),
    frozenset({"العراقي", "السوري"}),
    frozenset({"العراقي", "التوغولي"}),
    frozenset({"الأردني", "السعودي"}),
    frozenset({"طرابلس", "بنغازي"}),
    frozenset({"جدة", "السكندري"}),
    frozenset({"جدة", "دبي"}),
    frozenset({"مستغانم", "التونسي"}),
    frozenset({"مستغانم", "تونسي"}),
    frozenset({"ميلان", "ميامي"}),
    frozenset({"يونيون", "كولون"}),
}


def strip_arabic_diacritics_and_noise(text: str) -> str:
    """Strips tashkeel (diacritics), tatweel/kashida, and zero-width characters."""
    if not text:
        return ""
    t = re.sub(r'[\u064B-\u065F\u0670\u0640]', '', text)
    t = re.sub(r'[\u200B-\u200F\u202A-\u202E\uFEFF]', '', t)
    return t


def strip_club_affixes(text: str) -> str:
    """Removes non-distinguishing organisational prefixes and suffixes from Arabic club names."""
    if not text:
        return ""
    t = text.strip()
    changed = True
    while changed:
        before = t
        for p in _ARABIC_PREFIXES:
            t = re.sub(p, '', t, flags=re.IGNORECASE).strip()
        changed = (t != before)

    changed = True
    while changed:
        before = t
        for s in _ARABIC_SUFFIXES:
            t = re.sub(s, '', t, flags=re.IGNORECASE).strip()
        changed = (t != before)

    # Strip internal non-identifying noise words (e.g. 'الرياضي' inside 'النجم الرياضي الساحلي')
    t = re.sub(r'\b(?:الرياضي|الرياضية|رياضي|نادي|فريق)\b', '', t).strip()
    return t.strip()


def normalize_club_ar(text: str, aggressive: bool = False) -> str:
    """
    Standardizes Arabic club strings by normalizing character shapes, stripping noise,
    and optionally applying aggressive phonetic normalization for transliterated club names.
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

    # Lowercase any Latin characters
    t = t.lower()

    # Strip club noise prefixes/suffixes
    t = strip_club_affixes(t)

    # Collapse repeated whitespace and punctuation (including Unicode dashes)
    t = re.sub(r'[-\u2010-\u2015\u2212_/|,–—]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()

    if aggressive:
        # Strip Arabic definite article prefix Al- (e.g. الترجي -> ترجي, الأهلي -> اهلي)
        t = re.sub(r'\bال(?=[\u0600-\u06FF]{3,})', '', t)

        # 1. Consonant equivalence (Egyptian/Levantine ج vs Gulf/Maghrebi غ / ق)
        t = re.sub(r'[غق]', 'ج', t)

        # 2. Transliteration sound shifts
        t = re.sub(r'تس', 'س', t)
        t = re.sub(r'تش', 'ش', t)

        # 3. Soften optional internal vowels
        t = re.sub(r'(?<=[\u0600-\u06FF])ي(?=[\u0600-\u06FF]{1,})', '', t)

        # 4. Trailing Arabic nisba adjective ي
        if len(t) > 4 and t.endswith('ي'):
            t = t[:-1].strip()

    return t



def _has_arabic_conflicting_qualifiers(text1: str, text2: str) -> bool:
    """Checks if two Arabic club names contain conflicting geographic or identity qualifiers."""
    t1 = strip_arabic_diacritics_and_noise(text1)
    t2 = strip_arabic_diacritics_and_noise(text2)
    t1 = re.sub(r'[إأآٱ]', 'ا', t1)
    t1 = re.sub(r'[ىي]', 'ي', t1)
    t2 = re.sub(r'[إأآٱ]', 'ا', t2)
    t2 = re.sub(r'[ىي]', 'ي', t2)
    tokens1 = set(t1.split())
    tokens2 = set(t2.split())

    # Dundee FC vs Dundee United guard in Arabic
    if ("يونايتد" in tokens1 and "دندي" in tokens1 and "يونايتد" not in tokens2) or \
       ("يونايتد" in tokens2 and "دندي" in tokens2 and "يونايتد" not in tokens1):
        return True

    for pair in _ARABIC_CONFLICTING_PAIRS:
        p_list = list(pair)
        w1, w2 = p_list[0], p_list[1]
        if (w1 in tokens1 and w2 in tokens2 and w1 not in tokens2) or \
           (w2 in tokens1 and w1 in tokens2 and w2 not in tokens2):
            return True

    # Check Inter vs Milan in Arabic
    if ("انتر" in tokens1 or "إنتر" in tokens1) and ("ميلان" in tokens2 and "انتر" not in tokens2 and "إنتر" not in tokens2):
        return True
    if ("انتر" in tokens2 or "إنتر" in tokens2) and ("ميلان" in tokens1 and "انتر" not in tokens1 and "إنتر" not in tokens1):
        return True

    return False


def are_clubs_equivalent_ar(name1: str, name2: str) -> bool:
    """
    Determines if two Arabic club names represent the same team,
    accounting for dialect differences, affixes, and transliteration variations.
    """
    if not name1 or not name2:
        return False

    n1_clean = name1.strip()
    n2_clean = name2.strip()

    # Guard: conflicting country / regional / club qualifiers
    if _has_arabic_conflicting_qualifiers(n1_clean, n2_clean):
        return False

    # Level 1: Exact match
    if n1_clean.lower() == n2_clean.lower():
        return True

    # Level 2: Standard orthographic normalization match
    norm1 = normalize_club_ar(n1_clean, aggressive=False)
    norm2 = normalize_club_ar(n2_clean, aggressive=False)
    if norm1 and norm2 and norm1 == norm2:
        return True

    # Level 3: Aggressive phonetic transliteration fingerprint match
    fp1 = normalize_club_ar(n1_clean, aggressive=True)
    fp2 = normalize_club_ar(n2_clean, aggressive=True)
    if fp1 and fp2 and fp1 == fp2:
        return True

    # Level 4: Set equality of distinctive non-generic words
    if fp1 and fp2:
        words1 = [w for w in fp1.split() if w not in _GENERIC_CLUB_WORDS]
        words2 = [w for w in fp2.split() if w not in _GENERIC_CLUB_WORDS]
        if words1 and words2 and set(words1) == set(words2):
            return True

        tokens1 = set(fp1.split())
        tokens2 = set(fp2.split())
        if tokens1 and tokens2 and tokens1 == tokens2:
            if not _has_arabic_conflicting_qualifiers(n1_clean, n2_clean):
                return True

        distinct1 = {t for t in tokens1 if t not in _AR_LATIN_GENERICS}
        distinct2 = {t for t in tokens2 if t not in _AR_LATIN_GENERICS}
        if distinct1 and distinct2 and distinct1 == distinct2:
            if not _has_arabic_conflicting_qualifiers(n1_clean, n2_clean):
                return True

    # Level 5: High similarity ratio on aggressive fingerprints (> 0.82)
    # Protected by minimum length safety floor (len >= 5) so short names never collide
    if fp1 and fp2 and len(fp1) >= 5 and len(fp2) >= 5:
        words1 = fp1.split()
        words2 = fp2.split()
        if len(words1) == len(words2):
            ratio = difflib.SequenceMatcher(None, fp1, fp2).ratio()
            if ratio >= 0.82:
                return True

    return False
