from __future__ import annotations
"""Final cleanup and safety checks for WhatsApp replies."""
import re

_REINTRO_RE = re.compile(
    r"^\s*hola\s*,?\s*soy\s+(?:el\s+asistente\s+integrado\s+de\s+)?asistto(?:\s+de\s+humanio)?[.!:,]?\s*",
    re.IGNORECASE,
)
_MISSING_SPACE_AFTER_COMMA_RE = re.compile(r",(?=\S)")
_GREETING_RE = re.compile(
    r"^(?:si,?\s*)?(?:hola|buenos dias|buenos días|buenas tardes|buenas noches|hey|hello)[!.\s]*$",
    re.IGNORECASE,
)
_BROKEN_PATTERNS = (
    re.compile(r"\bAutoObetendr", re.IGNORECASE),
    re.compile(r"\bessays?-offer\b", re.IGNORECASE),
    re.compile(r"\bsharepoint\b", re.IGNORECASE),
    re.compile(r"\bn prodotto\b", re.IGNORECASE),
    re.compile(r"[\uFFFC\uFFFD]"),
)

_FALLBACK_REPLY = (
    "Asistto conecta el WhatsApp de tu negocio con un asistente de IA entrenado con tu información.\n"
    "El asistente responde dudas, captura prospectos y puede ayudar a agendar citas cuando la integración está activa.\n"
    "¿Qué tipo de negocio quieres automatizar?"
)


def _is_emoji(ch: str) -> bool:
    o = ord(ch)
    # Check common emoji and symbol blocks:
    # - Miscellaneous Symbols (2600-26FF)
    # - Dingbats (2700-27BF)
    # - Miscellaneous Symbols and Arrows (2B00-2BFF)
    # - Supplemental Arrows-B (2900-297F)
    # - Emoticons (1F600-1F64F)
    # - Miscellaneous Symbols and Pictographs (1F300-1F5FF)
    # - Transport and Map Symbols (1F680-1F6FF)
    # - Supplemental Symbols and Pictographs (1F900-1F9FF)
    # - Symbols and Pictographs Extended-A (1FA70-1FAFF)
    if (0x2600 <= o <= 0x27BF) or (0x2B00 <= o <= 0x2BFF) or (0x1F000 <= o <= 0x1FAFF):
        return True
    return False


def looks_broken(reply: str) -> bool:
    clean = reply or ""
    if any(pattern.search(clean) for pattern in _BROKEN_PATTERNS):
        return True
    if clean.endswith((",", ":", ";")):
        return True
    words = clean.split()
    if len(words) > 10:
        non_ascii_symbols = sum(1 for ch in clean if ord(ch) > 10000 and not _is_emoji(ch))
        if non_ascii_symbols >= 2:
            return True
    return False


_REASONING_INDICATORS = [
    # English patterns
    r"^\s*(?:we|i)\s+(?:need|must|should|can|will|have|already|am|would|do)\b",
    r"^\s*the\s+(?:user|customer|client|bot|agent|conversation|prompt)\s+(?:says|asked|wants|is|requested|asks|has|should|needs|will|tells|corrects)\b",
    r"^\s*(?:prompt|rule|instruction|guideline)\s+(?:says|asked|wants|is|requested|asks|has|should|needs|will|tells|corrects)\b",
    r"^\s*according\s+to\s+(?:the\s+)?rules\b",
    r"^\s*this\s+is\s+a\s+(?:request|greeting|case|message|follow-up)\b",
    r"^\s*thus\s+(?:we|i)\b",
    r"^\s*therefore\b",
    r"^\s*possibly\s+(?:we|i)\b",
    r"^\s*but\s+(?:we|i|there)\b",
    r"^\s*so\s+(?:we|i)\b",
    r"^\s*let's\s+(?:analyze|check|respond|say|keep|see|draft|write)\b",
    r"^\s*drafting\s+(?:a\s+)?(?:response|reply)\b",
    r"^\s*sure!?\s*,?\s*(?:here\s+is|here's)\b",
    r"^\s*(?:i\s+will|i'll)\s+(?:respond|reply|write|say)\b",
    r"^\s*(?:response|reply)\s*:\s*",
    r"^\s*answering\s+the\s+user\b",
    r"^\s*here\s+is\s+a\s+draft\b",
    r"^\s*the\s+conversation\b",
    r"^\s*in\s+this\s+case\b",
    r"^\s*they\s+(?:want|asked|said|are|need|asked)\b",
    r"^\s*(?:thought|reasoning|analysis|thinking\s+process)\s*:\s*",
    r"^\s*since\s+they\b",
    r"^\s*my\s+response\b",
    r"^\s*let\s+me\s+check\b",
    # Spanish patterns
    r"^\s*(?:necesitamos|debemos|tengo\s+que|voy\s+a)\s+(?:responder|preguntar|analizar|saludar)\b",
    r"^\s*el\s+(?:usuario|cliente)\s+(?:nos\s+)?(?:está\s+)?(?:saludando|preguntando|diciendo|pidiendo|saluda|dice|quiere|pregunta|pide|necesita|escribe)\b",
    r"^\s*según\s+(?:las\s+reglas|las\s+instrucciones|el\s+contexto)\b",
    r"^\s*mi\s+respuesta\s+debe\b",
    r"^\s*(?:pensamiento|razonamiento|análisis|proceso\s+de\s+pensamiento)\s*:\s*",
    r"^\s*(?:aquí\s+está\s+mi\s+respuesta|aquí\s+tienes\s+la\s+respuesta)\b",
    r"^\s*(?:redactando\s+respuesta|escribiendo\s+respuesta)\b",
]

