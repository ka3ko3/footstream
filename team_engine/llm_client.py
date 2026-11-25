# ---------------------------------------------------------------------------
# Team Engine: LLM Gateway & OpenRouter Client
# Handles batch translation API requests, model fallbacks, and resilient JSON parsing.
# ---------------------------------------------------------------------------

import os
import json
import requests
import logger

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_TIMEOUT = int(os.environ.get("OPENROUTER_TIMEOUT", 10))


def _clean_llm_json(content: str) -> str:
    """Strips markdown fences from LLM JSON response content."""
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content


def _call_openrouter_model(model: str, payload: dict, headers: dict) -> dict | None:
    """Executes a single OpenRouter model request and parses response JSON."""
    try:
        timeout = int(os.environ.get("OPENROUTER_TIMEOUT", OPENROUTER_TIMEOUT))
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"].get("content")
            if not content or not isinstance(content, str):
                logger.warning(f"Translation: Model {model} returned empty content.")
                return None
            logger.success(f"Translation: API call successful using model: {model}.")
            cleaned = _clean_llm_json(content)
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
            elif isinstance(parsed, list):
                res = {}
                for item in parsed:
                    if isinstance(item, dict):
                        res.update(item)
                return res
            return {"raw": str(parsed)}
        logger.error(f"Translation: Error with model {model}: HTTP {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Translation: Exception with model {model}: {e}")
    return None


def fetch_openrouter_mappings(
    unique_names: list,
    context_prompt: str | None = None,
    user_prompt: str | None = None
) -> dict:
    """
    Calls OpenRouter to batch translate Arabic team names to official English names.
    Supports custom context_prompt and custom user_prompt.
    """
    if not unique_names and not user_prompt:
        return {}

    default_system_prompt = (
        "Translate each Arabic football team or club name to its official English name.\n"
        "Output JSON format: {\"Arabic Name\": \"English Name\"}\n"
        "Example: {\"الأهلي\": \"Al Ahly\", \"ريال مدريد\": \"Real Madrid\"}\n"
        "Return raw JSON only."
    )

    system_prompt = context_prompt or default_system_prompt

    models = ["openrouter/free", "google/gemini-2.5-flash", "meta-llama/llama-3.1-8b-instruct"]
    api_key = os.environ.get("OPENROUTER_API_KEY", OPENROUTER_API_KEY)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/google/antigravity",
        "X-Title": "Google Antigravity"
    }

    user_content = user_prompt if user_prompt else json.dumps(unique_names, ensure_ascii=False)

    for model in models:
        logger.info(f"Translation: Requesting team details using model: {model}")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "response_format": {"type": "json_object"}
        }
        res = _call_openrouter_model(model, payload, headers)
        if res is not None:
            # Check if res is a non-empty dict containing at least one valid translation
            if isinstance(res, dict) and any(bool(v) for v in res.values()):
                return res
            logger.warning(f"Translation: Model {model} returned empty payload. Falling back to next model...")

    logger.warning("Translation: All models failed. Adding placeholder rows for human review.")
    return {}


def _extract_translation_name(llm_res: dict, arabic_name: str) -> str:
    """
    Resiliently extracts the English translation for an Arabic team name from LLM response.
    Handles flat strings, nested objects, case differences, and single-item dictionaries.
    """
    if not isinstance(llm_res, dict) or not arabic_name:
        return ""

    clean_ar = arabic_name.strip()

    # 1. Direct or stripped key match
    val = llm_res.get(clean_ar)
    if val is None:
        for k, v in llm_res.items():
            if str(k).strip() == clean_ar:
                val = v
                break

    if val is not None:
        if isinstance(val, str):
            return val.strip()
        elif isinstance(val, dict):
            for k in ("nameEn", "name", "english", "country", "team"):
                if val.get(k):
                    return str(val[k]).strip()

    # 2. Single-entry fallback: if LLM returned 1 key-value pair and 1 team was requested
    if len(llm_res) == 1:
        only_k, only_v = next(iter(llm_res.items()))
        if isinstance(only_v, str) and only_k.lower() in ("nameen", "name", "country", "team", "english"):
            return only_v.strip()
        if isinstance(only_v, str) and not any('\u0600' <= c <= '\u06FF' for c in only_v):
            return only_v.strip()
        if isinstance(only_v, dict):
            for k in ("nameEn", "name", "english", "country", "team"):
                if only_v.get(k):
                    return str(only_v[k]).strip()

    return ""


def is_unknown_team(name_en: str) -> bool:
    """Returns True if the AI response indicates it does not know this team."""
    if not name_en or not str(name_en).strip() or str(name_en).strip().lower() in ("unknown", "none"):
        return True
    if any('\u0600' <= c <= '\u06FF' for c in str(name_en)):
        return True
    return False
