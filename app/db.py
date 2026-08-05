from __future__ import annotations
"""Acceso a Postgres: pool, schema idempotente, lectura/escritura de historial."""
import json

import asyncpg
from app import config

_pool: asyncpg.Pool | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS clients (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','paused','archived')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    password_hash TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','disabled')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS client_users (
    client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('agency_admin','client_admin','client_viewer')),
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (client_id, user_id)
);

CREATE TABLE IF NOT EXISTS bots (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT REFERENCES clients(id) ON DELETE CASCADE,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('draft','active','paused','archived')),
    openai_model TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bot_whatsapp_numbers (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    phone_number_id TEXT UNIQUE NOT NULL,
    display_phone_number TEXT,
    whatsapp_access_token TEXT,
    business_id TEXT,
    waba_id TEXT,
    meta_app_id TEXT,
    meta_config_id TEXT,
    connected_at TIMESTAMPTZ,
    last_sync_status TEXT,
    last_sync_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','paused','archived')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bot_prompts (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    version INT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','active','archived')),
    content TEXT NOT NULL,
    pbd_constitution TEXT,
    pbd_specs TEXT,
    pbd_test_suite TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    published_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_bot_prompts_bot_status
    ON bot_prompts(bot_id, status, version DESC);

CREATE TABLE IF NOT EXISTS bot_knowledge (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','draft','archived')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bot_skills (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    skill_type TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(bot_id, skill_type)
);

