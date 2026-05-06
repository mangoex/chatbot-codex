"""Guardrails deterministicos para el flujo de agenda antes de llamar al modelo."""
import json
import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import calendar_client, config

_SCHEDULE_RE = re.compile(
    r"\b(?:quiero|quisiera|necesito|me interesa|puedo|podemos|ay[uú]dame|ayudame|vamos a|deseo|me gustar[ií]a)\b"
    r".{0,60}\b(?:agend\w*|cita|llamada|demo|reuni[oó]n)\b"
    r"|\b(?:agendar|agendemos|agenda una|programar una|reservar una)\b",
    re.IGNORECASE | re.DOTALL,
)
_CANCEL_RE = re.compile(
    r"\b(cancelar|cancela|cancele|cancelame|cancélame|no\s+(?:podre|podré|puedo|voy\s+a\s+poder)"
    r"(?:\s+\w+){0,4}\s+(?:asistir|ir)|no\s+asistire|no\s+asistiré)\b",
    re.IGNORECASE,
)
_RESCHEDULE_RE = re.compile(
    r"\b(cambiar|cambiarla|cambiarlo|mover|moverla|moverlo|reagendar|reagenda|"
    r"reprogramar|reprograma|modificar|modifica|pasar|posponer|no\s+voy\s+a\s+poder|"
    r"no\s+podre|no\s+podré)\b",
    re.IGNORECASE,
)
_THANKS_RE = re.compile(
    r"^(?:gracias|muchas gracias|ok gracias|perfecto gracias|listo gracias|va gracias)[!.\s]*$",
    re.IGNORECASE,
)
_SCHEDULED_CONFIRMATION_RE = re.compile(
    r"\b(?:quedo|quedó|agendada|agende|agendé)\b.*\b(?:llamada|cita)\b"
    r"|\blisto\b.*\b(?:agendada|agende|agendé)\b",
    re.IGNORECASE,
)
_RETRY_DATETIME_RE = re.compile(
    r"\b(ocupado|ocupada|otro dia|otro día|otra hora|dime otro|dime otra|lo reviso)\b",
    re.IGNORECASE,
)
_CANCEL_CLARIFY_RE = re.compile(
    r"\b(cita\s+activa|citas\s+activas|cita\s+que\s+quieres\s+cancelar|"
    r"dia\s+y\s+hora\s+de\s+la\s+cita|día\s+y\s+hora\s+de\s+la\s+cita|"
    r"no\s+encontre\s+una\s+cita|no\s+encontr[eé]\s+una\s+cita)\b",
    re.IGNORECASE,
)
_CANCEL_FOLLOWUP_RE = re.compile(
    r"\b(esa|esta|ésta|la|la\s+del|la\s+de|es\s+mia|es\s+mía|quiero\s+cancelar|"
    r"cancelarla|cancelar\s+esa|cancelar\s+esta)\b",
    re.IGNORECASE,
)
_GREETING_RE = re.compile(r"^(?:si,?\s*)?(?:hola|buenos dias|buenos días|buenas tardes|buenas noches|hey|hello)[!.\s]*$", re.IGNORECASE)
_NAME_RE = re.compile(
    r"\b(?:soy|me llamo|mi nombre es)\s+([a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+){0,3})",
    re.IGNORECASE,
)
_NAME_ONLY_RE = re.compile(
    r"^(?:si\s+claro,?\s*|sí\s+claro,?\s*|claro,?\s*)?"
    r"([a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+){1,3})\s*$",
    re.IGNORECASE,
)
_ASKED_NAME_RE = re.compile(r"\b(nombre completo|dime tu nombre|tu nombre)\b", re.IGNORECASE)
_ASKED_DATETIME_RE = re.compile(r"\b(d[ií]a y hora|fecha y hora|qu[eé] d[ií]a|qu[eé] hora)\b", re.IGNORECASE)
_RESCHEDULE_DATETIME_PROMPT_RE = re.compile(
    r"\b(sin problema|claro|ok|perfecto)\b.*\b(qu[eé] d[ií]a y hora|qu[eé] d[ií]a|qu[eé] hora|te queda)\b",
    re.IGNORECASE,
)
_SAME_TIME_RE = re.compile(r"\b(misma hora|la misma hora|igual hora|esa hora)\b", re.IGNORECASE)
_ASSISTANT_NAME_RE = re.compile(
    r"\b(?:gracias|listo),\s+([a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+){1,3})[.!?,]",
    re.IGNORECASE,
)
_SERVICE_SCHEDULING_RE = re.compile(
    r"^(?:agendar\s+llamadas|agendar\s+citas|agenda\s+de\s+citas|citas|llamadas|calendario|recordatorios)$",
    re.IGNORECASE,
)
_SERVICE_CONTEXT_RE = re.compile(
    r"\b(automatizar|captura de leads|consultas de servicios|agendar llamadas|tipo de negocio|servicio|como funciona|funciona)\b",
    re.IGNORECASE,
)
_ROLE_WORD_RE = re.compile(
    r"\b(consultor|consultora|asesor|asesora|dentista|doctor|doctora|medico|médico|abogado|abogada|arquitecto|arquitecta|contador|contadora|coach|agencia|empresa|negocio|clinica|clínica|restaurante|taller|inmobiliaria|servicios?|ia|marketing|ventas|finanzas|recursos|humanos|operaciones)\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(
    r"(?:\ba\s+las\b|\ba\s+la\b|\balas\b)?\s*\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b",
    re.IGNORECASE,
)
_EXPLICIT_TIME_RE = re.compile(
    r"(?:\ba\s+las\b|\ba\s+la\b|\balas\b)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?",
    re.IGNORECASE,
)
_DATE_NUM_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
_WEEKDAY_DAY_RE = re.compile(
    r"\b(?:lun|lunes|mar|martes|mie|mi[eé]rcoles|jue|jueves|vie|viernes|sab|s[aá]bado|dom|domingo)\.?\s+(\d{1,2})\b",
    re.IGNORECASE,
)
_DATE_MONTH_RE = re.compile(
    r"\b(\d{1,2})\s*(?:de\s*)?"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
    r"(?:\s*(?:de\s*)?(\d{4}))?\b",
    re.IGNORECASE,
)
_WEEKDAYS = {
    "lun": 0,
    "lunes": 0,
    "mar": 1,
    "martes": 1,
    "mie": 2,
    "miercoles": 2,
    "miércoles": 2,
    "jue": 3,
    "jueves": 3,
    "vie": 4,
    "viernes": 4,
    "sab": 5,
    "sabado": 5,
    "sábado": 5,
    "dom": 6,
    "domingo": 6,
}
_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _now() -> datetime:
    try:
        return datetime.now(ZoneInfo(config.GOOGLE_CALENDAR_TIMEZONE))
    except Exception:
        return datetime.now(ZoneInfo("America/Chihuahua"))


