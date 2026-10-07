import pytest
import os
import csv
import openpyxl
import io
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# Mock asyncpg, cryptography, and dotenv before imports
import sys
import types
sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import client, db, meta_provider


@pytest.fixture
def temp_csv_file(tmp_path):
    csv_file = tmp_path / "contacts.csv"
    with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Phone", "Full Name", "Company", "Tags"])
        writer.writerow(["5216869032840", "Juan Perez", "Clinica Smile", "VIP, Frecuente"])
        writer.writerow(["+1 555-0199", "John Doe", "Tech Corp", "Lead"])
    return str(csv_file)


@pytest.fixture
def temp_xlsx_file(tmp_path):
    xlsx_file = tmp_path / "contacts.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Phone", "Full Name", "Company", "Tags"])
    ws.append(["5216869032840", "Juan Perez", "Clinica Smile", "VIP, Frecuente"])
    ws.append(["+1 555-0199", "John Doe", "Tech Corp", "Lead"])
    wb.save(xlsx_file)
    return str(xlsx_file)


def test_extract_headers_from_file_csv(temp_csv_file):
    headers = client.extract_headers_from_file(temp_csv_file)
    assert headers == ["Phone", "Full Name", "Company", "Tags"]


def test_extract_headers_from_file_xlsx(temp_xlsx_file):
    headers = client.extract_headers_from_file(temp_xlsx_file)
    assert headers == ["Phone", "Full Name", "Company", "Tags"]


def test_parse_contacts_file_csv(temp_csv_file):
    contacts = client.parse_contacts_file(
        temp_csv_file,
        phone_col_idx=0,
        name_col_idx=1,
        business_col_idx=2,
        tags_col_idx=3,
    )
    assert len(contacts) == 2
    assert contacts[0] == {
        "wa_id": "5216869032840",
        "name": "Juan Perez",
        "business": "Clinica Smile",
        "tags": "VIP, Frecuente",
    }
    assert contacts[1] == {
        "wa_id": "+1 555-0199",
        "name": "John Doe",
        "business": "Tech Corp",
        "tags": "Lead",
    }


def test_parse_contacts_file_xlsx(temp_xlsx_file):
    contacts = client.parse_contacts_file(
        temp_xlsx_file,
        phone_col_idx=0,
        name_col_idx=1,
        business_col_idx=2,
        tags_col_idx=3,
    )
    assert len(contacts) == 2
    assert contacts[0] == {
        "wa_id": "5216869032840",
        "name": "Juan Perez",
        "business": "Clinica Smile",
        "tags": "VIP, Frecuente",
    }
    assert contacts[1] == {
        "wa_id": "+1 555-0199",
        "name": "John Doe",
        "business": "Tech Corp",
        "tags": "Lead",
    }


@pytest.mark.asyncio
@patch("app.db.update_broadcast_status")
@patch("app.db.get_broadcast")
@patch("app.db.get_pending_broadcast_recipients")
@patch("app.meta_provider.send_template_message")
@patch("app.db.update_broadcast_recipient_status")
async def test_process_broadcast_queue(
    mock_update_recipient_status,
    mock_send_template,
    mock_get_pending_recipients,
    mock_get_broadcast,
    mock_update_status,
):
    # Setup mocks
    mock_get_broadcast.return_value = {
        "id": 10,
        "bot_id": 43,
        "name": "Promo Test",
        "template_name": "welcome_template",
        "language_code": "es_MX",
        "variable_mappings": json.dumps([
            {"type": "name", "value": ""},
            {"type": "fixed", "value": "20%"},
            {"type": "business", "value": ""},
        ]),
    }

    # First iteration returns recipients, second returns empty list to stop loop
    mock_get_pending_recipients.side_effect = [
        [
            {
                "id": 101,
                "wa_id": "5216869032840",
                "contact_name": "Juan",
                "contact_business": "Smile Clinic",
            }
        ],
        []
    ]

    mock_send_template.return_value = {"wamid": "wamid.HBg12345", "response": {"messages": [{"id": "wamid.HBg12345"}]}}

    with patch("app.db.is_conversation_handoff_active", AsyncMock(return_value=False)):
        await client.process_broadcast_queue(broadcast_id=10, bot_id=43)

    # Check calls
    mock_update_status.assert_any_call(10, "running")
    mock_update_status.assert_any_call(10, "completed")
    
    # Verify parameter mapping resolution: name -> "Juan", fixed -> "20%", business -> "Smile Clinic"
    mock_send_template.assert_called_once_with(
        bot_id=43,
        to_wa_id="5216869032840",
        template_name="welcome_template",
        language_code="es_MX",
        parameters=["Juan", "20%", "Smile Clinic"],
        header_type=None,
        header_media_url=None,
    )
    
    mock_update_recipient_status.assert_called_once_with(101, "accepted", wamid="wamid.HBg12345")