CREATE TABLE IF NOT EXISTS bot_integrations (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    integration_type TEXT NOT NULL,
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS integration_secrets (
    id BIGSERIAL PRIMARY KEY,
    integration_id BIGINT NOT NULL REFERENCES bot_integrations(id) ON DELETE CASCADE,
    secret_name TEXT NOT NULL,
    encrypted_value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(integration_id, secret_name)
);

CREATE TABLE IF NOT EXISTS chatwoot_webhook_events (
    id BIGSERIAL PRIMARY KEY,
    integration_id BIGINT NOT NULL REFERENCES bot_integrations(id) ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(integration_id, event_key)
);

CREATE TABLE IF NOT EXISTS chatwoot_handoffs (
    bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    wa_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'human_active'
        CHECK (status IN ('human_active')),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (bot_id, wa_id)
);

CREATE TABLE IF NOT EXISTS leads (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    wa_id TEXT NOT NULL,
    nombre TEXT,
    negocio TEXT,
    qualification_status TEXT NOT NULL DEFAULT 'en_progreso'
        CHECK (qualification_status IN ('en_progreso', 'calificado', 'descalificado')),
    disqualify_reason TEXT,
    action_link_sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_bot_wa_unique
    ON leads(bot_id, wa_id);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(qualification_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_bot_status ON leads(bot_id, qualification_status, created_at DESC);

CREATE TABLE IF NOT EXISTS pending_follow_ups (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    wa_id TEXT NOT NULL,
    send_after TIMESTAMPTZ NOT NULL,
    sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_follow_ups_bot_wa_unique
    ON pending_follow_ups(bot_id, wa_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_due
    ON pending_follow_ups(send_after) WHERE sent = FALSE;

CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    wa_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conv_wa_id_ts ON conversations(wa_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_bot_wa_ts ON conversations(bot_id, wa_id, created_at DESC);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    processed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_appointments (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    wa_id TEXT NOT NULL,
    google_event_id TEXT UNIQUE NOT NULL,
    calendar_id TEXT NOT NULL,
    attendee_name TEXT,
    topic TEXT,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled','cancelled')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    cancelled_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_calendar_appts_wa_status
    ON calendar_appointments(wa_id, status, start_at);
CREATE INDEX IF NOT EXISTS idx_calendar_appts_bot_status
    ON calendar_appointments(bot_id, wa_id, status, start_at);

CREATE TABLE IF NOT EXISTS escalations (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    wa_id TEXT NOT NULL,
    customer_name TEXT,
    city TEXT,
    product TEXT,
    purchase_date TEXT,
    issue_summary TEXT,
    reason TEXT NOT NULL,
    reason_detail TEXT,
    media_count INT DEFAULT 0,
    last_media_type TEXT,
    conversation_excerpt TEXT,
    status TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (status IN ('pendiente','en_proceso','resuelto')),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_esc_status_ts
    ON escalations(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_esc_wa_status
    ON escalations(wa_id, status);
CREATE INDEX IF NOT EXISTS idx_esc_bot_wa_status
    ON escalations(bot_id, wa_id, status);

CREATE TABLE IF NOT EXISTS external_action_runs (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    wa_id TEXT,
    action_type TEXT NOT NULL,
    integration_id BIGINT REFERENCES bot_integrations(id) ON DELETE SET NULL,
    operation TEXT,
    status TEXT NOT NULL CHECK (status IN ('success','rejected','failed')),
    request_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_external_action_runs_bot_ts
    ON external_action_runs(bot_id, created_at DESC);

CREATE TABLE IF NOT EXISTS contacts (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE CASCADE,
    wa_id TEXT NOT NULL,
    name TEXT,
    business TEXT,
    tags TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(bot_id, wa_id)
);
CREATE INDEX IF NOT EXISTS idx_contacts_bot_search ON contacts(bot_id, name, wa_id);

CREATE TABLE IF NOT EXISTS broadcasts (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    template_name TEXT NOT NULL,
    language_code TEXT NOT NULL DEFAULT 'es_MX',
    variable_mappings JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_recipients INT DEFAULT 0,
    sent_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'running', 'completed', 'paused', 'failed')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS broadcast_recipients (
    id BIGSERIAL PRIMARY KEY,
    broadcast_id BIGINT REFERENCES broadcasts(id) ON DELETE CASCADE,
    wa_id TEXT NOT NULL,
    contact_name TEXT,
    contact_business TEXT,
    status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'sent', 'failed')),
    error_message TEXT,
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_recipients_exec ON broadcast_recipients(broadcast_id, status);
"""


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5)


async def close_pool() -> None:
    if _pool:
        await _pool.close()


async def check_health() -> bool:
    if not _pool:
        return False
    try:
        async with _pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception:
        return False


async def run_migrations() -> None:
    async with _pool.acquire() as conn:
        await conn.execute("ALTER TABLE bot_prompts ADD COLUMN IF NOT EXISTS pbd_constitution TEXT")
        await conn.execute("ALTER TABLE bot_prompts ADD COLUMN IF NOT EXISTS pbd_specs TEXT")
        await conn.execute("ALTER TABLE bot_prompts ADD COLUMN IF NOT EXISTS pbd_test_suite TEXT")

        # Existing deployments may already have these tables without bot_id.
        # Add the nullable column before SCHEMA_SQL creates bot_id indexes.
        for table in (
            "leads",
            "pending_follow_ups",
            "conversations",
            "processed_messages",
            "calendar_appointments",
            "escalations",
        ):
            await conn.execute(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('{table}') IS NOT NULL THEN
                        ALTER TABLE {table} ADD COLUMN IF NOT EXISTS bot_id BIGINT;
                    END IF;
                END $$;
                """
            )
        await conn.execute(SCHEMA_SQL)
        # Migrar bots de openrouter/free a openai/gpt-4o-mini
        await conn.execute(
            "UPDATE bots SET openai_model = 'openai/gpt-4o-mini' WHERE openai_model = 'openrouter/free'"
        )
        await conn.execute(
            "ALTER TABLE leads ADD COLUMN IF NOT EXISTS action_link_sent BOOLEAN NOT NULL DEFAULT FALSE"
        )
        for column, definition in (
            ("business_id", "TEXT"),
            ("waba_id", "TEXT"),
            ("meta_app_id", "TEXT"),
            ("meta_config_id", "TEXT"),
            ("connected_at", "TIMESTAMPTZ"),
            ("last_sync_status", "TEXT"),
            ("last_sync_at", "TIMESTAMPTZ"),
        ):
            await conn.execute(
                f"ALTER TABLE bot_whatsapp_numbers ADD COLUMN IF NOT EXISTS {column} {definition}"
            )
        await _migrate_tenant_scoped_contact_state(conn)
        # Setup RAG tables and extension
        from app import rag
        await rag.setup_rag_tables(conn)
    await ensure_default_bot()


async def _migrate_tenant_scoped_contact_state(conn) -> None:
    """Move legacy globally-unique contact state to bot-scoped uniqueness."""
    for table in ("leads", "pending_follow_ups"):
        await conn.execute(
            f"UPDATE {table} SET bot_id = 1 WHERE bot_id IS NULL"
        )

    await conn.execute(
        """
        DELETE FROM leads a
        USING leads b
        WHERE a.id < b.id
          AND a.wa_id = b.wa_id
          AND a.bot_id IS NOT DISTINCT FROM b.bot_id
        """
    )
    await conn.execute(
        """
        DELETE FROM pending_follow_ups a
        USING pending_follow_ups b
        WHERE a.id < b.id
          AND a.wa_id = b.wa_id
          AND a.bot_id IS NOT DISTINCT FROM b.bot_id
        """
    )
    await conn.execute("ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_wa_id_key")
    await conn.execute(
        "ALTER TABLE pending_follow_ups DROP CONSTRAINT IF EXISTS pending_follow_ups_wa_id_key"
    )
    await conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_bot_wa_unique ON leads(bot_id, wa_id)"
    )
    await conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_follow_ups_bot_wa_unique ON pending_follow_ups(bot_id, wa_id)"
    )


async def purge_old(ttl_days: int) -> int:
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM conversations WHERE created_at < now() - make_interval(days => $1)",
            int(ttl_days),
        )
        return int(result.split()[-1]) if result else 0


async def was_processed(message_id: str) -> bool:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM processed_messages WHERE message_id = $1", message_id
        )
        return row is not None


async def mark_processed(message_id: str, bot_id: int | None = None) -> bool:
    async with _pool.acquire() as conn:
        if bot_id is not None:
            result = await conn.execute(
                "INSERT INTO processed_messages(message_id, bot_id) VALUES($1, $2) "
                "ON CONFLICT DO NOTHING",
                message_id, bot_id,
            )
        else:
            result = await conn.execute(
                "INSERT INTO processed_messages(message_id) VALUES($1) "
                "ON CONFLICT DO NOTHING",
                message_id,
            )
        inserted = int(result.split()[-1]) if result else 0
        return inserted > 0


async def get_history(wa_id: str, limit: int, bot_id: int | None = None) -> list[dict]:
    """Devuelve los últimos `limit` mensajes en orden cronológico ascendente."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content FROM conversations
            WHERE wa_id = $1
              AND (
                $3::bigint IS NULL
                OR bot_id = $3
                OR ($3 = 1 AND bot_id IS NULL)
              )
            ORDER BY created_at DESC LIMIT $2
            """,
            wa_id, limit, bot_id,
        )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def list_conversation_threads(limit: int = 100, bot_id: int | None = None) -> list[dict]:
    """Lista conversaciones agrupadas por wa_id con ultimo mensaje y metadata de lead."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH last_messages AS (
                SELECT DISTINCT ON (wa_id)
                    wa_id, role, content, created_at
                FROM conversations
                WHERE (
                    $1::bigint IS NULL
                    OR bot_id = $1
                    OR ($1 = 1 AND bot_id IS NULL)
                )
                ORDER BY wa_id, created_at DESC
            ),
            counts AS (
                SELECT wa_id, COUNT(*) AS message_count
                FROM conversations
                WHERE (
                    $1::bigint IS NULL
                    OR bot_id = $1
                    OR ($1 = 1 AND bot_id IS NULL)
                )
                GROUP BY wa_id
            )
            SELECT
                lm.wa_id,
                lm.role AS last_role,
                lm.content AS last_content,
                lm.created_at AS last_message_at,
                counts.message_count,
                leads.nombre,
                leads.negocio,
                leads.qualification_status
            FROM last_messages lm
            JOIN counts ON counts.wa_id = lm.wa_id
            LEFT JOIN leads
              ON leads.wa_id = lm.wa_id
             AND (
                leads.bot_id = $1
                OR ($1 = 1 AND leads.bot_id IS NULL)
             )
            ORDER BY lm.created_at DESC
            LIMIT $2
            """,
            bot_id,
            limit,
        )
    return [dict(r) for r in rows]


async def list_conversation_messages(
    wa_id: str,
    limit: int = 100,
    bot_id: int | None = None,
) -> list[dict]:
    """Devuelve los mensajes de una conversacion en orden cronologico."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content, created_at
            FROM conversations
            WHERE wa_id = $1
              AND (
                $3::bigint IS NULL
                OR bot_id = $3
                OR ($3 = 1 AND bot_id IS NULL)
              )
            ORDER BY created_at DESC
            LIMIT $2
            """,
            wa_id,
            limit,
            bot_id,
        )
    return [dict(r) for r in reversed(rows)]


async def save_message(
    wa_id: str,
    role: str,
    content: str,
    bot_id: int | None = None,
    sync_chatwoot: bool = True,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO conversations(wa_id, role, content, bot_id) VALUES($1, $2, $3, $4)",
            wa_id, role, content, bot_id,
        )
    
    if bot_id and sync_chatwoot:
        import asyncio
        from app.chatwoot_client import sync_message_to_chatwoot
        
        # Determine name if available
        lead = await get_lead(wa_id, bot_id=bot_id)
        name = lead.get("nombre") if lead else wa_id
        
        asyncio.create_task(sync_message_to_chatwoot(bot_id, wa_id, name or wa_id, content, role))


async def find_pending_escalation(wa_id: str, bot_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM escalations WHERE wa_id=$1 AND bot_id=$2 AND status='pendiente' "
            "ORDER BY created_at DESC LIMIT 1",
            wa_id,
            bot_id,
        )
    return dict(row) if row else None


async def create_escalation(data: dict) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO escalations(
                wa_id, customer_name, city, product, purchase_date,
                issue_summary, reason, reason_detail, media_count,
                last_media_type, conversation_excerpt, bot_id
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            RETURNING id
            """,
            data.get("wa_id"),
            data.get("customer_name"),
            data.get("city"),
            data.get("product"),
            data.get("purchase_date"),
            data.get("issue_summary"),
            data["reason"],
            data.get("reason_detail"),
            data.get("media_count", 0),
            data.get("last_media_type"),
            data.get("conversation_excerpt"),
            data.get("bot_id"),
        )
    return row["id"]


async def bump_escalation(escalation_id: int, data: dict) -> None:
    """Actualiza una escalation existente con nueva info/contexto."""
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE escalations SET
                customer_name = COALESCE($2, customer_name),
                city = COALESCE($3, city),
                product = COALESCE($4, product),
                purchase_date = COALESCE($5, purchase_date),
                issue_summary = COALESCE($6, issue_summary),
                reason = COALESCE($7, reason),
                reason_detail = COALESCE($8, reason_detail),
                media_count = media_count + $9,
                last_media_type = COALESCE($10, last_media_type),
                conversation_excerpt = COALESCE($11, conversation_excerpt),
                bot_id = COALESCE($12, bot_id),
                updated_at = now()
            WHERE id = $1
            """,
            escalation_id,
            data.get("customer_name"),
            data.get("city"),
            data.get("product"),
            data.get("purchase_date"),
            data.get("issue_summary"),
            data.get("reason"),
            data.get("reason_detail"),
            int(data.get("media_count_delta", 0)),
            data.get("last_media_type"),
            data.get("conversation_excerpt"),
            data.get("bot_id"),
        )


async def list_escalations(status: str | None = None, limit: int = 200) -> list[dict]:
    query = "SELECT * FROM escalations"
    args: list = []
    if status:
        query += " WHERE status = $1"
        args.append(status)
    query += " ORDER BY created_at DESC LIMIT $%d" % (len(args) + 1)
    args.append(limit)
    async with _pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
    return [dict(r) for r in rows]


async def get_escalation(escalation_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM escalations WHERE id=$1", escalation_id)
    return dict(row) if row else None


async def update_escalation_status(
    escalation_id: int, status: str, notes: str | None = None
) -> None:
    async with _pool.acquire() as conn:
        if status == "resuelto":
            await conn.execute(
                "UPDATE escalations SET status=$2, notes=COALESCE($3, notes), "
                "resolved_at=now(), updated_at=now() WHERE id=$1",
                escalation_id, status, notes,
            )
        else:
            await conn.execute(
                "UPDATE escalations SET status=$2, notes=COALESCE($3, notes), "
                "updated_at=now() WHERE id=$1",
                escalation_id, status, notes,
            )


async def escalation_counts() -> dict:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT status, COUNT(*) AS n FROM escalations GROUP BY status"
        )
    return {r["status"]: r["n"] for r in rows}


async def upsert_lead(wa_id: str, bot_id: int | None = None, **kwargs) -> None:
    """Crea o actualiza el registro de lead. Solo actualiza los campos pasados."""
    if bot_id is None:
        raise ValueError("bot_id is required to upsert a lead")
    fields = {k: v for k, v in kwargs.items()
              if k in ("nombre", "negocio", "qualification_status",
                       "disqualify_reason", "action_link_sent")}
    if not fields:
        return
    set_clause = ", ".join(
        f"{col} = ${i + 3}" for i, col in enumerate(fields)
    )
    values = list(fields.values())
    async with _pool.acquire() as conn:
        await conn.execute(
            f"""
            INSERT INTO leads(wa_id, bot_id, {", ".join(fields)})
            VALUES($1, $2, {", ".join(f"${i+3}" for i in range(len(fields)))})
            ON CONFLICT (bot_id, wa_id) DO UPDATE SET
                {set_clause},
                updated_at = now()
            """,
            wa_id, bot_id, *values,
        )


async def get_lead(wa_id: str, bot_id: int | None = None) -> dict | None:
    if bot_id is None:
        raise ValueError("bot_id is required to read a lead")
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM leads
            WHERE wa_id = $1
              AND (
                $2::bigint IS NULL
                OR bot_id = $2
                OR ($2 = 1 AND bot_id IS NULL)
              )
            """,
            wa_id,
            bot_id,
        )
    return dict(row) if row else None


async def save_calendar_appointment(
    wa_id: str,
    google_event_id: str,
    calendar_id: str,
    attendee_name: str | None,
    topic: str | None,
    start_at,
    end_at,
    bot_id: int | None = None,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO calendar_appointments(
                wa_id, bot_id, google_event_id, calendar_id, attendee_name,
                topic, start_at, end_at
            )
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (google_event_id) DO UPDATE SET
                wa_id = EXCLUDED.wa_id,
                bot_id = COALESCE(EXCLUDED.bot_id, calendar_appointments.bot_id),
                calendar_id = EXCLUDED.calendar_id,
                attendee_name = EXCLUDED.attendee_name,
                topic = EXCLUDED.topic,
                start_at = EXCLUDED.start_at,
                end_at = EXCLUDED.end_at,
                status = 'scheduled',
                cancelled_at = NULL,
                updated_at = now()
            """,
            wa_id,
            bot_id,
            google_event_id,
            calendar_id,
            attendee_name,
            topic,
            start_at,
            end_at,
        )


