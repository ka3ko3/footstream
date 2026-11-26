import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
import logger
from utils import DEFAULT_HEADERS

# Domains that are never streaming iframes — always filter them out
_NON_STREAMING_DOMAINS = ["blogger.com", "google", "facebook", "twitter", "youtube", "cloudflare"]


def _extract_match_id(match_url: str) -> str:
    """Extracts numeric match ID from query string (?m= / ?match=) or trailing URL path."""
    m_match = re.search(r'[?&](?:m|match)=(\d+)', match_url)
    if m_match:
        return m_match.group(1)
    path = urlparse(match_url).path
    m_path = re.search(r'/(\d+)/?$', path)
    return m_path.group(1) if m_path else ""


def _extract_redirect_target_url(match_url: str, html_text: str, match_id: str) -> str:
    """Resolves Sir-TV DMCA redirect script (PLAYER_HOST + pid) into the intermediate player page URL."""
    if not match_id:
        return ""
    if "location.replace" not in html_text or ("PLAYER_HOST" not in html_text and "URLSearchParams" not in html_text):
        return ""

    m_host = re.search(r'PLAYER_HOST\s*=\s*[\'\"]([^\'\"]+)[\'\"]', html_text)
    host = m_host.group(1).strip() if m_host else "yassirtv.com"

    m_pid = re.search(r'[?&]p=([A-Za-z0-9]{1,32})', match_url)
    if m_pid:
        pid = m_pid.group(1)
    else:
        m_default_pid = re.search(r'\bvar\s+pid\s*=\s*[\'\"]([A-Za-z0-9]{1,32})[\'\"]', html_text)
        pid = m_default_pid.group(1) if m_default_pid else "87350"

    m_tpl = re.search(
        r"location\.replace\(\s*[\'\"]https?://[\'\"]\s*\+\s*PLAYER_HOST\s*\+\s*[\'\"](/[^\'\"]+)[\'\"]\s*\+\s*pid\s*\+\s*[\'\"]([^\'\"]+)[\'\"]",
        html_text,
    )
    if m_tpl:
        return f"https://{host}{m_tpl.group(1)}{pid}{m_tpl.group(2)}{match_id}"
    return f"https://{host}/hard/2908c7d4425d{pid}.html?match={match_id}"


def _extract_player_url_from_html(html_text: str, match_id: str = "", base_url: str = "") -> str:
    """Extracts the stream player URL from __playerSrc, player*.php patterns, or static <iframe> tags."""
    m_full = re.search(
        r'[\'\"](https?://[^\'\"]+/player[^/\'\"]*\.php\?[^\'\"]*match=\d+[^\'\"]*)[\'\"]',
        html_text,
    )
    if m_full:
        return m_full.group(1)

    m_base = re.search(
        r'[\'\"](https?://[^\'\"]+/player[^/\'\"]*\.php\?match=)[\'\"]',
        html_text,
    )
    if m_base and match_id:
        m_key = re.search(r'[?&]key=([A-Za-z0-9_-]+)', html_text)
        if m_key:
            return f"{m_base.group(1)}{match_id}&key={m_key.group(1)}"
        return f"{m_base.group(1)}{match_id}"

    m_psrc = re.search(r'__playerSrc\s*=\s*[\'\"](https?://[^\'\"]+)[\'\"]', html_text)
    if m_psrc and not m_psrc.group(1).endswith(("?match=", "&match=")):
        return m_psrc.group(1)

    soup = BeautifulSoup(html_text, "html.parser")
    for iframe in soup.find_all("iframe"):
        src = (iframe.get("src") or iframe.get("data-src") or "").strip()
        if not src:
            continue
        if any(domain in src.lower() for domain in _NON_STREAMING_DOMAINS):
            continue
        return urljoin(base_url, src) if base_url else src

    return ""


def extract_iframe(match_url: str, proxies: dict = None) -> str:
    """Extracts Sir-TV streaming iframe endpoint, resolving DMCA redirects and token handshakes."""
    try:
        resp = requests.get(match_url, headers=DEFAULT_HEADERS, timeout=12, proxies=proxies)
        if resp.status_code != 200:
            return ""

        match_id = _extract_match_id(match_url)
        target_url = _extract_redirect_target_url(match_url, resp.text, match_id)
        if target_url:
            r_target = requests.get(
                target_url,
                headers={**DEFAULT_HEADERS, "Referer": match_url},
                timeout=10,
                proxies=proxies,
            )
            if r_target.status_code == 200:
                player_url = _extract_player_url_from_html(
                    r_target.text, match_id=match_id, base_url=target_url
                )
                if player_url:
                    return player_url

        return _extract_player_url_from_html(resp.text, match_id=match_id, base_url=match_url)
    except Exception as e:
        logger.warning(f"Plugin (yallashoot/sir_tv): Failed to extract iframe from {match_url}: {e}")
    return ""


def extract_channels(match_url: str, proxies: dict = None) -> list[dict]:
    """Extracts stream channel list specifically for Sir-TV match URLs."""
    iframe_url = extract_iframe(match_url, proxies=proxies)
    if not iframe_url:
        return []
    return [{
        "id": 1,
        "name": "Live 1",
        "quality": "iFrame",
        "type": "iframe",
        "url": iframe_url,
        "sandbox": "allow-scripts allow-same-origin allow-presentation allow-forms",
    }]
