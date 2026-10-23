"""Consistent evidence and atomic publication for reviewed prompt changes."""
import json

from app import db, prompt_changes


def _safe_config(value):
    if isinstance(value, dict):
        return {k: ("[credencial omitida]" if any(word in k.lower() for word in
                ("secret", "token", "password", "api_key", "apikey", "authorization"))
                else _safe_config(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_config(v) for v in value]
    return value


async def _context(conn, bot_id):
    bot = await conn.fetchrow(
        "SELECT id, client_id, name, description, status FROM bots WHERE id = $1", bot_id)
    previous = await conn.fetchrow(
        "SELECT id, version, content, pbd_constitution, pbd_specs, pbd_test_suite "
        "FROM bot_prompts WHERE bot_id = $1 AND status = 'active' "
        "ORDER BY version DESC, published_at DESC NULLS LAST, created_at DESC LIMIT 1", bot_id)
    knowledge = await conn.fetch(
        "SELECT id, title, content, index_status, content_hash FROM bot_knowledge "
        "WHERE bot_id = $1 AND status = 'active' ORDER BY id", bot_id)

    async def configuration(table, kind):
        # Identifiers are constants below; values always use SQL parameters.
        rows = await conn.fetch(
            f"SELECT id, {kind}, enabled, config FROM {table} WHERE bot_id = $1 ORDER BY id", bot_id)
        result = []
        for row in rows:
            item = dict(row)
            cfg = item.get("config") or {}
            if isinstance(cfg, str):
                cfg = json.loads(cfg)
            item["config_digest"] = prompt_changes.fingerprint(cfg)
            item["config"] = _safe_config(cfg)
            result.append(item)
        return result

    return {"bot": dict(bot) if bot else {}, "previous": dict(previous) if previous else {},
            "knowledge": [dict(row) for row in knowledge],
            "integrations": await configuration("bot_integrations", "integration_type"),
            "skills": await configuration("bot_skills", "skill_type")}


async def get_context(bot_id):
    async with db._pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            return await _context(conn, bot_id)


async def publish(bot_id, receipt, submitted):
    try:
        async with db._pool.acquire() as conn:
            async with conn.transaction(isolation="serializable"):
                # Prevent dependency updates while checking/publishing, including
                # activation of previously inactive rows. Parent lock blocks FK inserts.
                await conn.fetchrow("SELECT id FROM bots WHERE id = $1 FOR UPDATE", bot_id)
                for table in ("bot_knowledge", "bot_integrations", "bot_skills", "bot_prompts"):
                    await conn.fetch(f"SELECT id FROM {table} WHERE bot_id = $1 FOR SHARE", bot_id)
                context = await _context(conn, bot_id)
                candidate = prompt_changes.verify_publication(context, receipt, submitted)
                previous = context["previous"]
                version = await conn.fetchval(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM bot_prompts WHERE bot_id = $1", bot_id)
                await conn.execute(
                    "UPDATE bot_prompts SET status = 'archived' WHERE bot_id = $1 AND status = 'active'", bot_id)
                row = await conn.fetchrow(
                    "INSERT INTO bot_prompts(bot_id, version, status, content, pbd_constitution, "
                    "pbd_specs, pbd_test_suite, published_at) VALUES($1,$2,'active',$3,$4,$5,$6,now()) RETURNING id",
                    bot_id, int(version), candidate, previous.get("pbd_constitution"),
                    previous.get("pbd_specs"), previous.get("pbd_test_suite"))
                return int(row["id"])
    except Exception as exc:
        if getattr(exc, "sqlstate", None) in {"40001", "40P01"}:
            raise prompt_changes.ChangeError("Hubo un cambio concurrente. Vuelve a revisar el ajuste.") from None
        raise
