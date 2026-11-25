# Pipeline Test Simulator

Test the entire real TiviGoal automation pipeline with synthetic match data without modifying a single line of production code.

---

## Quick Start

### 1. Interactive Scenario Selector
Run without arguments to display an interactive menu of all available scenarios:
```bash
python Pipeline/simulator/test_pipeline.py
```

### 2. Direct Execution by Filename
Run a specific scenario directly:
```bash
python Pipeline/simulator/test_pipeline.py 01_full_lifecycle.json
python Pipeline/simulator/test_pipeline.py 02_club_vs_national.json
```

---


## How to Create a New Scenario

Simply create a new `.json` file inside `Pipeline/simulator/scenarios/`:

```json
{
  "description": "Explaining the edge case being tested.",
  "probe_channels": false,
  "live_test": false,
  "plugin_health": {
    "footyy": true,
    "yallashoot": true
  },
  "matches": [
    {
      "team1_name": "ريال مدريد",
      "team2_name": "برشلونة",
      "team1_orig_img": "https://img.sofascore.com/teams/real-madrid.png",
      "team2_orig_img": "https://img.sofascore.com/teams/barcelona.png",
      "date_str": "TODAY",
      "time_str": "NOW-30M",
      "source_tz": "Africa/Casablanca",
      "status_class": "live",
      "plugin": "footyy",
      "channels": [
        {
          "name": "BeIN Sports 1 HD",
          "server_name": "Server 1",
          "type": "iframe",
          "url": "https://stream-server1.test/live/embed1"
        }
      ]
    }
  ]
}
```

### Scenario Flags
- **`probe_channels`**: Set `true` to run real Playwright sandbox stream verification; `false` (default) passes mock streams instantly.
- **`live_test`**: Set `true` to write matches to Sheets and sync to Cloudflare; `false` (default) runs a safe dry run and skips remote writes.

### Dynamic Time Tokens
To ensure tests never expire due to the 24-hour lookahead or TTL filter:
- **`date_str`**: `"TODAY"`, `"TOMORROW"`, `"YESTERDAY"`, `"TODAY+2"`
- **`time_str`**: `"NOW"`, `"NOW-30M"` (30 min ago), `"NOW+15M"` (in 15 min), `"NOW+2H"` (in 2 hours)