async def list_active_calendar_appointments(
    wa_id: str,
    bot_id: int | None = None,
) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM calendar_appointments
            WHERE wa_id = $1
              AND (
                $2::bigint IS NULL
                OR bot_id = $2
                OR ($2 = 1 AND bot_id IS NULL)
              )
              AND status = 'scheduled'
              AND start_at >= now() - interval '2 hours'
            ORDER BY start_at ASC
            """,
            wa_id,
            bot_id,
        )
    return [dict(r) for r in rows]


async def mark_calendar_appointment_cancelled(google_event_id: str, bot_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE calendar_appointments SET
                status = 'cancelled',
                cancelled_at = now(),
                updated_at = now()
            WHERE google_event_id = $1
              AND bot_id = $2
            """,
            google_event_id,
            bot_id,
        )


async def list_leads(
    status: str | None = None,
    limit: int = 200,
    bot_id: int | None = None,
) -> list[dict]:
    query = "SELECT * FROM leads"
    args: list = []
    filters: list[str] = []
    if status:
        args.append(status)
        filters.append(f"qualification_status = ${len(args)}")
    if bot_id:
        args.append(bot_id)
        filters.append(f"(bot_id = ${len(args)} OR (${len(args)} = 1 AND bot_id IS NULL))")
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += f" ORDER BY created_at DESC LIMIT ${len(args) + 1}"
    args.append(limit)
    async with _pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
    return [dict(r) for r in rows]


