from __future__ import annotations
"""Final cleanup and safety checks for WhatsApp replies."""
import re
from decimal import Decimal, InvalidOperation

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

_KNOWLEDGE_MARKER = "--- knowledge_base ---"
_RAG_GROUNDING_MARKER = "--- rag_grounding_required ---"
_RUNTIME_MARKER = "--- contexto_runtime ---"
_UNGROUNDED_AMOUNT_REPLY = (
    "No pude validar ese monto contra la información oficial recuperada y, para no darte "
    "una cifra incorrecta, prefiero no indicarlo. Por favor dime qué concepto necesitas "
    "consultar y volveré a buscar el apartado exacto; también puedes confirmarlo con "
    "Capital Humano."
)
_NUMBER_TOKEN = r"\d(?:[\d.,\s]*\d)?"
_EXPLICIT_MONEY_RE = re.compile(
    rf"(?:\b(?:MXN|USD)\s*)?\$\s*(?P<prefix>{_NUMBER_TOKEN})"
    rf"|(?P<suffix>{_NUMBER_TOKEN})\s*(?:pesos?|MXN|USD|d[oó]lares?)\b",
    re.IGNORECASE,
)
_CONTEXTUAL_MONEY_RE = re.compile(
    rf"\b(?:hasta|tope(?:\s+(?:de|diario|máximo|maximo))?|"
    rf"l[ií]mite(?:\s+(?:de|diario))?|monto(?:\s+(?:de|máximo|maximo))?)"
    rf"\s*(?:es|son|de|:)?\s*\$?\s*(?P<amount>{_NUMBER_TOKEN})"
    rf"|(?P<daily>{_NUMBER_TOKEN})\s*(?:diarios?|por\s+d[ií]a)\b",
    re.IGNORECASE,
)
_MONEY_TOPIC_RE = re.compile(
    r"\b(?:gastar|gasto(?:s)?|vi[aá]ticos?|precio|costo|alimentos?|comidas?|"
    r"alimentaci[oó]n|hospedaje|hotel|alojamiento|traslados?|transportes?|taxi)\b",
    re.IGNORECASE,
)
_MONEY_CONCEPTS = {
    "food": re.compile(r"\b(?:alimentos?|comidas?|alimentaci[oó]n)\b", re.IGNORECASE),
    "lodging": re.compile(r"\b(?:hospedaje|hotel|alojamiento)\b", re.IGNORECASE),
    "transport": re.compile(r"\b(?:traslados?|transportes?|taxi)\b", re.IGNORECASE),
}


def _visible_reply(reply: str) -> str:
    """Return only the customer-visible XML payload when one is present."""
    clean = reply or ""
    lowered = clean.lower()
    start = lowered.find("<respuesta>")
    if start == -1:
        return clean
    start += len("<respuesta>")
    end = lowered.find("</respuesta>", start)
    return clean[start:] if end == -1 else clean[start:end]


def knowledge_evidence(system_prompt: str) -> str | None:
    """Extract retrieved tenant knowledge, excluding prompts and runtime context."""
    if _KNOWLEDGE_MARKER not in (system_prompt or ""):
        return None
    evidence = system_prompt.split(_KNOWLEDGE_MARKER, 1)[1]
    if _RUNTIME_MARKER in evidence:
        evidence = evidence.split(_RUNTIME_MARKER, 1)[0]
    return evidence.strip()


def _normalize_amount(raw: str) -> str | None:
    value = re.sub(r"\s+", "", raw or "")
    if not value:
        return None

    comma = value.rfind(",")
    dot = value.rfind(".")
    if comma >= 0 and dot >= 0:
        decimal_sep = "," if comma > dot else "."
        thousands_sep = "." if decimal_sep == "," else ","
        value = value.replace(thousands_sep, "")
        value = value.replace(decimal_sep, ".")
    else:
        separator = "," if comma >= 0 else "." if dot >= 0 else None
        if separator:
            groups = value.split(separator)
            if len(groups) > 2:
                if len(groups[-1]) <= 2:
                    value = "".join(groups[:-1]) + "." + groups[-1]
                else:
                    value = "".join(groups)
            elif len(groups[-1]) == 3:
                value = "".join(groups)
            else:
                value = ".".join(groups)

    try:
        normalized = Decimal(value).normalize()
    except InvalidOperation:
        return None
    return format(normalized, "f")


def _claim_segment(text: str, start: int, end: int) -> str:
    left = max(text.rfind(separator, 0, start) for separator in ("\n", ";", "!", "?"))
    right_candidates = [
        index for separator in ("\n", ";", "!", "?")
        if (index := text.find(separator, end)) >= 0
    ]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left + 1:right]


