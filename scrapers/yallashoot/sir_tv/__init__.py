from . import channels

SITE_SLUG = "sir-tv"


_SIR_TV_DOMAIN_KEYWORDS = (
    "sir-tv",
    "sirtv",
    "siir-tv",
    "siirtv",
    "siiir-tv",
    "siiiir-tv",
    "sirftv",
    "ssirtv",
    "sirapp",
    "tv-sir",
    "tv-siir",
    "tvsir",
    "yasirtv",
    "yassirtv",
    "hes-goals",
    "hes-goal",
    "korat.",
    "korafor.",
    "okora.",
)


def can_handle_url(url: str) -> bool:
    """Pre-flight check: determines whether a URL belongs to the Sir-TV / YasirTV domain family."""
    lower_u = url.lower()
    return any(k in lower_u for k in _SIR_TV_DOMAIN_KEYWORDS)


__all__ = ["SITE_SLUG", "can_handle_url", "channels"]

