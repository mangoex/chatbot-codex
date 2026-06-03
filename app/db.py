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
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
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

CREATE TABLE IF NOT EXISTS leads (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    wa_id TEXT UNIQUE NOT NULL,
    nombre TEXT,
    negocio TEXT,
    qualification_status TEXT NOT NULL DEFAULT 'en_progreso'
        CHECK (qualification_status IN ('en_progreso', 'calificado', 'descalificado')),
    disqualify_reason TEXT,
    action_link_sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(qualification_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_bot_status ON leads(bot_id, qualification_status, created_at DESC);

CREATE TABLE IF NOT EXISTS pending_follow_ups (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    wa_id TEXT UNIQUE NOT NULL,
    send_after TIMESTAMPTZ NOT NULL,
    sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);
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
    await ensure_default_bot()


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


async def mark_processed(message_id: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO processed_messages(message_id) VALUES($1) "
            "ON CONFLICT DO NOTHING",
            message_id,
        )


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
            LEFT JOIN leads ON leads.wa_id = lm.wa_id
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
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO conversations(wa_id, role, content, bot_id) VALUES($1, $2, $3, $4)",
            wa_id, role, content, bot_id,
        )


async def find_pending_escalation(wa_id: str) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM escalations WHERE wa_id=$1 AND status='pendiente' "
            "ORDER BY created_at DESC LIMIT 1",
            wa_id,
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
            ON CONFLICT (wa_id) DO UPDATE SET
                {set_clause},
                bot_id = COALESCE($2, leads.bot_id),
                updated_at = now()
            """,
            wa_id, bot_id, *values,
        )


async def get_lead(wa_id: str, bot_id: int | None = None) -> dict | None:
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


async def mark_calendar_appointment_cancelled(google_event_id: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE calendar_appointments SET
                status = 'cancelled',
                cancelled_at = now(),
                updated_at = now()
            WHERE google_event_id = $1
            """,
            google_event_id,
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
) -> None:
    """Mueve un lead entre estados del CRM."""
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
            """,
            wa_id,
            status,
            disqualify_reason,
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


async def upsert_follow_up(wa_id: str, delay_minutes: int = 10) -> None:
    """Programa (o reprograma) un único follow-up para wa_id."""
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO pending_follow_ups(wa_id, send_after)
            VALUES($1, now() + make_interval(mins => $2))
            ON CONFLICT (wa_id) DO UPDATE SET
                send_after = now() + make_interval(mins => $2),
                sent = FALSE
            """,
            wa_id, delay_minutes,
        )


async def cancel_follow_up(wa_id: str) -> None:
    """Elimina el follow-up pendiente cuando el usuario vuelve a escribir."""
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM pending_follow_ups WHERE wa_id = $1 AND sent = FALSE",
            wa_id,
        )


async def get_due_follow_ups() -> list[dict]:
    """Devuelve los follow-ups listos para enviar (send_after <= ahora, no enviados)."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, wa_id FROM pending_follow_ups "
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


async def clear_contact_data(wa_ids: list[str]) -> dict[str, int]:
    """Borra estado conversacional y comercial de una lista de contactos."""
    async with _pool.acquire() as conn:
        results = {
            "conversations": await conn.execute(
                "DELETE FROM conversations WHERE wa_id = ANY($1::text[])",
                wa_ids,
            ),
            "leads": await conn.execute(
                "DELETE FROM leads WHERE wa_id = ANY($1::text[])",
                wa_ids,
            ),
            "escalations": await conn.execute(
                "DELETE FROM escalations WHERE wa_id = ANY($1::text[])",
                wa_ids,
            ),
            "pending_follow_ups": await conn.execute(
                "DELETE FROM pending_follow_ups WHERE wa_id = ANY($1::text[])",
                wa_ids,
            ),
            "calendar_appointments": await conn.execute(
                "DELETE FROM calendar_appointments WHERE wa_id = ANY($1::text[])",
                wa_ids,
            ),
        }
    return {
        key: int(value.split()[-1]) if value else 0
        for key, value in results.items()
    }


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
                ON CONFLICT (phone_number_id) DO UPDATE SET
                    bot_id = EXCLUDED.bot_id,
                    updated_at = now()
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
              AND bots.status = 'active'
            LIMIT 1
            """,
            phone_number_id,
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


async def publish_bot_prompt(bot_id: int, content: str) -> int:
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
                INSERT INTO bot_prompts(bot_id, version, status, content, published_at)
                VALUES($1, $2, 'active', $3, now())
                RETURNING id
                """,
                bot_id,
                int(version or 1),
                content,
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
    return int(row["id"])


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
    return result.endswith(" 1") if result else False


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
    return result.endswith(" 1") if result else False


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
