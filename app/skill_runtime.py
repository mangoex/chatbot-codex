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
    return await skill_enabled(bot_id, "google_calendar", default=True)

