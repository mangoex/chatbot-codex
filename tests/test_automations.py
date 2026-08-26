import pytest
import os
import json
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

# Mock asyncpg and dotenv before imports
import sys
import types
sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import client, db, meta_provider


@pytest.mark.asyncio
@patch("app.client._require_bot_editor")
@patch("app.db.create_template_trigger")
async def test_client_trigger_create_endpoint(mock_create_trigger, mock_require_editor):
    from fastapi import BackgroundTasks
    from starlette.requests import Request
    from starlette.datastructures import Headers, FormData

    mock_create_trigger.return_value = 5
    mock_require_editor.return_value = {"id": 43, "name": "Bot Test"}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/client/bots/43/triggers/create",
        "headers": [(b"host", b"testserver")],
        "session": {"user": "client@test.com", "role": "client_admin", "client_id": 1, "bot_id": 43},
    }
    request = Request(scope)

    # Form with 2 variable mappings
    async def mock_form():
        return FormData([
            ("trigger_name", "Reactivacion 24h"),
            ("trigger_type", "inactivity_hours"),
            ("inactivity_hours", "24"),
            ("crm_status", ""),
            ("template_name", "reactivacion_lead"),
            ("language_code", "es_MX"),
            ("vars_count", "2"),
            ("var_map_type_1", "name"),
            ("var_map_value_1", ""),
            ("var_map_type_2", "fixed"),
            ("var_map_value_2", "Promoción Especial"),
        ])
    request.form = mock_form

    response = await client.client_trigger_create(
        request=request,
        bot_id=43,
        trigger_name="Reactivacion 24h",
        trigger_type="inactivity_hours",
        template_name="reactivacion_lead",
        language_code="es_MX",
        inactivity_hours=24,
        crm_status="",
        vars_count=2,
    )

    assert response.status_code == 302
    assert "tab=campaigns" in response.headers["location"]
    assert "saved=trigger_created" in response.headers["location"]
    mock_create_trigger.assert_called_once()
    call_args = mock_create_trigger.call_args[1]
    assert call_args["bot_id"] == 43
    assert call_args["name"] == "Reactivacion 24h"
    assert call_args["trigger_type"] == "inactivity_hours"
    assert call_args["trigger_config"] == {"inactivity_hours": 24}
    assert call_args["template_name"] == "reactivacion_lead"
    assert len(call_args["variable_mappings"]) == 2


@pytest.mark.asyncio
@patch("app.client._require_bot_editor")
@patch("app.db.update_template_trigger_status")
async def test_client_trigger_toggle_endpoint(mock_update_status, mock_require_editor):
    from starlette.requests import Request

    mock_require_editor.return_value = {"id": 43, "name": "Bot Test"}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/client/bots/43/triggers/5/toggle",
        "headers": [(b"host", b"testserver")],
        "session": {"user": "client@test.com", "role": "client_admin", "client_id": 1, "bot_id": 43},
    }
    request = Request(scope)

    response = await client.client_trigger_toggle(
        request=request,
        bot_id=43,
        trigger_id=5,
        is_active=False,
    )

    assert response.status_code == 302
    assert "tab=campaigns" in response.headers["location"]
    mock_update_status.assert_called_once_with(5, 43, False)


@pytest.mark.asyncio
@patch("app.client._require_bot_editor")
@patch("app.db.delete_template_trigger")
async def test_client_trigger_delete_endpoint(mock_delete_trigger, mock_require_editor):
    from starlette.requests import Request

    mock_require_editor.return_value = {"id": 43, "name": "Bot Test"}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/client/bots/43/triggers/5/delete",
        "headers": [(b"host", b"testserver")],
        "session": {"user": "client@test.com", "role": "client_admin", "client_id": 1, "bot_id": 43},
    }
    request = Request(scope)

    response = await client.client_trigger_delete(
        request=request,
        bot_id=43,
        trigger_id=5,
    )

    assert response.status_code == 302
    assert "tab=campaigns" in response.headers["location"]
    mock_delete_trigger.assert_called_once_with(5, 43)