async def update_lead_status(
    wa_id: str,
    status: str,
    disqualify_reason: str | None = None,
    bot_id: int | None = None,
) -> None:
    """Mueve un lead entre estados del CRM."""
    if bot_id is None:
        raise ValueError("bot_id is required to update a lead")
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE leads SET
                qualification_status = $2,
                disqualify_reason = CASE
                    WHEN $2 = 'descalificado' THEN COALESCE($3, disqualify_reason)
                    ELSE NULL
                END,
                updated_at = now()
            WHERE wa_id = $1
              AND bot_id = $4
            """,
            wa_id,
            status,
            disqualify_reason,
            bot_id,
        )


async def crm_counts(bot_id: int | None = None) -> dict:
    async with _pool.acquire() as conn:
        if bot_id:
            rows = await conn.fetch(
                """
                SELECT qualification_status, COUNT(*) AS n
                FROM leads
                WHERE bot_id = $1 OR ($1 = 1 AND bot_id IS NULL)
                GROUP BY qualification_status
                """,
                bot_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT qualification_status, COUNT(*) AS n FROM leads GROUP BY qualification_status"
            )
    return {r["qualification_status"]: r["n"] for r in rows}


async def admin_metrics(bot_id: int | None = None) -> dict:
    """Metricas ligeras para el dashboard admin."""
    async with _pool.acquire() as conn:
        if bot_id:
            row = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(DISTINCT wa_id) FROM conversations WHERE bot_id = $1 OR ($1 = 1 AND bot_id IS NULL)) AS conversations,
                    (SELECT COUNT(*) FROM conversations WHERE bot_id = $1 OR ($1 = 1 AND bot_id IS NULL)) AS messages,
                    (SELECT COUNT(*) FROM leads WHERE bot_id = $1 OR ($1 = 1 AND bot_id IS NULL)) AS leads,
                    (SELECT COUNT(*) FROM leads WHERE qualification_status = 'calificado' AND (bot_id = $1 OR ($1 = 1 AND bot_id IS NULL))) AS qualified,
                    (SELECT COUNT(*) FROM escalations WHERE status = 'pendiente' AND (bot_id = $1 OR ($1 = 1 AND bot_id IS NULL))) AS pending_escalations
                """,
                bot_id,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(DISTINCT wa_id) FROM conversations) AS conversations,
                    (SELECT COUNT(*) FROM conversations) AS messages,
                    (SELECT COUNT(*) FROM leads) AS leads,
                    (SELECT COUNT(*) FROM leads WHERE qualification_status = 'calificado') AS qualified,
                    (SELECT COUNT(*) FROM escalations WHERE status = 'pendiente') AS pending_escalations
                """
            )
    return dict(row)


async def qualify_leads_with_action_link(
    action_url: str | None = None,
    bot_id: int | None = None,
) -> int:
    """Marca como calificados los leads a los que ya se les ofrecio una accion final."""
    async with _pool.acquire() as conn:
        if action_url:
            result = await conn.execute(
                """
                UPDATE leads SET
                    qualification_status = 'calificado',
                    action_link_sent = TRUE,
                    disqualify_reason = NULL,
                    updated_at = now()
                WHERE qualification_status <> 'calificado'
                  AND (
                    action_link_sent = TRUE
                    OR EXISTS (
                        SELECT 1 FROM conversations
                        WHERE conversations.wa_id = leads.wa_id
                          AND conversations.role = 'assistant'
                          AND conversations.content ILIKE '%' || $1 || '%'
                          AND (
                            $2::bigint IS NULL
                            OR conversations.bot_id = $2
                            OR ($2 = 1 AND conversations.bot_id IS NULL)
                          )
                    )
                  )
                  AND (
                    $2::bigint IS NULL
                    OR leads.bot_id = $2
                    OR ($2 = 1 AND leads.bot_id IS NULL)
                  )
                """,
                action_url,
                bot_id,
            )
        else:
            result = await conn.execute(
                """
                UPDATE leads SET
                    qualification_status = 'calificado',
                    action_link_sent = TRUE,
                    disqualify_reason = NULL,
                    updated_at = now()
                WHERE qualification_status <> 'calificado'
                  AND action_link_sent = TRUE
                  AND (
                    $1::bigint IS NULL
                    OR leads.bot_id = $1
                    OR ($1 = 1 AND leads.bot_id IS NULL)
                  )
                """,
                bot_id,
            )
    return int(result.split()[-1]) if result else 0


async def upsert_follow_up(wa_id: str, delay_minutes: int = 10, bot_id: int | None = None) -> None:
    """Programa (o reprograma) un único follow-up para wa_id."""
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO pending_follow_ups(wa_id, send_after, bot_id)
            VALUES($1, now() + make_interval(mins => $2), $3)
            ON CONFLICT (bot_id, wa_id) DO UPDATE SET
                send_after = now() + make_interval(mins => $2),
                sent = FALSE
            """,
            wa_id, delay_minutes, bot_id,
        )


async def cancel_follow_up(wa_id: str, bot_id: int) -> None:
    """Elimina el follow-up pendiente cuando el usuario vuelve a escribir."""
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pending_follow_ups WHERE wa_id = $1 AND bot_id = $2 AND sent = FALSE",
            wa_id,
            bot_id,
        )


async def get_due_follow_ups() -> list[dict]:
    """Devuelve los follow-ups listos para enviar (send_after <= ahora, no enviados)."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, wa_id, bot_id FROM pending_follow_ups "
            "WHERE sent = FALSE AND send_after <= now()"
        )
    return [dict(r) for r in rows]


async def mark_follow_up_sent(follow_up_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE pending_follow_ups SET sent = TRUE WHERE id = $1",
            follow_up_id,
        )


async def mark_all_follow_ups_sent() -> int:
    """Desactiva todos los follow-ups pendientes."""
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE pending_follow_ups SET sent = TRUE WHERE sent = FALSE"
        )
    return int(result.split()[-1]) if result else 0


def get_phone_variants(phone: str) -> list[str]:
    """Obtiene variantes válidas de un número telefónico (ej. con/sin el '1' para números de México)."""
    clean = "".join(c for c in phone if c.isdigit())
    variants = [clean]
    if clean.startswith("52") and len(clean) == 13 and clean[2] == "1":
        # Es un número de México de 13 dígitos con el '1'
        # Variante sin el '1': '52' + últimos 10 dígitos
        variants.append("52" + clean[3:])
    elif clean.startswith("52") and len(clean) == 12 and clean[2] != "1":
        # Es un número de México de 12 dígitos sin el '1'
        # Variante con el '1': '521' + últimos 10 dígitos
        variants.append("521" + clean[2:])
    return list(set(variants))


async def clear_contact_data(wa_ids: list[str], bot_id: int | None = None) -> dict[str, int]:
    """Borra estado conversacional y comercial de una lista de contactos."""
    expanded_wa_ids = []
    for wa_id in wa_ids:
        expanded_wa_ids.extend(get_phone_variants(wa_id))
    expanded_wa_ids = list(set(expanded_wa_ids))

    bot_filter = "" if bot_id is None else " AND bot_id = $2"
    args: list = [expanded_wa_ids] if bot_id is None else [expanded_wa_ids, bot_id]
    async with _pool.acquire() as conn:
        results = {
            "conversations": await conn.execute(
                f"DELETE FROM conversations WHERE wa_id = ANY($1::text[]){bot_filter}",
                *args,
            ),
            "leads": await conn.execute(
                f"DELETE FROM leads WHERE wa_id = ANY($1::text[]){bot_filter}",
                *args,
            ),
            "escalations": await conn.execute(
                f"DELETE FROM escalations WHERE wa_id = ANY($1::text[]){bot_filter}",
                *args,
            ),
            "pending_follow_ups": await conn.execute(
                f"DELETE FROM pending_follow_ups WHERE wa_id = ANY($1::text[]){bot_filter}",
                *args,
            ),
            "calendar_appointments": await conn.execute(
                f"DELETE FROM calendar_appointments WHERE wa_id = ANY($1::text[]){bot_filter}",
                *args,
            ),
            "contacts": await conn.execute(
                f"DELETE FROM contacts WHERE wa_id = ANY($1::text[]){bot_filter}",
                *args,
            ),
        }
    return {
        key: int(value.split()[-1]) if value else 0
        for key, value in results.items()
    }


async def clear_conversation_history(wa_id: str, bot_id: int) -> None:
    """Borra el historial de conversaciones para resetear la memoria del bot."""
    variants = get_phone_variants(wa_id)
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM conversations WHERE wa_id = ANY($1::text[]) AND bot_id = $2",
            variants, bot_id
        )


async def record_external_action_run(
    *,
    bot_id: int | None,
    wa_id: str | None,
    action_type: str,
    integration_id: int | None,
    operation: str | None,
    status: str,
    request_data: dict | None = None,
    response_data: dict | None = None,
    error_message: str | None = None,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO external_action_runs(
                bot_id, wa_id, action_type, integration_id, operation,
                status, request_data, response_data, error_message
            )
            VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9)
            """,
            bot_id,
            wa_id,
            action_type,
            integration_id,
            operation,
            status,
            json.dumps(request_data or {}),
            json.dumps(response_data or {}),
            error_message,
        )


