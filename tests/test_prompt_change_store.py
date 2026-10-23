import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import prompt_changes as pc
from tests.test_prompt_changes import context, ORIGINAL


def receipt(ctx, candidate=ORIGINAL):
    return {"bot_id": 7, "actor": "owner", "context": pc.fingerprint(ctx), "result": pc.fingerprint(candidate)}


def request(role="client_admin", client_id=44):
    return SimpleNamespace(session={"user": "owner", "role": role, "client_id": client_id})


def mock_pool():
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={"id": 13})
    conn.fetchval = AsyncMock(return_value=4)
    conn.execute = AsyncMock()
    conn.transaction.return_value.__aexit__.return_value = False
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = False
    return pool, conn


@pytest.mark.asyncio
async def test_natural_language_route_uses_authoritative_context_and_never_publishes():
    from app import client, db, prompt_change_store as store
    ctx = context()
    with patch.object(db, "get_bot", return_value={"id": 7, "client_id": 44}), \
         patch.object(store, "get_context", return_value=ctx), \
         patch.object(pc, "assist_changes", return_value={"ok": True, "published": False}) as assist, \
         patch.object(store, "publish") as publish:
        response = await client.client_prompt_assist(
            request(), 7, instruction="Cambia el horario del sábado a 9 a 14", current_prompt=ORIGINAL,
            mode="guarded_prompt", pbd_constitution="Reglas manipuladas", auto_publish="true", review_receipt="prior",
        )
        assert response.status_code == 200
        assert json.loads(response.body)["published"] is False
        assert assist.await_args.kwargs["context"] == ctx
        assert assist.await_args.kwargs["receipt"] == "prior"
        assert "Reglas manipuladas" not in str(assist.await_args)
        publish.assert_not_called()


@pytest.mark.asyncio
async def test_blocked_review_keeps_prompt_and_explains_dependency():
    from app import client, db, prompt_change_store as store
    with patch.object(db, "get_bot", return_value={"id": 7, "client_id": 44}), \
         patch.object(store, "get_context", return_value=context()), \
         patch.object(pc, "assist_changes", side_effect=pc.ChangeError("Revisa el horario en Calendario")):
        response = await client.client_prompt_assist(request(), 7, instruction="Cambia horario", mode="guarded_prompt")
        data = json.loads(response.body)
        assert response.status_code == 400
        assert data["blocked"]
        assert "Calendario" in data["blocked_reason"]
        assert "prompt" not in data


@pytest.mark.asyncio
async def test_permissions_for_editing_and_publishing():
    from app import client, db, prompt_change_store as store
    from fastapi import HTTPException
    with patch.object(db, "get_bot", return_value={"id": 7, "client_id": 44}), \
         patch.object(store, "get_context") as read, patch.object(store, "publish") as publish:
        for req in (request(role="client_viewer"), request(client_id=99)):
            with pytest.raises(HTTPException):
                await client.client_prompt_assist(req, 7, instruction="Cambio", mode="guarded_prompt")
            with pytest.raises(HTTPException):
                await client.client_prompt_save(req, 7, prompt=ORIGINAL, review_required="1", review_receipt="signed")
        read.assert_not_called()
        publish.assert_not_called()


@pytest.mark.asyncio
async def test_receipt_required_for_generated_result_even_when_format_is_changed():
    from app import client, db, prompt_change_store as store
    with patch.object(pc.config, "SESSION_SECRET", "local-test-only"), \
         patch.object(db, "get_bot", return_value={"id": 7, "client_id": 44}), \
         patch.object(store, "publish", return_value=13) as publish:
        token = pc._signer().dumps(receipt(context()))
        for bad in ("", token + "x"):
            response = await client.client_prompt_save(
                request(), 7, prompt=ORIGINAL, prompt_format="single_prompt", review_required="1", review_receipt=bad)
            assert "saved=err_" in response.headers["location"]
        publish.assert_not_called()
        response = await client.client_prompt_save(
            request(), 7, prompt=ORIGINAL, prompt_format="pbd", review_required="0", review_receipt=token)
        assert "saved=1" in response.headers["location"]
        publish.assert_awaited_once_with(7, receipt(context()), ORIGINAL)
        publish.side_effect = pc.ChangeError("Las fuentes cambiaron")
        response = await client.client_prompt_save(
            request(), 7, prompt=ORIGINAL, review_required="1", review_receipt=token)
        assert "saved=err_" in response.headers["location"]


@pytest.mark.asyncio
async def test_transaction_preserves_constitution_specs_tests_and_rejects_tampering():
    from app import db, prompt_change_store as store
    ctx = context()
    pool, conn = mock_pool()
    with patch.object(db, "_pool", pool), patch.object(store, "_context", return_value=ctx):
        assert await store.publish(7, receipt(ctx), ORIGINAL.replace("\n", "\r\n")) == 13
    conn.transaction.assert_called_once_with(isolation="serializable")
    assert conn.fetchrow.await_args.args[1:] == (7, 4, ORIGINAL, ctx["previous"]["pbd_constitution"],
                                                ctx["previous"]["pbd_specs"], ctx["previous"]["pbd_test_suite"])
    assert len(conn.fetch.await_args_list) == 4
    assert all("FOR SHARE" in call.args[0] for call in conn.fetch.await_args_list)
    for changed_context, candidate in ((ctx, ORIGINAL + " Otra regla"),
                                       ({**ctx, "knowledge": [{"id": 100}]}, ORIGINAL)):
        pool, conn = mock_pool()
        with patch.object(db, "_pool", pool), patch.object(store, "_context", return_value=changed_context):
            with pytest.raises(pc.ChangeError):
                await store.publish(7, receipt(ctx), candidate)
        conn.execute.assert_not_called()
        assert all("INSERT" not in call.args[0] for call in conn.fetchrow.await_args_list)


@pytest.mark.asyncio
async def test_complete_source_snapshot_and_redacted_configuration():
    from app import db, prompt_change_store as store
    pool, conn = mock_pool()
    conn.fetchrow.side_effect = [context()["bot"], context()["previous"]]
    conn.fetch.side_effect = [
        [{"id": 1, "title": "Fuente", "content": "x" * 40000, "index_status": "indexed"}],
        [{"id": 2, "integration_type": "calendar", "enabled": True,
          "config": '{"location":"Sede","api_key":"dummy-credential"}'}],
        [{"id": 3, "skill_type": "escalation", "enabled": True, "config": {"keywords": ["humano"]}}],
    ]
    with patch.object(db, "_pool", pool):
        ctx = await store.get_context(7)
    assert len(ctx["knowledge"][0]["content"]) == 40000
    assert "dummy-credential" not in json.dumps(ctx)
    assert ctx["integrations"][0]["config"]["location"] == "Sede"
    conn.transaction.assert_called_once_with(isolation="repeatable_read", readonly=True)
    for call in conn.fetch.await_args_list + conn.fetchrow.await_args_list:
        assert call.args[1] == 7


@pytest.mark.asyncio
async def test_serialization_conflict_does_not_publish():
    from app import db, prompt_change_store as store
    class ConcurrentWrite(Exception):
        sqlstate = "40001"
    pool, conn = mock_pool()
    conn.fetchrow.side_effect = ConcurrentWrite()
    with patch.object(db, "_pool", pool), pytest.raises(pc.ChangeError, match="concurrente"):
        await store.publish(7, receipt(context()), ORIGINAL)
    conn.execute.assert_not_called()
