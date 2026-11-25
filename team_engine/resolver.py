# ---------------------------------------------------------------------------
# Team Engine: Master Teams Resolver
# Coordinates match context detection, zero-cost youth synthesis,
# national team resolution, club resolution, and Reverse English Catch.
# ---------------------------------------------------------------------------

import logger
from normalization import (
    is_national_team_en,
    extract_nation_category_ar,
    extract_nation_category_en,
    register_national_teams,
)
from .lookup import find_existing_translation, _find_matching_cached_team
from .llm_client import (
    fetch_openrouter_mappings,
    _extract_translation_name,
    is_unknown_team,
)
from .youth import (
    resolve_known_youth_teams,
    format_youth_category_names,
    build_synthesized_youth_dict,
)
from .nations_resolver import (
    resolve_national_teams,
    apply_mother_row_alias_golden_rule,
)
from .clubs_resolver import resolve_club_teams


def resolve_missing_teams(
    missing_team_names: list,
    team_translations: dict,
    matches_to_process: list
) -> tuple[list, list]:
    """
    Resolves Arabic team names not found in local cache with match-type isolation:
    - Layer 0 (Zero-Cost Youth Pre-Check): Synthesizes recognized mother youth teams instantly ($0 LLM).
    - Layer 1 (Constrained International): If an opponent in an international match missed lookup,
      prompts AI with national context and auto-learns the alias into _cache_national_teams Col A.
    - Layer 2 (Reverse English Catch): Promotes to international match ONLY if BOTH teams return 211 nations.
    - Club Resolution: Resolves clubs strictly against _cache_clubs, auto-learning aliases as before.
    """
    new_translations_list = []
    alias_updates = []

    if not missing_team_names:
        skip_msg = f"{logger.COLOR_DARK_GRAY}Skipping OpenRouter.{logger.COLOR_RESET}"
        logger.info(f"Translation: All teams found in translation cache. {skip_msg}")
        return new_translations_list, alias_updates

    # Layer 0: Zero-Cost Youth Teams Pre-Check (instant synthesis for recognized mother roots)
    missing_team_names = resolve_known_youth_teams(
        missing_team_names,
        team_translations,
        new_translations_list,
        alias_updates
    )
    if not missing_team_names:
        return new_translations_list, alias_updates

    # Group missing teams by match context
    intl_missing_map = {}  # missing_team -> known_opponent_name
    club_missing_set = set()

    for m in matches_to_process:
        t1 = m.get("team1_name", "").strip()
        t2 = m.get("team2_name", "").strip()
        if not t1 or not t2:
            continue

        t1_cached = team_translations.get(t1) or find_existing_translation(t1, team_translations)
        t2_cached = team_translations.get(t2) or find_existing_translation(t2, team_translations)

        t1_known_nat = bool(t1_cached and t1_cached.get("type") == "national" and t1_cached.get("nameEn") not in ("Unknown", "", None))
        t2_known_nat = bool(t2_cached and t2_cached.get("type") == "national" and t2_cached.get("nameEn") not in ("Unknown", "", None))

        if t1_known_nat and t2 in missing_team_names:
            intl_missing_map[t2] = t1_cached.get("nameEn") or t1
        elif t2_known_nat and t1 in missing_team_names:
            intl_missing_map[t1] = t2_cached.get("nameEn") or t2
        else:
            if t1 in missing_team_names:
                club_missing_set.add(t1)
            if t2 in missing_team_names:
                club_missing_set.add(t2)

    # -----------------------------------------------------------------------
    # Layer 1: Constrained National Resolution for known international matches
    # Exactly ONE batched request for all missing national teams!
    # -----------------------------------------------------------------------
    if intl_missing_map:
        resolve_national_teams(
            intl_missing_map,
            team_translations,
            new_translations_list,
            alias_updates
        )

    # -----------------------------------------------------------------------
    # Layer 2 & Club Resolution: For teams not part of an established intl match
    # Exactly ONE batched request for all remaining clubs!
    # -----------------------------------------------------------------------
    remaining_names = [n for n in missing_team_names if n not in intl_missing_map]
    if not remaining_names:
        return new_translations_list, alias_updates

    logger.info(f"Translation: Sending {len(remaining_names)} club/unclassified team(s) to OpenRouter...")
    club_system_prompt = (
        "Translate each Arabic football team or club name to its official English name.\n"
        "Output JSON format: {\"Arabic Name\": \"English Name\"}\n"
        "Example: {\"الأهلي\": \"Al Ahly\", \"ريال مدريد\": \"Real Madrid\"}\n"
        "Return raw JSON only."
    )
    llm_mappings = fetch_openrouter_mappings(remaining_names, context_prompt=club_system_prompt)

    # Check match pairs for Reverse English Catch
    promoted_to_intl = set()
    for m in matches_to_process:
        t1 = m.get("team1_name", "").strip()
        t2 = m.get("team2_name", "").strip()
        if t1 in remaining_names and t2 in remaining_names:
            t1_en = _extract_translation_name(llm_mappings, t1)
            t2_en = _extract_translation_name(llm_mappings, t2)
            if t1_en and t2_en and not is_unknown_team(t1_en) and not is_unknown_team(t2_en):
                if is_national_team_en(t1_en) and is_national_team_en(t2_en):
                    logger.success(f"Translation: Reverse English Catch promoted match '{t1}' ({t1_en}) vs '{t2}' ({t2_en}) to International!")
                    promoted_to_intl.add(t1)
                    promoted_to_intl.add(t2)

    standard_clubs = []
    for name in remaining_names:
        name_en = _extract_translation_name(llm_mappings, name) or "Unknown"

        # If promoted via Reverse English Catch:
        if name in promoted_to_intl:
            root_cand, cat_en, cat_ar = extract_nation_category_ar(name)
            mother_cand_en = name_en
            if cat_en and name_en:
                clean_mother_en, _ = extract_nation_category_en(name_en)
                if clean_mother_en:
                    mother_cand_en = clean_mother_en

            matched_nat = _find_matching_cached_team(mother_cand_en, team_translations, is_national=True)
            if matched_nat:
                if cat_en:
                    if root_cand:
                        apply_mother_row_alias_golden_rule(matched_nat, root_cand, alias_updates)
                    primary_ar, youth_en = format_youth_category_names(matched_nat, cat_en, cat_ar)
                    scraped_alias = name if name != primary_ar else ""
                    youth_entry = build_synthesized_youth_dict(matched_nat, primary_ar, youth_en, scraped_alias=scraped_alias)
                    team_translations[name] = youth_entry
                    team_translations[primary_ar] = youth_entry
                    register_national_teams([youth_entry])
                    new_translations_list.append((primary_ar, youth_en, scraped_alias, youth_entry["logo_url"], "national", youth_entry["code"]))
                    logger.success(f"Translation: Reverse English promoted and synthesized youth team '{youth_en}' ('{primary_ar}').")
                else:
                    canonical_en = matched_nat.get("nameEn", name_en)
                    primary_ar = matched_nat.get("primary_arabic", "")
                    aliases = matched_nat.get("arabic_aliases", [])
                    if name != primary_ar and name not in aliases:
                        orig_cell = matched_nat.get("original_aliases_cell", "")
                        new_val = f"{orig_cell} | {name}" if orig_cell else name
                        matched_nat["original_aliases_cell"] = new_val
                        matched_nat.setdefault("arabic_aliases", []).append(name)
                        register_national_teams([matched_nat])
                        row_num = matched_nat.get("row_num")
                        if row_num:
                            alias_updates.append((row_num, "_cache_national_teams", 1, new_val))
                    team_translations[name] = matched_nat
                    logger.success(f"Translation: Auto-linked national alias '{name}' -> '{canonical_en}' in _cache_national_teams.")
            else:
                logger.warning(f"Translation: Reverse English promoted '{name}' ({name_en}) but team not in cache. Adding review row to _cache_national_teams.")
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
            continue

        standard_clubs.append(name)

    # Standard Club Path:
    if standard_clubs:
        resolve_club_teams(
            standard_clubs,
            team_translations,
            matches_to_process,
            new_translations_list,
            alias_updates,
            llm_mappings=llm_mappings
        )

    return new_translations_list, alias_updates