def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _history_text(history: list[dict], limit: int = 12) -> str:
    return "\n".join(item.get("content", "") for item in history[-limit:])


def _last_assistant_text(history: list[dict]) -> str:
    for item in reversed(history):
        if item.get("role") == "assistant":
            return item.get("content", "")
    return ""


def _last_user_date(history: list[dict]) -> datetime | None:
    for item in reversed(history[:-1]):
        if item.get("role") != "user":
            continue
        date = _extract_date(item.get("content", ""))
        if date:
            return date
    return None


def _last_user_start(history: list[dict]) -> datetime | None:
    for item in reversed(history[:-1]):
        if item.get("role") != "user":
            continue
        start = _extract_start(item.get("content", ""))
        if start:
            return start
    return None


def _is_cancel_clarification(history: list[dict]) -> bool:
    return bool(_CANCEL_CLARIFY_RE.search(_last_assistant_text(history)))


def _is_cancel_continuation(user_text: str, history: list[dict]) -> bool:
    if not _is_cancel_clarification(history):
        return False
    if _extract_start_with_context(user_text, history):
        return True
    return bool(_CANCEL_FOLLOWUP_RE.search(user_text))


def _is_reschedule_continuation(user_text: str, history: list[dict]) -> bool:
    last_assistant = _last_assistant_text(history)
    if _RESCHEDULE_DATETIME_PROMPT_RE.search(last_assistant):
        return True
    recent = _history_text(history, limit=8)
    if _RESCHEDULE_RE.search(recent) and (_extract_date(user_text) or _SAME_TIME_RE.search(user_text)):
        return True
    return False


def _looks_like_service_scheduling(user_text: str, history: list[dict]) -> bool:
    """Distingue seleccionar la habilidad de agendar llamadas de pedir una cita real."""
    text = user_text.strip(" .,!¡¿?")
    last_assistant = _last_assistant_text(history)
    if not _SERVICE_SCHEDULING_RE.match(text):
        return False
    return bool(_SERVICE_CONTEXT_RE.search(last_assistant))