@pytest.mark.asyncio
@patch("app.client._require_client_login")
@patch("app.client._require_bot_editor")
@patch("app.db.upsert_contact")
async def test_client_contacts_create_manual(
    mock_upsert,
    mock_editor,
    mock_login,
):
    mock_login.return_value = {"client_id": 44, "user": "user@test.com", "role": "client_admin"}
    
    class MockRequest:
        session = {}

    response = await client.client_contacts_create_manual(
        MockRequest(),
        bot_id=43,
        name="Jose Lopez",
        wa_id="+52 (686) 903-28-40",
        business="Abarrotes Jose",
        tags="Cliente, VIP",
    )

    assert response.status_code == 302
    assert "saved=1" in response.headers["location"]
    # Phone number should be cleaned: +52 (686) 903-28-40 -> 526869032840
    mock_upsert.assert_called_once_with(
        43,
        wa_id="526869032840",
        name="Jose Lopez",
        business="Abarrotes Jose",
        tags="Cliente, VIP",
    )


@pytest.mark.asyncio
@patch("app.client._require_client_login")
@patch("app.client._require_bot_editor")
@patch("app.db.delete_contacts")
async def test_client_contacts_delete(
    mock_delete,
    mock_editor,
    mock_login,
):
    mock_login.return_value = {"client_id": 44, "user": "user@test.com", "role": "client_admin"}
    
    class MockRequest:
        session = {}

    response = await client.client_contacts_delete(
        MockRequest(),
        bot_id=43,
        selected_contacts=["5216869032840", "15550199"]
    )

    assert response.status_code == 302
    assert "deleted=2" in response.headers["location"]
    mock_delete.assert_called_once_with(43, ["5216869032840", "15550199"])


@pytest.mark.asyncio
@patch("app.client._require_client_login")
@patch("app.client._require_bot_editor")
@patch("app.db.list_contacts")
@patch("app.db.create_broadcast")
async def test_client_campaigns_create(
    mock_create_broadcast,
    mock_list_contacts,
    mock_editor,
    mock_login,
):
    mock_login.return_value = {"client_id": 44, "user": "user@test.com", "role": "client_admin"}
    mock_list_contacts.return_value = [
        {"wa_id": "5216869032840", "name": "Juan Perez", "business": "Smile"},
        {"wa_id": "15550199", "name": "John Doe", "business": "Tech"},
    ]
    mock_create_broadcast.return_value = 55
    
    # Mock FastAPI Request Form data
    class MockRequest:
        session = {}
        async def form(self):
            return {
                "var_map_type_1": "name",
                "var_map_value_1": "",
                "var_map_type_2": "fixed",
                "var_map_value_2": "PromoCode10",
            }

    background_tasks_mock = MagicMock()

    response = await client.client_campaigns_create(
        MockRequest(),
        bot_id=43,
        background_tasks=background_tasks_mock,
        campaign_name="Test Campaign",
        template_name="hello_world",
        language_code="es_MX",
        recipients_option="selected",
        selected_wa_ids="5216869032840",
        vars_count=2,
        confirm_send="CONFIRMAR",
    )

    assert response.status_code == 302
    assert "saved=1" in response.headers["location"]
    
    # Should create broadcast in db
    mock_create_broadcast.assert_called_once_with(
        bot_id=43,
        name="Test Campaign",
        template_name="hello_world",
        language_code="es_MX",
        variable_mappings=[
            {"var_idx": 1, "type": "name", "value": ""},
            {"var_idx": 2, "type": "fixed", "value": "PromoCode10"},
        ],
        recipients=[
            {"wa_id": "5216869032840", "name": "Juan Perez", "business": "Smile"}
        ],
        header_type=None,
        header_media_url=None,
    )
    
    # Should schedule task in background tasks
    background_tasks_mock.add_task.assert_called_once()


