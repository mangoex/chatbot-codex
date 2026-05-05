"""Creacion de citas en Google Calendar usando OAuth refresh token."""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app import config

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
    body = {
        "timeMin": check_start.isoformat(),
        "timeMax": check_end.isoformat(),
        "timeZone": config.GOOGLE_CALENDAR_TIMEZONE,
        "items": [{"id": config.GOOGLE_CALENDAR_ID}],
    }
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{_CALENDAR_API}/freeBusy", headers=headers, json=body)
        resp.raise_for_status()
        payload = resp.json()
    calendars = payload.get("calendars", {})
    busy = calendars.get(config.GOOGLE_CALENDAR_ID, {}).get("busy", [])
    return not busy


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
        await _insert_event(token, data, start, end)
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