def _in_schedule_flow(user_text: str, history: list[dict]) -> bool:
    """Agenda solo si el usuario la pide o si ya estamos pidiendo datos de cita."""
    last_assistant = _last_assistant_text(history)
    if _is_cancel_clarification(history):
        return False
    if _looks_like_service_scheduling(user_text, history):
        return False
    if _SCHEDULE_RE.search(user_text):
        return True
    if _is_reschedule_continuation(user_text, history):
        return True
    if _ASKED_NAME_RE.search(last_assistant) or _ASKED_DATETIME_RE.search(last_assistant):
        return True
    if _RETRY_DATETIME_RE.search(last_assistant) and _extract_time(user_text):
        return True
    return False


def _clean_name(name: str) -> str | None:
    clean = name.strip(" .,;:¡!¿?")
    stop = re.search(r"\b(doy|tengo|quiero|necesito|para|porque|con|y|de|mañana|manana|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\b", clean, re.IGNORECASE)
    if stop:
        clean = clean[: stop.start()].strip(" .,;:¡!¿?")
    if len(clean) < 2 or len(clean) > 60:
        return None
    if any(ch.isdigit() for ch in clean):
        return None
    if _ROLE_WORD_RE.search(clean):
        return None
    return clean.title()


def _direct_name(text: str) -> str | None:
    direct = _NAME_ONLY_RE.search(text.strip())
    if direct:
        return _clean_name(direct.group(1))
    return None


def _extract_name(text: str, history: list[dict]) -> str | None:
    current = _NAME_RE.search(text)
    if current:
        return _clean_name(current.group(1))

    if _ASKED_NAME_RE.search(_last_assistant_text(history)):
        direct = _direct_name(text)
        if direct:
            return direct

    # Buscar primero expresiones explicitas en mensajes recientes.
    for item in reversed(history[-20:]):
        if item.get("role") != "user":
            continue
        match = _NAME_RE.search(item.get("content", ""))
        if match:
            name = _clean_name(match.group(1))
            if name:
                return name

    # Reutilizar el nombre ya confirmado por el bot en este hilo.
    for item in reversed(history[-20:]):
        if item.get("role") != "assistant":
            continue
        match = _ASSISTANT_NAME_RE.search(item.get("content", ""))
        if match:
            name = _clean_name(match.group(1))
            if name:
                return name

    # Buscar pares: asistente pidio nombre -> siguiente mensaje de usuario fue el nombre.
    previous_assistant = ""
    for item in history[-20:]:
        role = item.get("role")
        content = item.get("content", "")
        if role == "assistant":
            previous_assistant = content
            continue
        if role == "user" and _ASKED_NAME_RE.search(previous_assistant):
            name = _direct_name(content)
            if name:
                return name

    return None


def _extract_date(text: str) -> datetime | None:
    base = _now()
    lower = _norm(text)

    if "pasadomanana" in lower or "pasado manana" in lower:
        return base + timedelta(days=2)
    if "manana" in lower:
        return base + timedelta(days=1)
    if "hoy" in lower:
        return base

    weekday_day_match = _WEEKDAY_DAY_RE.search(lower)
    if weekday_day_match:
        day = int(weekday_day_match.group(1))
        return base.replace(day=day)

    month_match = _DATE_MONTH_RE.search(lower)
    if month_match:
        day = int(month_match.group(1))
        month = _MONTHS[month_match.group(2)]
        year = int(month_match.group(3) or base.year)
        return base.replace(year=year, month=month, day=day)

    num_match = _DATE_NUM_RE.search(lower)
    if num_match:
        day = int(num_match.group(1))
        month = int(num_match.group(2))
        raw_year = num_match.group(3)
        year = base.year if not raw_year else int(raw_year)
        if year < 100:
            year += 2000
        return base.replace(year=year, month=month, day=day)

    for label, weekday in _WEEKDAYS.items():
        if label in lower:
            days = (weekday - base.weekday()) % 7
            if days == 0:
                days = 7
            return base + timedelta(days=days)

    return None


def _extract_time(text: str) -> tuple[int, int] | None:
    match = _EXPLICIT_TIME_RE.search(text)
    if not match:
        candidates = list(_TIME_RE.finditer(text))
        candidates = [m for m in candidates if m.group(2) or m.group(3)]
        match = candidates[-1] if candidates else None
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = (match.group(3) or "").lower().replace(".", "")
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    if not suffix and 1 <= hour <= 7:
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _extract_start(text: str) -> datetime | None:
    date = _extract_date(text)
    time = _extract_time(text)
    if not date or not time:
        return None
    return date.replace(hour=time[0], minute=time[1], second=0, microsecond=0)


