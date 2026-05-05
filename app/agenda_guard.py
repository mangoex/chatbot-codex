"""Guardrails deterministicos para el flujo de agenda antes de llamar al modelo."""
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import calendar_client, config

_SCHEDULE_RE = re.compile(
    r"\b(agend|agenda|agendar|cita|llamada|demo|reunion|reunión)\b",
    re.IGNORECASE,
)
_NAME_RE = re.compile(
    r"\b(?:soy|me llamo|mi nombre es)\s+([a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+){0,3})",
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
_DATE_MONTH_RE = re.compile(
    r"\b(\d{1,2})\s*(?:de\s*)?"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
    r"(?:\s*(?:de\s*)?(\d{4}))?\b",
    re.IGNORECASE,
)
_WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
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


def _history_text(history: list[dict], limit: int = 6) -> str:
    return "\n".join(item.get("content", "") for item in history[-limit:])


def _in_schedule_flow(user_text: str, history: list[dict]) -> bool:
    text = f"{_history_text(history)}\n{user_text}"
    return bool(_SCHEDULE_RE.search(text))


def _extract_name(text: str, history: list[dict]) -> str | None:
    joined = f"{_history_text(history)}\n{text}"
    match = _NAME_RE.search(joined)
    if not match:
        return None
    name = match.group(1).strip()
    stop = re.search(r"\b(doy|tengo|quiero|necesito|y|para)\b", name, re.IGNORECASE)
    if stop:
        name = name[: stop.start()].strip()
    return name.title() if len(name) >= 2 else None


def _extract_date(text: str) -> datetime | None:
    base = _now()
    lower = text.lower()

    if "mañana" in lower or "manana" in lower:
        return base + timedelta(days=1)
    if "hoy" in lower:
        return base

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
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _extract_start(text: str) -> datetime | None:
    date = _extract_date(text)
    time = _extract_time(text)
    if not date or not time:
        return None
    return date.replace(hour=time[0], minute=time[1], second=0, microsecond=0)


def _topic(user_text: str, history: list[dict]) -> str:
    joined = f"{_history_text(history)}\n{user_text}".lower()
    if "consult" in joined:
        return "Automatizar atencion por WhatsApp para consultoria"
    if "dental" in joined or "clinica" in joined or "clínica" in joined:
        return "Automatizar WhatsApp y citas"
    if "whatsapp" in joined:
        return "Automatizar atencion por WhatsApp"
    return "Conocer Asistto y revisar automatizacion"


async def maybe_handle(wa_id: str, user_text: str, history: list[dict]) -> tuple[str | None, bool]:
    """Devuelve (respuesta, cita_creada) si se puede resolver agenda sin IA."""
    if not _in_schedule_flow(user_text, history):
        return None, False

    name = _extract_name(user_text, history)
    start = _extract_start(user_text)

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
    return await calendar_client.process_reply(wa_id, marker)