async def ensure_default_bot() -> int:
    """Creates the default Asistto client/bot/number rows for backwards compatibility."""
    async with _pool.acquire() as conn:
        client = await conn.fetchrow(
            """
            INSERT INTO clients(name, slug)
            VALUES('Humanio', 'humanio')
            ON CONFLICT (slug) DO UPDATE SET updated_at = now()
            RETURNING id
            """
        )
        bot = await conn.fetchrow(
            """
            INSERT INTO bots(client_id, slug, name, description, openai_model)
            VALUES($1, $2, 'Asistto', 'Bot principal de Humanio para Asistto', $3)
            ON CONFLICT (slug) DO UPDATE SET
                client_id = EXCLUDED.client_id,
                openai_model = EXCLUDED.openai_model,
                updated_at = now()
            RETURNING id
            """,
            client["id"],
            config.DEFAULT_BOT_SLUG or "asistto",
            config.OPENAI_MODEL,
        )
        if config.WHATSAPP_PHONE_NUMBER_ID:
            await conn.execute(
                """
                INSERT INTO bot_whatsapp_numbers(bot_id, phone_number_id, display_phone_number)
                VALUES($1, $2, '')
                ON CONFLICT (phone_number_id) DO NOTHING
                """,
                bot["id"],
                config.WHATSAPP_PHONE_NUMBER_ID,
            )
        return int(bot["id"])


async def get_bot_by_phone_number_id(phone_number_id: str) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                bots.id AS bot_id,
                bots.client_id,
                bots.slug,
                bots.name,
                bots.status,
                bot_whatsapp_numbers.phone_number_id,
                bot_whatsapp_numbers.display_phone_number,
                bot_whatsapp_numbers.whatsapp_access_token,
                bot_whatsapp_numbers.business_id,
                bot_whatsapp_numbers.waba_id,
                bot_whatsapp_numbers.meta_app_id,
                bot_whatsapp_numbers.meta_config_id,
                bots.openai_model
            FROM bot_whatsapp_numbers
            JOIN bots ON bots.id = bot_whatsapp_numbers.bot_id
            WHERE bot_whatsapp_numbers.phone_number_id = $1
              AND bot_whatsapp_numbers.status = 'active'
              AND bots.status IN ('active', 'paused')
            LIMIT 1
            """,
            phone_number_id,
        )
    return dict(row) if row else None


async def get_bot_whatsapp_number(bot_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                phone_number_id,
                display_phone_number,
                whatsapp_access_token,
                business_id,
                waba_id,
                meta_app_id,
                meta_config_id,
                connected_at,
                last_sync_status,
                last_sync_at,
                status
            FROM bot_whatsapp_numbers
            WHERE bot_id = $1
              AND status = 'active'
            LIMIT 1
            """,
            bot_id,
        )
    return dict(row) if row else None



async def list_clients(limit: int = 200) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                clients.*,
                COUNT(bots.id) AS bot_count
            FROM clients
            LEFT JOIN bots ON bots.client_id = clients.id
            GROUP BY clients.id
            ORDER BY clients.created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


async def get_client(client_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM clients WHERE id = $1", client_id)
    return dict(row) if row else None


async def create_client(name: str, slug: str) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO clients(name, slug)
            VALUES($1, $2)
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                status = 'active',
                updated_at = now()
            RETURNING id
            """,
            name,
            slug,
        )
    return int(row["id"])


async def list_bots(client_id: int | None = None, limit: int = 200) -> list[dict]:
    async with _pool.acquire() as conn:
        if client_id:
            rows = await conn.fetch(
                """
                SELECT
                    bots.*,
                    clients.name AS client_name,
                    bot_whatsapp_numbers.phone_number_id,
                    bot_whatsapp_numbers.display_phone_number,
                    bot_whatsapp_numbers.business_id,
                    bot_whatsapp_numbers.waba_id,
                    bot_whatsapp_numbers.connected_at,
                    bot_whatsapp_numbers.status AS whatsapp_status
                FROM bots
                LEFT JOIN clients ON clients.id = bots.client_id
                LEFT JOIN bot_whatsapp_numbers ON bot_whatsapp_numbers.bot_id = bots.id
                WHERE bots.client_id = $1
                ORDER BY bots.created_at DESC
                LIMIT $2
                """,
                client_id,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    bots.*,
                    clients.name AS client_name,
                    bot_whatsapp_numbers.phone_number_id,
                    bot_whatsapp_numbers.display_phone_number,
                    bot_whatsapp_numbers.business_id,
                    bot_whatsapp_numbers.waba_id,
                    bot_whatsapp_numbers.connected_at,
                    bot_whatsapp_numbers.status AS whatsapp_status
                FROM bots
                LEFT JOIN clients ON clients.id = bots.client_id
                LEFT JOIN bot_whatsapp_numbers ON bot_whatsapp_numbers.bot_id = bots.id
                ORDER BY bots.created_at DESC
                LIMIT $1
                """,
                limit,
            )
    return [dict(r) for r in rows]


async def get_bot(bot_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                bots.*,
                clients.name AS client_name,
                bot_whatsapp_numbers.phone_number_id,
                bot_whatsapp_numbers.display_phone_number,
                bot_whatsapp_numbers.business_id,
                bot_whatsapp_numbers.waba_id,
                bot_whatsapp_numbers.meta_app_id,
                bot_whatsapp_numbers.meta_config_id,
                bot_whatsapp_numbers.connected_at,
                bot_whatsapp_numbers.last_sync_status,
                bot_whatsapp_numbers.last_sync_at,
                bot_whatsapp_numbers.status AS whatsapp_status
            FROM bots
            LEFT JOIN clients ON clients.id = bots.client_id
            LEFT JOIN bot_whatsapp_numbers ON bot_whatsapp_numbers.bot_id = bots.id
            WHERE bots.id = $1
            """,
            bot_id,
        )
    return dict(row) if row else None


async def create_bot(
    client_id: int,
    slug: str,
    name: str,
    description: str | None = None,
    phone_number_id: str | None = None,
    display_phone_number: str | None = None,
) -> int:
    async with _pool.acquire() as conn:
        bot = await conn.fetchrow(
            """
            INSERT INTO bots(client_id, slug, name, description, openai_model)
            VALUES($1, $2, $3, $4, $5)
            ON CONFLICT (slug) DO UPDATE SET
                client_id = EXCLUDED.client_id,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                openai_model = EXCLUDED.openai_model,
                updated_at = now()
            RETURNING id
            """,
            client_id,
            slug,
            name,
            description,
            config.OPENAI_MODEL,
        )
        if phone_number_id:
            await conn.execute(
                """
                INSERT INTO bot_whatsapp_numbers(bot_id, phone_number_id, display_phone_number)
                VALUES($1, $2, $3)
                ON CONFLICT (phone_number_id) DO UPDATE SET
                    bot_id = EXCLUDED.bot_id,
                    display_phone_number = EXCLUDED.display_phone_number,
                    updated_at = now()
                """,
                bot["id"],
                phone_number_id,
                display_phone_number or "",
            )
    return int(bot["id"])


async def upsert_bot_whatsapp_connection(
    bot_id: int,
    phone_number_id: str,
    display_phone_number: str | None = None,
    business_id: str | None = None,
    waba_id: str | None = None,
    meta_app_id: str | None = None,
    meta_config_id: str | None = None,
    sync_status: str | None = None,
) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO bot_whatsapp_numbers(
                bot_id,
                phone_number_id,
                display_phone_number,
                business_id,
                waba_id,
                meta_app_id,
                meta_config_id,
                connected_at,
                last_sync_status,
                last_sync_at
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, now(), $8, now())
            ON CONFLICT (phone_number_id) DO UPDATE SET
                bot_id = EXCLUDED.bot_id,
                display_phone_number = COALESCE(NULLIF(EXCLUDED.display_phone_number, ''), bot_whatsapp_numbers.display_phone_number),
                business_id = COALESCE(NULLIF(EXCLUDED.business_id, ''), bot_whatsapp_numbers.business_id),
                waba_id = COALESCE(NULLIF(EXCLUDED.waba_id, ''), bot_whatsapp_numbers.waba_id),
                meta_app_id = COALESCE(NULLIF(EXCLUDED.meta_app_id, ''), bot_whatsapp_numbers.meta_app_id),
                meta_config_id = COALESCE(NULLIF(EXCLUDED.meta_config_id, ''), bot_whatsapp_numbers.meta_config_id),
                connected_at = COALESCE(bot_whatsapp_numbers.connected_at, now()),
                last_sync_status = EXCLUDED.last_sync_status,
                last_sync_at = now(),
                status = 'active',
                updated_at = now()
            RETURNING id
            """,
            bot_id,
            phone_number_id,
            display_phone_number or "",
            business_id or "",
            waba_id or "",
            meta_app_id or "",
            meta_config_id or "",
            sync_status or "connected",
        )
    return int(row["id"])


