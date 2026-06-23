from __future__ import annotations
"""Creacion de citas en Google Calendar usando OAuth refresh token."""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app import config, db, secure_store, skill_runtime

log = logging.getLogger("calendar")

_MARKER_RE = re.compile(r"\[\[CALENDAR_EVENT:\s*(\{.*?\})\s*\]\]", re.DOTALL)
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
_WEEKDAY_NAMES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)
_MONTH_NAMES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


@dataclass(frozen=True)
class CalendarRuntime:
    enabled: bool
    client_id: str
    client_secret: str
    refresh_token: str
    calendar_id: str
    timezone: str
    duration_minutes: int
    buffer_minutes: int
    summary_prefix: str
    location: str
    source: str
    integration_id: int | None = None
    bot_name: str = "Asistto"


def enabled() -> bool:
    return bool(
        config.GOOGLE_CALENDAR_ENABLED
        and config.GOOGLE_CLIENT_ID
        and config.GOOGLE_CLIENT_SECRET
        and config.GOOGLE_REFRESH_TOKEN
        and config.GOOGLE_CALENDAR_ID
    )


def _global_runtime() -> CalendarRuntime:
    return CalendarRuntime(
        enabled=enabled(),
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        refresh_token=config.GOOGLE_REFRESH_TOKEN,
        calendar_id=config.GOOGLE_CALENDAR_ID,
        timezone=config.GOOGLE_CALENDAR_TIMEZONE,
        duration_minutes=config.GOOGLE_APPOINTMENT_DURATION_MINUTES,
        buffer_minutes=config.GOOGLE_APPOINTMENT_BUFFER_MINUTES,
        summary_prefix=config.GOOGLE_APPOINTMENT_SUMMARY_PREFIX,
        location=config.GOOGLE_APPOINTMENT_LOCATION,
        source="env",
        bot_name="Asistto",
    )


def _secret(secrets: dict[str, str], *names: str) -> str:
    for name in names:
        encrypted = secrets.get(name)
        if not encrypted:
            continue
        value = secure_store.decrypt_secret(encrypted)
        if value:
            return value
    return ""


def _int_config(data: dict, key: str, default: int) -> int:
    try:
        return int(data.get(key, default))
    except (TypeError, ValueError):
        return default


