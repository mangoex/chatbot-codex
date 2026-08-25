from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app import easybroker_client, db, secure_store


@pytest.mark.asyncio
async def test_format_property_doc():
    """Verifica que el formateador transforme correctamente el payload de Easybroker a un documento para RAG."""
    raw_prop = {
        "public_id": "EB-12345",
        "title": "Hermosa Casa en Providencia",
        "property_type": "House",
        "description": "Excelente casa con amplio jardín, acabados de lujo y paneles solares.",
        "location": "Providencia, Guadalajara, Jalisco",
        "bedrooms": 3,
        "bathrooms": 2.5,
        "parking_spaces": 2,
        "lot_size": 250,
        "construction_size": 220,
        "public_url": "https://www.easybroker.com/mx/inmueble/EB-12345",
        "operations": [
            {
                "type": "sale",
                "amount": 4500000,
                "currency": "MXN",
                "formatted_amount": "$4,500,000 MXN",
            }
        ],
    }

    title, content = easybroker_client.format_property_doc(raw_prop)

    assert "[Easybroker]" in title
    assert "EB-12345" in title
    assert "Hermosa Casa en Providencia" in title

    assert "Precio de Venta: $4,500,000 MXN" in content or "4500000" in content
    assert "Ubicación: Providencia, Guadalajara, Jalisco" in content
    assert "Recámaras: 3" in content
    assert "Baños: 2.5" in content
    assert "Estacionamientos: 2" in content
    assert "https://www.easybroker.com/mx/inmueble/EB-12345" in content
    assert "acabados de lujo" in content


@pytest.mark.asyncio
async def test_verify_api_key_success():
    """Verifica que verify_api_key retorne True cuando la API de Easybroker responde 200."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"pagination": {"total": 10}, "content": []},
            raise_for_status=lambda: None,
        )
        mock_client_cls.return_value = mock_instance

        ok, message = await easybroker_client.verify_api_key("valid_api_key_123")
        assert ok is True
        assert "éxito" in message.lower() or "correcta" in message.lower() or "verificada" in message.lower()


@pytest.mark.asyncio
async def test_verify_api_key_failure():
    """Verifica que verify_api_key maneje credenciales inválidas (401/403)."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_response = MagicMock(status_code=401, text="Unauthorized")
        mock_instance.get.side_effect = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_response)
        mock_client_cls.return_value = mock_instance

        ok, message = await easybroker_client.verify_api_key("invalid_key")
        assert ok is False
        assert "no válida" in message.lower() or "inválida" in message.lower() or "error" in message.lower()


