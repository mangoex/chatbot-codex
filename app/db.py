"""Acceso a Postgres: pool, schema idempotente, lectura/escritura de historial."""
import asyncpg
from app import config

_pool: asyncpg.Pool | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    id BIGSERIAL PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS pending_follow_ups (
    id BIGSERIAL PRIMARY KEY,
    wa_id TEXT UNIQUE NOT NULL,
    send_after TIMESTAMPTZ NOT NULL,
    sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_follow_ups_due
    ON pending_follow_ups(send_after) WHERE sent = FALSE;

CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY,
    wa_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conv_wa_id_ts ON conversations(wa_id, created_at DESC);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    processed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_appointments (
    id BIGSERIAL PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS escalations (
    id BIGSERIAL PRIMARY KEY,
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


async def run_migrations() -> None:
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
        await conn.execute(
            "ALTER TABLE leads ADD COLUMN IF NOT EXISTS action_link_sent BOOLEAN NOT NULL DEFAULT FALSE"
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


async def mark_processed(message_id: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO processed_messages(message_id) VALUES($1) "
            "ON CONFLICT DO NOTHING",
            message_id,
        )


async def get_history(wa_id: str, limit: int) -> list[dict]:
    """Devuelve los últimos `limit` mensajes en orden cronológico ascendente."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, content FROM conversations "
            "WHERE wa_id = $1 ORDER BY created_at DESC LIMIT $2",
            wa_id, limit,
        )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def list_conversation_threads(limit: int = 100) -> list[dict]:
    """Lista conversaciones agrupadas por wa_id con ultimo mensaje y metadata de lead."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH last_messages AS (
                SELECT DISTINCT ON (wa_id)
                    wa_id, role, content, created_at
                FROM conversations
                ORDER BY wa_id, created_at DESC
            ),
            counts AS (
                SELECT wa_id, COUNT(*) AS message_count
                FROM conversations
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
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


async def list_conversation_messages(wa_id: str, limit: int = 100) -> list[dict]:
    """Devuelve los mensajes de una conversacion en orden cronologico."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content, created_at
            FROM conversations
            WHERE wa_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            wa_id,
            limit,
        )
    return [dict(r) for r in reversed(rows)]


async def save_message(wa_id: str, role: str, content: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO conversations(wa_id, role, content) VALUES($1, $2, $3)",
            wa_id, role, content,
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
                last_media_type, conversation_excerpt
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
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


async def upsert_lead(wa_id: str, **kwargs) -> None:
    """Crea o actualiza el registro de lead. Solo actualiza los campos pasados."""
    fields = {k: v for k, v in kwargs.items()
              if k in ("nombre", "negocio", "qualification_status",
                       "disqualify_reason", "action_link_sent")}
    if not fields:
        return
    set_clause = ", ".join(
        f"{col} = ${i + 2}" for i, col in enumerate(fields)
    )
    values = list(fields.values())
    async with _pool.acquire() as conn:
        await conn.execute(
            f"""
            INSERT INTO leads(wa_id, {", ".join(fields)})
            VALUES($1, {", ".join(f"${i+2}" for i in range(len(fields)))})
            ON CONFLICT (wa_id) DO UPDATE SET {set_clause}, updated_at = now()
            """,
            wa_id, *values,
        )


async def get_lead(wa_id: str) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM leads WHERE wa_id = $1", wa_id)
    return dict(row) if row else None


async def save_calendar_appointment(
    wa_id: str,
    google_event_id: str,
    calendar_id: str,
    attendee_name: str | None,
    topic: str | None,
    start_at,
    end_at,
) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO calendar_appointments(
                wa_id, google_event_id, calendar_id, attendee_name,
                topic, start_at, end_at
            )
            VALUES($1,$2,$3,$4,$5,$6,$7)
            ON CONFLICT (google_event_id) DO UPDATE SET
                wa_id = EXCLUDED.wa_id,
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
            google_event_id,
            calendar_id,
            attendee_name,
            topic,
            start_at,
            end_at,
        )


async def list_active_calendar_appointments(wa_id: str) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM calendar_appointments
            WHERE wa_id = $1
              AND status = 'scheduled'
              AND start_at >= now() - interval '2 hours'
            ORDER BY start_at ASC
            """,
            wa_id,
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


async def list_leads(status: str | None = None, limit: int = 200) -> list[dict]:
    query = "SELECT * FROM leads"
    args: list = []
    if status:
        query += " WHERE qualification_status = $1"
        args.append(status)
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


async def crm_counts() -> dict:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT qualification_status, COUNT(*) AS n FROM leads GROUP BY qualification_status"
        )
    return {r["qualification_status"]: r["n"] for r in rows}


async def admin_metrics() -> dict:
    """Metricas ligeras para el dashboard admin."""
    async with _pool.acquire() as conn:
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


async def qualify_leads_with_action_link(action_url: str | None = None) -> int:
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
                    )
                  )
                """,
                action_url,
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
                """
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
