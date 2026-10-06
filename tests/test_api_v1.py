from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import bots, db, main, secure_store


class ApiV1Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.bot_id = 42
        self.mock_bot = bots.BotContext(
            id=self.bot_id,
            client_id=1,
            slug="test-bot",
            name="Bot de Prueba",
            whatsapp_phone_number_id="wa_phone_123",
            whatsapp_access_token="wa_token_abc",
        )

    async def test_ping_unauthorized(self):
        with patch.object(bots, "resolve_by_bot_id", AsyncMock(return_value=self.mock_bot)):
            resp = self.client.get(f"/api/v1/bots/{self.bot_id}/ping")
            self.assertEqual(resp.status_code, 401)
            self.assertIn("Missing API Key or Secret", resp.json()["detail"])

    async def test_ping_authorized_with_grok_secret(self):
        mock_integration = {"id": 10, "enabled": True}
        raw_secret = "secret-super-seguro"

        with (
            patch.object(bots, "resolve_by_bot_id", AsyncMock(return_value=self.mock_bot)),
            patch.object(db, "get_active_bot_integration", AsyncMock(return_value=mock_integration)),
            patch.object(db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(secure_store, "decrypt_secret", return_value=raw_secret),
        ):
            # Test with X-Grok-Secret
            resp = self.client.get(
                f"/api/v1/bots/{self.bot_id}/ping",
                headers={"X-Grok-Secret": raw_secret},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["status"], "ok")
            self.assertEqual(resp.json()["bot_id"], self.bot_id)

            # Test with X-API-Key
            resp2 = self.client.get(
                f"/api/v1/bots/{self.bot_id}/ping",
                headers={"X-API-Key": raw_secret},
            )
            self.assertEqual(resp2.status_code, 200)

            # Test with Bearer token
            resp3 = self.client.get(
                f"/api/v1/bots/{self.bot_id}/ping",
                headers={"Authorization": f"Bearer {raw_secret}"},
            )
            self.assertEqual(resp3.status_code, 200)

    async def test_create_contact_single(self):
        mock_integration = {"id": 10, "enabled": True}
        raw_secret = "test-secret"

        with (
            patch.object(bots, "resolve_by_bot_id", AsyncMock(return_value=self.mock_bot)),
            patch.object(db, "get_active_bot_integration", AsyncMock(return_value=mock_integration)),
            patch.object(db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(secure_store, "decrypt_secret", return_value=raw_secret),
            patch.object(db, "upsert_contact", AsyncMock()) as mock_upsert_contact,
            patch.object(db, "upsert_lead", AsyncMock()) as mock_upsert_lead,
        ):
            payload = {
                "wa_id": "+52 1 55 1234 5678",
                "name": "Juan Perez",
                "business": "Tacos El Pastor",
                "tags": ["grok_lead", "prospecto_octubre"],
                "qualification_status": "en_progreso",
            }
            resp = self.client.post(
                f"/api/v1/bots/{self.bot_id}/contacts",
                json=payload,
                headers={"X-API-Key": raw_secret},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["wa_id"], "5215512345678")
            self.assertEqual(data["name"], "Juan Perez")

            mock_upsert_contact.assert_awaited_once_with(
                bot_id=self.bot_id,
                wa_id="5215512345678",
                name="Juan Perez",
                business="Tacos El Pastor",
                tags="grok_lead, prospecto_octubre",
            )
            mock_upsert_lead.assert_awaited_once_with(
                "5215512345678",
                bot_id=self.bot_id,
                nombre="Juan Perez",
                negocio="Tacos El Pastor",
                qualification_status="en_progreso",
            )

    async def test_create_contacts_batch(self):
        mock_integration = {"id": 10, "enabled": True}
        raw_secret = "test-secret"

        with (
            patch.object(bots, "resolve_by_bot_id", AsyncMock(return_value=self.mock_bot)),
            patch.object(db, "get_active_bot_integration", AsyncMock(return_value=mock_integration)),
            patch.object(db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(secure_store, "decrypt_secret", return_value=raw_secret),
            patch.object(db, "upsert_contact", AsyncMock()) as mock_upsert_contact,
            patch.object(db, "upsert_lead", AsyncMock()) as mock_upsert_lead,
        ):
            payload = {
                "contacts": [
                    {"wa_id": "5215511111111", "name": "Contacto Uno", "tags": "lead_1"},
                    {"wa_id": "5215522222222", "name": "Contacto Dos", "business": "Negocio 2"},
                ]
            }
            resp = self.client.post(
                f"/api/v1/bots/{self.bot_id}/contacts/batch",
                json=payload,
                headers={"X-API-Key": raw_secret},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["total_received"], 2)
            self.assertEqual(data["success_count"], 2)
            self.assertEqual(data["failed_count"], 0)
            self.assertEqual(mock_upsert_contact.await_count, 2)
            self.assertEqual(mock_upsert_lead.await_count, 2)

    async def test_list_contacts(self):
        mock_integration = {"id": 10, "enabled": True}
        raw_secret = "test-secret"

        mock_contacts = [
            {"id": 1, "wa_id": "5215511111111", "name": "Contacto Uno", "business": "A", "tags": "grok"},
            {"id": 2, "wa_id": "5215522222222", "name": "Contacto Dos", "business": "B", "tags": "grok"},
        ]

        with (
            patch.object(bots, "resolve_by_bot_id", AsyncMock(return_value=self.mock_bot)),
            patch.object(db, "get_active_bot_integration", AsyncMock(return_value=mock_integration)),
            patch.object(db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(secure_store, "decrypt_secret", return_value=raw_secret),
            patch.object(db, "list_contacts", AsyncMock(return_value=mock_contacts)),
            patch.object(db, "count_contacts", AsyncMock(return_value=2)),
        ):
            resp = self.client.get(
                f"/api/v1/bots/{self.bot_id}/contacts?tag=grok",
                headers={"X-API-Key": raw_secret},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["total"], 2)
            self.assertEqual(len(data["contacts"]), 2)

    async def test_list_templates(self):
        mock_integration = {"id": 10, "enabled": True}
        raw_secret = "test-secret"

        from app import meta_provider
        mock_templates_res = {
            "data": [
                {
                    "name": "plantilla_bienvenida",
                    "status": "APPROVED",
                    "category": "MARKETING",
                    "language": "es_MX",
                    "components": [{"type": "BODY", "text": "Hola {{1}}, tenemos una promo."}],
                }
            ]
        }

        with (
            patch.object(bots, "resolve_by_bot_id", AsyncMock(return_value=self.mock_bot)),
            patch.object(db, "get_active_bot_integration", AsyncMock(return_value=mock_integration)),
            patch.object(db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(secure_store, "decrypt_secret", return_value=raw_secret),
            patch.object(meta_provider, "list_message_templates", AsyncMock(return_value=mock_templates_res)),
        ):
            resp = self.client.get(
                f"/api/v1/bots/{self.bot_id}/templates",
                headers={"X-API-Key": raw_secret},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("templates", data)
            self.assertEqual(len(data["templates"]), 1)
            self.assertEqual(data["templates"][0]["name"], "plantilla_bienvenida")

    async def test_create_campaign_immediate(self):
        mock_integration = {"id": 10, "enabled": True}
        raw_secret = "test-secret"

        contacts = [
            {"id": 1, "wa_id": "5215511111111", "name": "Contacto Uno", "business": "A", "tags": "grok"},
            {"id": 2, "wa_id": "5215522222222", "name": "Contacto Dos", "business": "B", "tags": "grok"},
        ]

        from app import client as app_client
        with (
            patch.object(bots, "resolve_by_bot_id", AsyncMock(return_value=self.mock_bot)),
            patch.object(db, "get_active_bot_integration", AsyncMock(return_value=mock_integration)),
            patch.object(db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(secure_store, "decrypt_secret", return_value=raw_secret),
            patch.object(db, "list_contacts", AsyncMock(return_value=contacts)),
            patch.object(db, "create_broadcast", AsyncMock(return_value=999)) as mock_create_broadcast,
            patch.object(app_client, "process_broadcast_queue", AsyncMock()) as mock_queue,
        ):
            payload = {
                "name": "Campaña Grok Test",
                "template_name": "plantilla_bienvenida",
                "language_code": "es_MX",
                "audience": {
                    "type": "tag",
                    "tag": "grok",
                },
                "variable_mappings": [
                    {"var_idx": 1, "type": "name"},
                ],
            }
            resp = self.client.post(
                f"/api/v1/bots/{self.bot_id}/campaigns",
                json=payload,
                headers={"X-API-Key": raw_secret},
            )
            self.assertEqual(resp.status_code, 202)
            data = resp.json()
            self.assertEqual(data["status"], "queued")
            self.assertEqual(data["campaign_id"], 999)
            self.assertEqual(data["recipients_count"], 2)
            mock_create_broadcast.assert_awaited_once()

    async def test_get_campaign_status(self):
        mock_integration = {"id": 10, "enabled": True}
        raw_secret = "test-secret"

        broadcast_data = {
            "id": 999,
            "bot_id": self.bot_id,
            "name": "Campaña Grok Test",
            "template_name": "plantilla_bienvenida",
            "language_code": "es_MX",
            "status": "running",
            "total_recipients": 10,
            "sent_count": 8,
            "failed_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "scheduled_at": None,
        }

        with (
            patch.object(bots, "resolve_by_bot_id", AsyncMock(return_value=self.mock_bot)),
            patch.object(db, "get_active_bot_integration", AsyncMock(return_value=mock_integration)),
            patch.object(db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc:secret"})),
            patch.object(secure_store, "decrypt_secret", return_value=raw_secret),
            patch.object(db, "get_broadcast", AsyncMock(return_value=broadcast_data)),
        ):
            resp = self.client.get(
                f"/api/v1/bots/{self.bot_id}/campaigns/999/status",
                headers={"X-API-Key": raw_secret},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["campaign_id"], 999)
            self.assertEqual(data["status"], "running")
            self.assertEqual(data["sent_count"], 8)
            self.assertEqual(data["total_recipients"], 10)