@pytest.mark.asyncio
async def test_fetch_all_properties():
    """Verifica la paginación y obtención de propiedades desde Easybroker."""
    page_1 = {
        "pagination": {"page": 1, "total": 2, "next_page": None},
        "content": [
            {"public_id": "EB-1", "title": "Casa 1", "operations": [{"type": "sale", "amount": 1000000, "currency": "MXN"}]},
            {"public_id": "EB-2", "title": "Depto 2", "operations": [{"type": "rental", "amount": 15000, "currency": "MXN"}]},
        ],
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.get.return_value = MagicMock(
            status_code=200,
            json=lambda: page_1,
            raise_for_status=lambda: None,
        )
        mock_client_cls.return_value = mock_instance

        props = await easybroker_client.fetch_all_properties("valid_key", limit=10)
        assert len(props) == 2
        assert props[0]["public_id"] == "EB-1"
        assert props[1]["public_id"] == "EB-2"


@pytest.mark.asyncio
async def test_send_contact_request():
    """Verifica el envío de un lead / contacto a Easybroker."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "successful"},
            raise_for_status=lambda: None,
        )
        mock_client_cls.return_value = mock_instance

        lead_data = {
            "name": "Juan Pérez",
            "phone": "5512345678",
            "email": "juan@example.com",
            "message": "Hola, me interesa la casa en Providencia",
            "property_id": "EB-12345",
        }

        ok = await easybroker_client.send_contact_request("valid_key", lead_data)
        assert ok is True
        mock_instance.post.assert_called_once()
        _, kwargs = mock_instance.post.call_args
        assert kwargs["headers"]["X-Authorization"] == "valid_key"
        assert kwargs["json"]["name"] == "Juan Pérez"
        assert kwargs["json"]["property_id"] == "EB-12345"


@pytest.mark.asyncio
async def test_sync_properties_to_bot_knowledge():
    """Verifica que la sincronización elimine docs antiguos de Easybroker y cree los nuevos en el bot."""
    sample_props = [
        {
            "public_id": "EB-TEST-1",
            "title": "Departamento en Renta",
            "property_type": "Apartment",
            "description": "2 recámaras con balcón",
            "location": "Americana, Guadalajara",
            "bedrooms": 2,
            "bathrooms": 1,
            "operations": [{"type": "rental", "amount": 18000, "currency": "MXN"}],
        }
    ]

    with patch("app.easybroker_client.fetch_all_properties", new_callable=AsyncMock) as mock_fetch, \
         patch("app.db._pool") as mock_pool:

        mock_fetch.return_value = sample_props
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 1")
        mock_conn.fetchrow = AsyncMock(return_value={"id": 99})
        mock_tx = MagicMock()
        mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction.return_value = mock_tx
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        res = await easybroker_client.sync_properties_to_bot_knowledge(
            bot_id=147,
            api_key="valid_key",
        )

        assert res["success"] is True
        assert res["synced_count"] == 1
        assert res["bot_id"] == 147


@pytest.mark.asyncio
async def test_easybroker_lead_action_execution():
    """Verifica que process_reply capture el marcador EASYBROKER_LEAD y despache la petición."""
    from app import external_actions

    raw_reply = 'Claro, con gusto te damos informes de la casa.\n[[EASYBROKER_LEAD: {"name": "Carlos", "phone": "5599887766", "property_id": "EB-999", "message": "Interesado en visita"}]]'

    with patch("app.external_actions._execute_action", new_callable=AsyncMock) as mock_exec:
        clean = await external_actions.process_reply("5215599887766", raw_reply, bot_id=147)
        assert clean == "Claro, con gusto te damos informes de la casa."
        mock_exec.assert_called_once()
        _, _, action = mock_exec.call_args[0]
        assert action["action_type"] == "easybroker_lead"
        assert action["payload"]["name"] == "Carlos"
        assert action["payload"]["property_id"] == "EB-999"


@pytest.mark.asyncio
async def test_easybroker_system_instructions():
    """Verifica que las instrucciones del sistema incluyan la sección de Easybroker cuando está activo."""
    from app import external_actions

    with patch("app.external_actions._skill_on", new_callable=AsyncMock) as mock_skill_on, \
         patch("app.db.get_bot_skill", new_callable=AsyncMock) as mock_get_skill:
        
        mock_skill_on.side_effect = lambda bot_id, itype: True if itype == "easybroker" else False
        mock_get_skill.return_value = None

        instructions = await external_actions.system_instructions(bot_id=147)
        assert "Easybroker CRM" in instructions
        assert "EASYBROKER_LEAD" in instructions


def test_is_sync_due():
    """Verifica el cálculo de si un bot debe sincronizarse según su intervalo y última sincronización."""
    from datetime import datetime, timezone, timedelta

    # 1. Nunca sincronizado -> True
    cfg_never = {"auto_sync": True, "sync_interval_hours": 12, "last_synced_at": ""}
    assert easybroker_client.is_sync_due(cfg_never) is True

    # 2. Auto sync deshabilitado -> False
    cfg_disabled = {"auto_sync": False, "sync_interval_hours": 12, "last_synced_at": ""}
    assert easybroker_client.is_sync_due(cfg_disabled) is False

    # 3. Sincronizado recientemente (hace 2 horas de un intervalo de 6) -> False
    now = datetime.now(timezone.utc)
    two_hours_ago = (now - timedelta(hours=2)).isoformat()
    cfg_recent = {"auto_sync": True, "sync_interval_hours": 6, "last_synced_at": two_hours_ago}
    assert easybroker_client.is_sync_due(cfg_recent) is False

    # 4. Sincronizado hace 13 horas de un intervalo de 12 -> True
    thirteen_hours_ago = (now - timedelta(hours=13)).isoformat()
    cfg_expired = {"auto_sync": True, "sync_interval_hours": 12, "last_synced_at": thirteen_hours_ago}
    assert easybroker_client.is_sync_due(cfg_expired) is True

    # 5. Formato de fecha corrupto/inválido -> False (no ciclar infinitamente)
    cfg_corrupt = {"auto_sync": True, "sync_interval_hours": 12, "last_synced_at": "fecha_invalida_123"}
    assert easybroker_client.is_sync_due(cfg_corrupt) is False


@pytest.mark.asyncio
async def test_sync_properties_atomic_transaction():
    """Verifica que la sincronización utilice una transacción para atomicidad."""
    sample_props = [
        {"public_id": "EB-10", "title": "Casa 10", "property_type": "House", "operations": []}
    ]
    with patch("app.easybroker_client.fetch_all_properties", new_callable=AsyncMock) as mock_fetch, \
         patch("app.db._pool") as mock_pool:

        mock_fetch.return_value = sample_props
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 1")
        mock_conn.fetchrow = AsyncMock(return_value={"id": 10})
        mock_tx = MagicMock()
        mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction.return_value = mock_tx
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        res = await easybroker_client.sync_properties_to_bot_knowledge(
            bot_id=147,
            api_key="valid_key",
        )

        assert res["success"] is True
        mock_conn.transaction.assert_called_once()


@pytest.mark.asyncio
async def test_sync_due_bots():
    """Verifica que sync_due_bots ejecute la sincronización solo para los bots que lo requieren."""
    active_integrations = [
        {
            "id": 1,
            "bot_id": 101,
            "enabled": True,
            "config": {"auto_sync": True, "sync_interval_hours": 6, "last_synced_at": ""},
        },
        {
            "id": 2,
            "bot_id": 102,
            "enabled": True,
            "config": {"auto_sync": False, "sync_interval_hours": 12, "last_synced_at": ""},
        },
    ]

    with patch("app.db._pool") as mock_pool, \
         patch("app.db.get_integration_secret_values", new_callable=AsyncMock) as mock_secrets, \
         patch("app.secure_store.decrypt_secret", return_value="valid_key"), \
         patch("app.easybroker_client.sync_properties_to_bot_knowledge", new_callable=AsyncMock) as mock_sync:

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = active_integrations
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_secrets.return_value = {"api_key": "enc_key"}
        mock_sync.return_value = {"success": True, "synced_count": 5}


        synced_bots = await easybroker_client.sync_due_bots()

        assert len(synced_bots) == 1
        assert synced_bots[0]["bot_id"] == 101
        mock_sync.assert_awaited_once_with(101, "valid_key")

