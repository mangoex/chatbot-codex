"""Integración contra Postgres con semilla ficticia. No usa datos de clientes."""
from __future__ import annotations

import os

import asyncpg
import pytest

from app import config, db

pytestmark = pytest.mark.integration

URL_LOCAL = "postgresql://asistto:asistto_test_only@127.0.0.1:5432/asistto_test"


def _url_de_prueba() -> str:
    url = os.getenv("TEST_DATABASE_URL", URL_LOCAL)
    destino = url.split("@")[-1]
    if not url.startswith("postgres") or "asistto_test" not in destino:
        pytest.fail("TEST_DATABASE_URL debe apuntar a una base llamada asistto_test")
    return url


@pytest.fixture
async def base_ficticia():
    url = _url_de_prueba()
    try:
        sonda = await asyncpg.connect(url)
    except Exception as exc:
        if os.getenv("REQUIRE_TEST_DATABASE") == "1":
            pytest.fail(f"Postgres de prueba no está disponible: {exc}")
        pytest.skip(f"Postgres de prueba no está disponible: {exc}")
    await sonda.close()

    anterior = {
        "DATABASE_URL": config.DATABASE_URL,
        "DEFAULT_BOT_SLUG": config.DEFAULT_BOT_SLUG,
        "WHATSAPP_PHONE_NUMBER_ID": config.WHATSAPP_PHONE_NUMBER_ID,
    }
    config.DATABASE_URL = url
    config.DEFAULT_BOT_SLUG = "asistto-ficticio"
    config.WHATSAPP_PHONE_NUMBER_ID = ""
    await db.init_pool()
    try:
        async with db._pool.acquire() as conn:
            await conn.execute("DROP SCHEMA public CASCADE")
            await conn.execute("CREATE SCHEMA public")
            # run_migrations altera tablas que en producción ya existen.
            # En una base vacía el esquema actual se aplica primero.
            await conn.execute(db.SCHEMA_SQL)
        await db.run_migrations()
        async with db._pool.acquire() as conn:
            cliente = await conn.fetchrow(
                """
                INSERT INTO clients(name, slug)
                VALUES('Taquería El Ejemplo', 'taqueria-ejemplo')
                RETURNING id
                """
            )
            taqueria = await conn.fetchrow(
                """
                INSERT INTO bots(client_id, slug, name, description, status)
                VALUES($1, 'bot-taqueria-ejemplo', 'Bot Taquería Ejemplo', 'Semilla ficticia', 'active')
                RETURNING id
                """,
                cliente["id"],
            )
            cafeteria = await conn.fetchrow(
                """
                INSERT INTO bots(client_id, slug, name, description, status)
                VALUES($1, 'bot-cafeteria-ejemplo', 'Bot Cafetería Ejemplo', 'Semilla ficticia', 'active')
                RETURNING id
                """,
                cliente["id"],
            )
            await conn.execute(
                """
                INSERT INTO bot_whatsapp_numbers(bot_id, phone_number_id, display_phone_number)
                VALUES($1, 'phone-ficticio-taqueria', '5215550100001')
                """,
                taqueria["id"],
            )
            await conn.execute(
                """
                INSERT INTO contacts(bot_id, wa_id, name, business, tags)
                VALUES($1, '5215550100099', 'Cliente Ficticio', 'Negocio Imaginario', 'demo')
                """,
                taqueria["id"],
            )
        yield {"taqueria": int(taqueria["id"]), "cafeteria": int(cafeteria["id"])}
    finally:
        await db.close_pool()
        db._pool = None
        config.DATABASE_URL = anterior["DATABASE_URL"]
        config.DEFAULT_BOT_SLUG = anterior["DEFAULT_BOT_SLUG"]
        config.WHATSAPP_PHONE_NUMBER_ID = anterior["WHATSAPP_PHONE_NUMBER_ID"]


async def test_la_semilla_ficticia_queda_aislada_por_bot(base_ficticia):
    taqueria = base_ficticia["taqueria"]
    cafeteria = base_ficticia["cafeteria"]
    wa_id = "5215550100099"

    await db.save_message(wa_id, "user", "Quiero dos tacos de ejemplo", bot_id=taqueria, sync_chatwoot=False)
    await db.save_message(wa_id, "user", "Un café de ejemplo", bot_id=cafeteria, sync_chatwoot=False)

    historial_taqueria = await db.get_history(wa_id, 10, bot_id=taqueria)
    historial_cafeteria = await db.get_history(wa_id, 10, bot_id=cafeteria)
    assert [m["content"] for m in historial_taqueria] == ["Quiero dos tacos de ejemplo"]
    assert [m["content"] for m in historial_cafeteria] == ["Un café de ejemplo"]

    async with db._pool.acquire() as conn:
        contacto = await conn.fetchrow(
            "SELECT name, business FROM contacts WHERE bot_id = $1 AND wa_id = $2",
            taqueria,
            wa_id,
        )
        ajeno = await conn.fetchrow(
            "SELECT 1 FROM contacts WHERE bot_id = $1 AND wa_id = $2",
            cafeteria,
            wa_id,
        )
        predeterminado = await conn.fetchval(
            "SELECT slug FROM bots WHERE slug = 'asistto-ficticio'"
        )
    assert contacto["name"] == "Cliente Ficticio"
    assert contacto["business"] == "Negocio Imaginario"
    assert ajeno is None
    assert predeterminado == "asistto-ficticio"
