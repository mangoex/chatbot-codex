"""Bot configuration resolution for multi-bot routing."""
from dataclasses import dataclass

from app import config, db, secure_store


@dataclass(frozen=True)
class BotContext:
    id: int
    client_id: int | None
    slug: str
    name: str
    whatsapp_phone_number_id: str
    whatsapp_access_token: str
    display_phone_number: str = ""
    openai_model: str = ""


def default_bot() -> BotContext:
    return BotContext(
        id=1,
        client_id=1,
        slug=config.DEFAULT_BOT_SLUG or "asistto",
        name="Asistto",
        whatsapp_phone_number_id=config.WHATSAPP_PHONE_NUMBER_ID,
        whatsapp_access_token=config.WHATSAPP_API_TOKEN,
        display_phone_number="",
        openai_model=config.OPENAI_MODEL,
    )


def _from_row(row: dict) -> BotContext:
    return BotContext(
        id=int(row["bot_id"]),
        client_id=int(row["client_id"]) if row.get("client_id") else None,
        slug=row["slug"],
        name=row["name"],
        whatsapp_phone_number_id=row["phone_number_id"],
        whatsapp_access_token=row.get("whatsapp_access_token") or config.WHATSAPP_API_TOKEN,
        display_phone_number=row.get("display_phone_number") or "",
        openai_model=row.get("openai_model") or config.OPENAI_MODEL,
    )


async def _whatsapp_cloud_token(bot_id: int) -> str:
    integration = await db.get_active_bot_integration(bot_id, "whatsapp_cloud")
    if not integration:
        return ""
    encrypted_values = await db.get_integration_secret_values(int(integration["id"]))
    for name in ("access_token", "whatsapp_access_token", "token"):
        encrypted = encrypted_values.get(name)
        if encrypted:
            token = secure_store.decrypt_secret(encrypted)
            if token:
                return token
    return ""


async def resolve_by_phone_number_id(phone_number_id: str | None) -> BotContext:
    if phone_number_id:
        row = await db.get_bot_by_phone_number_id(phone_number_id)
        if row:
            if not row.get("whatsapp_access_token"):
                row = {**row, "whatsapp_access_token": await _whatsapp_cloud_token(int(row["bot_id"]))}
            return _from_row(row)
    return default_bot()
