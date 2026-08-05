from __future__ import annotations
"""Runtime skill toggles for bot-specific capabilities."""
import logging

from app import db

log = logging.getLogger("whatsapp-bot")


async def skill_enabled(
    bot_id: int | None,
    skill_type: str,
    default: bool = True,
) -> bool:
    if not bot_id:
        return default
    try:
        row = await db.get_bot_skill(bot_id, skill_type)
    except Exception:
        log.exception("No se pudo leer la habilidad %s del bot %s", skill_type, bot_id)
        return default
    if row is None:
        return default
    return bool(row.get("enabled"))


async def calendar_skill_enabled(bot_id: int | None) -> bool:
    # Calendar is an opt-in capability scoped to one bot. Missing configuration
    # or a lookup failure must never expose another bot's scheduling behavior.
    if not bot_id:
        return False
    if not await skill_enabled(bot_id, "google_calendar", default=False):
        return False
    try:
        integration = await db.get_active_bot_integration(bot_id, "google_calendar")
    except Exception:
        log.exception("No se pudo leer la integracion google_calendar del bot %s", bot_id)
        return False
    return integration is not None


async def webhook_skill_enabled(bot_id: int | None) -> bool:
    return await skill_enabled(bot_id, "webhook", default=False)


async def external_api_skill_enabled(bot_id: int | None) -> bool:
    return await skill_enabled(bot_id, "external_api", default=False)


async def crm_skill_enabled(bot_id: int | None) -> bool:
    return await skill_enabled(bot_id, "crm", default=False)
