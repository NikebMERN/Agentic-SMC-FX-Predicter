# utils/compliance.py
"""Compliance-safe wording for all user-facing prediction output."""

DISCLAIMER = (
    "Probabilistic market bias only — not financial advice. "
    "No guaranteed profit. Past patterns do not ensure future results."
)

FORBIDDEN_PHRASES = (
    "guaranteed",
    "guarantee",
    "sure signal",
    "100% win",
    "100 percent win",
    "sure profit",
    "cannot lose",
    "will go up",
    "will go down",
    "the market will",
)


def assert_safe_wording(text: str) -> str:
    """Scrub forbidden guarantee language from outgoing text."""
    if not text:
        return text
    out = text
    lower = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lower:
            out = out.replace(phrase, "[removed]")
            out = out.replace(phrase.title(), "[removed]")
    return out


def format_direction_label(action: str) -> str:
    """Human-readable direction label."""
    labels = {
        "BUY_BIAS": "BUY bias",
        "SELL_BIAS": "SELL bias",
        "NO_TRADE": "NO TRADE",
        "WAIT_FOR_CONFIRMATION": "WAIT — confirmation pending",
        "BUY": "BUY bias",
        "SELL": "SELL bias",
    }
    return labels.get(action, action)


def attach_disclaimer(payload: dict) -> dict:
    payload = dict(payload)
    payload["disclaimer"] = DISCLAIMER
    return payload