async def _runtime(bot_id: int | None = None) -> CalendarRuntime:
    bot_name = "Asistto"
    if bot_id:
        try:
            bot_data = await db.get_bot(bot_id)
            if bot_data and bot_data.get("name"):
                bot_name = bot_data["name"]
        except Exception:
            pass

    if bot_id:
        integration = await db.get_active_bot_integration(bot_id, "google_calendar")
        if integration:
            cfg = integration.get("config") or {}
            secrets = await db.get_integration_secret_values(int(integration["id"]))
            client_id = (
                str(cfg.get("client_id") or "").strip()
                or _secret(secrets, "client_id", "google_client_id")
            )
            client_secret = _secret(secrets, "client_secret", "google_client_secret")
            refresh_token = _secret(secrets, "refresh_token", "google_refresh_token")
            calendar_id = str(cfg.get("calendar_id") or "primary").strip()
            timezone = str(cfg.get("timezone") or config.GOOGLE_CALENDAR_TIMEZONE).strip()

            summary_prefix = str(cfg.get("summary_prefix") or "").strip()
            if not summary_prefix:
                summary_prefix = config.GOOGLE_APPOINTMENT_SUMMARY_PREFIX
                if summary_prefix == "Llamada Asistto" and bot_name != "Asistto":
                    summary_prefix = f"Llamada {bot_name}"

            return CalendarRuntime(
                enabled=bool(client_id and client_secret and refresh_token and calendar_id),
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
                calendar_id=calendar_id,
                timezone=timezone,
                duration_minutes=_int_config(
                    cfg,
                    "duration_minutes",
                    config.GOOGLE_APPOINTMENT_DURATION_MINUTES,
                ),
                buffer_minutes=_int_config(
                    cfg,
                    "buffer_minutes",
                    config.GOOGLE_APPOINTMENT_BUFFER_MINUTES,
                ),
                summary_prefix=summary_prefix,
                location=str(cfg.get("location") or "").strip(),
                source="bot_integration",
                integration_id=int(integration["id"]),
                bot_name=bot_name,
            )
        if bot_id != 1:
            return CalendarRuntime(
                enabled=False,
                client_id="",
                client_secret="",
                refresh_token="",
                calendar_id="",
                timezone=config.GOOGLE_CALENDAR_TIMEZONE,
                duration_minutes=config.GOOGLE_APPOINTMENT_DURATION_MINUTES,
                buffer_minutes=config.GOOGLE_APPOINTMENT_BUFFER_MINUTES,
                summary_prefix=f"Llamada {bot_name}",
                location="",
                source="missing_bot_integration",
                bot_name=bot_name,
            )

    global_rt = _global_runtime()
    summary_prefix = global_rt.summary_prefix
    if summary_prefix == "Llamada Asistto" and bot_name != "Asistto":
        summary_prefix = f"Llamada {bot_name}"

    return CalendarRuntime(
        enabled=global_rt.enabled,
        client_id=global_rt.client_id,
        client_secret=global_rt.client_secret,
        refresh_token=global_rt.refresh_token,
        calendar_id=global_rt.calendar_id,
        timezone=global_rt.timezone,
        duration_minutes=global_rt.duration_minutes,
        buffer_minutes=global_rt.buffer_minutes,
        summary_prefix=summary_prefix,
        location=global_rt.location,
        source=global_rt.source,
        bot_name=bot_name,
    )


def config_status() -> dict[str, bool | str]:
    return {
        "GOOGLE_CALENDAR_ENABLED": bool(config.GOOGLE_CALENDAR_ENABLED),
        "GOOGLE_CLIENT_ID": bool(config.GOOGLE_CLIENT_ID),
        "GOOGLE_CLIENT_SECRET": bool(config.GOOGLE_CLIENT_SECRET),
        "GOOGLE_REFRESH_TOKEN": bool(config.GOOGLE_REFRESH_TOKEN),
        "GOOGLE_CALENDAR_ID": bool(config.GOOGLE_CALENDAR_ID),
        "GOOGLE_CALENDAR_TIMEZONE": config.GOOGLE_CALENDAR_TIMEZONE,
        "enabled": enabled(),
    }


async def runtime_status(bot_id: int | None = None) -> dict[str, bool | str | int | None]:
    skill_on = await skill_runtime.calendar_skill_enabled(bot_id)
    runtime = await _runtime(bot_id)
    status: dict[str, bool | str | int | None] = {
        "source": runtime.source,
        "integration_id": runtime.integration_id,
        "skill_enabled": skill_on,
        "GOOGLE_CLIENT_ID": bool(runtime.client_id),
        "GOOGLE_CLIENT_SECRET": bool(runtime.client_secret),
        "GOOGLE_REFRESH_TOKEN": bool(runtime.refresh_token),
        "GOOGLE_CALENDAR_ID": bool(runtime.calendar_id),
        "GOOGLE_CALENDAR_TIMEZONE": runtime.timezone,
        "enabled": bool(skill_on and runtime.enabled),
    }
    if bot_id and runtime.integration_id:
        integration = await db.get_active_bot_integration(bot_id, "google_calendar")
        cfg = integration.get("config") if integration else {}
        secrets = await db.get_integration_secret_values(runtime.integration_id)
        status.update({
            "secret_client_id_saved": bool(
                (cfg or {}).get("client_id")
                or secrets.get("client_id")
                or secrets.get("google_client_id")
            ),
            "secret_client_secret_saved": bool(
                secrets.get("client_secret") or secrets.get("google_client_secret")
            ),
            "secret_refresh_token_saved": bool(
                secrets.get("refresh_token") or secrets.get("google_refresh_token")
            ),
            "secret_client_secret_decryptable": bool(runtime.client_secret),
            "secret_refresh_token_decryptable": bool(runtime.refresh_token),
        })
    return status


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        text = exc.response.text[:500]
        return f"HTTP {exc.response.status_code}: {text}"
    return str(exc)[:500]


