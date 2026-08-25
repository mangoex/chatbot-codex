import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

# Mock asyncpg and cryptography before imports
import sys
import types
sys.modules.pop("fastapi", None)
sys.modules.pop("fastapi.responses", None)
sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import calendar_client, escalations

# Clean sys.modules after module loading
sys.modules.pop("httpx", None)
sys.modules.pop("cryptography", None)
sys.modules.pop("cryptography.fernet", None)


class TestClientPanelFeatures:
    def test_client_layout_logout_includes_csrf_token(self):
        from app import client

        html = client._layout(
            "Panel",
            "<div>Contenido</div>",
            {
                "user": "client@example.com",
                "role": "client_admin",
                "client_id": 44,
                "user_id": 5,
                "name": "Cliente",
                "_csrf_token": "csrf-client-123",
            },
            bots_list=[{"id": 1, "name": "Bot 1"}],
            selected_bot_id=1,
        )

        assert 'action="/admin/logout"' in html
        assert 'name="csrf_token" value="csrf-client-123"' in html

    
    @pytest.mark.asyncio
    @patch("app.db.get_bot_skill")
    async def test_business_hours_validation(self, mock_get_skill):
        # Mock business hours config: open Mon-Fri 09:00-18:00, Sat closed
        mock_get_skill.return_value = {
            "enabled": True,
            "config": {
                "lunes": {"open": True, "start": "09:00", "end": "18:00"},
                "martes": {"open": True, "start": "09:00", "end": "18:00"},
                "miercoles": {"open": True, "start": "09:00", "end": "18:00"},
                "jueves": {"open": True, "start": "09:00", "end": "18:00"},
                "viernes": {"open": True, "start": "09:00", "end": "18:00"},
                "sabado": {"open": False, "start": "09:00", "end": "13:00"},
                "domingo": {"open": False, "start": "00:00", "end": "00:00"}
            }
        }
        
        # Test Case 1: Monday 10:00 AM (Valid)
        # Weekday: Monday = 0
        dt_monday_ok = datetime(2026, 6, 1, 10, 0, tzinfo=ZoneInfo("America/Chihuahua"))
        is_ok, err = await calendar_client._is_within_business_hours(1, dt_monday_ok)
        assert is_ok is True
        assert err == ""
        
        # Test Case 2: Monday 9:00 PM (Invalid - Outside Hours)
        dt_monday_late = datetime(2026, 6, 1, 21, 0, tzinfo=ZoneInfo("America/Chihuahua"))
        is_ok, err = await calendar_client._is_within_business_hours(1, dt_monday_late)
        assert is_ok is False
        assert "fuera de nuestra jornada" in err.lower()
        
        # Test Case 3: Saturday 11:00 AM (Invalid - Day Closed)
        # Weekday: Saturday = 5
        dt_saturday = datetime(2026, 6, 6, 11, 0, tzinfo=ZoneInfo("America/Chihuahua"))
        is_ok, err = await calendar_client._is_within_business_hours(1, dt_saturday)
        assert is_ok is False
        assert "no laboramos los días sabado" in err.lower()

    @pytest.mark.asyncio
    @patch("app.db.get_bot_skill")
    async def test_custom_escalation_rules(self, mock_get_skill):
        # Mock escalation config: keywords triggers enabled
        mock_get_skill.return_value = {
            "enabled": True,
            "config": {
                "keywords": ["hablar con miguel", "reclamar reembolso"],
                "escalate_on_media": True
            }
        }
        
        # Test Case 1: normal text - no escalation
        reason = await escalations.detect_reason("hola, me gustaria agendar una cita", "con gusto", "text", bot_id=1)
        assert reason is None
        
        # Test Case 2: trigger custom keyword "hablar con miguel"
        reason = await escalations.detect_reason("quiero hablar con miguel por favor", "si claro", "text", bot_id=1)
        assert reason is not None
        assert reason[0] == "cliente_solicito_humano"
        assert "palabra clave personalizada" in reason[1].lower()
        
        # Test Case 3: media escalation with toggle off
        mock_get_skill.return_value = {
            "enabled": True,
            "config": {
                "keywords": [],
                "escalate_on_media": False
            }
        }
        reason = await escalations.detect_reason("", "", "image", bot_id=1)
        assert reason is None
        
        # Test Case 4: media escalation with toggle on (default)
        mock_get_skill.return_value = {
            "enabled": True,
            "config": {
                "keywords": [],
                "escalate_on_media": True
            }
        }
        reason = await escalations.detect_reason("", "", "image", bot_id=1)
        assert reason is not None
        assert reason[0] == "media_recibida"

    @pytest.mark.asyncio
    @patch("app.db.list_bots")
    @patch("app.db.get_bot_whatsapp_number")
    @patch("app.db.get_active_bot_prompt")
    @patch("app.db.get_bot_skill")
    @patch("app.db.list_bot_knowledge")
    @patch("app.db.get_active_bot_integration")
    @patch("app.db.admin_metrics")
    @patch("app.db.list_conversation_threads")
    @patch("app.db.qualify_leads_with_action_link")
    @patch("app.db.crm_counts")
    @patch("app.db.list_leads")
    @patch("app.db.get_bot_integration_by_type", new=AsyncMock(return_value=None))
    async def test_client_app_view(
        self,
        mock_list_leads,
        mock_crm_counts,
        mock_qualify,
        mock_threads,
        mock_metrics,
        mock_integration,
        mock_knowledge,
        mock_skill,
        mock_prompt,
        mock_wa_num,
        mock_list_bots
    ):
        from app import client
        
        class Request:
            session = {
                "user": "client@example.com",
                "role": "client_admin",
                "client_id": 44,
                "user_id": 5,
            }
            
        mock_list_bots.return_value = [{"id": 1, "name": "Bot 1", "status": "active"}]
        mock_wa_num.return_value = {"phone_number_id": "123", "display_phone_number": "+521"}
        mock_prompt.return_value = {
            "content": "Prompt text",
            "pbd_constitution": "Constitucion actual",
            "pbd_specs": "Especificaciones actuales",
            "pbd_test_suite": "Suite actual",
        }
        mock_skill.return_value = {"enabled": True, "config": {}}
        mock_knowledge.return_value = []
        mock_integration.return_value = None
        mock_metrics.return_value = {}
        mock_threads.return_value = []
        mock_qualify.return_value = 0
        mock_crm_counts.return_value = {}
        mock_list_leads.return_value = []
        
        response = await client.client_app(Request(), bot_id=1)
        assert response is not None
        html_body = response.body.decode("utf-8")
        assert "Bot 1" in html_body
        assert "Agente PBD con IA" in html_body
        assert "PBD" in html_body
        assert "Guardar documentos PBD" in html_body
        assert "Constitucion actual" in html_body
        assert "Especificaciones actuales" in html_body
        assert "Suite actual" in html_body

    @pytest.mark.asyncio
    @patch("app.db.get_bot")
    @patch("app.db.update_bot_status")
    async def test_client_bot_toggle_status(self, mock_update, mock_get):
        from app import client
        
        class MockRequest:
            def __init__(self):
                self.headers = {"referer": "/client/app?bot_id=1"}
                self.session = {
                    "user": "client@example.com",
                    "role": "client_admin",
                    "client_id": 44,
                    "user_id": 5,
                }
        
        # Mock active status
        mock_get.return_value = {
            "id": 1,
            "client_id": 44,
            "slug": "test",
            "name": "Bot 1",
            "status": "active",
        }
        
        # Test Case 1: toggle status to paused
        req = MockRequest()
        response = await client.client_bot_toggle_status(req, bot_id=1)
        assert response is not None
        assert response.status_code == 302
        assert response.headers["location"] == "/client/app?bot_id=1"
        mock_update.assert_called_once_with(1, "paused")
        
        # Test Case 2: toggle status back to active
        mock_update.reset_mock()
        mock_get.return_value["status"] = "paused"
        response = await client.client_bot_toggle_status(req, bot_id=1)
        assert response is not None
        assert response.status_code == 302
        assert response.headers["location"] == "/client/app?bot_id=1"
        mock_update.assert_called_once_with(1, "active")

    @pytest.mark.asyncio
    @patch("app.db.list_bots")
    @patch("app.db.get_bot_whatsapp_number")
    @patch("app.db.get_active_bot_prompt")
    @patch("app.db.get_bot_skill")
    @patch("app.db.list_bot_knowledge")
    @patch("app.db.get_active_bot_integration")
    @patch("app.db.admin_metrics")
    @patch("app.db.list_conversation_threads")
    @patch("app.db.qualify_leads_with_action_link")
    @patch("app.db.crm_counts")
    @patch("app.db.list_leads")
    @patch("app.meta_provider.list_message_templates")
    @patch("app.db.get_bot_integration_by_type", new=AsyncMock(return_value=None))
    async def test_client_app_view_with_templates(
        self,
        mock_list_templates,
        mock_list_leads,
        mock_crm_counts,
        mock_qualify,
        mock_threads,
        mock_metrics,
        mock_integration,
        mock_knowledge,
        mock_skill,
        mock_prompt,
        mock_wa_num,
        mock_list_bots
    ):
        from app import client
        
        class Request:
            session = {
                "user": "client@example.com",
                "role": "client_admin",
                "client_id": 44,
                "user_id": 5,
            }
            
        mock_list_bots.return_value = [{"id": 1, "name": "Bot 1", "status": "active"}]
        mock_wa_num.return_value = {"phone_number_id": "123", "display_phone_number": "+521"}
        mock_prompt.return_value = {"content": "Prompt text"}
        mock_skill.return_value = {"enabled": True, "config": {}}
        mock_knowledge.return_value = []
        mock_integration.return_value = None
        mock_metrics.return_value = {}
        mock_threads.return_value = []
        mock_qualify.return_value = 0
        mock_crm_counts.return_value = {}
        mock_list_leads.return_value = []
        mock_list_templates.return_value = {"data": [{"name": "template_test", "language": "es_MX", "category": "UTILITY", "status": "APPROVED"}]}
        
        response = await client.client_app(Request(), bot_id=1)
        assert response is not None
        html_body = response.body.decode("utf-8")
        assert "Bot 1" in html_body
        assert "template_test" in html_body
        assert "Crear Plantilla en Meta" in html_body

    @pytest.mark.asyncio
    @patch("app.db.get_bot")
    @patch("app.meta_provider.create_message_template")
    async def test_client_whatsapp_templates_submit(self, mock_create, mock_get_bot):
        from app import client
        
        class MockRequest:
            def __init__(self):
                self.session = {
                    "user": "client@example.com",
                    "role": "client_admin",
                    "client_id": 44,
                    "user_id": 5,
                }
        
        mock_get_bot.return_value = {"id": 1, "client_id": 44, "status": "active"}
        mock_create.return_value = {"id": "123"}
        
        response = await client.client_whatsapp_templates_submit(
            MockRequest(),
            bot_id=1,
            name="new_template",
            language="es_MX",
            category="UTILITY",
            body_text="Hola {{1}}",
            examples=["Juan"]
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/client/app?bot_id=1&tab=templates&saved=1"
        mock_create.assert_called_once_with(1, "new_template", "es_MX", "UTILITY", "Hola {{1}}", examples=["Juan"])

    @pytest.mark.asyncio
    @patch("app.db.get_bot")
    @patch("app.meta_provider.create_message_template")
    async def test_client_whatsapp_templates_submit_error(self, mock_create, mock_get_bot):
        from app import client
        
        class MockRequest:
            def __init__(self):
                self.session = {
                    "user": "client@example.com",
                    "role": "client_admin",
                    "client_id": 44,
                    "user_id": 5,
                }
        
        mock_get_bot.return_value = {"id": 1, "client_id": 44, "status": "active"}
        mock_create.side_effect = ValueError("Meta API: Invalid variable format")
        
        response = await client.client_whatsapp_templates_submit(
            MockRequest(),
            bot_id=1,
            name="new_template",
            language="es_MX",
            category="UTILITY",
            body_text="Hola {{1}}",
            examples=["Juan"]
        )
        assert response.status_code == 302
        # Should redirect with encoded message: err_Meta%20API%3A%20Invalid%20variable%20format
        assert "saved=err_Meta%20API" in response.headers["location"]

    @pytest.mark.asyncio
    @patch("app.db.get_bot")
    @patch("app.db.list_bot_knowledge")
    @patch("app.db.list_bot_integrations")
    @patch("app.db.list_bot_skills")
    @patch("app.prompt_assistant.assist_prompt")
    @patch("app.db.publish_bot_prompt")
    async def test_client_prompt_assist_auto_publish(
        self,
        mock_publish,
        mock_assist,
        mock_skills,
        mock_integrations,
        mock_knowledge,
        mock_get_bot,
    ):
        from app import client

        class MockRequest:
            session = {
                "user": "client@example.com",
                "role": "client_admin",
                "client_id": 44,
                "user_id": 5,
            }

        mock_get_bot.return_value = {"id": 1, "client_id": 44, "status": "active"}
        mock_knowledge.return_value = []
        mock_integrations.return_value = []
        mock_skills.return_value = []
        mock_assist.return_value = {
            "ok": True,
            "blocked": False,
            "prompt": "<rol>Bot Test</rol>",
            "pbd_constitution": "CON-001",
            "pbd_specs": "SPEC-001",
            "pbd_test_suite": "TEST-001",
        }

        response = await client.client_prompt_assist(
            MockRequest(),
            bot_id=1,
            instruction="Actualiza horarios",
            mode="update",
            auto_publish="true",
        )
        assert response.status_code == 200
        import json
        data = json.loads(response.body.decode("utf-8"))
        assert data["ok"] is True
        assert data["published"] is True
        mock_publish.assert_called_once_with(1, "<rol>Bot Test</rol>", "CON-001", "SPEC-001", "TEST-001")

    @pytest.mark.asyncio
    @patch("app.db.get_bot")
    @patch("app.db.get_active_bot_prompt")
    async def test_client_prompt_pbd_export_zip(self, mock_prompt, mock_get_bot):

        import io
        import zipfile
        from app import client

        class MockRequest:
            session = {
                "user": "client@example.com",
                "role": "client_admin",
                "client_id": 44,
                "user_id": 5,
            }

        mock_get_bot.return_value = {"id": 1, "name": "Dental Smile", "client_id": 44}
        mock_prompt.return_value = {
            "content": "<rol>Master</rol>",
            "pbd_constitution": "# 01 - Const",
            "pbd_specs": "# 02 - Specs",
            "pbd_test_suite": "# 03 - Tests",
        }

        response = await client.client_prompt_pbd_export(MockRequest(), bot_id=1)
        assert response.status_code == 200
        assert response.media_type == "application/zip"
        assert "pbd_dental_smile_docs.zip" in response.headers["content-disposition"]

        with zipfile.ZipFile(io.BytesIO(response.body), "r") as z:
            names = z.namelist()
            assert "docs/pbd/01-constitution.md" in names
            assert "docs/pbd/02-behavior-specs.md" in names
            assert "docs/pbd/03-test-suite.md" in names
            assert "docs/pbd/04-master-prompt.md" in names
            assert "prompts/master.xml" in names
            assert z.read("docs/pbd/01-constitution.md").decode("utf-8") == "# 01 - Const"