@pytest.mark.asyncio
@patch("app.db.update_broadcast_status")
@patch("app.db.get_broadcast")
@patch("app.db.get_pending_broadcast_recipients")
@patch("app.meta_provider.send_template_message")
@patch("app.db.update_broadcast_recipient_status")
async def test_process_broadcast_queue_with_image_header(
    mock_update_recipient_status,
    mock_send_template,
    mock_get_pending_recipients,
    mock_get_broadcast,
    mock_update_status,
):
    """Verifica que los encabezados con imagen se propagan a send_template_message."""
    mock_get_broadcast.side_effect = [
        {
            "id": 12,
            "bot_id": 43,
            "name": "Promo Tacos con Foto",
            "template_name": "mimenu_tacos",
            "language_code": "es_MX",
            "header_type": "image",
            "header_media_url": "https://images.unsplash.com/photo-tacos.jpg",
            "variable_mappings": json.dumps([{"type": "name", "value": ""}]),
        },
        # final_b call
        {
            "id": 12,
            "bot_id": 43,
            "sent_count": 1,
            "failed_count": 0,
        }
    ]

    mock_get_pending_recipients.side_effect = [
        [{"id": 201, "wa_id": "5216861234567", "contact_name": "Carlos", "contact_business": ""}],
        []
    ]

    mock_send_template.return_value = {"wamid": "wamid.HBgHeaderTest"}

    with patch("app.db.is_conversation_handoff_active", AsyncMock(return_value=False)):
        await client.process_broadcast_queue(broadcast_id=12, bot_id=43)

    mock_send_template.assert_called_once_with(
        bot_id=43,
        to_wa_id="5216861234567",
        template_name="mimenu_tacos",
        language_code="es_MX",
        parameters=["Carlos"],
        header_type="image",
        header_media_url="https://images.unsplash.com/photo-tacos.jpg",
    )
    mock_update_recipient_status.assert_called_once_with(201, "accepted", wamid="wamid.HBgHeaderTest")
    mock_update_status.assert_any_call(12, "completed")


@pytest.mark.asyncio
@patch("app.db.update_broadcast_status")
@patch("app.db.get_broadcast")
@patch("app.db.get_pending_broadcast_recipients")
@patch("app.meta_provider.send_template_message")
@patch("app.db.update_broadcast_recipient_status")
async def test_process_broadcast_queue_handles_meta_error_and_marks_failed(
    mock_update_recipient_status,
    mock_send_template,
    mock_get_pending_recipients,
    mock_get_broadcast,
    mock_update_status,
):
    """Verifica que los errores de Meta se capturen y el estado final sea 'failed' si no hubo envíos exitosos."""
    mock_get_broadcast.side_effect = [
        {
            "id": 15,
            "bot_id": 43,
            "name": "Fallo Meta Header",
            "template_name": "mimenu_tacos",
            "language_code": "es_MX",
            "header_type": None,
            "header_media_url": None,
            "variable_mappings": "[]",
        },
        # final_b call
        {
            "id": 15,
            "bot_id": 43,
            "sent_count": 0,
            "failed_count": 1,
        }
    ]

    mock_get_pending_recipients.side_effect = [
        [{"id": 301, "wa_id": "5216869999999", "contact_name": "Ana", "contact_business": ""}],
        []
    ]

    meta_error = "Meta API error 100 (OAuthException): Param template['components'] is invalid: expected IMAGE"
    mock_send_template.side_effect = Exception(meta_error)

    with patch("app.db.is_conversation_handoff_active", AsyncMock(return_value=False)):
        await client.process_broadcast_queue(broadcast_id=15, bot_id=43)

    mock_update_recipient_status.assert_called_once_with(301, "failed", error_message=meta_error)
    # Status should be updated to 'failed' because sent_count is 0 and failed_count > 0
    mock_update_status.assert_any_call(15, "failed")