def _extract_start_with_context(text: str, history: list[dict]) -> datetime | None:
    start = _extract_start(text)
    if start:
        return start

    date = _extract_date(text)
    if date and _SAME_TIME_RE.search(text):
        previous_start = _last_user_start(history)
        if previous_start:
            return date.replace(
                hour=previous_start.hour,
                minute=previous_start.minute,
                second=0,
                microsecond=0,
            )

    time = _extract_time(text)
    if not time or date:
        return None

    last_assistant = _last_assistant_text(history)
    if not _RETRY_DATETIME_RE.search(last_assistant):
        return None

    date = _last_user_date(history)
    if date:
        return date.replace(hour=time[0], minute=time[1], second=0, microsecond=0)
    return None


def _extract_cancel_start(text: str, history: list[dict]) -> datetime | None:
    start = _extract_start(text)
    if start:
        return start

    previous_start = _last_user_start(history)
    if previous_start and _CANCEL_FOLLOWUP_RE.search(text):
        return previous_start

    time = _extract_time(text)
    date = _last_user_date(history)
    if time and date:
        return date.replace(hour=time[0], minute=time[1], second=0, microsecond=0)
    return None


def _topic(user_text: str, history: list[dict]) -> str:
    joined = f"{_history_text(history)}\n{user_text}".lower()
    if "consult" in joined:
        return "Automatizar atencion por WhatsApp para consultoria"
    if "dental" in joined or "clinica" in joined or "clínica" in joined:
        return "Automatizar WhatsApp y citas"
    if "whatsapp" in joined:
        return "Automatizar atencion por WhatsApp"
    return "Conocer Asistto y revisar automatizacion"


async def maybe_handle(
    wa_id: str,
    user_text: str,
    history: list[dict],
    bot_id: int | None = None,
) -> tuple[str | None, bool]:
    """Devuelve (respuesta, cita_creada) si se puede resolver sin IA."""
    if _GREETING_RE.match(user_text.strip()):
        return (
            "Hola, soy Asistto de Humanio. Te puedo explicar como funcionan los chatbots de WhatsApp con IA, paquetes o casos de uso para tu negocio. ¿Qué te gustaría resolver primero?",
            False,
        )

    if _THANKS_RE.match(user_text.strip()) and _SCHEDULED_CONFIRMATION_RE.search(_last_assistant_text(history)):
        return "Con gusto. Te esperamos en la llamada.", False

    if _CANCEL_RE.search(user_text) or _is_cancel_continuation(user_text, history):
        return await calendar_client.cancel_appointment(
            wa_id,
            _extract_cancel_start(user_text, history),
            bot_id=bot_id,
        )

    reschedule_flow = _RESCHEDULE_RE.search(user_text) or _is_reschedule_continuation(user_text, history)
    if reschedule_flow and not _extract_start_with_context(user_text, history):
        return "Sin problema. ¿Qué día y hora te queda?", False

    if _looks_like_service_scheduling(user_text, history):
        return (
            "Perfecto. Asistto puede pedir datos al prospecto, entender el motivo de la llamada y crear la cita en tu calendario. ¿Quieres que te recomiende un paquete para eso?",
            False,
        )

    if not _in_schedule_flow(user_text, history):
        return None, False

    name = _extract_name(user_text, history)
    start = _extract_start_with_context(user_text, history)

    if not name:
        return "Claro. Para agendar la llamada, dime tu nombre completo.", False

    if not start:
        return f"Gracias, {name}. ¿Qué día y hora te queda para la llamada?", False

    data = {
        "title": f"{config.GOOGLE_APPOINTMENT_SUMMARY_PREFIX} con {name}",
        "start": start.isoformat(),
        "duration_minutes": config.GOOGLE_APPOINTMENT_DURATION_MINUTES,
        "attendee_name": name,
        "topic": _topic(user_text, history),
    }
    marker = f"[[CALENDAR_EVENT: {json.dumps(data, ensure_ascii=False)}]]"
    return await calendar_client.process_reply(
        wa_id,
        marker,
        bot_id=bot_id,
        replace_existing=bool(reschedule_flow),
    )
