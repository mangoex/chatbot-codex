"""Migración idempotente y reversible sobre Postgres de prueba."""
from __future__ import annotations

import json

import pytest

from app import db, routing_decision, routing_migrate

pytestmark = pytest.mark.integration


async def _integracion(bot_id: int, kind: str, config: dict, secret_name: str | None = None) -> None:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO bot_integrations(bot_id, integration_type, name, enabled, config)
            VALUES($1,$2,$3,TRUE,$4::jsonb)
            RETURNING id
            """,
            bot_id,
            kind,
            kind,
            json.dumps(config),
        )
        if secret_name:
            await conn.execute(
                """
                INSERT INTO integration_secrets(integration_id, secret_name, encrypted_value)
                VALUES($1,$2,$3)
                """,
                row["id"],
                secret_name,
                "cifrado-ficticio",
            )


async def test_la_migracion_es_idempotente_reversible_y_equivalente(base_ficticia):
    bot_id = base_ficticia["taqueria"]
    await _integracion(
        bot_id,
        "attention_policy",
        {"version": 1, "default_handler": "external_agent", "admin_grok_enabled": True, "admin_phone_numbers": ["5215550100001"]},
    )
    await _integracion(bot_id, "grok_bot", {"webhook_url": "https://grok.example/hook", "handle_inbound": False, "allow_campaigns": False}, "webhook_secret")
    await _integracion(bot_id, "external_agent", {"webhook_url": "https://kiwi.example/hook", "handle_inbound": True}, "webhook_secret")
    await _integracion(
        bot_id,
        "routing_rules",
        {"rules": [{"action": "forward_and_bypass", "webhook_url": "https://app.example/equipo", "phone_numbers": ["5215550100002"]}]},
        "webhook_auth_token",
    )

    await routing_migrate.reconcile_all()
    await routing_migrate.reconcile_all()

    async with db.acquire() as conn:
        conexiones = await conn.fetchval(
            "SELECT COUNT(*) FROM external_connections WHERE bot_id = $1 AND origin = 'chg-012'",
            bot_id,
        )
        reglas = await conn.fetchval(
            "SELECT COUNT(*) FROM routing_rules_v2 WHERE bot_id = $1 AND origin = 'chg-012'",
            bot_id,
        )
        secreto = await conn.fetchval(
            """
            SELECT encrypted_value FROM external_connection_secrets s
            JOIN external_connections c ON c.id = s.connection_id
            WHERE c.bot_id = $1 AND c.preset = 'kiwipos' AND s.secret_name = 'reply_api_key'
            """,
            bot_id,
        )
        flag = await conn.fetchval("SELECT routing_v2_enabled FROM bots WHERE id = $1", bot_id)
        snapshot = await routing_migrate._snapshot(conn, bot_id)
        loaded_rules, loaded_connections = await routing_migrate.load_runtime(conn, bot_id)
    assert conexiones == 3
    assert reglas >= 3
    assert secreto == "cifrado-ficticio"
    assert flag is False
    for wa_id in ("5215550100001", "525550100001", "5215550100002", "5215550100099"):
        legado = routing_decision.legacy_handler(snapshot, wa_id)
        nuevo = routing_decision.decide(loaded_rules, loaded_connections, wa_id).handler
        assert nuevo == legado, (wa_id, legado, nuevo)

    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE bot_integrations SET config = $2::jsonb WHERE bot_id = $1 AND integration_type = 'external_agent'",
            bot_id,
            json.dumps({"webhook_url": "https://kiwi.example/nuevo", "handle_inbound": True}),
        )
    await routing_migrate.reconcile_all()
    async with db.acquire() as conn:
        url = await conn.fetchval(
            "SELECT webhook_url FROM external_connections WHERE bot_id = $1 AND preset = 'kiwipos'",
            bot_id,
        )
    assert url == "https://kiwi.example/nuevo"

    await routing_migrate.reverse_all()
    async with db.acquire() as conn:
        quedan = await conn.fetchval("SELECT COUNT(*) FROM external_connections WHERE origin = 'chg-012'")
        legado = await conn.fetchval(
            "SELECT COUNT(*) FROM bot_integrations WHERE bot_id = $1",
            bot_id,
        )
        flag = await conn.fetchval("SELECT routing_v2_enabled FROM bots WHERE id = $1", bot_id)
    assert quedan == 0
    assert legado == 4
    assert flag is False
