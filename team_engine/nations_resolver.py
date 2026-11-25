# ---------------------------------------------------------------------------
# Team Engine: National Teams Resolver
# Resolves international match opponents and enforces the Mother Row Golden Rule.
# ---------------------------------------------------------------------------

import logger
from normalization import (
    extract_nation_category_ar,
    extract_nation_category_en,
    register_national_teams,
)
from .llm_client import (
    fetch_openrouter_mappings,
    _extract_translation_name,
    is_unknown_team,
)
from .lookup import _find_matching_cached_team
from .youth import (
    format_youth_category_names,
    build_synthesized_youth_dict,
)


def apply_mother_row_alias_golden_rule(mother: dict, typo_alias: str, alias_updates: list):
    """
    The Golden Rule: strictly appends a typo/unrecognized root alias to Column A
    of the Mother Nation row in _cache_national_teams.
    """
    if not mother or not typo_alias:
        return

    primary_ar = mother.get("primary_arabic", "")
    aliases = mother.get("arabic_aliases", [])

    if typo_alias != primary_ar and typo_alias not in aliases:
        orig_cell = mother.get("original_aliases_cell", "")
        new_val = f"{orig_cell} | {typo_alias}" if orig_cell else typo_alias
        mother["original_aliases_cell"] = new_val
        mother.setdefault("arabic_aliases", []).append(typo_alias)
        register_national_teams([mother])

        row_num = mother.get("row_num")
        sheet_name = mother.get("sheet_name")
        if row_num and sheet_name == "_cache_national_teams":
            alias_updates.append((row_num, "_cache_national_teams", 1, new_val))
            logger.success(f"Translation: Golden Rule auto-linked root alias '{typo_alias}' -> '{mother.get('nameEn')}' in Mother row {row_num}.")


def resolve_national_teams(
    intl_missing_map: dict,
    team_translations: dict,
    new_translations_list: list,
    alias_updates: list
):
    """
    Constrained National Resolution for known international matches:
    Batches missing national teams, prompts AI for FIFA country names,
    auto-links Arabic aliases into Column A of _cache_national_teams,
    and synthesizes youth variants when categories are present.
    """
    if not intl_missing_map:
        return

    missing_nats = list(intl_missing_map.keys())
    logger.info(f"Translation: Requesting batched national translation for {len(missing_nats)} team(s)...")

    nat_system_prompt = (
        "Translate each Arabic country name to its official English FIFA name.\n"
        "Output JSON format: {\"Arabic Name\": \"English Name\"}\n"
        "Example: {\"اسكتلندا\": \"Scotland\", \"بورندي\": \"Burundi\"}\n"
        "Return raw JSON only."
    )

    user_lines = [f'- "{name}" (playing against {intl_missing_map[name]})' for name in missing_nats]
    nat_user_prompt = "Translate these national football teams to English country names:\n" + "\n".join(user_lines)

    llm_res = fetch_openrouter_mappings(missing_nats, context_prompt=nat_system_prompt, user_prompt=nat_user_prompt)

    for name in missing_nats:
        opponent = intl_missing_map[name]
        name_en = _extract_translation_name(llm_res, name)

        root_cand, cat_en, cat_ar = extract_nation_category_ar(name)

        mother_cand_en = name_en
        if cat_en and name_en:
            clean_mother_en, _ = extract_nation_category_en(name_en)
            if clean_mother_en:
                mother_cand_en = clean_mother_en

        matched_nat = _find_matching_cached_team(mother_cand_en, team_translations, is_national=True) if mother_cand_en and not is_unknown_team(mother_cand_en) else None

        if matched_nat:
            if cat_en:
                # Apply The Golden Rule to Mother Row for typo root
                if root_cand:
                    apply_mother_row_alias_golden_rule(matched_nat, root_cand, alias_updates)

                primary_ar, youth_en = format_youth_category_names(matched_nat, cat_en, cat_ar)
                scraped_alias = name if name != primary_ar else ""
                youth_entry = build_synthesized_youth_dict(matched_nat, primary_ar, youth_en, scraped_alias=scraped_alias)
                team_translations[name] = youth_entry
                team_translations[primary_ar] = youth_entry
                register_national_teams([youth_entry])
                new_translations_list.append((primary_ar, youth_en, scraped_alias, youth_entry["logo_url"], "national", youth_entry["code"]))
                logger.success(f"Translation: Created youth entry '{youth_en}' ('{primary_ar}') with alias '{scraped_alias}' linked to mother '{matched_nat.get('nameEn')}'.")
            else:
                canonical_en = matched_nat.get("nameEn", name_en)
                primary_ar = matched_nat.get("primary_arabic", "")
                aliases = matched_nat.get("arabic_aliases", [])

                # Auto-learn Arabic alias into Column A of _cache_national_teams
                if name != primary_ar and name not in aliases:
                    orig_cell = matched_nat.get("original_aliases_cell", "")
                    new_val = f"{orig_cell} | {name}" if orig_cell else name
                    matched_nat["original_aliases_cell"] = new_val
                    matched_nat.setdefault("arabic_aliases", []).append(name)
                    register_national_teams([matched_nat])
                    row_num = matched_nat.get("row_num")
                    sheet_name = matched_nat.get("sheet_name")
                    if row_num and sheet_name == "_cache_national_teams":
                        alias_updates.append((row_num, "_cache_national_teams", 1, new_val))

                team_translations[name] = matched_nat
                logger.success(f"Translation: Auto-linked national Arabic alias '{name}' -> '{canonical_en}' in _cache_national_teams.")
        else:
            logger.warning(f"Translation: Unresolved national team '{name}' playing against '{opponent}'. Adding review row to _cache_national_teams.")
            review_entry = {
                "nameEn": name_en if name_en and not is_unknown_team(name_en) else "Unknown",
                "code": "",
                "logo_url": "",
                "sofascore_code": "",
                "type": "national",
                "primary_arabic": name,
                "arabic_aliases": [],
                "canonical_synonyms": [],
                "original_aliases_cell": ""
            }
            team_translations[name] = review_entry
            new_translations_list.append((name, review_entry["nameEn"], "", "", "national"))
