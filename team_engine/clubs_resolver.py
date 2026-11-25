# ---------------------------------------------------------------------------
# Team Engine: Club Teams Resolver
# Translates clubs via OpenRouter, extracts crest logos, and auto-learns aliases into _cache_clubs.
# ---------------------------------------------------------------------------

import logger
from utils import sanitize_sheet_image_url
from .llm_client import (
    fetch_openrouter_mappings,
    _extract_translation_name,
    is_unknown_team,
)
from .lookup import _find_matching_cached_team


def resolve_scraped_club_logo(name: str, matches_to_process: list) -> str:
    """Extracts original scraped crest URL for a club from matches_to_process."""
    for m in matches_to_process:
        if m.get("team1_name") == name:
            return sanitize_sheet_image_url(m.get("team1_orig_img", ""))
        elif m.get("team2_name") == name:
            return sanitize_sheet_image_url(m.get("team2_orig_img", ""))
    return ""


def resolve_club_teams(
    remaining_names: list,
    team_translations: dict,
    matches_to_process: list,
    new_translations_list: list,
    alias_updates: list,
    llm_mappings: dict | None = None
):
    """
    Resolves missing club teams:
    Batches missing names to OpenRouter, attaches scraped crest logos,
    auto-links Arabic aliases into Column A of _cache_clubs,
    and appends review rows for unknown clubs.
    """
    if not remaining_names:
        return

    if llm_mappings is None:
        logger.info(f"Translation: Sending {len(remaining_names)} club/unclassified team(s) to OpenRouter...")
        club_system_prompt = (
            "Translate each Arabic football team or club name to its official English name.\n"
            "Output JSON format: {\"Arabic Name\": \"English Name\"}\n"
            "Example: {\"الأهلي\": \"Al Ahly\", \"ريال مدريد\": \"Real Madrid\"}\n"
            "Return raw JSON only."
        )
        llm_mappings = fetch_openrouter_mappings(remaining_names, context_prompt=club_system_prompt)

    for name in remaining_names:
        name_en = _extract_translation_name(llm_mappings, name) or "Unknown"
        club_logo = resolve_scraped_club_logo(name, matches_to_process)

        if is_unknown_team(name_en):
            logger.warning(f"Translation: Unknown club '{name}' — adding row with empty English name to _cache_clubs for human review.")
            team_translations[name] = {
                "nameEn": "Unknown",
                "code": "",
                "logo_url": club_logo,
                "sofascore_code": "",
                "type": "club",
                "primary_arabic": name,
                "arabic_aliases": [],
                "canonical_synonyms": [],
                "original_aliases_cell": ""
            }
            new_translations_list.append((name, "", "", club_logo, "club"))
            continue

        matched_cached_club = _find_matching_cached_team(name_en, team_translations, is_national=False)

        if matched_cached_club:
            canonical_en = matched_cached_club.get("nameEn", name_en)
            primary_ar = matched_cached_club.get("primary_arabic", "")
            aliases = matched_cached_club.get("arabic_aliases", [])

            if name != primary_ar and name not in aliases:
                orig_cell = matched_cached_club.get("original_aliases_cell", "")
                new_val = f"{orig_cell} | {name}" if orig_cell else name
                matched_cached_club["original_aliases_cell"] = new_val
                matched_cached_club.setdefault("arabic_aliases", []).append(name)
                row_num = matched_cached_club.get("row_num")
                sheet_name = matched_cached_club.get("sheet_name")
                if row_num and sheet_name == "_cache_clubs":
                    alias_updates.append((row_num, "_cache_clubs", 1, new_val))

            if club_logo and matched_cached_club.get("logo_url") != club_logo:
                matched_cached_club["logo_url"] = club_logo
                row_num = matched_cached_club.get("row_num")
                sheet_name = matched_cached_club.get("sheet_name")
                if row_num and sheet_name == "_cache_clubs":
                    alias_updates.append((row_num, "_cache_clubs", 5, club_logo))

            team_translations[name] = matched_cached_club
            logger.success(f"Translation: Auto-linked club Arabic alias '{name}' -> '{canonical_en}'.")
            continue

        # Brand new club team:
        team_translations[name] = {
            "nameEn": name_en,
            "code": "",
            "logo_url": club_logo,
            "sofascore_code": "",
            "type": "club",
            "primary_arabic": name,
            "arabic_aliases": [],
            "canonical_synonyms": [],
            "original_aliases_cell": ""
        }
        new_translations_list.append((name, name_en, "", club_logo, "club"))
