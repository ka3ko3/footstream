#!/usr/bin/env python3
"""
=============================================================================
TiviGoal Pipeline Test Simulator
=============================================================================
Runs the 100% real TiviGoal automation pipeline against synthetic mock match
fixtures without modifying a single line of production code.

Usage:
    python Pipeline/simulator/test_pipeline.py
    python Pipeline/simulator/test_pipeline.py 02_club_vs_national.json
=============================================================================
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from unittest.mock import patch
from contextlib import nullcontext

# Ensure Pipeline directory is on sys.path
SIMULATOR_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(SIMULATOR_DIR)
SCENARIOS_DIR = os.path.join(SIMULATOR_DIR, "scenarios")

if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

import logger
import utils
utils.load_env()

import sheets_client
import channels_engine
import scraper_engine
import run_pipeline


# ---------------------------------------------------------------------------
# Scenario Discovery
# ---------------------------------------------------------------------------

def list_scenarios() -> list[dict]:
    """Scans simulator/scenarios/ directory and returns sorted metadata for all scenarios."""
    if not os.path.exists(SCENARIOS_DIR):
        os.makedirs(SCENARIOS_DIR, exist_ok=True)
        return []

    files = [f for f in os.listdir(SCENARIOS_DIR) if f.endswith(".json")]
    files.sort()

    scenarios = []
    for f in files:
        full_path = os.path.join(SCENARIOS_DIR, f)
        try:
            with open(full_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            scenarios.append({
                "filename": f,
                "path": full_path,
                "name": data.get("scenario_name") or f.replace(".json", "").replace("_", " ").title(),
                "description": data.get("description", ""),
                "match_count": len(data.get("matches", [])),
                "data": data,
            })
        except Exception as e:
            scenarios.append({
                "filename": f,
                "path": full_path,
                "name": f,
                "description": f"Failed to parse JSON: {e}",
                "match_count": 0,
                "data": None,
            })
    return scenarios


# ---------------------------------------------------------------------------
# Dynamic Time & Date Preprocessor
# ---------------------------------------------------------------------------

def resolve_dynamic_datetime(date_str: str, time_str: str, source_tz=None) -> tuple[str, str]:
    """
    Substitutes relative tokens like TODAY, TOMORROW, NOW, NOW-30M, NOW+2H
    with dynamic timestamps relative to the local default timezone.
    Ensures mock fixtures never expire due to the 24-hour lookahead or TTL filter.
    """
    tz = utils.resolve_timezone(source_tz or utils.get_default_timezone())
    now = datetime.now(tz)

    date_out = str(date_str or "").strip()
    time_out = str(time_str or "").strip()

    # Process date_str tokens
    d_upper = date_out.upper()
    if d_upper in ("TODAY", ""):
        date_out = now.strftime("%Y-%m-%d")
    elif d_upper == "TOMORROW":
        date_out = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    elif d_upper == "YESTERDAY":
        date_out = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    elif d_upper.startswith("TODAY+"):
        try:
            days = int(d_upper.split("+")[1])
            date_out = (now + timedelta(days=days)).strftime("%Y-%m-%d")
        except Exception:
            pass
    elif d_upper.startswith("TODAY-"):
        try:
            days = int(d_upper.split("-")[1])
            date_out = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        except Exception:
            pass

    # Process time_str tokens
    t_upper = time_out.upper()
    if t_upper in ("NOW", ""):
        time_out = now.strftime("%H:%M")
    elif re.match(r"^NOW([+-])(\d+)([MH])$", t_upper):
        m = re.match(r"^NOW([+-])(\d+)([MH])$", t_upper)
        sign = 1 if m.group(1) == "+" else -1
        amount = int(m.group(2))
        unit = m.group(3)
        delta = timedelta(hours=amount) if unit == "H" else timedelta(minutes=amount)
        calculated_time = now + (sign * delta)
        time_out = calculated_time.strftime("%H:%M")
        # If date was TODAY or default, sync date with calculated_time to handle midnight rollover
        if d_upper in ("TODAY", ""):
            date_out = calculated_time.strftime("%Y-%m-%d")

    return date_out, time_out


def prepare_scenario_matches(raw_matches: list) -> tuple[list, dict]:
    """
    Preprocesses matches from scenario JSON:
    1. Resolves relative timestamps.
    2. Builds a mapping of match_url/event -> mock channels.
    """
    processed = []
    channels_map = {}

    for idx, raw in enumerate(raw_matches):
        item = dict(raw)
        s_tz = item.get("source_tz") or "Africa/Casablanca"
        d_str, t_str = resolve_dynamic_datetime(item.get("date_str", "TODAY"), item.get("time_str", "NOW"), s_tz)
        item["date_str"] = d_str
        item["time_str"] = t_str
        item["source_tz"] = s_tz

        if not item.get("match_url"):
            item["match_url"] = f"https://mock-stream-source.test/match/{idx + 1}"

        # If scenario defines explicit channels, register them in our channel resolver map
        if "channels" in item:
            channels_map[item["match_url"]] = item["channels"]

        processed.append(item)

    return processed, channels_map


# ---------------------------------------------------------------------------
# Interactive Selection CLI
# ---------------------------------------------------------------------------

def select_scenario_interactive(scenarios: list[dict]) -> dict:
    """Displays a clean interactive menu for selecting among available scenarios."""
    logger.step_header("SIMULATOR", "TiviGoal Pipeline Test Simulator")
    print("Available Test Scenarios:")
    print()

    for idx, sc in enumerate(scenarios, start=1):
        num_str = f"[{idx}]"
        desc_str = f" - {sc['description']}" if sc['description'] else ""
        print(f"  {logger.COLOR_GREEN}{logger.COLOR_BOLD}{num_str:<5}{logger.COLOR_RESET} {logger.COLOR_BOLD}{sc['filename']:<30}{logger.COLOR_RESET}{desc_str}")

    print()
    while True:
        try:
            choice = input(f"{logger.COLOR_YELLOW}Select scenario to run [1-{len(scenarios)}]: {logger.COLOR_RESET}").strip()
            if not choice:
                print(f"\nPlease enter a number between 1 and {len(scenarios)}.\n")
                continue
            val = int(choice)
            if 1 <= val <= len(scenarios):
                return scenarios[val - 1]
            print(f"\nPlease enter a number between 1 and {len(scenarios)}.\n")
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(130)
        except ValueError:
            print(f"\nPlease enter a number between 1 and {len(scenarios)}.\n")


def resolve_scenario_from_arg(arg: str, scenarios: list[dict]) -> dict:
    """Resolves scenario by exact filename or direct file path."""
    clean_arg = os.path.basename(arg.strip())
    if not clean_arg.endswith(".json"):
        clean_arg = f"{clean_arg}.json"

    for sc in scenarios:
        if sc["filename"].lower() == clean_arg.lower():
            return sc

    # Direct file path
    if os.path.isfile(arg):
        with open(arg, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "filename": os.path.basename(arg),
            "path": os.path.abspath(arg),
            "name": data.get("scenario_name", os.path.basename(arg)),
            "description": data.get("description", ""),
            "match_count": len(data.get("matches", [])),
            "data": data,
        }

    return None


# ---------------------------------------------------------------------------
# Runner Entry Point
# ---------------------------------------------------------------------------

def run_simulation():
    scenarios = list_scenarios()
    if not scenarios:
        logger.error(f"No scenarios found in {SCENARIOS_DIR}.")
        sys.exit(1)

    selected_scenario = None
    if len(sys.argv) > 1:
        scenario_target = sys.argv[1]
        selected_scenario = resolve_scenario_from_arg(scenario_target, scenarios)
        if not selected_scenario:
            logger.error(f"Scenario '{scenario_target}' not found. Available scenarios:")
            for sc in scenarios:
                print(f"  - {sc['filename']}")
            sys.exit(1)
    else:
        selected_scenario = select_scenario_interactive(scenarios)

    data = selected_scenario["data"]
    if not data:
        logger.error(f"Invalid or empty scenario data in {selected_scenario['path']}.")
        sys.exit(1)

    raw_matches = data.get("matches", [])
    plugin_health = data.get("plugin_health", {})
    processed_matches, channels_map = prepare_scenario_matches(raw_matches)

    probe_channels = bool(data.get("probe_channels", False))

    # Define channel resolver interceptor
    orig_resolve_channels = channels_engine.resolve_match_channels

    def mock_resolve_channels(match_url, status_class, is_far_future, plugin_name, proxies=None, context=None):
        if not match_url or status_class == "finished" or is_far_future:
            return []

        if match_url in channels_map:
            raw_ch_list = channels_map[match_url]
            valid_channels = []
            for ch in raw_ch_list:
                item = dict(ch)
                if not item.get("type"):
                    item["type"] = "iframe"

                if probe_channels:
                    # 100% Real channel validation & Playwright sandbox probing
                    match_context = {
                        "match_name": (context or {}).get("match_name", ""),
                        "channel_name": item.get("name", ""),
                        "event_id": (context or {}).get("event_id", ""),
                        "blog_post_id": (context or {}).get("blog_post_id", ""),
                    }
                    if channels_engine.is_stream_playable(item, proxies=proxies, match_context=match_context):
                        valid_channels.append(item)
                else:
                    # Fast mock pass-through for synthetic offline tests
                    valid_channels.append(item)

            valid_channels.sort(key=lambda ch: (
                channels_engine.get_channel_priority(ch),
                int(ch.get("id", 999)) if str(ch.get("id", "")).isdigit() else 999,
            ))
            for i, ch in enumerate(valid_channels, start=1):
                ch["id"] = i
                ch["name"] = f"Live {i}"
            return valid_channels

        return orig_resolve_channels(match_url, status_class, is_far_future, plugin_name, proxies, context)

    is_live_test = bool(data.get("live_test", False))

    if not is_live_test:
        def dry_sync_data_step(client, spreadsheet_name, matches_cache, cloudflare_api_url, sync_token):
            active_matches_list = run_pipeline.assemble_matches_feed(matches_cache)
            channels_map = run_pipeline.assemble_channels_map(matches_cache)

            logger.info(f"Active matches formatted for Cloudflare feed ({len(active_matches_list)} matches):")
            run_pipeline.display_data_matches(active_matches_list)

            # Persist matches cache to the test Google Sheet
            sheets_client.save_matches_cache(client, matches_cache, spreadsheet_name)

            logger.success("Dry test finished.")
            return True

        sync_patch = patch("run_pipeline.sync_data_step", side_effect=dry_sync_data_step)
    else:
        sync_patch = nullcontext()

    def mock_fetch_and_parse_urls(urls_to_scrape: list) -> tuple[list, dict]:
        plugin_counts: dict[str, int] = {}
        for m in processed_matches:
            p_name = m.get("plugin") or "mock_source"
            plugin_counts[p_name] = plugin_counts.get(p_name, 0) + 1

        for p_name in plugin_health:
            plugin_counts.setdefault(p_name, 0)

        max_len = max((len(p) for p in plugin_counts.keys()), default=10)

        for p_name, count in plugin_counts.items():
            padded = p_name.ljust(max_len)
            is_healthy = plugin_health.get(p_name, True)

            if is_healthy:
                match_label = "match" if count == 1 else "matches"
                logger.info(f"Scraper: Fetching matches from: {padded}  :  {logger.COLOR_CYAN}➤{logger.COLOR_RESET}  Found {count} {match_label}.")
            else:
                logger.error(f"Scraper: Fetching matches from: {padded}  :  ❌  Failed: 504 Gateway Timeout")

        return processed_matches, plugin_health

    # Reset sys.argv for the underlying run_pipeline parser
    sys.argv = ["run_pipeline.py"]

    # Execute 100% real pipeline with patched scraper ingestion & dummy SCRAPER_URLS to bypass guard
    with patch.object(scraper_engine, "SCRAPER_URLS", [("https://mock-stream-source.test", None)]), \
         patch("scraper_engine._fetch_and_parse_urls", side_effect=mock_fetch_and_parse_urls), \
         patch("scraper_engine.resolve_match_channels", side_effect=mock_resolve_channels), \
         patch("channels_engine.resolve_match_channels", side_effect=mock_resolve_channels), \
         sync_patch:
        run_pipeline.main()


if __name__ == "__main__":
    print()
    run_simulation()