@pytest.mark.asyncio
@patch("app.client._require_client_login")
@patch("app.client._require_bot_editor")
@patch("app.db.list_contacts")
@patch("app.db.create_broadcast")
async def test_client_campaigns_create_with_header_image(
    mock_create_broadcast,
    mock_list_contacts,
    mock_editor,
    mock_login,
):
    mock_login.return_value = {"client_id": 44, "user": "user@test.com", "role": "client_admin"}
    mock_list_contacts.return_value = [
        {"wa_id": "5216869032840", "name": "Juan Perez", "business": "Smile"}
    ]
    mock_create_broadcast.return_value = 88

    class MockRequest:
        session = {}
        async def form(self):
            return {}

    background_tasks_mock = MagicMock()

    response = await client.client_campaigns_create(
        MockRequest(),
        bot_id=43,
        background_tasks=background_tasks_mock,
        campaign_name="Campaña Con Foto",
        template_name="mimenu_tacos",
        language_code="es_MX",
        recipients_option="selected",
        selected_wa_ids="5216869032840",
        vars_count=0,
        confirm_send="CONFIRMAR",
        header_type="IMAGE",
        header_media_url="https://ejemplo.com/tacos.jpg",
    )

    assert response.status_code == 302
    assert "saved=1" in response.headers["location"]

    mock_create_broadcast.assert_called_once_with(
        bot_id=43,
        name="Campaña Con Foto",
        template_name="mimenu_tacos",
        language_code="es_MX",
        variable_mappings=[],
        recipients=[{"wa_id": "5216869032840", "name": "Juan Perez", "business": "Smile"}],
        header_type="image",
        header_media_url="https://ejemplo.com/tacos.jpg",
    )


@pytest.mark.asyncio
@patch("app.client._require_client_login")
@patch("app.client._require_bot_editor")
@patch("app.db.create_template_trigger")
async def test_client_trigger_create_with_header_image(
    mock_create_trigger,
    mock_editor,
    mock_login,
):
    mock_login.return_value = {"client_id": 44, "user": "user@test.com", "role": "client_admin"}

    class MockRequest:
        session = {}
        async def form(self):
            return {}

    response = await client.client_trigger_create(
        MockRequest(),
        bot_id=43,
        trigger_name="Disparador Reenganche con Imagen",
        trigger_type="inactivity_hours",
        template_name="mimenu_tacos",
        language_code="es_MX",
        inactivity_hours=48,
        header_type="IMAGE",
        header_media_url="https://ejemplo.com/banner.png",
    )

    assert response.status_code == 302
    assert "saved=trigger_created" in response.headers["location"]

    mock_create_trigger.assert_called_once_with(
        bot_id=43,
        name="Disparador Reenganche con Imagen",
        trigger_type="inactivity_hours",
        trigger_config={
            "inactivity_hours": 48,
            "header_type": "image",
            "header_media_url": "https://ejemplo.com/banner.png",
        },
        template_name="mimenu_tacos",
        language_code="es_MX",
        variable_mappings=[],
        is_active=True,
    )


@pytest.mark.asyncio
@patch("app.client._require_client_login")
@patch("app.client._require_bot_editor")
@patch("app.db.get_broadcast")
@patch("app.db.list_broadcast_recipients")
async def test_client_get_campaign_recipients_endpoint(
    mock_list_recipients,
    mock_get_broadcast,
    mock_editor,
    mock_login,
):
    mock_login.return_value = {"client_id": 44, "user": "user@test.com", "role": "client_admin"}
    mock_get_broadcast.return_value = {
        "id": 10,
        "name": "Campaña Test",
        "template_name": "promo_1",
        "total_recipients": 2,
        "accepted_count": 2,
        "delivered_count": 1,
        "read_count": 1,
        "sent_count": 2,
        "failed_count": 0,
    }
    mock_list_recipients.return_value = [
        {
            "id": 101,
            "wa_id": "5215512345678",
            "contact_name": "Ana",
            "status": "read",
            "wamid": "wamid.HBg9999",
            "error_message": None,
            "error_data": None,
            "sent_at": None,
            "delivered_at": None,
            "read_at": None,
            "status_timestamp": None,
        },
        {
            "id": 102,
            "wa_id": "5215587654321",
            "contact_name": "Carlos",
            "status": "failed",
            "wamid": "wamid.HBg8888",
            "error_message": "Meta Error 131026: Undeliverable",
            "error_data": {"code": 131026},
            "sent_at": None,
            "delivered_at": None,
            "read_at": None,
            "status_timestamp": None,
        },
    ]

    class MockRequest:
        session = {}

    response = await client.client_get_campaign_recipients(
        MockRequest(),
        bot_id=43,
        broadcast_id=10,
    )

    assert response.status_code == 200
    data = json.loads(response.body)
    assert data["campaign"]["id"] == 10
    assert data["campaign"]["delivered_count"] == 1
    assert data["campaign"]["read_count"] == 1
    assert len(data["recipients"]) == 2
    assert data["recipients"][0]["wamid"] == "wamid.HBg9999"
    assert data["recipients"][0]["status"] == "read"
    assert data["recipients"][1]["status"] == "failed"
    assert "131026" in data["recipients"][1]["error_message"]


