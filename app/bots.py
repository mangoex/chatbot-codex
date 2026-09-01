from __future__ import annotations
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
    status: str = "active"
    admin_phone_numbers: tuple[str, ...] = ()


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
        status="active",
    )


def _from_row(row: dict) -> BotContext:
    bot_id = int(row["bot_id"])
    token = row.get("whatsapp_access_token") or ""
    if bot_id == 1 and not token:
        token = config.WHATSAPP_API_TOKEN
    return BotContext(
        id=bot_id,
        client_id=int(row["client_id"]) if row.get("client_id") else None,
        slug=row["slug"],
        name=row["name"],
        whatsapp_phone_number_id=row["phone_number_id"],
        whatsapp_access_token=token,
        display_phone_number=row.get("display_phone_number") or "",
        openai_model=row.get("openai_model") or config.OPENAI_MODEL,
        status=row.get("status") or "active",
        admin_phone_numbers=tuple(row.get("admin_phone_numbers") or ()),
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


async def resolve_by_phone_number_id(phone_number_id: str | None) -> BotContext | None:
    if phone_number_id:
        row = await db.get_bot_by_phone_number_id(phone_number_id)
        if row:
            if not row.get("whatsapp_access_token"):
                row = {**row, "whatsapp_access_token": await _whatsapp_cloud_token(int(row["bot_id"]))}
            return _from_row(row)
    return None


async def resolve_by_bot_id(bot_id: int | None) -> BotContext | None:
    if bot_id and bot_id != 1:
        row = await db.get_bot(bot_id)
        if row:
            token = await _whatsapp_cloud_token(bot_id)
            wa_row = await db.get_bot_whatsapp_number(bot_id)
            phone_number_id = wa_row.get("phone_number_id", "") if wa_row else ""
            display_num = wa_row.get("display_phone_number", "") if wa_row else ""
            full_row = {
                "bot_id": bot_id,
                "client_id": row.get("client_id"),
                "slug": row.get("slug"),
                "name": row.get("name"),
                "phone_number_id": phone_number_id,
                "whatsapp_access_token": token,
                "display_phone_number": display_num,
                "openai_model": row.get("openai_model"),
                "status": row.get("status"),
                "admin_phone_numbers": wa_row.get("admin_phone_numbers", ()) if wa_row else (),
            }
            return _from_row(full_row)
        return None
    if bot_id == 1 or bot_id is None:
        return default_bot()
    return None