def _monetary_claims(text: str) -> list[tuple[str, str]]:
    claims: list[tuple[str, str]] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in (_EXPLICIT_MONEY_RE, _CONTEXTUAL_MONEY_RE):
        for match in pattern.finditer(text or ""):
            span = match.span()
            if span in seen_spans:
                continue
            segment = _claim_segment(text or "", *span)
            if pattern is _CONTEXTUAL_MONEY_RE and not _MONEY_TOPIC_RE.search(segment):
                continue
            raw = next((group for group in match.groups() if group is not None), None)
            normalized = _normalize_amount(raw or "")
            if normalized is not None:
                claims.append((normalized, segment))
                seen_spans.add(span)
    return claims


def monetary_amounts(text: str) -> set[str]:
    """Return normalized amounts that are expressed as monetary claims."""
    return {amount for amount, _segment in _monetary_claims(text)}


def _monetary_concept_pairs(text: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for amount, segment in _monetary_claims(text):
        for concept, pattern in _MONEY_CONCEPTS.items():
            if pattern.search(segment):
                pairs.add((concept, amount))
    return pairs


def unsupported_monetary_amounts(reply: str, system_prompt: str) -> set[str]:
    """Return customer-visible monetary claims absent from official evidence."""
    if _RAG_GROUNDING_MARKER not in (system_prompt or ""):
        return set()
    evidence = knowledge_evidence(system_prompt)
    if evidence is None:
        return set()
    visible = _visible_reply(reply)
    unsupported_amounts = monetary_amounts(visible) - monetary_amounts(evidence)
    unsupported_pairs = _monetary_concept_pairs(visible) - _monetary_concept_pairs(evidence)
    return unsupported_amounts | {amount for _concept, amount in unsupported_pairs}


def remove_ungrounded_assistant_history(
    history: list[dict],
    system_prompt: str,
) -> list[dict]:
    """Discard stale assistant amounts that conflict with current official evidence."""
    if _RAG_GROUNDING_MARKER not in (system_prompt or ""):
        return list(history)
    return [
        item
        for item in history
        if item.get("role") != "assistant"
        or not unsupported_monetary_amounts(str(item.get("content") or ""), system_prompt)
    ]


def enforce_grounded_monetary_claims(reply: str, system_prompt: str) -> tuple[str, set[str]]:
    """Fail closed when the model produces a monetary amount not in official evidence."""
    unsupported = unsupported_monetary_amounts(reply, system_prompt)
    if unsupported:
        return _UNGROUNDED_AMOUNT_REPLY, unsupported
    return reply, set()


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
    if clean.endswith((",", ";")):
        return True
        
    # Verificar paréntesis o corchetes sin cerrar (síntoma de corte)
    if clean.count("(") > clean.count(")"):
        return True
    if clean.count("[") > clean.count("]"):
        return True

    # Verificar markdown de negritas sin cerrar (síntoma de corte)
    if clean.count("*") % 2 != 0:
        last_star = clean.rfind("*")
        if last_star != -1 and (last_star == len(clean) - 1 or not clean[last_star + 1].isspace()):
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


def _strip_reasoning(clean: str, is_english_conversation: bool = False) -> str:
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
            
            # If conversation is not in English, lines containing English helper words are treated as reasoning
            if not is_english_conversation:
                english_words = len(_ENGLISH_DETECT_RE.findall(stripped_line))
                if english_words >= 3 or (english_words >= 1 and not re.search(r"[áéíóúüñ¿¡]", stripped_line)):
                    continue

        in_reasoning = False
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def polish(reply: str, history: list[dict], user_text: str | None = None, bot_name: str = "Asistto") -> str:
    clean = (reply or "").strip()
    has_xml_tag = False

    # Extraer contenido de la etiqueta XML <respuesta> si existe
    if "<respuesta>" in clean.lower():
        start_idx = clean.lower().find("<respuesta>") + len("<respuesta>")
        end_idx = clean.lower().find("</respuesta>", start_idx)
        if end_idx != -1:
            clean = clean[start_idx:end_idx].strip()
        else:
            clean = clean[start_idx:].strip()
        has_xml_tag = True

    # Remove safety/moderation headers generated by certain gateways/models
    # e.g., "User Safety: safe Response Safety: safe"
    clean = re.sub(r"\buser\s+safety:\s*\w+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bresponse\s+safety:\s*\w+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bsafety:\s*\w+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = clean.strip()

    # Detect if user message is predominantly in English
    ut = (user_text or "").strip()
    is_english = bool(ut and len(_ENGLISH_DETECT_RE.findall(ut)) >= 2 and not re.search(r"[áéíóúüñ¿¡]", ut))

    if not has_xml_tag:
        clean = _strip_reasoning(clean, is_english_conversation=is_english)


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