async def update_bot_status(bot_id: int, status: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE bots
            SET status = $2,
                updated_at = now()
            WHERE id = $1
            """,
            bot_id,
            status,
        )


async def update_bot_whatsapp_sync_status(
    bot_id: int,
    phone_number_id: str,
    sync_status: str,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE bot_whatsapp_numbers
            SET last_sync_status = $3,
                last_sync_at = now(),
                updated_at = now()
            WHERE bot_id = $1 AND phone_number_id = $2
            """,
            bot_id,
            phone_number_id,
            sync_status,
        )


async def get_active_bot_prompt(bot_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT *
            FROM bot_prompts
            WHERE bot_id = $1 AND status = 'active'
            ORDER BY version DESC, published_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            bot_id,
        )
    return dict(row) if row else None


async def publish_bot_prompt(
    bot_id: int, 
    content: str, 
    pbd_constitution: str | None = None, 
    pbd_specs: str | None = None, 
    pbd_test_suite: str | None = None
) -> int:
    async with _pool.acquire() as conn:
        async with conn.transaction():
            version = await conn.fetchval(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM bot_prompts WHERE bot_id = $1",
                bot_id,
            )
            await conn.execute(
                """
                UPDATE bot_prompts
                SET status = 'archived'
                WHERE bot_id = $1 AND status = 'active'
                """,
                bot_id,
            )
            row = await conn.fetchrow(
                """
                INSERT INTO bot_prompts(bot_id, version, status, content, pbd_constitution, pbd_specs, pbd_test_suite, published_at)
                VALUES($1, $2, 'active', $3, $4, $5, $6, now())
                RETURNING id
                """,
                bot_id,
                int(version or 1),
                content,
                pbd_constitution,
                pbd_specs,
                pbd_test_suite,
            )
    return int(row["id"])


async def list_bot_knowledge(
    bot_id: int,
    active_only: bool = True,
) -> list[dict]:
    query = """
        SELECT *
        FROM bot_knowledge
        WHERE bot_id = $1
    """
    if active_only:
        query += " AND status = 'active'"
    query += " ORDER BY updated_at DESC, created_at DESC"
    async with _pool.acquire() as conn:
        rows = await conn.fetch(query, bot_id)
    return [dict(r) for r in rows]


async def get_bot_knowledge(bot_id: int, knowledge_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT *
            FROM bot_knowledge
            WHERE bot_id = $1 AND id = $2
            """,
            bot_id,
            knowledge_id,
        )
    return dict(row) if row else None


async def create_bot_knowledge(bot_id: int, title: str, content: str) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO bot_knowledge(bot_id, title, content, status)
            VALUES($1, $2, $3, 'active')
            RETURNING id
            """,
            bot_id,
            title,
            content,
        )
        knowledge_id = int(row["id"])
        from app import rag
        await rag.index_document(conn, bot_id, knowledge_id, content)
    return knowledge_id


async def update_bot_knowledge(
    bot_id: int,
    knowledge_id: int,
    title: str,
    content: str,
    status: str = "active",
) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE bot_knowledge
            SET title = $3,
                content = $4,
                status = $5,
                updated_at = now()
            WHERE bot_id = $1 AND id = $2
            """,
            bot_id,
            knowledge_id,
            title,
            content,
            status,
        )
        success = result.endswith(" 1") if result else False
        if success:
            from app import rag
            if status == "active":
                await rag.index_document(conn, bot_id, knowledge_id, content)
            else:
                await rag.delete_document_chunks(conn, knowledge_id)
    return success


async def archive_bot_knowledge(bot_id: int, knowledge_id: int) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE bot_knowledge
            SET status = 'archived',
                updated_at = now()
            WHERE bot_id = $1 AND id = $2
            """,
            bot_id,
            knowledge_id,
        )
        success = result.endswith(" 1") if result else False
        if success:
            from app import rag
            await rag.delete_document_chunks(conn, knowledge_id)
    return success


def _normalize_config(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _dict_rows(rows) -> list[dict]:
    result = []
    for row in rows:
        item = dict(row)
        if "config" in item:
            item["config"] = _normalize_config(item.get("config"))
        result.append(item)
    return result


async def list_bot_integrations(
    bot_id: int,
    include_archived: bool = False,
) -> list[dict]:
    query = """
        SELECT
            bot_integrations.*,
            (
                SELECT COUNT(*)
                FROM integration_secrets
                WHERE integration_secrets.integration_id = bot_integrations.id
            ) AS secret_count
        FROM bot_integrations
        WHERE bot_id = $1
    """
    if not include_archived:
        query += " AND enabled = TRUE"
    query += " ORDER BY updated_at DESC, created_at DESC"
    async with _pool.acquire() as conn:
        rows = await conn.fetch(query, bot_id)
    return _dict_rows(rows)


async def get_bot_integration(bot_id: int, integration_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                bot_integrations.*,
                (
                    SELECT COUNT(*)
                    FROM integration_secrets
                    WHERE integration_secrets.integration_id = bot_integrations.id
                ) AS secret_count
            FROM bot_integrations
            WHERE bot_id = $1 AND id = $2
            """,
            bot_id,
            integration_id,
        )
    if not row:
        return None
    item = dict(row)
    item["config"] = _normalize_config(item.get("config"))
    return item


async def get_active_bot_integration(
    bot_id: int,
    integration_type: str,
) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                bot_integrations.*,
                (
                    SELECT COUNT(*)
                    FROM integration_secrets
                    WHERE integration_secrets.integration_id = bot_integrations.id
                ) AS secret_count
            FROM bot_integrations
            WHERE bot_id = $1
              AND integration_type = $2
              AND enabled = TRUE
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            bot_id,
            integration_type,
        )
    if not row:
        return None
    item = dict(row)
    item["config"] = _normalize_config(item.get("config"))
    return item


async def get_bot_integration_by_type(
    bot_id: int,
    integration_type: str,
) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                bot_integrations.*,
                (
                    SELECT COUNT(*)
                    FROM integration_secrets
                    WHERE integration_secrets.integration_id = bot_integrations.id
                ) AS secret_count
            FROM bot_integrations
            WHERE bot_id = $1
              AND integration_type = $2
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            bot_id,
            integration_type,
        )
    if not row:
        return None
    item = dict(row)
    item["config"] = _normalize_config(item.get("config"))
    return item


async def create_bot_integration(
    bot_id: int,
    integration_type: str,
    name: str,
    config_data: dict | None = None,
    enabled: bool = True,
) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO bot_integrations(bot_id, integration_type, name, enabled, config)
            VALUES($1, $2, $3, $4, $5::jsonb)
            RETURNING id
            """,
            bot_id,
            integration_type,
            name,
            enabled,
            json.dumps(config_data or {}),
        )
    return int(row["id"])


async def update_bot_integration(
    bot_id: int,
    integration_id: int,
    integration_type: str,
    name: str,
    config_data: dict | None = None,
    enabled: bool = True,
) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE bot_integrations
            SET integration_type = $3,
                name = $4,
                enabled = $5,
                config = $6::jsonb,
                updated_at = now()
            WHERE bot_id = $1 AND id = $2
            """,
            bot_id,
            integration_id,
            integration_type,
            name,
            enabled,
            json.dumps(config_data or {}),
        )
    return result.endswith(" 1") if result else False


async def archive_bot_integration(bot_id: int, integration_id: int) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE bot_integrations
            SET enabled = FALSE,
                updated_at = now()
            WHERE bot_id = $1 AND id = $2
            """,
            bot_id,
            integration_id,
        )
    return result.endswith(" 1") if result else False


