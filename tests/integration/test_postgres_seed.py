"""Integración contra Postgres con semilla ficticia. No usa datos de clientes."""
from __future__ import annotations

import pytest

from app import db

pytestmark = pytest.mark.integration


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
