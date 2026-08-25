import asyncio
import sys
import types
import unittest

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import external_actions




class _Response:
    status_code = 200
    text = '{"ok": true}'

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


class _AsyncClient:
    calls = []

    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs, self.timeout))
        return _Response()


class ExternalActionsTests(unittest.TestCase):
    def setUp(self):
        _AsyncClient.calls = []

    def test_extracts_markers_and_strips_visible_reply(self):
        reply = (
            "Claro, voy a registrar tus datos.\n"
            '[[CRM_LEAD: {"name":"Miguel","phone":"521555","status":"new"}]]\n'
            "Listo."
        )

        clean, actions = external_actions.extract_actions(reply)

        self.assertEqual(clean, "Claro, voy a registrar tus datos.\nListo.")
        self.assertEqual(actions[0]["action_type"], "crm_lead")
        self.assertEqual(actions[0]["payload"]["name"], "Miguel")

    def test_rejects_unsupported_methods(self):
        action = {
            "action_type": "external_api_request",
            "payload": {"method": "DELETE", "path": "/clients/1"},
        }
        integration = {"config": {"base_url": "https://api.example.com"}}

        self.assertIsNone(external_actions.build_request(action, integration, {}))

    def test_rejects_model_supplied_absolute_url(self):
        action = {
            "action_type": "external_api_request",
            "payload": {
                "operation": "buscar_cliente",
                "url": "https://evil.example.com/steal",
            },
        }
        integration = {
            "config": {
                "base_url": "https://api.example.com",
                "operations": [{"name": "buscar_cliente", "method": "GET", "path": "/clients"}],
            }
        }

        self.assertIsNone(external_actions.build_request(action, integration, {}))

    def test_marker_only_reply_gets_safe_visible_text(self):
        clean, actions = external_actions.extract_actions(
            '[[CRM_LEAD: {"name":"Miguel","phone":"521555"}]]'
        )

        self.assertEqual(clean, "Listo.")
        self.assertEqual(actions[0]["action_type"], "crm_lead")

    def test_builds_secret_backed_bearer_request(self):
        action = {
            "action_type": "external_api_request",
            "payload": {
                "operation": "crear_lead",
                "json": {"name": "Miguel"},
            },
        }
        integration = {
            "config": {
                "base_url": "https://api.example.com",
                "headers": {"X-Source": "whatsapp"},
                "operations": [
                    {
                        "name": "crear_lead",
                        "method": "POST",
                        "path": "/leads",
                    }
                ],
            }
        }

        request_data = external_actions.build_request(
            action,
            integration,
            {"api_key": "dummy-value"},
        )

        self.assertEqual(request_data["method"], "POST")
        self.assertEqual(request_data["url"], "https://api.example.com/leads")
        self.assertEqual(request_data["json"], {"name": "Miguel"})
        self.assertEqual(request_data["headers"]["X-Source"], "whatsapp")
        self.assertEqual(request_data["headers"]["Authorization"], "Bearer dummy-value")

    def test_builds_named_operation_request(self):
        action = {
            "action_type": "external_api_request",
            "payload": {
                "operation": "buscar_cliente",
                "params": {"phone": "521555"},
            },
        }
        integration = {
            "config": {
                "base_url": "https://api.example.com",
                "operations": [
                    {
                        "name": "buscar_cliente",
                        "method": "GET",
                        "path": "/clients/search",
                        "params": {"source": "whatsapp"},
                    }
                ],
            }
        }

        request_data = external_actions.build_request(action, integration, {})

        self.assertEqual(request_data["method"], "GET")
        self.assertEqual(request_data["url"], "https://api.example.com/clients/search")
        self.assertEqual(
            request_data["params"],
            {"source": "whatsapp", "phone": "521555"},
        )

    def test_operation_lines_expose_available_api_actions(self):
        lines = external_actions._operation_instruction_lines(
            {
                "operations": [
                    {
                        "name": "crear_cita",
                        "method": "POST",
                        "path": "/appointments",
                        "description": "Crea una cita en el sistema del cliente",
                    }
                ]
            }
        )

        self.assertIn("crear_cita: POST /appointments", lines[0])

    def test_process_reply_executes_enabled_webhook_and_removes_marker(self):
        async def run():
            original_client = external_actions.httpx.AsyncClient
            original_skill = external_actions.skill_runtime.webhook_skill_enabled
            original_integration = external_actions.db.get_active_bot_integration
            original_secret_values = external_actions.db.get_integration_secret_values
            original_decrypt = external_actions.secure_store.decrypt_secret
            original_record = external_actions.db.record_external_action_run

            async def fake_skill_enabled(bot_id):
                return bot_id == 7

            async def fake_integration(bot_id, integration_type):
                self.assertEqual(bot_id, 7)
                self.assertEqual(integration_type, "webhook")
                return {
                    "id": 3,
                    "config": {
                        "url": "https://hooks.example.com/lead",
                        "headers": {"X-Bot": "demo"},
                    },
                }

            async def fake_secret_values(integration_id):
                self.assertEqual(integration_id, 3)
                return {"access_token": "encrypted"}

            def fake_decrypt(value):
                return "dummy-access-value" if value == "encrypted" else None

            async def fake_record(**kwargs):
                return None

            try:
                external_actions.httpx.AsyncClient = _AsyncClient
                external_actions.skill_runtime.webhook_skill_enabled = fake_skill_enabled
                external_actions.db.get_active_bot_integration = fake_integration
                external_actions.db.get_integration_secret_values = fake_secret_values
                external_actions.secure_store.decrypt_secret = fake_decrypt
                external_actions.db.record_external_action_run = fake_record

                reply = (
                    "Ya lo envie."
                    '[[WEBHOOK_POST: {"payload":{"name":"Miguel","phone":"521555"}}]]'
                )

                clean = await external_actions.process_reply("521555", reply, bot_id=7)

                self.assertEqual(clean, "Ya lo envie.")
                self.assertEqual(len(_AsyncClient.calls), 1)
                method, url, kwargs, timeout = _AsyncClient.calls[0]
                self.assertEqual(method, "POST")
                self.assertEqual(url, "https://hooks.example.com/lead")
                self.assertEqual(kwargs["headers"]["Authorization"], "Bearer dummy-access-value")
                self.assertEqual(kwargs["json"], {"name": "Miguel", "phone": "521555"})
                self.assertEqual(timeout, 20)
            finally:
                external_actions.httpx.AsyncClient = original_client
                external_actions.skill_runtime.webhook_skill_enabled = original_skill
                external_actions.db.get_active_bot_integration = original_integration
                external_actions.db.get_integration_secret_values = original_secret_values
                external_actions.secure_store.decrypt_secret = original_decrypt
                external_actions.db.record_external_action_run = original_record

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