@pytest.mark.asyncio
@patch("app.meta_provider.get_bot_whatsapp_runtime")
@patch("app.meta_provider.graph_post")
@patch("app.db.save_message")
async def test_send_template_message_extracts_wamid(mock_save_msg, mock_graph_post, mock_runtime):
    mock_runtime.return_value = {
        "bot": {"phone_number_id": "123456", "whatsapp_access_token": "token123"},
        "integration": {},
        "access_token": "token123",
    }
    mock_graph_post.return_value = {
        "messaging_product": "whatsapp",
        "contacts": [{"input": "5215512345678", "wa_id": "5215512345678"}],
        "messages": [{"id": "wamid.HBgTestMessageId123"}],
    }

    res = await meta_provider.send_template_message(
        bot_id=1,
        to_wa_id="5215512345678",
        template_name="test_tpl",
        language_code="es_MX",
    )

    assert res["wamid"] == "wamid.HBgTestMessageId123"
    assert res["phone_number_id"] == "123456"


def test_whatsapp_client_extract_statuses_with_errors():
    from app import whatsapp_client

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1000",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5215500000000",
                                "phone_number_id": "999888",
                            },
                            "statuses": [
                                {
                                    "id": "wamid.HBgFailureStatus",
                                    "status": "failed",
                                    "timestamp": "1728248400",
                                    "recipient_id": "5215512345678",
                                    "errors": [
                                        {
                                            "code": 131026,
                                            "title": "Message undeliverable",
                                            "message": "Message Undeliverable",
                                            "error_data": {
                                                "details": "Cloud API message undeliverable"
                                            },
                                        }
                                    ],
                                },
                                {
                                    "id": "wamid.HBgDeliveredStatus",
                                    "status": "delivered",
                                    "timestamp": "1728248410",
                                    "recipient_id": "5215599999999",
                                },
                            ],
                        },
                    }
                ],
            }
        ],
    }

    statuses = whatsapp_client.extract_statuses(payload)
    assert len(statuses) == 2

    s0 = statuses[0]
    assert s0["wamid"] == "wamid.HBgFailureStatus"
    assert s0["status"] == "failed"
    assert s0["recipient_id"] == "5215512345678"
    assert s0["phone_number_id"] == "999888"
    assert len(s0["errors"]) == 1
    assert s0["errors"][0]["code"] == 131026

    s1 = statuses[1]
    assert s1["wamid"] == "wamid.HBgDeliveredStatus"
    assert s1["status"] == "delivered"
    assert s1["recipient_id"] == "5215599999999"
    assert s1["errors"] == []


def test_parse_contacts_file_latin1_and_semicolon(tmp_path):
    """Verifica que el parser soporte archivos CSV con codificación Latin-1 y delimitador de punto y coma."""
    csv_file = tmp_path / "latin1_contacts.csv"
    content = "Nombre;Teléfono;Negocio;Tags\nTaquería Sinaloa;526675014742;Taquería;Score A\nTaquería El Viejón;526677674125;Taquería;Score A\n"
    with open(csv_file, "w", encoding="latin-1") as f:
        f.write(content)

    headers = client.extract_headers_from_file(str(csv_file))
    assert headers == ["Nombre", "Teléfono", "Negocio", "Tags"]

    contacts = client.parse_contacts_file(
        str(csv_file),
        phone_col_idx=1,
        name_col_idx=0,
        business_col_idx=2,
        tags_col_idx=3,
    )
    assert len(contacts) == 2
    assert contacts[0]["name"] == "Taquería Sinaloa"
    assert contacts[0]["wa_id"] == "526675014742"
    assert contacts[0]["business"] == "Taquería"
    assert contacts[1]["name"] == "Taquería El Viejón"


def test_parse_contacts_file_xlsx_numeric_phone(tmp_path):
    """Verifica que números telefónicos numéricos o floats en Excel no sufran distorsión."""
    xlsx_file = tmp_path / "numeric_contacts.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Nombre", "Telefono", "Negocio"])
    ws.append(["Tacos Don Pepe", 526671234567.0, "Taquería"])
    wb.save(xlsx_file)

    contacts = client.parse_contacts_file(
        str(xlsx_file),
        phone_col_idx=1,
        name_col_idx=0,
        business_col_idx=2,
    )
    assert len(contacts) == 1
    assert contacts[0]["wa_id"] == "526671234567"
    assert contacts[0]["name"] == "Tacos Don Pepe"



