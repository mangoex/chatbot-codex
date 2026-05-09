"""Small final-pass cleanup before sending WhatsApp replies."""
import re

_REINTRO_RE = re.compile(
    r"^\s*hola\s*,?\s*soy\s+asistto(?:\s+de\s+humanio)?[.!:,]?\s*",
    re.IGNORECASE,
)
_MISSING_SPACE_AFTER_COMMA_RE = re.compile(r",(?=\S)")


def polish(reply: str, history: list[dict]) -> str:
    clean = (reply or "").strip()
    clean = _MISSING_SPACE_AFTER_COMMA_RE.sub(", ", clean)

    has_prior_assistant = any(item.get("role") == "assistant" for item in history)
    if has_prior_assistant and _REINTRO_RE.match(clean):
        clean = _REINTRO_RE.sub("", clean, count=1).lstrip()
        clean = clean[:1].upper() + clean[1:] if clean else ""

    if clean.endswith(","):
        clean = clean[:-1].rstrip() + "."
    return clean