async def diagnostics(bot_id: int | None = None) -> dict:
    status = await runtime_status(bot_id)
    result: dict[str, Any] = {"config": status, "token_ok": False, "calendar_ok": False}
    runtime = await _runtime(bot_id)
    if not status["enabled"]:
        result["error"] = "Google Calendar no esta activo o faltan variables."
        return result
    try:
        token = await _access_token(runtime)
        result["token_ok"] = True
        calendar_id = quote(runtime.calendar_id, safe="")
        now = datetime.now(_tz(runtime))
        params = {
            "timeMin": now.isoformat(),
            "timeMax": (now + timedelta(days=1)).isoformat(),
            "timeZone": runtime.timezone,
            "singleEvents": "true",
            "maxResults": "1",
        }
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{_CALENDAR_API}/calendars/{calendar_id}/events",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            payload = resp.json()
        result["calendar_ok"] = True
        result["calendar_id"] = runtime.calendar_id
        result["items_seen"] = len(payload.get("items", []))
    except Exception as exc:
        result["error"] = _safe_error(exc)
    return result


def _tz(runtime: CalendarRuntime | None = None) -> ZoneInfo:
    tz_name = runtime.timezone if runtime else config.GOOGLE_CALENDAR_TIMEZONE
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("America/Chihuahua")


def _parse_start(value: str, runtime: CalendarRuntime | None = None) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz(runtime))
    return dt.astimezone(_tz(runtime))


def _format_dt(dt: datetime) -> str:
    weekday = _WEEKDAY_NAMES[dt.weekday()]
    month = _MONTH_NAMES[dt.month - 1]
    return f"{weekday} {dt.day} de {month} de {dt.year} a las {dt:%H:%M}"


def _first_name(name: str) -> str:
    clean = (name or "").strip()
    return clean.split()[0] if clean else ""


def _event_start(
    item: dict[str, Any],
    runtime: CalendarRuntime | None = None,
) -> datetime | None:
    raw = item.get("start", {}).get("dateTime")
    if not raw:
        return None
    try:
        return _parse_start(raw, runtime)
    except Exception:
        return None


def _same_slot(
    a: datetime | None,
    b: datetime | None,
    runtime: CalendarRuntime | None = None,
) -> bool:
    if not a or not b:
        return False
    a = a.astimezone(_tz(runtime))
    b = b.astimezone(_tz(runtime))
    return a.date() == b.date() and abs((a - b).total_seconds()) <= 60 * 75


