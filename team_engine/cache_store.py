# ---------------------------------------------------------------------------
# Team Engine: Cache Store & Google Sheets Persistence
# Handles reading from and updating _cache_national_teams and _cache_clubs.
# Includes Safety Shield preventing accidental modifications to national flags/codes.
# ---------------------------------------------------------------------------

import re
import gspread
import logger
from sheets_client import open_spreadsheet
from utils import sanitize_sheet_image_url, get_spreadsheet_name
from normalization import (
    register_national_teams,
    set_canonical_synonyms,
)


def _parse_translation_sheet(
    sh,
    sheet_name: str,
    type_label: str,
    translations: dict,
    dynamic_synonyms: dict,
    national_teams_list: list = None
):
    """
    Loads a single cache worksheet and parses rows into translations dict.
    Supports 7-column schema for _cache_national_teams and 6-column schema for _cache_clubs.
    """
    try:
        worksheet = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="7" if type_label == "national" else "6")
        if type_label == "national":
            worksheet.append_row(["arabic_aliases", "primary_arabic_name", "primary_english_name", "canonical_synonyms", "code", "logo_url", "sofascore_code"])
        else:
            worksheet.append_row(["arabic_aliases", "primary_arabic_name", "primary_english_name", "canonical_synonyms", "logo_url", "sofascore_code"])
        return

    all_values = worksheet.get_all_values()
    if not all_values or len(all_values) <= 1:
        return

    headers = [h.strip().lower() for h in all_values[0]]
    rows = all_values[1:]
    header_map = {h: idx for idx, h in enumerate(headers)}

    for idx, row in enumerate(rows, start=2):
        padded_row = row + [""] * (max(len(headers), 7) - len(row))

        aliases_raw = padded_row[header_map.get("arabic_aliases", 0)].strip()
        primary_arabic = padded_row[header_map.get("primary_arabic_name", header_map.get("arabic_name", 1))].strip()

        # Fallback if primary_arabic is in aliases cell
        if not primary_arabic and aliases_raw:
            primary_arabic = [a.strip() for a in re.split(r'[|;\n,]', aliases_raw) if a.strip()][0]

        if not primary_arabic:
            continue

        arabic_aliases = [a.strip() for a in re.split(r'[|;\n,]', aliases_raw) if a.strip()]
        name_en = padded_row[header_map.get("primary_english_name", header_map.get("english_name", 2))].strip()
        synonyms_raw = padded_row[header_map["canonical_synonyms"]].strip() if "canonical_synonyms" in header_map else ""
        canonical_synonyms = [s.strip() for s in re.split(r'[|;\n,]', synonyms_raw) if s.strip()]

        if type_label == "national":
            code = padded_row[header_map["code"]].strip() if "code" in header_map else (padded_row[4].strip() if len(padded_row) > 4 else "")
            logo_url = padded_row[header_map["logo_url"]].strip() if "logo_url" in header_map else (padded_row[5].strip() if len(padded_row) > 5 else "")
            if code and not logo_url:
                logo_url = f"https://flagcdn.com/{code.lower()}.svg"
            sofascore_code = padded_row[header_map["sofascore_code"]].strip() if "sofascore_code" in header_map else (padded_row[6].strip() if len(padded_row) > 6 else "")
        else:
            code = ""
            logo_url = padded_row[header_map["logo_url"]].strip() if "logo_url" in header_map else (padded_row[4].strip() if len(padded_row) > 4 else "")
            sofascore_code = padded_row[header_map["sofascore_code"]].strip() if "sofascore_code" in header_map else (padded_row[5].strip() if len(padded_row) > 5 else "")

        # Empty string means "needs human review" — treat as Unknown so the script never uses bad data
        if not name_en:
            name_en = "Unknown"
            if type_label == "national":
                code = ""

        if type_label == "club" and name_en and name_en != "Unknown":
            for syn in canonical_synonyms:
                dynamic_synonyms[syn.lower()] = name_en

        entry = {
            "nameEn": name_en,
            "code": code,
            "logo_url": logo_url,
            "sofascore_code": sofascore_code,
            "type": type_label,
            "row_num": idx,
            "sheet_name": sheet_name,
            "primary_arabic": primary_arabic,
            "arabic_aliases": arabic_aliases,
            "canonical_synonyms": canonical_synonyms,
            "original_aliases_cell": aliases_raw
        }

        translations[primary_arabic] = entry
        if type_label == "national" and national_teams_list is not None:
            national_teams_list.append(entry)


