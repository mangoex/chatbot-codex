from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app import db, escalations


@pytest.mark.asyncio
async def test_unified_handoff_db_functions():
    """Verifica que las funciones unificadas de handoff en db interactúen correctamente con la base de datos."""
    with patch("app.db._pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # 1. Set active
        await db.set_conversation_handoff_active(bot_id=1, wa_id="5215512345678")
        mock_conn.execute.assert_called_once()
        assert "INSERT INTO chatwoot_handoffs" in mock_conn.execute.call_args[0][0]

        # 2. Check active (True)
        mock_conn.fetchrow.return_value = {"1": 1}
        is_active = await db.is_conversation_handoff_active(bot_id=1, wa_id="5215512345678")
        assert is_active is True

        # 3. Check active (False)
        mock_conn.fetchrow.return_value = None
        is_active = await db.is_conversation_handoff_active(bot_id=1, wa_id="5215512345678")
        assert is_active is False

        # 4. Clear handoff
        await db.clear_conversation_handoff(bot_id=1, wa_id="5215512345678")
        assert "DELETE FROM chatwoot_handoffs" in mock_conn.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_admin_escalation_update_sets_and_clears_handoff():
    """Verifica que al actualizar una escalación en el panel admin a 'en_proceso' o 'resuelto', se gestione el handoff."""
    from app import admin
    from fastapi import Request

    with patch("app.admin._require_agency", return_value=None), \
         patch("app.db.update_escalation_status", new_callable=AsyncMock) as mock_update, \
         patch("app.db.get_escalation", new_callable=AsyncMock) as mock_get_esc, \
         patch("app.db.set_conversation_handoff_active", new_callable=AsyncMock) as mock_set_handoff, \
         patch("app.db.clear_conversation_handoff", new_callable=AsyncMock) as mock_clear_handoff:

        mock_get_esc.return_value = {
            "id": 42,
            "bot_id": 10,
            "wa_id": "5215599887766",
            "status": "pendiente",
        }

        req = MagicMock(spec=Request)
        req.session = {"admin_logged_in": True, "agency": True}

        # Cambiar a 'en_proceso' activa el handoff para pausar la IA
        await admin.escalation_update(req, eid=42, status="en_proceso", notes="Atendiendo por teléfono")
        mock_set_handoff.assert_awaited_once_with(10, "5215599887766")

        # Cambiar a 'resuelto' limpia el handoff para reanudar el bot
        await admin.escalation_update(req, eid=42, status="resuelto", notes="Caso cerrado")
        mock_clear_handoff.assert_awaited_once_with(10, "5215599887766")