_REASONING_REGEX = re.compile("|".join(_REASONING_INDICATORS), re.IGNORECASE)

_QUOTED_REASONING_RE = re.compile(
    r"(?:respond|say|reply|write|answer|send|responder|decir|enviar|escribir)"
    r"(?:\s+with|\s+to\s+the\s+user|\s+con|\s+al\s+usuario)?\s*[:,-]?\s*"
    r"[\"'“]([^\n\"'“”]+)[\"'“”]?\s*$",
    re.IGNORECASE
)

# Helper to detect if a line looks like English reasoning
_ENGLISH_DETECT_RE = re.compile(
    r"\b(?:the|and|that|have|for|not|with|you|this|but|his|from|they|she|him|her|its|our|their|will|would|about|there|their|what|out|about|who|get|which|go|guidelines|guideline|rules|let|lets|let's|draft|drafts|drafting|response|responses|reply|replies|here|is|are|hello|writing|saying|telling|need|must|should|can|could|already|done|been|was|were|am|are|of|on|at|by|an|as|first|i|my|we|our|us|your|shouldn't|don't|didn't|doesn't|won't|can't|couldn't|isn't|aren't|wasn't|weren't|haven't|hasn't|hadn't|prompt|prompts|says|say|ask|asks|asking|option|options|list|listing|rule|rules|guideline|guidelines|instruction|instructions|context)\b",
    re.IGNORECASE
)


def _strip_reasoning(clean: str) -> str:
    # Quoted extraction for reasoning endings in English or Spanish
    # Matches patterns like: We can respond "¡Hola! or responder: "¡Hola!"
    quote_match = _QUOTED_REASONING_RE.search(clean)
    if quote_match:
        return quote_match.group(1).strip()

    # Pre-clean inline reasoning prefixes at the very start of the text
    clean = re.sub(
        r"^\s*(?:prompt|rule|instruction|guideline|system|let's|draft|reasoning|thinking|thought|analysis)\s+(?:says|asked|wants|is|requested|asks|has|should|needs|will|tells|corrects|draft|write|think|process|analysis)?\b[^.!?\n]*[.!?]\s*",
        "",
        clean,
        flags=re.IGNORECASE
    )

    # Otherwise, split by lines and filter out reasoning lines from the beginning
    lines = clean.split("\n")
    cleaned_lines = []
    in_reasoning = True
    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            if in_reasoning:
                continue
            else:
                cleaned_lines.append(line)
                continue

        # If we are in reasoning mode, check indicators or if the line has heavy English vocabulary
        if in_reasoning:
            if _REASONING_REGEX.search(stripped_line):
                continue
            
            # Since the user language is Spanish, if the line contains typical English words,
            # we treat it as reasoning and skip it.
            english_words = len(_ENGLISH_DETECT_RE.findall(stripped_line))
            if english_words >= 3 or (english_words >= 1 and not re.search(r"[áéíóúüñ¿¡]", stripped_line)):
                continue

        in_reasoning = False
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def polish(reply: str, history: list[dict], user_text: str | None = None, bot_name: str = "Asistto") -> str:
    clean = (reply or "").strip()

    # Remove safety/moderation headers generated by certain gateways/models
    # e.g., "User Safety: safe Response Safety: safe"
    clean = re.sub(r"\buser\s+safety:\s*\w+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bresponse\s+safety:\s*\w+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bsafety:\s*\w+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = clean.strip()

    clean = _strip_reasoning(clean)

    has_prior_assistant = any(item.get("role") == "assistant" for item in history)

    if not clean.strip() or looks_broken(clean):
        if has_prior_assistant:
            clean = "Entendido. Si tienes alguna otra duda o deseas continuar más adelante, escríbeme y con gusto lo revisamos."
        elif bot_name == "Asistto":
            clean = _FALLBACK_REPLY
        else:
            clean = (
                "Conectamos el WhatsApp de tu negocio con un asistente de IA entrenado con tu información.\n"
                "El asistente responde dudas, captura prospectos y puede ayudar a agendar citas cuando la integración está activa.\n"
                "¿Qué tipo de negocio tienes?"
            )

    clean = _MISSING_SPACE_AFTER_COMMA_RE.sub(", ", clean)

    current_message_is_greeting = bool(_GREETING_RE.match((user_text or "").strip()))
    
    # Check standard Asistto intro removal
    if has_prior_assistant and not current_message_is_greeting and _REINTRO_RE.match(clean):
        clean = _REINTRO_RE.sub("", clean, count=1).lstrip()
        clean = clean[:1].upper() + clean[1:] if clean else ""
        
    # Check dynamic bot name intro removal
    if bot_name and bot_name != "Asistto":
        intro_pat = re.compile(
            rf"^\s*hola\s*,?\s*soy\s+(?:el\s+asistente\s+integrado\s+de\s+)?{re.escape(bot_name)}[.!:,]?\s*",
            re.IGNORECASE,
        )
        if has_prior_assistant and not current_message_is_greeting and intro_pat.match(clean):
            clean = intro_pat.sub("", clean, count=1).lstrip()
            clean = clean[:1].upper() + clean[1:] if clean else ""

    if clean.endswith(","):
        clean = clean[:-1].rstrip() + "."
    return clean