async def list_integration_secrets(integration_id: int) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT secret_name, created_at, updated_at
            FROM integration_secrets
            WHERE integration_id = $1
            ORDER BY secret_name ASC
            """,
            integration_id,
        )
    return [dict(r) for r in rows]


async def get_integration_secret_values(integration_id: int) -> dict[str, str]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT secret_name, encrypted_value
            FROM integration_secrets
            WHERE integration_id = $1
            """,
            integration_id,
        )
    return {r["secret_name"]: r["encrypted_value"] for r in rows}


async def upsert_integration_secret(
    integration_id: int,
    secret_name: str,
    encrypted_value: str,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO integration_secrets(integration_id, secret_name, encrypted_value)
            VALUES($1, $2, $3)
            ON CONFLICT (integration_id, secret_name) DO UPDATE SET
                encrypted_value = EXCLUDED.encrypted_value,
                updated_at = now()
            """,
            integration_id,
            secret_name,
            encrypted_value,
        )


async def delete_integration_secret(integration_id: int, secret_name: str) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM integration_secrets
            WHERE integration_id = $1 AND secret_name = $2
            """,
            integration_id,
            secret_name,
        )
    return result.endswith(" 1") if result else False


async def claim_chatwoot_webhook_event(integration_id: int, event_key: str) -> bool:
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM chatwoot_webhook_events WHERE created_at < now() - interval '30 days'"
        )
        row = await conn.fetchrow(
            """
            INSERT INTO chatwoot_webhook_events(integration_id, event_key)
            VALUES($1, $2)
            ON CONFLICT (integration_id, event_key) DO NOTHING
            RETURNING id
            """,
            integration_id,
            event_key,
        )
    return row is not None


async def release_chatwoot_webhook_event(integration_id: int, event_key: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM chatwoot_webhook_events WHERE integration_id=$1 AND event_key=$2",
            integration_id,
            event_key,
        )


async def set_chatwoot_handoff_active(bot_id: int, wa_id: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chatwoot_handoffs(bot_id, wa_id)
            VALUES($1, $2)
            ON CONFLICT (bot_id, wa_id) DO UPDATE SET
                status='human_active',
                updated_at=now()
            """,
            bot_id,
            wa_id,
        )


async def clear_chatwoot_handoff(bot_id: int, wa_id: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM chatwoot_handoffs WHERE bot_id=$1 AND wa_id=$2",
            bot_id,
            wa_id,
        )


async def is_chatwoot_handoff_active(bot_id: int, wa_id: str) -> bool:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM chatwoot_handoffs WHERE bot_id=$1 AND wa_id=$2",
            bot_id,
            wa_id,
        )
    return row is not None


async def list_bot_skills(bot_id: int) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM bot_skills
            WHERE bot_id = $1
            ORDER BY skill_type ASC
            """,
            bot_id,
        )
    return _dict_rows(rows)


async def get_bot_skill(bot_id: int, skill_type: str) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT *
            FROM bot_skills
            WHERE bot_id = $1 AND skill_type = $2
            """,
            bot_id,
            skill_type,
        )
    if not row:
        return None
    item = dict(row)
    item["config"] = _normalize_config(item.get("config"))
    return item


async def upsert_bot_skill(
    bot_id: int,
    skill_type: str,
    enabled: bool = True,
    config_data: dict | None = None,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO bot_skills(bot_id, skill_type, enabled, config)
            VALUES($1, $2, $3, $4::jsonb)
            ON CONFLICT (bot_id, skill_type) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                config = EXCLUDED.config,
                updated_at = now()
            """,
            bot_id,
            skill_type,
            enabled,
            json.dumps(config_data or {}),
        )


async def list_client_users(client_id: int) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT users.id, users.email, users.name, users.status, client_users.role
            FROM client_users
            JOIN users ON users.id = client_users.user_id
            WHERE client_users.client_id = $1
            ORDER BY users.email ASC
            """,
            client_id,
        )
    return [dict(r) for r in rows]


async def list_users(client_id: int | None = None, limit: int = 200) -> list[dict]:
    async with _pool.acquire() as conn:
        if client_id:
            rows = await conn.fetch(
                """
                SELECT
                    users.id,
                    users.email,
                    users.name,
                    users.status,
                    client_users.role,
                    client_users.client_id,
                    clients.name AS client_name,
                    clients.slug AS client_slug
                FROM users
                JOIN client_users ON client_users.user_id = users.id
                JOIN clients ON clients.id = client_users.client_id
                WHERE client_users.client_id = $1
                ORDER BY users.email ASC
                LIMIT $2
                """,
                client_id,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    users.id,
                    users.email,
                    users.name,
                    users.status,
                    client_users.role,
                    client_users.client_id,
                    clients.name AS client_name,
                    clients.slug AS client_slug
                FROM users
                JOIN client_users ON client_users.user_id = users.id
                JOIN clients ON clients.id = client_users.client_id
                ORDER BY clients.name ASC, users.email ASC
                LIMIT $1
                """,
                limit,
            )
    return [dict(r) for r in rows]


async def create_client_user(
    client_id: int,
    email: str,
    name: str | None,
    password_hash: str,
    role: str = "client_admin",
) -> int:
    async with _pool.acquire() as conn:
        user = await conn.fetchrow(
            """
            INSERT INTO users(email, name, password_hash)
            VALUES($1, $2, $3)
            ON CONFLICT (email) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, users.name),
                password_hash = EXCLUDED.password_hash,
                status = 'active',
                updated_at = now()
            RETURNING id
            """,
            email.lower().strip(),
            name,
            password_hash,
        )
        await conn.execute(
            """
            INSERT INTO client_users(client_id, user_id, role)
            VALUES($1, $2, $3)
            ON CONFLICT (client_id, user_id) DO UPDATE SET role = EXCLUDED.role
            """,
            client_id,
            user["id"],
            role,
        )
    return int(user["id"])


