# ---------------------------------------------------------------------------
# Team Engine: National Youth Teams Zero-Cost Synthesis
# Decomposes age groups (U17, U20, Olympic) and synthesizes entries from mother nations ($0 LLM).
# ---------------------------------------------------------------------------

import logger
from normalization import (
    extract_nation_category_ar,
    get_national_team_ar,
    register_national_teams,
)
from .lookup import find_existing_translation


def format_youth_category_names(mother: dict, cat_en: str, cat_ar: str) -> tuple[str, str]:
    """Formats standardized primary Arabic and English names for youth national teams."""
    mother_ar = mother.get("primary_arabic") or mother.get("primary_arabic_name", "")
    mother_en = mother.get("nameEn") or mother.get("primary_english_name", "")
    primary_ar = f"{mother_ar} {cat_ar}".strip()
    primary_en = f"{mother_en} {cat_en}".strip()
    return primary_ar, primary_en


def build_synthesized_youth_dict(mother: dict, primary_ar: str, name_en: str, scraped_alias: str = "") -> dict:
    """Builds an in-memory dictionary for a synthesized youth national team."""
    code = mother.get("code", "")
    logo_url = mother.get("logo_url") or (f"https://flagcdn.com/{code.lower()}.svg" if code else "")
    aliases = [scraped_alias] if scraped_alias and scraped_alias != primary_ar else []

    return {
        "nameEn": name_en,
        "primary_arabic": primary_ar,
        "code": code,
        "logo_url": logo_url,
        "sofascore_code": "",
        "type": "national",
        "is_youth_variant": True,
        "mother_team": mother,
        "mother_row_num": mother.get("row_num"),
        "sheet_name": "_cache_national_teams",
        "row_num": None,
        "arabic_aliases": aliases,
        "canonical_synonyms": [],
        "original_aliases_cell": scraped_alias if aliases else "",
    }


def resolve_known_youth_teams(
    missing_names: list,
    team_translations: dict,
    new_translations_list: list,
    alias_updates: list
) -> list:
    """
    Pre-checks missing team names for recognized mother nations with categories.
    Synthesizes them at $0 LLM cost and queues them for sheet persistence.
    Returns the list of remaining unresolved team names.
    """
    unresolved = []
    for name in missing_names:
        root_cand, cat_en, cat_ar = extract_nation_category_ar(name)
        if cat_en and cat_ar and root_cand:
            mother = get_national_team_ar(root_cand)
            if mother:
                primary_ar, name_en = format_youth_category_names(mother, cat_en, cat_ar)
                scraped_alias = name if name != primary_ar else ""

                # Check if this youth variation already exists in cache
                existing_youth = find_existing_translation(primary_ar, team_translations, is_national=True)
                if existing_youth and existing_youth.get("row_num"):
                    if scraped_alias and scraped_alias not in existing_youth.get("arabic_aliases", []):
                        orig_cell = existing_youth.get("original_aliases_cell", "")
                        new_val = f"{orig_cell} | {scraped_alias}" if orig_cell else scraped_alias
                        existing_youth["original_aliases_cell"] = new_val
                        existing_youth.setdefault("arabic_aliases", []).append(scraped_alias)
                        row_num = existing_youth.get("row_num")
                        if row_num:
                            alias_updates.append((row_num, "_cache_national_teams", 1, new_val))
                    team_translations[name] = existing_youth
                else:
                    youth_entry = build_synthesized_youth_dict(mother, primary_ar, name_en, scraped_alias=scraped_alias)
                    team_translations[name] = youth_entry
                    team_translations[primary_ar] = youth_entry
                    register_national_teams([youth_entry])
                    new_translations_list.append((primary_ar, name_en, scraped_alias, youth_entry["logo_url"], "national", youth_entry["code"]))
                    logger.success(f"Translation: Zero-cost synthesized '{name_en}' ('{primary_ar}') from mother '{mother.get('nameEn')}'.")
                continue

        unresolved.append(name)
    return unresolved
