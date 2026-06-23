from __future__ import annotations
"""Procesamiento de marcadores de calificacion y tracking de leads."""
import logging
import re

from app import config, db

log = logging.getLogger("leads")

_ACTION_MARKERS = ("[[ACTION_LINK]]", "[[AGENDA_LINK]]")
_DISQUALIFY_RE = re.compile(r"\[\[DESCALIFICADO(?::\s*([^\]]+))?\]\]", re.IGNORECASE)
_INVALID_NAME_RE = re.compile(
    r"\b(quien|quien toma|toma|decision|decisi[oó]n|due[nñ]o|socio|negocio|"
    r"empresa|encargado|responsable|yo|nosotros|equipo|"
    r"si|sí|no|claro|ok|okay|vale|listo|bien|va|perfecto|correcto|entendido|bueno|as[ií])\b",
    re.IGNORECASE,
)


def _joined_user_history(history: list[dict]) -> str:
    return "\n".join(m["content"] for m in history if m.get("role") == "user")


def _extract_nombre(history: list[dict]) -> str | None:
    """Heuristica conservadora: solo acepta respuestas claramente dadas como nombre."""
    joined = _joined_user_history(history)
    patterns = [
        r"(?:me\s+llamo|mi\s+nombre\s+es)\s+([a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+){0,2})",
        r"(?:soy|yo\s+soy)\s+([a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+){0,1})(?:[,.!]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, joined, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if not _INVALID_NAME_RE.search(candidate) and 2 <= len(candidate) <= 45:
                return candidate.title()

    # Nuevo: Extraer si el asistente pidió el nombre y el siguiente mensaje del usuario
    # empieza directamente con un nombre compuesto (ej: "Miguel Gonzalez y soy...")
    _ASKED_NAME_RE = re.compile(
        r"\b(nombre completo|dime tu nombre|tu nombre|a nombre de qui[eé]n|nombre)\b",
        re.IGNORECASE,
    )
    previous_assistant_asked_name = False
    for item in history:
        role = item.get("role")
        content = item.get("content", "")
        if role == "assistant":
            previous_assistant_asked_name = bool(_ASKED_NAME_RE.search(content))
        elif role == "user" and previous_assistant_asked_name:
            content_clean = content.strip()
            start_match = re.match(r"^([a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+){1,2})", content_clean)
            if start_match:
                candidate = start_match.group(1).strip()
                stop = re.search(r"\b(y|de|soy|tengo|con)\b", candidate, re.IGNORECASE)
                if stop:
                    candidate = candidate[:stop.start()].strip()
                
                # Eliminar palabras de respuesta o confirmación al inicio
                while True:
                    new_candidate = re.sub(r"^(?:si|sí|no|claro|ok|okay|vale|bien|perfecto|bueno)\b\s*,?\s*", "", candidate, flags=re.IGNORECASE)
                    if new_candidate == candidate:
                        break
                    candidate = new_candidate

                if not _INVALID_NAME_RE.search(candidate) and len(candidate) >= 2:
                    return candidate.title()
            previous_assistant_asked_name = False
    return None


def _extract_negocio(history: list[dict]) -> str | None:
    """Heuristica simple: busca menciones del tipo de negocio o empresa."""
    joined = _joined_user_history(history)
    patterns = [
        r"(?:mi\s+empresa\s+se\s+llama|mi\s+negocio\s+se\s+llama|la\s+empresa\s+se\s+llama)\s+(.{2,60}?)(?:\.|,|$)",
        r"(?:tengo|manejo|mi\s+negocio\s+(?:es|se\s+llama))\s+(.{5,60}?)(?:\.|,|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, joined, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _replace_action_markers(reply: str) -> tuple[str, bool]:
    found = any(marker in reply for marker in _ACTION_MARKERS)
    clean = reply
    for marker in _ACTION_MARKERS:
        clean = clean.replace(marker, config.QUALIFIED_CTA_URL or "")
    return clean.strip(), found


async def process_reply(
    wa_id: str,
    reply: str,
    history: list[dict],
    bot_id: int | None = None,
) -> str:
    """
    Detecta marcadores en la respuesta del modelo, actualiza el lead en DB
    y devuelve la respuesta limpia lista para enviar al usuario.
    """
    nombre = _extract_nombre(history)
    negocio = _extract_negocio(history)

    clean_reply, offered_action = _replace_action_markers(reply)

    lead_fields = {}
    if nombre is not None:
        lead_fields["nombre"] = nombre
    if negocio is not None:
        lead_fields["negocio"] = negocio

    if offered_action:
        await db.upsert_lead(
            wa_id,
            bot_id=bot_id,
            qualification_status="calificado",
            action_link_sent=True,
            **lead_fields
        )
        log.info("Lead CALIFICADO: wa_id=%s negocio=%s", wa_id, negocio)
        return clean_reply

    match = _DISQUALIFY_RE.search(reply)
    if match:
        reason = (match.group(1) or "sin especificar").strip()
        clean_reply = _DISQUALIFY_RE.sub("", reply).strip()
        await db.upsert_lead(
            wa_id,
            bot_id=bot_id,
            qualification_status="descalificado",
            disqualify_reason=reason,
            **lead_fields
        )
        log.info("Lead DESCALIFICADO: wa_id=%s motivo=%s", wa_id, reason)
        return clean_reply

    await db.upsert_lead(
        wa_id,
        bot_id=bot_id,
        qualification_status="en_progreso",
        **lead_fields
    )
    return reply