@pytest.mark.asyncio
@patch("app.db.get_due_scheduled_broadcasts")
@patch("app.client.process_broadcast_queue")
async def test_process_scheduled_campaigns(mock_process_broadcast, mock_get_due):
    from app import automations

    mock_get_due.return_value = [
        {"id": 101, "bot_id": 43},
        {"id": 102, "bot_id": 44},
    ]

    await automations.process_scheduled_campaigns()

    # Allow spawned tasks to run
    await asyncio.sleep(0.01)

    assert mock_process_broadcast.call_count == 2
    mock_process_broadcast.assert_any_call(101, 43)
    mock_process_broadcast.assert_any_call(102, 44)


@pytest.mark.asyncio
@patch("app.db.list_active_template_triggers_by_type")
@patch("app.db.get_inactive_conversations_for_trigger")
@patch("app.db.has_recent_trigger_execution")
@patch("app.meta_provider.send_template_message")
@patch("app.db.record_trigger_execution")
async def test_evaluate_inactivity_triggers(
    mock_record_exec,
    mock_send_template,
    mock_has_recent,
    mock_get_inactive,
    mock_list_triggers,
):
    from app import automations

    mock_list_triggers.return_value = [
        {
            "id": 1,
            "bot_id": 43,
            "name": "Reactivar tras 24h",
            "trigger_type": "inactivity_hours",
            "trigger_config": {"inactivity_hours": 24},
            "template_name": "reactivar_lead",
            "language_code": "es_MX",
            "variable_mappings": [
                {"var_idx": 1, "type": "name", "value": ""},
            ],
            "is_active": True,
        }
    ]

    mock_get_inactive.return_value = [
        {
            "wa_id": "5215512345678",
            "contact_name": "Carlos Gomez",
            "contact_business": "Empresa ABC",
            "last_message_at": datetime.now(timezone.utc) - timedelta(hours=25),
        }
    ]
    mock_has_recent.return_value = False

    await automations.evaluate_inactivity_triggers()

    mock_send_template.assert_called_once_with(
        bot_id=43,
        to_wa_id="5215512345678",
        template_name="reactivar_lead",
        language_code="es_MX",
        parameters=["Carlos Gomez"],
    )
    mock_record_exec.assert_called_once()
    assert mock_record_exec.call_args[1]["status"] == "sent"


@pytest.mark.asyncio
@patch("app.db.list_active_template_triggers_by_type")
@patch("app.db.get_contact_by_wa_id")
@patch("app.meta_provider.send_template_message")
@patch("app.db.record_trigger_execution")
async def test_trigger_crm_status_change(
    mock_record_exec,
    mock_send_template,
    mock_get_contact_by_wa_id,
    mock_list_triggers,
):
    from app import automations

    mock_list_triggers.return_value = [
        {
            "id": 2,
            "bot_id": 43,
            "name": "Bienvenida Calificado",
            "trigger_type": "crm_status_changed",
            "trigger_config": {"crm_status": "calificado"},
            "template_name": "bienvenida_calificado",
            "language_code": "es_MX",
            "variable_mappings": [
                {"var_idx": 1, "type": "name", "value": ""},
                {"var_idx": 2, "type": "fixed", "value": "Asistto Plus"},
            ],
            "is_active": True,
        }
    ]

    mock_get_contact_by_wa_id.return_value = {
        "wa_id": "5215587654321",
        "name": "Lucia Mendez",
        "business": "Inmobiliaria Real",
    }

    await automations.trigger_crm_status_change(
        bot_id=43,
        wa_id="5215587654321",
        new_status="calificado",
        old_status="pendiente",
    )

    mock_send_template.assert_called_once_with(
        bot_id=43,
        to_wa_id="5215587654321",
        template_name="bienvenida_calificado",
        language_code="es_MX",
        parameters=["Lucia Mendez", "Asistto Plus"],
    )
    mock_record_exec.assert_called_once()
    assert mock_record_exec.call_args[1]["status"] == "sent"