def _row_timestamp(row: dict, key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _latest_existing_appointment(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    indexed = list(enumerate(rows))
    _, row = max(
        indexed,
        key=lambda item: (
            _row_timestamp(item[1], "created_at")
            or _row_timestamp(item[1], "updated_at")
            or -1,
            item[0],
        ),
    )
    return row


async def _access_token(runtime: CalendarRuntime) -> str:
    data = {
        "client_id": runtime.client_id,
        "client_secret": runtime.client_secret,
        "refresh_token": runtime.refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(_TOKEN_URL, data=data)
        resp.raise_for_status()
        payload = resp.json()
    return payload["access_token"]


async def _is_available(
    runtime: CalendarRuntime,
    token: str,
    start: datetime,
    end: datetime,
) -> bool:
    buffer_minutes = max(runtime.buffer_minutes, 0)
    check_start = start - timedelta(minutes=buffer_minutes)
    check_end = end + timedelta(minutes=buffer_minutes)
    calendar_id = quote(runtime.calendar_id, safe="")
    params = {
        "timeMin": check_start.isoformat(),
        "timeMax": check_end.isoformat(),
        "timeZone": runtime.timezone,
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "10",
    }
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_CALENDAR_API}/calendars/{calendar_id}/events",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        payload = resp.json()
    for item in payload.get("items", []):
        if item.get("status") == "cancelled":
            continue
        if item.get("transparency") == "transparent":
            continue
        return False
    return True


async def _insert_event(
    runtime: CalendarRuntime,
    token: str,
    data: dict[str, Any],
    start: datetime,
    end: datetime,
) -> dict:
    calendar_id = quote(runtime.calendar_id, safe="")
    attendee_name = str(data.get("attendee_name") or "Prospecto").strip()
    topic = str(data.get("topic") or f"Revisar {runtime.bot_name}").strip()
    title = str(data.get("title") or "").strip()
    summary = title or f"{runtime.summary_prefix} - {attendee_name}"
    body = {
        "summary": summary[:180],
        "description": (
            f"Cita creada desde el bot de WhatsApp {runtime.bot_name}.\n"
            f"Nombre: {attendee_name}\n"
            f"Objetivo: {topic}\n"
            f"Origen: WhatsApp {data.get('wa_id', '')}\n"
        ),
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": runtime.timezone,
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": runtime.timezone,
        },
    }
    if runtime.location:
        body["location"] = runtime.location

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{_CALENDAR_API}/calendars/{calendar_id}/events",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


async def _delete_event(runtime: CalendarRuntime, token: str, event_id: str) -> bool:
    calendar_id = quote(runtime.calendar_id, safe="")
    event_id = quote(event_id, safe="")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.delete(
            f"{_CALENDAR_API}/calendars/{calendar_id}/events/{event_id}",
            headers=headers,
        )
        if resp.status_code in (404, 410):
            return False
        resp.raise_for_status()
    return True


async def _search_events_for_wa_id(
    runtime: CalendarRuntime,
    token: str,
    wa_id: str,
) -> list[dict]:
    calendar_id = quote(runtime.calendar_id, safe="")
    now = datetime.now(_tz(runtime)) - timedelta(hours=2)
    params = {
        "timeMin": now.isoformat(),
        "timeMax": (now + timedelta(days=90)).isoformat(),
        "timeZone": runtime.timezone,
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "20",
        "q": wa_id,
    }
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{_CALENDAR_API}/calendars/{calendar_id}/events",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        payload = resp.json()
    return [
        item
        for item in payload.get("items", [])
        if item.get("status") != "cancelled" and item.get("id")
    ]


def _filter_candidates(
    candidates: list[dict],
    hint_start: datetime | None,
    runtime: CalendarRuntime | None = None,
) -> list[dict]:
    if not hint_start:
        return candidates
    return [
        item for item in candidates
        if _same_slot(_event_start(item, runtime), hint_start, runtime)
    ]


async def _candidate_from_db(
    wa_id: str,
    hint_start: datetime | None,
    bot_id: int | None = None,
    runtime: CalendarRuntime | None = None,
) -> tuple[dict | None, int]:
    rows = await db.list_active_calendar_appointments(wa_id, bot_id=bot_id)
    candidates: list[dict] = []
    for row in rows:
        candidates.append(
            {
                "id": row["google_event_id"],
                "summary": row.get("attendee_name") or row.get("topic") or f"Llamada {runtime.bot_name if runtime else 'Asistto'}",
                "start": {"dateTime": row["start_at"].isoformat()},
                "_db": True,
            }
        )
    filtered = _filter_candidates(candidates, hint_start, runtime)
    if len(filtered) == 1:
        return filtered[0], len(candidates)
    return None, len(filtered)


async def cancel_appointment(
    wa_id: str,
    hint_start: datetime | None = None,
    bot_id: int | None = None,
) -> tuple[str, bool]:
    """Cancela una cita activa del contacto y borra el evento real de Google Calendar."""
    if not await skill_runtime.calendar_skill_enabled(bot_id):
        return (
            "Puedo ayudarte con la cita, pero la habilidad de calendario no esta activa para este bot.",
            False,
        )
    runtime = await _runtime(bot_id)
    if not runtime.enabled:
        return (
            "Puedo ayudarte a cancelar, pero el calendario no esta activo en este momento. Te paso con el equipo para revisarlo.",
            False,
        )

    try:
        token = await _access_token(runtime)
        candidate, count = await _candidate_from_db(
            wa_id,
            hint_start,
            bot_id=bot_id,
            runtime=runtime,
        )
        if candidate is None:
            searched = await _search_events_for_wa_id(runtime, token, wa_id)
            searched = _filter_candidates(searched, hint_start, runtime)
            if len(searched) == 1:
                candidate = searched[0]
            elif len(searched) > 1 or count > 1:
                return (
                    "Tengo mas de una cita activa. Dime el dia y hora de la cita que quieres cancelar.",
                    False,
                )
            else:
                return (
                    "No encontre una cita activa ligada a este WhatsApp. Si quieres, dime el dia y hora y la revisamos.",
                    False,
                )

        event_id = str(candidate["id"])
        deleted = await _delete_event(runtime, token, event_id)
        await db.mark_calendar_appointment_cancelled(event_id, bot_id)
        start = _event_start(candidate, runtime)
        when = f" del {_format_dt(start)}" if start else ""
        if deleted:
            return f"Listo, cancele tu cita{when} y la borre del calendario.", True
        return f"Esa cita{when} ya no aparece activa en calendario. La marque como cancelada.", True
    except httpx.HTTPStatusError as exc:
        log.exception("Google Calendar rechazo la cancelacion: %s", exc.response.text[:500])
    except Exception:
        log.exception("Error cancelando cita en Google Calendar")
    return (
        "No pude cancelar la cita en calendario en este momento. Te paso con el equipo para revisarlo.",
        False,
    )


async def _is_within_business_hours(bot_id: int | None, dt: datetime) -> tuple[bool, str]:
    """
    Valida si el datetime proporcionado está dentro de los horarios de atención del bot.
    """
    if not bot_id:
        return True, ""
    try:
        skill = await db.get_bot_skill(bot_id, "business_hours")
    except Exception:
        log.exception("Error consultando horarios para bot %s", bot_id)
        return True, "" # Fail open
    if not skill or not skill.get("enabled", True):
        return True, ""
    cfg = skill.get("config") or {}
    if not cfg:
        return True, ""
    
    # 0 = lunes, 6 = domingo
    weekday_map = {
        0: "lunes",
        1: "martes",
        2: "miercoles",
        3: "jueves",
        4: "viernes",
        5: "sabado",
        6: "domingo"
    }
    day_name = weekday_map.get(dt.weekday())
    day_cfg = cfg.get(day_name)
    if not day_cfg:
        return True, ""
    if not day_cfg.get("open", True):
        return False, f"Lo siento, no laboramos los días {day_name.capitalize()}. ¿Podrías elegir otro día?"
        
    start_str = day_cfg.get("start", "09:00")
    end_str = day_cfg.get("end", "18:00")
    try:
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
    except Exception:
        return True, "" # Formato inválido, fail open
        
    slot_time = dt.hour * 60 + dt.minute
    start_time = sh * 60 + sm
    end_time = eh * 60 + em
    if slot_time < start_time or slot_time > end_time:
        return False, f"Ese horario está fuera de nuestra jornada de atención ({start_str} a {end_str}). ¿Podrías elegir otra hora?"
    return True, ""


async def process_reply(
    wa_id: str,
    reply: str,
    bot_id: int | None = None,
    replace_existing: bool = False,
) -> tuple[str, bool]:
    """Procesa el marcador [[CALENDAR_EVENT: {...}]] y devuelve respuesta limpia."""
    match = _MARKER_RE.search(reply)
    if not match:
        return reply, False

    visible = _MARKER_RE.sub("", reply).strip()
    if not await skill_runtime.calendar_skill_enabled(bot_id):
        fallback = "Tengo tus datos para la llamada, pero la agenda no esta activa para este bot."
        return (visible or fallback).strip(), False

    runtime = await _runtime(bot_id)
    if not runtime.enabled:
        if runtime.source == "bot_integration":
            return (
                "No pude confirmar la cita porque la integracion de calendario de este bot no esta completa. Te paso con el equipo para revisarlo.",
                False,
            )
        fallback = "Tengo tus datos para la llamada. Te dejo el siguiente paso para avanzar:"
        if config.QUALIFIED_CTA_URL:
            fallback = f"{fallback} {config.QUALIFIED_CTA_URL}"
        return (visible or fallback).strip(), False

    try:
        data = json.loads(match.group(1))
        data["wa_id"] = wa_id
        start = _parse_start(str(data["start"]), runtime)
        duration = int(runtime.duration_minutes or data.get("duration_minutes") or 30)
        duration = max(duration, 15)
        end = start + timedelta(minutes=duration)
    except Exception:
        log.exception("Marcador de calendario invalido")
        return (
            "Ya casi. Para agendar bien la llamada, dime que dia y hora te queda mejor.",
            False,
        )

    if start < datetime.now(_tz(runtime)) + timedelta(minutes=2):
        return "Ese horario ya paso o esta demasiado cerca. Dime otro dia y hora, por favor.", False

    # Validar horarios del cliente
    in_hours, err_msg = await _is_within_business_hours(bot_id, start)
    if not in_hours:
        return err_msg, False

    existing_rows = []
    if replace_existing:
        existing_rows = await db.list_active_calendar_appointments(wa_id, bot_id=bot_id)

    try:
        token = await _access_token(runtime)
        if not await _is_available(runtime, token, start, end):
            return (
                "Ese horario aparece ocupado en mi calendario. Dime otro dia u hora y lo reviso.",
                False,
            )
        event = await _insert_event(runtime, token, data, start, end)
        event_id = event.get("id")
        if event_id:
            await db.save_calendar_appointment(
                wa_id=wa_id,
                google_event_id=event_id,
                calendar_id=runtime.calendar_id,
                attendee_name=str(data.get("attendee_name") or "").strip() or None,
                topic=str(data.get("topic") or "").strip() or None,
                start_at=start,
                end_at=end,
                bot_id=bot_id,
            )
            if replace_existing:
                previous_row = _latest_existing_appointment(existing_rows)
                for row in [previous_row] if previous_row else []:
                    old_event_id = str(row.get("google_event_id") or "")
                    if not old_event_id or old_event_id == event_id:
                        continue
                    try:
                        await _delete_event(runtime, token, old_event_id)
                    except Exception:
                        log.exception("No se pudo borrar cita anterior %s", old_event_id)
                    await db.mark_calendar_appointment_cancelled(old_event_id, bot_id)
    except httpx.HTTPStatusError as exc:
        log.exception("Google Calendar rechazo la cita: %s", exc.response.text[:500])
        return (
            "No pude confirmar la cita en calendario en este momento. Te paso con el equipo para revisarlo.",
            False,
        )
    except Exception:
        log.exception("Error creando cita en Google Calendar")
        return (
            "No pude confirmar la cita en calendario en este momento. Te paso con el equipo para revisarlo.",
            False,
        )

    attendee = str(data.get("attendee_name") or "").strip()
    who = f", {_first_name(attendee)}" if attendee else ""
    if replace_existing and existing_rows:
        confirmation = f"Listo{who}. Reprogramé la llamada para el {_format_dt(start)} y cancelé la cita anterior."
    else:
        confirmation = f"Listo{who}. Quedó agendada tu llamada para el {_format_dt(start)}."
    if visible:
        return f"{visible}\n\n{confirmation}", True
    return confirmation, True
