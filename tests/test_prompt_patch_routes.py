"""Route authorization and publication boundary for factual edits."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import prompt_patch as pp
from tests.test_prompt_patch import context, BEFORE, AFTER, ORIGINAL


def request(role="client_admin", client_id=44):
    return SimpleNamespace(session={"user": "owner", "role": role, "client_id": client_id})


def receipt(ctx):
    return {"bot_id": 7, "actor": "owner", "context": pp.fingerprint(ctx), "before": BEFORE, "after": AFTER}


@pytest.mark.asyncio
async def test_assist_uses_server_context_and_never_publishes():
    from app import client, db
    ctx = context()
    with patch.object(db, "get_bot", return_value={"id": 7, "client_id": 44}), \
         patch.object(db, "get_prompt_patch_context", return_value=ctx), \
         patch.object(pp, "review_patch", return_value={"ok": True, "published": False}) as review, \
         patch.object(db, "publish_bot_prompt_patch") as publish:
        response = await client.client_prompt_assist(
            request(), 7, instruction="Cambiar sede", current_prompt=ORIGINAL, mode="targeted_patch",
            patch_before=BEFORE, patch_after=AFTER, pbd_constitution="Reglas manipuladas",
            auto_publish="true", allow_constitution_change="true",
        )
        assert response.status_code == 200
        assert review.await_args.kwargs["context"] == ctx
        assert "Reglas manipuladas" not in str(review.await_args)
        assert json.loads(response.body)["published"] is False
        publish.assert_not_called()


@pytest.mark.asyncio
async def test_assist_returns_block_reason_and_no_candidate():
    from app import client, db
    with patch.object(db, "get_bot", return_value={"id": 7, "client_id": 44}), \
         patch.object(db, "get_prompt_patch_context", return_value=context()), \
         patch.object(pp, "review_patch", side_effect=pp.PatchError("Conflicto con la constitución")):
        response = await client.client_prompt_assist(
            request(), 7, instruction="Cambiar sede", current_prompt=ORIGINAL, mode="targeted_patch",
            patch_before=BEFORE, patch_after=AFTER,
        )
        data = json.loads(response.body)
        assert response.status_code == 400
        assert data["blocked"] is True
        assert "constitución" in data["blocked_reason"]
        assert "prompt" not in data


@pytest.mark.asyncio
async def test_patch_routes_enforce_tenant_and_editor_permissions():
    from app import client, db
    from fastapi import HTTPException
    with patch.object(db, "get_bot", return_value={"id": 7, "client_id": 44}), \
         patch.object(db, "get_prompt_patch_context") as read, \
         patch.object(db, "publish_bot_prompt_patch") as publish:
        for req in (request(role="client_viewer"), request(client_id=99)):
            with pytest.raises(HTTPException):
                await client.client_prompt_assist(req, 7, instruction="Cambia", mode="targeted_patch")
            with pytest.raises(HTTPException):
                await client.client_prompt_save(req, 7, prompt=ORIGINAL, prompt_format="targeted_patch")
        read.assert_not_called()
        publish.assert_not_called()


@pytest.mark.asyncio
async def test_save_requires_valid_receipt_and_surfaces_stale_context():
    from app import client, db
    ctx = context()
    with patch.object(pp.config, "SESSION_SECRET", "local-test-only"), \
         patch.object(db, "get_bot", return_value={"id": 7, "client_id": 44}), \
         patch.object(db, "publish_bot_prompt_patch", return_value=13) as publish:
        token = pp._serializer().dumps(receipt(ctx))
        for bad in ("", token + "x"):
            response = await client.client_prompt_save(
                request(), 7, prompt=ORIGINAL.replace(BEFORE, AFTER), prompt_format="targeted_patch", patch_receipt=bad,
            )
            assert "saved=err_" in response.headers["location"]
        publish.assert_not_called()
        response = await client.client_prompt_save(
            request(), 7, prompt=ORIGINAL.replace(BEFORE, AFTER), prompt_format="targeted_patch", patch_receipt=token,
        )
        assert "saved=1" in response.headers["location"]
        publish.assert_awaited_once_with(7, receipt(ctx), ORIGINAL.replace(BEFORE, AFTER))
        # A supplied receipt cannot be bypassed by downgrading the format field.
        response = await client.client_prompt_save(
            request(), 7, prompt=ORIGINAL.replace(BEFORE, AFTER), prompt_format="single_prompt", patch_receipt=token,
        )
        assert "saved=1" in response.headers["location"]
        assert publish.await_count == 2
        publish.side_effect = pp.PatchError("La base de conocimiento cambió")
        response = await client.client_prompt_save(
            request(), 7, prompt=ORIGINAL.replace(BEFORE, AFTER), prompt_format="targeted_patch", patch_receipt=token,
        )
        assert "saved=err_" in response.headers["location"]


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
async def test_db_publication_revalidates_before_writes_and_preserves_pbd():
    from app import db
    ctx = context()
    pool, conn = mock_pool()
    with patch.object(db, "_pool", pool), patch.object(db, "_prompt_patch_context", return_value=ctx):
        candidate = ORIGINAL.replace(BEFORE, AFTER)
        assert await db.publish_bot_prompt_patch(7, receipt(ctx), candidate) == 13
        conn.transaction.assert_called_once_with(isolation="serializable")
        insertion = conn.fetchrow.await_args.args
        assert insertion[1:] == (7, 4, candidate, ctx["previous"]["pbd_constitution"],
                                ctx["previous"]["pbd_specs"], ctx["previous"]["pbd_test_suite"])
        assert len(conn.fetch.await_args_list) == 4
        assert all("FOR SHARE" in call.args[0] for call in conn.fetch.await_args_list)

    for kind in ("additional_rule", "stale_version", "changed_knowledge"):
        pool, conn = mock_pool()
        changed = copy.deepcopy(ctx)
        submitted = candidate
        if kind == "additional_rule":
            submitted += "\nRegla adicional"
        elif kind == "stale_version":
            changed["previous"]["id"] = 14
        else:
            changed["knowledge"] = [{"id": 1, "content": "Otra dirección"}]
        with patch.object(db, "_pool", pool), patch.object(db, "_prompt_patch_context", return_value=changed):
            with pytest.raises(pp.PatchError):
                await db.publish_bot_prompt_patch(7, receipt(ctx), submitted)
            conn.execute.assert_not_called()
            assert all("INSERT" not in call.args[0] for call in conn.fetchrow.await_args_list)


@pytest.mark.asyncio
async def test_context_loads_complete_sources_and_omits_credentials():
    from app import db
    pool, conn = mock_pool()
    conn.fetchrow.side_effect = [context()["bot"], context()["previous"]]
    conn.fetch.side_effect = [
        [{"id": 1, "title": "Fuente", "content": "z" * 40000, "index_status": "indexed"}],
        [{"id": 2, "integration_type": "calendar", "enabled": True,
          "config": '{"location":"Sede","api_key":"dummy-credential"}'}],
        [{"id": 3, "skill_type": "escalation", "enabled": True, "config": {"keywords": ["humano"]}}],
    ]
    with patch.object(db, "_pool", pool):
        ctx = await db.get_prompt_patch_context(7)
    assert len(ctx["knowledge"][0]["content"]) == 40000
    assert "dummy-credential" not in json.dumps(ctx)
    assert ctx["integrations"][0]["config"]["location"] == "Sede"
    assert ctx["skills"][0]["config"]["keywords"] == ["humano"]
    conn.transaction.assert_called_once_with(isolation="repeatable_read", readonly=True)
    for call in conn.fetch.await_args_list + conn.fetchrow.await_args_list:
        assert call.args[1] == 7


@pytest.mark.asyncio
async def test_serialization_conflict_is_a_reviewable_block():
    from app import db
    class ConcurrentWrite(Exception):
        sqlstate = "40001"
    pool, conn = mock_pool()
    conn.fetchrow.side_effect = ConcurrentWrite()
    with patch.object(db, "_pool", pool), pytest.raises(pp.PatchError, match="concurrente"):
        await db.publish_bot_prompt_patch(7, receipt(context()), ORIGINAL.replace(BEFORE, AFTER))
    conn.execute.assert_not_called()
