from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import db, whatsapp_client, meta_provider


@pytest.mark.asyncio
async def test_expiration_check_cannot_delete_a_concurrent_human_intervention():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    with patch.object(db, "_pool", pool):
        assert not await db.is_conversation_handoff_active(170, "5215512345678", 12)
    # An echo can commit after SELECT. A read must never delete that new row.
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_handoff_lookup_matches_mexican_device_and_cloud_ids():
    conn = AsyncMock()
    async def stored_handoff(query, bot_id, recipients, *timeout):
        ids = recipients if isinstance(recipients, list) else [recipients]
        return {"1": 1} if bot_id == 170 and "525512345678" in ids else None
    conn.fetchrow.side_effect = stored_handoff
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    with patch.object(db, "_pool", pool):
        assert await db.is_conversation_handoff_active(170, "5215512345678", 12)
        assert not await db.is_conversation_handoff_active(171, "5215512345678", 12)
        assert not await db.is_conversation_handoff_active(170, "5215512345679", 12)


@pytest.mark.asyncio
async def test_assistant_history_does_not_restart_expired_handoff():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"first_role": "assistant", "last_created_at": None}
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    with patch.object(db, "_pool", pool), patch.object(
        db, "is_conversation_handoff_active", AsyncMock(return_value=False)
    ):
        assert not await db.is_conversation_initiated_by_agent(170, "5215512345678", 12)


@pytest.mark.asyncio
@pytest.mark.parametrize("hours,sql_hours", [(12, 12), (0, None)])
async def test_media_and_followup_checks_use_configured_window(hours, sql_hours):
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    with patch.object(db, "_pool", pool), patch.object(db, "get_bot_skill", AsyncMock(
        return_value={"enabled": True, "config": {"handoff_expiration_hours": hours}}
    )):
        assert not await db.is_conversation_handoff_active(170, "5215512345678")
    assert conn.fetchrow.await_args.args[-1] == sql_hours


@pytest.mark.asyncio
async def test_manual_resolution_clears_both_variants_for_only_one_bot():
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    with patch.object(db, "_pool", pool):
        await db.clear_conversation_handoff(170, "525512345678")
    query, bot_id, variants = conn.execute.await_args.args
    assert "bot_id=$1" in query
    assert bot_id == 170
    assert set(variants) == {"525512345678", "5215512345678"}


def test_outgoing_echo_never_enters_customer_pipeline_even_if_rule_disabled():
    payload = {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "phone-170", "display_phone_number": "525599999999"},
        "messages": [{"id": "device-1", "from": "525599999999", "to": "525512345678",
                      "is_echo": True, "type": "text", "text": {"body": "Hola"}}],
    }}]}]}
    assert len(whatsapp_client.extract_human_message_echoes(payload)) == 1
    assert whatsapp_client.extract_messages(payload) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fields,expected", [(["messages"], "missing"), (["messages", "smb_message_echoes"], "verified")])
async def test_diagnostic_checks_app_fields_not_just_waba_subscription(fields, expected):
    runtime = {"bot": {"id": 170, "meta_app_id": "app-test"}, "integration": None, "access_token": ""}
    with patch.object(meta_provider, "get_bot_whatsapp_runtime", AsyncMock(return_value=runtime)), \
         patch.object(meta_provider.config, "META_APP_ID", "app-test"), \
         patch.object(meta_provider.config, "META_APP_SECRET", "test-secret"), \
         patch.object(meta_provider, "graph_get", AsyncMock(return_value={"data": [{
             "object": "whatsapp_business_account", "active": True,
             "fields": [{"name": field} for field in fields],
         }]})) as graph:
        result = await meta_provider.diagnose_bot_connection(170)
    assert result["webhook_field_verification"] == expected
    assert graph.await_args.args[0] == "app-test/subscriptions"
    if expected == "missing":
        assert not result["ok"]
        assert "smb_message_echoes" in result["error"]