def load_team_translations(client, spreadsheet_name: str = None) -> dict:
    """
    Fetches team translations from '_cache_national_teams' (7 cols) and '_cache_clubs' (6 cols).
    Primes the modular normalizer engine with national teams and dynamic club synonyms.
    """
    spreadsheet_name = (spreadsheet_name or get_spreadsheet_name()).strip()
    sh = open_spreadsheet(client, spreadsheet_name)
    translations = {}
    dynamic_synonyms = {}
    national_teams_list = []

    _parse_translation_sheet(sh, "_cache_national_teams", "national", translations, dynamic_synonyms, national_teams_list)
    _parse_translation_sheet(sh, "_cache_clubs", "club", translations, dynamic_synonyms)

    if national_teams_list:
        register_national_teams(national_teams_list)
    if dynamic_synonyms:
        set_canonical_synonyms(dynamic_synonyms)

    return translations


def update_team_aliases(client, alias_updates: list, spreadsheet_name: str = None):
    """
    Appends new aliases to Column A or updates logo URLs in Google Sheets using a single batch update.
    Safety Shield: Strictly prevents modifying logo_url, code, or other columns in _cache_national_teams.
    """
    if not alias_updates:
        return

    spreadsheet_name = (spreadsheet_name or get_spreadsheet_name()).strip()
    sh = open_spreadsheet(client, spreadsheet_name)
    by_sheet = {}
    for update in alias_updates:
        row_num, sheet_name = update[0], update[1]
        col_idx, new_val = (update[2], update[3]) if len(update) == 4 else (1, update[2])

        # Safety Shield: For _cache_national_teams, ONLY Column A (col_idx == 1) can ever be updated!
        if sheet_name == "_cache_national_teams" and col_idx != 1:
            logger.warning(f"Sheets: Blocked attempt to update protected column {col_idx} in '_cache_national_teams'")
            continue

        if col_idx == 5 and sheet_name != "_cache_national_teams":
            new_val = sanitize_sheet_image_url(new_val)

        by_sheet.setdefault(sheet_name, {})[(row_num, col_idx)] = new_val

    for sheet_name, updates in by_sheet.items():
        if not updates:
            continue
        try:
            worksheet = sh.worksheet(sheet_name)
        except Exception as e:
            logger.error(f"Sheets: Worksheet '{sheet_name}' not found: {e}")
            continue

        batch_data = []
        for (row_num, col_idx), new_val in updates.items():
            cell_a1 = gspread.utils.rowcol_to_a1(row_num, col_idx)
            batch_data.append({"range": cell_a1, "values": [[new_val]]})

        if batch_data:
            try:
                worksheet.batch_update(batch_data)
            except Exception as e:
                logger.error(f"Sheets: Failed batch updating '{sheet_name}': {e}")


def save_new_team_translations_separated(client, new_translations: list, spreadsheet_name: str = None):
    """
    Appends new translation rows to either '_cache_national_teams' (7 cols) or '_cache_clubs' (6 cols).
    For _cache_national_teams, only appends review placeholder rows with empty logo and code.
    """
    if not new_translations:
        return

    spreadsheet_name = (spreadsheet_name or get_spreadsheet_name()).strip()
    sh = open_spreadsheet(client, spreadsheet_name)

    # national rows: [arabic_aliases, primary_arabic_name, primary_english_name, canonical_synonyms, code, logo_url, sofascore_code]
    national_rows = []
    club_rows = []
    for t in new_translations:
        if t[4] == "national":
            alias_ar = t[2] if len(t) > 2 and t[2] else ""
            primary_ar = t[0]
            name_en = t[1]
            logo_url = t[3] if len(t) > 3 and t[3] else ""
            code = t[5] if len(t) > 5 and t[5] else ""
            national_rows.append([alias_ar, primary_ar, name_en, "", code, logo_url, ""])
        else:
            club_rows.append(["", t[0], t[1], "", sanitize_sheet_image_url(t[3]), ""])

    for sheet_name, rows, headers, cols in [
        ("_cache_national_teams", national_rows, ["arabic_aliases", "primary_arabic_name", "primary_english_name", "canonical_synonyms", "code", "logo_url", "sofascore_code"], "7"),
        ("_cache_clubs", club_rows, ["arabic_aliases", "primary_arabic_name", "primary_english_name", "canonical_synonyms", "logo_url", "sofascore_code"], "6")
    ]:
        if not rows:
            continue
        try:
            worksheet = sh.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=sheet_name, rows="1000", cols=cols)
            worksheet.append_row(headers)

        worksheet.append_rows(rows)
        logger.success(f"Sheets: Appended {len(rows)} new rows to '{sheet_name}'.")