async def get_user_login(email: str) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                users.id AS user_id,
                users.email,
                users.name,
                users.password_hash,
                client_users.client_id,
                client_users.role
            FROM users
            JOIN client_users ON client_users.user_id = users.id
            WHERE users.email = $1
              AND users.status = 'active'
            ORDER BY client_users.created_at ASC
            LIMIT 1
            """,
            email.lower().strip(),
        )
    return dict(row) if row else None


async def delete_user(user_id: int, client_id: int | None = None) -> bool:
    async with _pool.acquire() as conn:
        if client_id:
            result = await conn.execute(
                """
                DELETE FROM users
                WHERE id = $1
                  AND EXISTS (
                      SELECT 1 FROM client_users
                      WHERE client_users.user_id = users.id
                        AND client_users.client_id = $2
                  )
                """,
                user_id,
                client_id,
            )
        else:
            result = await conn.execute("DELETE FROM users WHERE id = $1", user_id)
        return result != "DELETE 0"


async def delete_client(client_id: int) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute("DELETE FROM clients WHERE id = $1", client_id)
        return result != "DELETE 0"


async def delete_bot(bot_id: int) -> bool:
    async with _pool.acquire() as conn:
        result = await conn.execute("DELETE FROM bots WHERE id = $1", bot_id)
        return result != "DELETE 0"


# --- CONTACTS & BROADCASTS DB OPERATIONS ---

async def list_contact_tags(bot_id: int) -> list[str]:
    """Devuelve una lista de etiquetas únicas usadas por los contactos del bot."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT trim(unnest(string_to_array(tags, ','))) AS tag
            FROM contacts
            WHERE bot_id = $1 AND tags IS NOT NULL AND tags != ''
            ORDER BY tag ASC
            """,
            bot_id,
        )
        return [r["tag"] for r in rows if r["tag"]]


async def upsert_contact(
    bot_id: int,
    wa_id: str,
    name: str | None = None,
    business: str | None = None,
    tags: str | None = None,
) -> None:
    """Inserta o actualiza un contacto en el catálogo del cliente."""
    clean_wa_id = "".join(filter(str.isdigit, wa_id))
    if not clean_wa_id:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO contacts (bot_id, wa_id, name, business, tags, updated_at)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (bot_id, wa_id) DO UPDATE SET
                name = COALESCE($3, contacts.name),
                business = COALESCE($4, contacts.business),
                tags = COALESCE($5, contacts.tags),
                updated_at = now()
            """,
            bot_id,
            clean_wa_id,
            name,
            business,
            tags,
        )


async def list_contacts(
    bot_id: int,
    search: str | None = None,
    tag: str | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict]:
    """Lista contactos de un bot específico con filtros de búsqueda y tags."""
    async with _pool.acquire() as conn:
        query = "SELECT * FROM contacts WHERE bot_id = $1"
        args = [bot_id]
        
        if search:
            args.append(f"%{search}%")
            query += f" AND (name ILIKE ${len(args)} OR wa_id ILIKE ${len(args)} OR business ILIKE ${len(args)})"
            
        if tag:
            args.append(f"%{tag}%")
            query += f" AND tags ILIKE ${len(args)}"
            
        args.append(limit)
        query += f" ORDER BY name ASC, created_at DESC LIMIT ${len(args)}"
        args.append(offset)
        query += f" OFFSET ${len(args)}"
        
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]


async def count_contacts(
    bot_id: int,
    search: str | None = None,
    tag: str | None = None,
) -> int:
    """Devuelve el total de contactos que coinciden con los criterios."""
    async with _pool.acquire() as conn:
        query = "SELECT COUNT(*) FROM contacts WHERE bot_id = $1"
        args = [bot_id]
        
        if search:
            args.append(f"%{search}%")
            query += f" AND (name ILIKE ${len(args)} OR wa_id ILIKE ${len(args)} OR business ILIKE ${len(args)})"
            
        if tag:
            args.append(f"%{tag}%")
            query += f" AND tags ILIKE ${len(args)}"
            
        row = await conn.fetchrow(query, *args)
        return row[0] if row else 0


async def delete_contacts(bot_id: int, wa_ids: list[str]) -> bool:
    """Elimina uno o varios contactos de un bot."""
    if not wa_ids:
        return False
    async with _pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM contacts WHERE bot_id = $1 AND wa_id = ANY($2::text[])",
            bot_id,
            wa_ids,
        )
        return result != "DELETE 0"


async def create_broadcast(
    bot_id: int,
    name: str,
    template_name: str,
    language_code: str,
    variable_mappings: list[dict],
    recipients: list[dict],
) -> int:
    """Crea una campaña de envío masivo y sus destinatarios pendientes."""
    if not recipients:
        raise ValueError("Se requiere al menos un destinatario para crear la campaña.")
        
    async with _pool.acquire() as conn:
        async with conn.transaction():
            # Crear la campaña
            broadcast_id = await conn.fetchval(
                """
                INSERT INTO broadcasts (bot_id, name, template_name, language_code, variable_mappings, total_recipients)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                bot_id,
                name,
                template_name,
                language_code,
                json.dumps(variable_mappings),
                len(recipients),
            )
            
            # Insertar los destinatarios por lotes
            values = []
            for r in recipients:
                clean_wa = "".join(filter(str.isdigit, r["wa_id"]))
                if clean_wa:
                    values.append((broadcast_id, clean_wa, r.get("name"), r.get("business")))
            
            if values:
                await conn.executemany(
                    """
                    INSERT INTO broadcast_recipients (broadcast_id, wa_id, contact_name, contact_business)
                    VALUES ($1, $2, $3, $4)
                    """,
                    values,
                )
            
            return broadcast_id


async def list_broadcasts(bot_id: int, limit: int = 50) -> list[dict]:
    """Lista las campañas de un bot ordenadas por fecha de creación descendente."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM broadcasts WHERE bot_id = $1 ORDER BY created_at DESC LIMIT $2",
            bot_id,
            limit,
        )
        return [dict(r) for r in rows]


async def get_broadcast(broadcast_id: int, bot_id: int) -> dict | None:
    """Obtiene los detalles de una campaña de envío masivo."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM broadcasts WHERE id = $1 AND bot_id = $2",
            broadcast_id,
            bot_id,
        )
        return dict(row) if row else None


async def update_broadcast_status(broadcast_id: int, status: str) -> None:
    """Actualiza el estado principal de una campaña."""
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE broadcasts SET status = $1, updated_at = now() WHERE id = $2",
            status,
            broadcast_id,
        )


async def get_pending_broadcast_recipients(broadcast_id: int, limit: int = 100) -> list[dict]:
    """Obtiene destinatarios pendientes de envío de una campaña específica."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM broadcast_recipients WHERE broadcast_id = $1 AND status = 'pending' LIMIT $2",
            broadcast_id,
            limit,
        )
        return [dict(r) for r in rows]


async def update_broadcast_recipient_status(
    recipient_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """Actualiza el estado de entrega de un destinatario individual y actualiza contadores de campaña."""
    async with _pool.acquire() as conn:
        async with conn.transaction():
            # Actualizar destinatario
            row = await conn.fetchrow(
                """
                UPDATE broadcast_recipients
                SET status = $1, error_message = $2, sent_at = now()
                WHERE id = $3
                RETURNING broadcast_id
                """,
                status,
                error_message,
                recipient_id,
            )
            
            if row:
                broadcast_id = row["broadcast_id"]
                # Incrementar el contador correspondiente en la campaña
                if status == "sent":
                    await conn.execute(
                        "UPDATE broadcasts SET sent_count = sent_count + 1, updated_at = now() WHERE id = $1",
                        broadcast_id,
                    )
                elif status == "failed":
                    await conn.execute(
                        "UPDATE broadcasts SET failed_count = failed_count + 1, updated_at = now() WHERE id = $1",
                        broadcast_id,
                    )
