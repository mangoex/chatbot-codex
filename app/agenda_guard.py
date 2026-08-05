from __future__ import annotations
"""Guardrails deterministicos para el flujo de agenda antes de llamar al modelo."""
import calendar
import json
import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import calendar_client, config

_SCHEDULE_RE = re.compile(
    r"\b(?:quiero|quisiera|necesito|me interesa|puedo|podemos|ay[uú]dame|ayudame|vamos a|deseo|me gustar[ií]a|ponme|dame|hazme|ag[eé]ndame|crear?|programar?|reservar?|hacer|haz)\b"
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
    r"reprogramar|reprograma|modificar|modifica|posponer|no\s+voy\s+a\s+poder|"
    r"no\s+voy\s+a\s+estar|no\s+estare|no\s+estar[eé]|no\s+podre|no\s+podré|"
    r"mejor|ese\s+d[ií]a\s+no|ese\s+dia\s+no|esa\s+fecha\s+no)\b",
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
_SINGLE_NAME_RE = re.compile(
    r"^(?:si\s+claro,?\s*|sí\s+claro,?\s*|claro,?\s*)?"
    r"([a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]{2,30})\s*$",
    re.IGNORECASE,
)
_START_NAME_RE = re.compile(
    r"^\s*([a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+){0,2})",
    re.IGNORECASE
)
_ASKED_NAME_RE = re.compile(
    r"\b(nombre completo|dime tu nombre|tu nombre|a nombre de qui[eé]n|nombre)\b",
    re.IGNORECASE,
)
_ASKED_DATETIME_RE = re.compile(r"\b(d[ií]a y hora|fecha y hora|qu[eé] d[ií]a|qu[eé] hora)\b", re.IGNORECASE)
_RESCHEDULE_DATETIME_PROMPT_RE = re.compile(
    r"\b(sin problema|claro|ok|perfecto)\b.*\b(qu[eé] d[ií]a y hora|qu[eé] d[ií]a|qu[eé] hora|te queda)\b",
    re.IGNORECASE,
)
_RESCHEDULE_CONFIRM_RE = re.compile(
    r"^(?:s[ií]|ok|va|dale|claro|perfecto|se puede|sí se puede)[?!.¡¿\s]*$",
    re.IGNORECASE,
)
_BYPASS_FLOW_RE = re.compile(
    r"\b(?:precio|costo|costa|cuesta|cobran|valor|tarifa|paquete|plan|planes|paquetes|diferencia)\b"
    r"|\b(?:c[oó]mo funciona|de qu[eé] se trata|explic\w*|informaci[oó]n|saber m[aá]s)\b"
    r"|\b(?:antes|primero|pero)\b"
    r"|\b(?:el\s+bot|el\s+sistema|la\s+ia|tu\s+plataforma|tu\s+servicio|el\s+servicio)\b"
    r"|\b(?:mi\s+calendario|mis\s+clientes|mi\s+negocio|mis\s+citas|mi\s+empresa|conmigo|para\s+m[ií])\b"
    r"|\b(?:saber\s+si|pregunta\s+si|saber\s+c[oó]mo)\b"
    r"|\b(?:puede|pueden|se\s+puede)\s+(?:agendar|hacer|atender|conectar|funcionar|servir)\b",
    re.IGNORECASE,
)
_SAME_TIME_RE = re.compile(r"\b(misma hora|la misma hora|igual hora|esa hora)\b", re.IGNORECASE)
_TEST_APPOINTMENT_RE = re.compile(r"\b(probar|prueba|simular|simulacion|simulación)\b", re.IGNORECASE)
_ASSISTANT_NAME_RE = re.compile(
    r"\b(?:gracias|listo),\s+([a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[a-zA-ZÁÉÍÓÚÜÑáéíóúüñ]+){0,3})[.!?,]",
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
_DAY_WITH_TIME_RE = re.compile(
    r"(?:^|\b(?:el|dia|día)\s+)(\d{1,2})(?=\s+(?:a\s+las|a\s+la|alas)\b)",
    re.IGNORECASE,
)
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


def _last_history_time(history: list[dict]) -> tuple[int, int] | None:
    for item in reversed(history):
        time = _extract_time(item.get("content", ""))
        if time:
            return time
    return None


def _last_user_start_after_latest_name_prompt(history: list[dict]) -> datetime | None:
    seen_name_prompt = False
    for item in reversed(history[:-1]):
        role = item.get("role")
        content = item.get("content", "")
        if role == "assistant":
            if not seen_name_prompt and _ASKED_NAME_RE.search(content):
                seen_name_prompt = True
                continue
            if seen_name_prompt:
                break
        if role == "user" and seen_name_prompt:
            start = _extract_start(content)
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
    if _SCHEDULED_CONFIRMATION_RE.search(last_assistant) and (
        _RESCHEDULE_RE.search(user_text) or _extract_start_with_context(user_text, history)
    ):
        return True
    recent = _history_text(history, limit=8)
    recent_user = "\n".join(item.get("content", "") for item in history[-8:] if item.get("role") == "user")
    if _RESCHEDULE_RE.search(recent_user) and (_extract_date(user_text) or _SAME_TIME_RE.search(user_text)):
        return True
    if _SCHEDULED_CONFIRMATION_RE.search(recent) and _RESCHEDULE_RE.search(recent_user):
        return bool(_RESCHEDULE_CONFIRM_RE.match(user_text.strip()))
    return False


def _looks_like_service_scheduling(user_text: str, history: list[dict]) -> bool:
    """Distingue seleccionar la habilidad de agendar llamadas de pedir una cita real."""
    text = user_text.strip(" .,!¡¿?")
    last_assistant = _last_assistant_text(history)
    if not _SERVICE_SCHEDULING_RE.match(text):
        return False
    return bool(_SERVICE_CONTEXT_RE.search(last_assistant))


def _is_booking_context(text: str) -> bool:
    return bool(re.search(
        r"\b(?:agend\w*|cit[as]\w*|llamada\w*|demo\b|demostr\w*|reuni\w*|calendario\w*|d[ií]a\s*y\s*hora|fecha\s*y\s*hora)\b",
        text,
        re.IGNORECASE
    ))


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
    if _is_booking_context(last_assistant):
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
    
    # Eliminar palabras de respuesta o confirmación al inicio (ej: "Sí, claro, Miguel" -> "Miguel")
    while True:
        new_clean = re.sub(r"^(?:si|sí|no|claro|ok|okay|vale|bien|perfecto|bueno)\b\s*,?\s*", "", clean, flags=re.IGNORECASE)
        if new_clean == clean:
            break
        clean = new_clean

    if not clean.strip():
        return None

    # Filtrar pronombres, palabras de preguntas, y términos comerciales comunes
    lower_name = clean.lower()
    forbidden_names = {
        "que", "qué", "como", "cómo", "cuánto", "cuanto", "cuál", "cual", "quién", "quien",
        "dime", "antes", "precio", "costo", "paquetes", "precios", "hola", "ver", "saber",
        "info", "información", "informacion", "paquete", "servicio", "servicios", "costa",
        "cuesta", "pregunta", "duda", "ayuda", "llamada", "cita", "reunion", "reunión",
        "demo", "contacto", "asesor", "humano", "persona", "negocio", "empresa", "sistema",
        "asistto", "robot", "bot", "ia", "artificial", "inteligencia", "gracias",
        "si", "sí", "no", "claro", "ok", "okay", "vale", "listo", "bien", "va", "perfecto",
        "correcto", "entendido", "bueno", "así", "asi"
    }
    if lower_name in forbidden_names:
        return None

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


def _direct_name_after_prompt(text: str) -> str | None:
    direct = _direct_name(text)
    if direct:
        return direct
    single = _SINGLE_NAME_RE.search(text.strip())
    if single:
        return _clean_name(single.group(1))
    return None


def _first_name(name: str) -> str:
    clean = (name or "").strip()
    return clean.split()[0] if clean else ""


def _testing_appointment_context(user_text: str, history: list[dict]) -> bool:
    if _TEST_APPOINTMENT_RE.search(user_text):
        return True
    return bool(_TEST_APPOINTMENT_RE.search(_history_text(history, limit=6)))


def _extract_name(text: str, history: list[dict]) -> str | None:
    current = _NAME_RE.search(text)
    if current:
        name = _clean_name(current.group(1))
        if name:
            return name

    if _ASKED_NAME_RE.search(_last_assistant_text(history)):
        direct = _direct_name_after_prompt(text)
        if direct:
            return direct
        start_match = _START_NAME_RE.match(text)
        if start_match:
            candidate = _clean_name(start_match.group(1))
            if candidate:
                return candidate

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
            name = _direct_name_after_prompt(content)
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

    day_with_time_match = _DAY_WITH_TIME_RE.search(lower)
    if day_with_time_match:
        return _upcoming_day_of_month(base, int(day_with_time_match.group(1)))

    for label, weekday in _WEEKDAYS.items():
        if re.search(rf"\b{label}\b", lower):
            days = (weekday - base.weekday()) % 7
            if days == 0:
                days = 7
            return base + timedelta(days=days)

    return None


def _upcoming_day_of_month(base: datetime, day: int) -> datetime | None:
    if day < 1 or day > 31:
        return None
    year = base.year
    month = base.month
    for offset in range(13):
        candidate_month = month + offset
        candidate_year = year + (candidate_month - 1) // 12
        candidate_month = ((candidate_month - 1) % 12) + 1
        last_day = calendar.monthrange(candidate_year, candidate_month)[1]
        if day > last_day:
            continue
        candidate = base.replace(
            year=candidate_year,
            month=candidate_month,
            day=day,
        )
        if candidate.date() >= base.date():
            return candidate
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

    if _ASKED_NAME_RE.search(_last_assistant_text(history)):
        previous_start = _last_user_start_after_latest_name_prompt(history)
        if previous_start:
            return previous_start

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
        last_time = _last_history_time(history)
        if last_time:
            return date.replace(
                hour=last_time[0],
                minute=last_time[1],
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


def _topic(user_text: str, history: list[dict], bot_name: str = "Asistto") -> str:
    joined = f"{_history_text(history)}\n{user_text}".lower()
    if "consult" in joined:
        return "Automatizar atencion por WhatsApp para consultoria"
    if "dental" in joined or "clinica" in joined or "clínica" in joined:
        return "Automatizar WhatsApp y citas"
    if "whatsapp" in joined:
        return "Automatizar atencion por WhatsApp"
    return f"Conocer {bot_name} y revisar automatizacion"


async def maybe_handle(
    wa_id: str,
    user_text: str,
    history: list[dict],
    bot_id: int | None = None,
) -> tuple[str | None, bool]:
    """Devuelve (respuesta, cita_creada) si se puede resolver sin IA."""
    if _GREETING_RE.match(user_text.strip()):
        return None, False


    if _THANKS_RE.match(user_text.strip()) and _SCHEDULED_CONFIRMATION_RE.search(_last_assistant_text(history)):
        return "Con gusto. Te esperamos en la llamada.", False

    is_cancel = bool(_CANCEL_RE.search(user_text) or _is_cancel_continuation(user_text, history))
    is_reschedule = bool(_RESCHEDULE_RE.search(user_text) or _is_reschedule_continuation(user_text, history))

    if is_cancel and not is_reschedule:
        return await calendar_client.cancel_appointment(
            wa_id,
            _extract_cancel_start(user_text, history),
            bot_id=bot_id,
        )

    reschedule_flow = _RESCHEDULE_RE.search(user_text) or _is_reschedule_continuation(user_text, history)
    if reschedule_flow and not _extract_start_with_context(user_text, history):
        if "?" in user_text:
            return None, False
        return "Sin problema. ¿Qué día y hora te queda?", False



    if not _in_schedule_flow(user_text, history):
        return None, False

    # Si el usuario pregunta algo (tiene '?') o pide información/precios/paquetes explícitamente,
    # dejamos que la IA responda en lugar de forzar el flujo determinista de la agenda.
    if (
        "?" in user_text 
        or _BYPASS_FLOW_RE.search(user_text)
    ) and not _extract_start_with_context(user_text, history):
        return None, False

    name = _extract_name(user_text, history)
    start = _extract_start_with_context(user_text, history)

    if not name:
        if _testing_appointment_context(user_text, history):
            return "Claro. ¿A nombre de quién agendo la llamada?", False
        return "Claro. ¿A nombre de quién agendo la llamada?", False

    if not start:
        display_name = _first_name(name) or name
        return f"Gracias, {display_name}. ¿Qué día y hora quieres para la llamada?", False

    bot_name = "Asistto"
    if bot_id:
        try:
            from app import db
            bot_data = await db.get_bot(bot_id)
            if bot_data and bot_data.get("name"):
                bot_name = bot_data["name"]
        except Exception:
            pass

    summary_prefix = config.GOOGLE_APPOINTMENT_SUMMARY_PREFIX
    if summary_prefix == "Llamada Asistto" and bot_name != "Asistto":
        summary_prefix = f"Llamada {bot_name}"

    data = {
        "title": f"{summary_prefix} con {name}",
        "start": start.isoformat(),
        "duration_minutes": config.GOOGLE_APPOINTMENT_DURATION_MINUTES,
        "attendee_name": name,
        "topic": _topic(user_text, history, bot_name=bot_name),
    }
    marker = f"[[CALENDAR_EVENT: {json.dumps(data, ensure_ascii=False)}]]"
    return await calendar_client.process_reply(
        wa_id,
        marker,
        bot_id=bot_id,
        replace_existing=bool(reschedule_flow),
    )
