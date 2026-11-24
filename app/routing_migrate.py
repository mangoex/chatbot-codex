"""Traduce la configuración actual a conexiones y reglas. Idempotente y reversible."""
from __future__ import annotations

import logging

from app import db, routing_decision as decision

log = logging.getLogger("whatsapp-bot")

SCHEMA_SQL = """
ALTER TABLE bots ADD COLUMN IF NOT EXISTS routing_v2_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS external_connections (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    preset TEXT NOT NULL CHECK (preset IN ('grok_bot','kiwipos','webhook_custom')),
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    webhook_url TEXT NOT NULL DEFAULT '',
    allow_campaigns BOOLEAN NOT NULL DEFAULT FALSE,
    handoff_timeout_minutes INT NOT NULL DEFAULT 1440,
    legacy_integration_type TEXT,
    legacy_integration_id BIGINT,
    origin TEXT NOT NULL DEFAULT 'manual',
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_external_connections_legacy
    ON external_connections(bot_id, legacy_integration_type)
    WHERE origin = 'chg-012' AND legacy_integration_type IS NOT NULL;

CREATE TABLE IF NOT EXISTS external_connection_secrets (
    id BIGSERIAL PRIMARY KEY,
    connection_id BIGINT NOT NULL REFERENCES external_connections(id) ON DELETE CASCADE,
    secret_name TEXT NOT NULL,
    encrypted_value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(connection_id, secret_name)
);

CREATE TABLE IF NOT EXISTS routing_rules_v2 (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    position INT NOT NULL,
    match_kind TEXT NOT NULL CHECK (match_kind IN ('admin_phone','phone','tag','default')),
    match_value TEXT NOT NULL DEFAULT '',
    handler TEXT NOT NULL CHECK (handler IN ('asistto','grok_bot','external_agent','routing_webhook','silence')),
    connection_id BIGINT REFERENCES external_connections(id) ON DELETE SET NULL,
    applies_to TEXT NOT NULL DEFAULT 'all' CHECK (applies_to IN ('all','text')),
    record_history BOOLEAN NOT NULL DEFAULT FALSE,
    webhook_url TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    origin TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(bot_id, position)
);

CREATE TABLE IF NOT EXISTS conversation_attendants (
    bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    wa_id TEXT NOT NULL,
    attendant TEXT NOT NULL CHECK (attendant IN ('asistto','connection')),
    connection_id BIGINT REFERENCES external_connections(id) ON DELETE SET NULL,
    reason TEXT NOT NULL DEFAULT '',
    handoff_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (bot_id, wa_id)
);

CREATE TABLE IF NOT EXISTS routing_v2_migration_state (
    bot_id BIGINT PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE,
    source_hash TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'chg-012',
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""


async def reconcile_all() -> None:
    if db._pool is None:
        return
    async with db.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
        bots = await conn.fetch("SELECT id FROM bots ORDER BY id")
        for bot in bots:
            await _reconcile_bot(conn, int(bot["id"]))


async def reverse_all() -> None:
    """Borra solo lo creado por la migración y apaga el flag. No toca bot_integrations."""
    if db._pool is None:
        return
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM routing_rules_v2 WHERE origin = $1", decision.ORIGIN)
        await conn.execute("DELETE FROM external_connections WHERE origin = $1", decision.ORIGIN)
        await conn.execute("DELETE FROM routing_v2_migration_state WHERE origin = $1", decision.ORIGIN)
        await conn.execute("UPDATE bots SET routing_v2_enabled = FALSE")


async def _reconcile_bot(conn, bot_id: int) -> None:
    snapshot = await _snapshot(conn, bot_id)
    connections, rules = decision.translate(snapshot)
    digest = decision.snapshot_hash(snapshot)
    by_type: dict[str, int] = {}
    kept_ids: list[int] = []
    for draft in connections:
        row = await conn.fetchrow(
            """
            INSERT INTO external_connections(
                bot_id, preset, name, enabled, webhook_url, allow_campaigns,
                handoff_timeout_minutes, legacy_integration_type, legacy_integration_id, origin
            )
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (bot_id, legacy_integration_type) WHERE origin = 'chg-012' AND legacy_integration_type IS NOT NULL
            DO UPDATE SET
                preset = EXCLUDED.preset,
                name = EXCLUDED.name,
                enabled = EXCLUDED.enabled,
                webhook_url = EXCLUDED.webhook_url,
                allow_campaigns = EXCLUDED.allow_campaigns,
                handoff_timeout_minutes = EXCLUDED.handoff_timeout_minutes,
                legacy_integration_id = EXCLUDED.legacy_integration_id,
                updated_at = now()
            RETURNING id
            """,
            bot_id,
            draft.preset,
            draft.name,
            draft.enabled,
            draft.webhook_url,
            draft.allow_campaigns,
            draft.handoff_timeout_minutes,
            draft.legacy_integration_type,
            draft.legacy_integration_id,
            decision.ORIGIN,
        )
        by_type[draft.legacy_integration_type] = int(row["id"])
        kept_ids.append(int(row["id"]))
        await _copy_secrets(conn, draft.legacy_integration_id, int(row["id"]))

    if kept_ids:
        await conn.execute(
            """
            DELETE FROM external_connections
            WHERE bot_id = $1 AND origin = $2 AND id <> ALL($3::bigint[])
            """,
            bot_id,
            decision.ORIGIN,
            kept_ids,
        )
    else:
        await conn.execute(
            "DELETE FROM external_connections WHERE bot_id = $1 AND origin = $2",
            bot_id,
            decision.ORIGIN,
        )

    previous = await conn.fetchval(
        "SELECT source_hash FROM routing_v2_migration_state WHERE bot_id = $1",
        bot_id,
    )
    if previous == digest:
        return
    await conn.execute(
        "DELETE FROM routing_rules_v2 WHERE bot_id = $1 AND origin = $2",
        bot_id,
        decision.ORIGIN,
    )
    for rule in rules:
        connection_id = by_type.get(rule.legacy_integration_type or "")
        if rule.handler in {"asistto", "silence"}:
            connection_id = None
        await conn.execute(
            """
            INSERT INTO routing_rules_v2(
                bot_id, position, match_kind, match_value, handler, connection_id,
                applies_to, record_history, webhook_url, enabled, origin
            )
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,TRUE,$10)
            """,
            bot_id,
            rule.position,
            rule.match_kind,
            rule.match_value,
            rule.handler,
            connection_id,
            rule.applies_to,
            rule.record_history,
            rule.webhook_url,
            decision.ORIGIN,
        )
    await conn.execute(
        """
        INSERT INTO routing_v2_migration_state(bot_id, source_hash, origin)
        VALUES($1,$2,$3)
        ON CONFLICT (bot_id) DO UPDATE SET
            source_hash = EXCLUDED.source_hash,
            origin = EXCLUDED.origin,
            updated_at = now()
        """,
        bot_id,
        digest,
        decision.ORIGIN,
    )


async def _copy_secrets(conn, integration_id: int, connection_id: int) -> None:
    rows = await conn.fetch(
        """
        SELECT secret_name, encrypted_value
        FROM integration_secrets
        WHERE integration_id = $1
          AND secret_name IN ('webhook_secret','webhook_auth_token','auth_header')
        """,
        integration_id,
    )
    copied = {row["secret_name"]: row["encrypted_value"] for row in rows}
    reply_key = copied.get("webhook_secret") or copied.get("webhook_auth_token")
    hmac_secret = copied.get("webhook_secret") or copied.get("webhook_auth_token") or copied.get("auth_header")
    for name, value in (("reply_api_key", reply_key), ("hmac_secret", hmac_secret)):
        if not value:
            continue
        await conn.execute(
            """
            INSERT INTO external_connection_secrets(connection_id, secret_name, encrypted_value)
            VALUES($1,$2,$3)
            ON CONFLICT (connection_id, secret_name) DO UPDATE SET
                encrypted_value = EXCLUDED.encrypted_value,
                updated_at = now()
            """,
            connection_id,
            name,
            value,
        )


async def _snapshot(conn, bot_id: int) -> decision.BotSnapshot:
    rows = await conn.fetch(
        """
        SELECT id, integration_type, enabled, config
        FROM bot_integrations
        WHERE bot_id = $1
          AND integration_type IN ('attention_policy','routing_rules','grok_bot','external_agent')
        ORDER BY updated_at DESC, id DESC
        """,
        bot_id,
    )
    found: dict[str, decision.IntegrationView] = {}
    for row in rows:
        kind = row["integration_type"]
        if kind in found:
            continue
        found[kind] = decision.IntegrationView(
            id=int(row["id"]),
            type=kind,
            enabled=bool(row["enabled"]),
            config=db._normalize_config(row["config"]),
        )
    return decision.BotSnapshot(
        bot_id=bot_id,
        attention=found.get("attention_policy"),
        routing=found.get("routing_rules"),
        grok=found.get("grok_bot"),
        external=found.get("external_agent"),
    )


async def load_runtime(conn, bot_id: int) -> tuple[list[decision.LiveRule], dict[int, decision.LiveConnection]]:
    connections: dict[int, decision.LiveConnection] = {}
    for row in await conn.fetch(
        """
        SELECT id, preset, enabled, webhook_url, allow_campaigns, handoff_timeout_minutes
        FROM external_connections
        WHERE bot_id = $1
        """,
        bot_id,
    ):
        connections[int(row["id"])] = decision.LiveConnection(
            id=int(row["id"]),
            preset=row["preset"],
            enabled=bool(row["enabled"]),
            webhook_url=row["webhook_url"] or "",
            allow_campaigns=bool(row["allow_campaigns"]),
            handoff_timeout_minutes=int(row["handoff_timeout_minutes"] or 1440),
        )
    rules = []
    for row in await conn.fetch(
        """
        SELECT position, match_kind, match_value, handler, connection_id, applies_to,
               record_history, webhook_url, enabled
        FROM routing_rules_v2
        WHERE bot_id = $1
        ORDER BY position
        """,
        bot_id,
    ):
        rules.append(
            decision.LiveRule(
                position=int(row["position"]),
                match_kind=row["match_kind"],
                match_value=row["match_value"] or "",
                handler=row["handler"],
                connection_id=int(row["connection_id"]) if row["connection_id"] else None,
                applies_to=row["applies_to"],
                record_history=bool(row["record_history"]),
                webhook_url=row["webhook_url"] or "",
                enabled=bool(row["enabled"]),
            )
        )
    return rules, connections
