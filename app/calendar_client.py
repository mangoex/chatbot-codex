"""Creacion de citas en Google Calendar usando OAuth refresh token."""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app import config, db

log = logging.getLogger("calendar")

_MARKER_RE = re.compile(r"\[\[CALENDAR_EVENT:\s*(\{.*?\})\s*\]\]", re.DOTALL)
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3"


def enabled() -> bool:
    return bool(
        config.GOOGLE_CALENDAR_ENABLED
        and config.GOOGLE_CLIENT_ID
        and config.GOOGLE_CLIENT_SECRET
        and config.GOOGLE_REFRESH_TOKEN
        and config.GOOGLE_CALENDAR_ID
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


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        text = exc.response.text[:500]
        return f"HTTP {exc.response.status_code}: {text}"
    return str(exc)[:500]


async def diagnostics() -> dict:
    status = config_status()
    result: dict[str, Any] = {"config": status, "token_ok": False, "calendar_ok": False}
    if not enabled():
        result["error"] = "Google Calendar no esta activo o faltan variables."
        return result
    try:
        token = await _access_token()
        result["token_ok"] = True
        calendar_id = quote(config.GOOGLE_CALENDAR_ID, safe="")
        now = datetime.now(_tz())
        params = {
            "timeMin": now.isoformat(),
            "timeMax": (now + timedelta(days=1)).isoformat(),
            "timeZone": config.GOOGLE_CALENDAR_TIMEZONE,
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
        result["calendar_id"] = config.GOOGLE_CALENDAR_ID
        result["items_seen"] = len(payload.get("items", []))
    except Exception as exc:
        result["error"] = _safe_error(exc)
    return result


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(config.GOOGLE_CALENDAR_TIMEZONE)
    except Exception:
        return ZoneInfo("America/Chihuahua")


def _parse_start(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz())
    return dt.astimezone(_tz())


def _format_dt(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y a las %H:%M")


def _event_start(item: dict[str, Any]) -> datetime | None:
    raw = item.get("start", {}).get("dateTime")
    if not raw:
        return None
    try:
        return _parse_start(raw)
    except Exception:
        return None


def _same_slot(a: datetime | None, b: datetime | None) -> bool:
    if not a or not b:
        return False
    a = a.astimezone(_tz())
    b = b.astimezone(_tz())
    return a.date() == b.date() and abs((a - b).total_seconds()) <= 60 * 75


async def _access_token() -> str:
    data = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "refresh_token": config.GOOGLE_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(_TOKEN_URL, data=data)
        resp.raise_for_status()
        payload = resp.json()
    return payload["access_token"]


async def _is_available(token: str, start: datetime, end: datetime) -> bool:
    buffer_minutes = max(config.GOOGLE_APPOINTMENT_BUFFER_MINUTES, 0)
    check_start = start - timedelta(minutes=buffer_minutes)
    check_end = end + timedelta(minutes=buffer_minutes)
    calendar_id = quote(config.GOOGLE_CALENDAR_ID, safe="")
    params = {
        "timeMin": check_start.isoformat(),
        "timeMax": check_end.isoformat(),
        "timeZone": config.GOOGLE_CALENDAR_TIMEZONE,
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


async def _insert_event(token: str, data: dict[str, Any], start: datetime, end: datetime) -> dict:
    calendar_id = quote(config.GOOGLE_CALENDAR_ID, safe="")
    attendee_name = str(data.get("attendee_name") or "Prospecto").strip()
    topic = str(data.get("topic") or "Revisar Asistto").strip()
    title = str(data.get("title") or "").strip()
    summary = title or f"{config.GOOGLE_APPOINTMENT_SUMMARY_PREFIX} - {attendee_name}"
    body = {
        "summary": summary[:180],
        "description": (
            "Cita creada desde el bot de WhatsApp Asistto.\n"
            f"Nombre: {attendee_name}\n"
            f"Objetivo: {topic}\n"
            f"Origen: WhatsApp {data.get('wa_id', '')}\n"
        ),
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": config.GOOGLE_CALENDAR_TIMEZONE,
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": config.GOOGLE_CALENDAR_TIMEZONE,
        },
    }
    if config.GOOGLE_APPOINTMENT_LOCATION:
        body["location"] = config.GOOGLE_APPOINTMENT_LOCATION

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{_CALENDAR_API}/calendars/{calendar_id}/events",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


async def _delete_event(token: str, event_id: str) -> bool:
    calendar_id = quote(config.GOOGLE_CALENDAR_ID, safe="")
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


async def _search_events_for_wa_id(token: str, wa_id: str) -> list[dict]:
    calendar_id = quote(config.GOOGLE_CALENDAR_ID, safe="")
    now = datetime.now(_tz()) - timedelta(hours=2)
    params = {
        "timeMin": now.isoformat(),
        "timeMax": (now + timedelta(days=90)).isoformat(),
        "timeZone": config.GOOGLE_CALENDAR_TIMEZONE,
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


def _filter_candidates(candidates: list[dict], hint_start: datetime | None) -> list[dict]:
    if not hint_start:
        return candidates
    return [item for item in candidates if _same_slot(_event_start(item), hint_start)]


async def _candidate_from_db(wa_id: str, hint_start: datetime | None) -> tuple[dict | None, int]:
    rows = await db.list_active_calendar_appointments(wa_id)
    candidates: list[dict] = []
    for row in rows:
        candidates.append(
            {
                "id": row["google_event_id"],
                "summary": row.get("attendee_name") or row.get("topic") or "Llamada Asistto",
                "start": {"dateTime": row["start_at"].isoformat()},
                "_db": True,
            }
        )
    filtered = _filter_candidates(candidates, hint_start)
    if len(filtered) == 1:
        return filtered[0], len(candidates)
    return None, len(filtered)


async def cancel_appointment(
    wa_id: str,
    hint_start: datetime | None = None,
) -> tuple[str, bool]:
    """Cancela una cita activa del contacto y borra el evento real de Google Calendar."""
    if not enabled():
        return (
            "Puedo ayudarte a cancelar, pero el calendario no esta activo en este momento. Te paso con el equipo para revisarlo.",
            False,
        )

    try:
        token = await _access_token()
        candidate, count = await _candidate_from_db(wa_id, hint_start)
        if candidate is None:
            searched = await _search_events_for_wa_id(token, wa_id)
            searched = _filter_candidates(searched, hint_start)
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
        deleted = await _delete_event(token, event_id)
        await db.mark_calendar_appointment_cancelled(event_id)
        start = _event_start(candidate)
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


async def process_reply(wa_id: str, reply: str) -> tuple[str, bool]:
    """Procesa el marcador [[CALENDAR_EVENT: {...}]] y devuelve respuesta limpia."""
    match = _MARKER_RE.search(reply)
    if not match:
        return reply, False

    visible = _MARKER_RE.sub("", reply).strip()
    if not enabled():
        fallback = "Tengo tus datos para la llamada. Te dejo el siguiente paso para avanzar:"
        if config.QUALIFIED_CTA_URL:
            fallback = f"{fallback} {config.QUALIFIED_CTA_URL}"
        return (visible or fallback).strip(), False

    try:
        data = json.loads(match.group(1))
        data["wa_id"] = wa_id
        start = _parse_start(str(data["start"]))
        duration = int(data.get("duration_minutes") or config.GOOGLE_APPOINTMENT_DURATION_MINUTES)
        duration = max(duration, 15)
        end = start + timedelta(minutes=duration)
    except Exception:
        log.exception("Marcador de calendario invalido")
        return (
            "Ya casi. Para agendar bien la llamada, dime que dia y hora te queda mejor.",
            False,
        )

    if start < datetime.now(_tz()) + timedelta(minutes=2):
        return "Ese horario ya paso o esta demasiado cerca. Dime otro dia y hora, por favor.", False

    try:
        token = await _access_token()
        if not await _is_available(token, start, end):
            return (
                "Ese horario aparece ocupado en mi calendario. Dime otro dia u hora y lo reviso.",
                False,
            )
        event = await _insert_event(token, data, start, end)
        event_id = event.get("id")
        if event_id:
            await db.save_calendar_appointment(
                wa_id=wa_id,
                google_event_id=event_id,
                calendar_id=config.GOOGLE_CALENDAR_ID,
                attendee_name=str(data.get("attendee_name") or "").strip() or None,
                topic=str(data.get("topic") or "").strip() or None,
                start_at=start,
                end_at=end,
            )
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
    who = f", {attendee}" if attendee else ""
    confirmation = f"Listo{who}. Quedo agendada la llamada para el {_format_dt(start)}."
    if visible:
        return f"{visible}\n\n{confirmation}", True
    return confirmation, True
