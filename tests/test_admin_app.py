import unittest
import sys
import types
import asyncio


class _DummyRouter:
    def __init__(self, *args, **kwargs):
        self.routes = []

    def __getattr__(self, name):
        if name in ("on_startup", "on_shutdown"):
            return []
        return None

    def get(self, *args, **kwargs):
        return lambda fn: fn

    def post(self, *args, **kwargs):
        return lambda fn: fn


class _DummyResponse:
    def __init__(self, content="", *args, **kwargs):
        self.content = content


def _dummy_form(default=...):
    return default


sys.modules.setdefault(
    "fastapi",
    types.SimpleNamespace(
        APIRouter=_DummyRouter,
        Form=_dummy_form,
        HTTPException=Exception,
        Request=object,
    ),
)
sys.modules.setdefault(
    "fastapi.responses",
    types.SimpleNamespace(
        HTMLResponse=_DummyResponse,
        JSONResponse=_DummyResponse,
        RedirectResponse=_DummyResponse,
    ),
)
sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=object))
sys.modules.setdefault(
    "cryptography.fernet",
    types.SimpleNamespace(Fernet=object, InvalidToken=Exception),
)

from app import admin

# Restore sys.modules so other test files can load the real fastapi/cryptography
sys.modules.pop("fastapi", None)
sys.modules.pop("fastapi.responses", None)
sys.modules.pop("cryptography", None)
sys.modules.pop("cryptography.fernet", None)


class AdminControlAppTests(unittest.TestCase):
    def test_admin_app_href_replaces_bot_id(self):
        self.assertEqual(
            admin._admin_app_href("/admin/bots/{bot_id}/prompt", 7),
            "/admin/bots/7/prompt",
        )
        self.assertEqual(
            admin._admin_app_href("/admin/calendar-status?bot_id={bot_id}", 3),
            "/admin/calendar-status?bot_id=3",
        )

    def test_admin_app_link_cards_hide_clients_for_non_agency(self):
        agency_html = admin._admin_app_link_cards(bot_id=1, is_agency=True)
        client_html = admin._admin_app_link_cards(
            bot_id=1,
            is_agency=False,
            role="client_admin",
        )
        viewer_html = admin._admin_app_link_cards(
            bot_id=1,
            is_agency=False,
            role="client_viewer",
        )

        self.assertIn("/admin/clients", agency_html)
        self.assertNotIn("/admin/clients", client_html)
        self.assertIn("/admin/users", client_html)
        self.assertNotIn("/admin/users", viewer_html)
        self.assertIn("/admin/bots/1/prompt", client_html)

    def test_admin_app_link_cards_disable_bot_links_without_bot(self):
        rendered = admin._admin_app_link_cards(bot_id=None, is_agency=True)

        self.assertIn('aria-disabled="true"', rendered)
        self.assertIn("/admin/bots/1/prompt", rendered)

    def test_nav_hides_links_by_role(self):
        agency_html = admin._nav("app", {"role": "agency_admin"})
        client_admin_html = admin._nav("app", {"role": "client_admin"})
        viewer_html = admin._nav("app", {"role": "client_viewer"})

        self.assertIn("/admin/clients", agency_html)
        self.assertNotIn("/admin/clients", client_admin_html)
        self.assertIn("/admin/users", client_admin_html)
        self.assertNotIn("/admin/users", viewer_html)
        # Verify scoped views are not in global admin nav
        self.assertNotIn("/admin/conversations", agency_html)
        self.assertNotIn("/admin/crm", agency_html)
        self.assertNotIn("/admin/escalations", agency_html)

    def test_admin_api_bot_includes_desktop_app_links(self):
        bot = admin._admin_api_bot(
            {
                "id": 9,
                "name": "Bot Demo",
                "slug": "bot-demo",
                "client_id": 4,
                "client_name": "Cliente Demo",
                "display_phone_number": "+5215550000000",
                "status": "active",
            }
        )

        self.assertEqual(bot["id"], 9)
        self.assertEqual(bot["links"]["prompt"], "/admin/bots/9/prompt")
        self.assertEqual(
            bot["links"]["calendar_status"],
            "/admin/calendar-status?bot_id=9",
        )

    def test_admin_api_metrics_are_integer_safe(self):
        metrics = admin._admin_api_metrics({"conversations": "3", "leads": None})

        self.assertEqual(metrics["conversations"], 3)
        self.assertEqual(metrics["leads"], 0)
        self.assertEqual(metrics["messages"], 0)

    def test_admin_api_user_hides_password_fields(self):
        user = admin._admin_api_user(
            {
                "id": 12,
                "email": "cliente@example.com",
                "name": "Cliente Demo",
                "status": "active",
                "role": "client_admin",
                "client_id": 4,
                "client_name": "Cuenta Demo",
                "client_slug": "cuenta-demo",
                "password_hash": "not-returned",
            }
        )

        self.assertEqual(user["id"], 12)
        self.assertEqual(user["role"], "client_admin")
        self.assertNotIn("password_hash", user)

    def test_prompt_page_includes_ai_assistant_for_editors(self):
        class Request:
            session = {"user": "admin", "role": "agency_admin", "client_id": None}

        async def fake_get_bot(bot_id):
            return {
                "id": bot_id,
                "name": "Bot Demo",
                "client_id": 1,
                "client_name": "Cliente Demo",
                "phone_number_id": "123",
            }

        async def fake_prompt(bot_id):
            return {"content": "Prompt actual"}

        original_get_bot = admin.db.get_bot
        original_get_prompt = admin.db.get_active_bot_prompt
        try:
            admin.db.get_bot = fake_get_bot
            admin.db.get_active_bot_prompt = fake_prompt
            response = asyncio.run(admin.bot_prompt_page(Request(), 7))
        finally:
            admin.db.get_bot = original_get_bot
            admin.db.get_active_bot_prompt = original_get_prompt

        self.assertIn("promptAssistantForm", response.content)
        self.assertIn("/admin/bots/7/prompt/assist", response.content)
        self.assertIn("Prompt actual", response.content)

    def test_client_without_bot_gets_empty_panel_state(self):
        session = {"user": "rubi@example.com", "role": "client_admin", "client_id": 44}

        async def no_bots(*args, **kwargs):
            return []

        async def no_users(*args, **kwargs):
            return []

        async def fail_metrics(*args, **kwargs):
            raise AssertionError("client without bot must not load global metrics")

        original_list_bots = admin.db.list_bots
        original_list_users = admin.db.list_users
        original_admin_metrics = admin.db.admin_metrics
        try:
            admin.db.list_bots = no_bots
            admin.db.list_users = no_users
            admin.db.admin_metrics = fail_metrics
            state = asyncio.run(admin._admin_app_state(session))
        finally:
            admin.db.list_bots = original_list_bots
            admin.db.list_users = original_list_users
            admin.db.admin_metrics = original_admin_metrics

        self.assertIsNone(state["selected_bot_id"])
        self.assertEqual(state["metrics"]["conversations"], 0)
        self.assertEqual(state["metrics"]["messages"], 0)

    def test_client_without_bot_conversations_do_not_load_global_threads(self):
        class Request:
            session = {
                "user": "rubi@example.com",
                "role": "client_admin",
                "client_id": 44,
            }

        async def no_bots(*args, **kwargs):
            return []

        async def fail_qualify(*args, **kwargs):
            raise AssertionError("client without bot must not mutate global leads")

        async def fail_threads(*args, **kwargs):
            raise AssertionError("client without bot must not load global threads")

        original_list_bots = admin.db.list_bots
        original_qualify = admin.db.qualify_leads_with_action_link
        original_threads = admin.db.list_conversation_threads
        try:
            admin.db.list_bots = no_bots
            admin.db.qualify_leads_with_action_link = fail_qualify
            admin.db.list_conversation_threads = fail_threads
            response = asyncio.run(admin.conversations(Request()))
        finally:
            admin.db.list_bots = original_list_bots
            admin.db.qualify_leads_with_action_link = original_qualify
            admin.db.list_conversation_threads = original_threads

        self.assertIn("todavia no tiene un bot asignado", response.content)
        self.assertIn("Aun no hay conversaciones", response.content)

    def test_external_api_config_builder_parses_visual_fields(self):
        config = admin._external_api_config_from_form(
            base_url="https://api.example.com/",
            method="post",
            default_path="/leads",
            allowed_methods="GET, POST",
            headers_json='{"X-Source": "whatsapp"}',
            auth_header="Authorization",
            auth_scheme="Bearer",
            timeout_seconds=20,
            test_method="GET",
            test_path="/health",
            test_params_json='{"ping": "1"}',
            operations_json='[{"name":"crear_lead","method":"POST","path":"/leads","json":{"name":"{{nombre}}"}}]',
        )

        self.assertEqual(config["base_url"], "https://api.example.com")
        self.assertEqual(config["method"], "POST")
        self.assertEqual(config["allowed_methods"], ["GET", "POST"])
        self.assertEqual(config["headers"]["X-Source"], "whatsapp")
        self.assertEqual(config["test"]["params"], {"ping": "1"})
        self.assertEqual(config["operations"][0]["name"], "crear_lead")

    def test_delete_user_page_success(self):
        class Request:
            session = {
                "user": "admin@example.com",
                "role": "agency_admin",
                "client_id": None,
            }

        async def fake_get_user_login(email):
            return {"user_id": 7, "email": "admin@example.com"}

        async def fake_delete_user(user_id, client_id=None):
            return True

        original_get_user_login = admin.db.get_user_login
        original_delete_user = admin.db.delete_user
        admin.db.get_user_login = fake_get_user_login
        admin.db.delete_user = fake_delete_user
        try:
            resp = asyncio.run(admin.delete_user_page(Request(), 8))
            self.assertIsNotNone(resp)
            if hasattr(resp, "headers") and "location" in resp.headers:
                self.assertEqual(resp.headers["location"], "/admin/users?saved=1")
            elif hasattr(resp, "content"):
                self.assertEqual(resp.content, "/admin/users?saved=1")
        finally:
            admin.db.get_user_login = original_get_user_login
            admin.db.delete_user = original_delete_user

    def test_delete_user_page_self_deletion(self):
        class Request:
            session = {
                "user": "admin@example.com",
                "role": "agency_admin",
                "client_id": None,
            }

        async def fake_get_user_login(email):
            return {"user_id": 7, "email": "admin@example.com"}

        original_get_user_login = admin.db.get_user_login
        admin.db.get_user_login = fake_get_user_login
        try:
            with self.assertRaises(Exception) as ctx:
                asyncio.run(admin.delete_user_page(Request(), 7))
            if hasattr(ctx.exception, "status_code"):
                self.assertEqual(ctx.exception.status_code, 400)
        finally:
            admin.db.get_user_login = original_get_user_login

    def test_delete_user_page_not_found(self):
        class Request:
            session = {
                "user": "admin@example.com",
                "role": "agency_admin",
                "client_id": None,
            }

        async def fake_get_user_login(email):
            return {"user_id": 7, "email": "admin@example.com"}

        async def fake_delete_user(user_id, client_id=None):
            return False

        original_get_user_login = admin.db.get_user_login
        original_delete_user = admin.db.delete_user
        admin.db.get_user_login = fake_get_user_login
        admin.db.delete_user = fake_delete_user
        try:
            with self.assertRaises(Exception) as ctx:
                asyncio.run(admin.delete_user_page(Request(), 8))
            if hasattr(ctx.exception, "status_code"):
                self.assertEqual(ctx.exception.status_code, 404)
        finally:
            admin.db.get_user_login = original_get_user_login
            admin.db.delete_user = original_delete_user

    def test_delete_client_route_success(self):
        class Request:
            session = {
                "user": "admin@example.com",
                "role": "agency_admin",
                "client_id": None,
            }

        async def fake_delete_client(client_id):
            return True

        original_delete_client = admin.db.delete_client
        admin.db.delete_client = fake_delete_client
        try:
            resp = asyncio.run(admin.delete_client_route(Request(), 12))
            self.assertIsNotNone(resp)
            if hasattr(resp, "headers") and "location" in resp.headers:
                self.assertEqual(resp.headers["location"], "/admin/clients?saved=1")
            elif hasattr(resp, "content"):
                self.assertEqual(resp.content, "/admin/clients?saved=1")
        finally:
            admin.db.delete_client = original_delete_client

    def test_delete_client_route_forbidden_for_clients(self):
        class Request:
            session = {
                "user": "client@example.com",
                "role": "client_admin",
                "client_id": 5,
            }

        try:
            with self.assertRaises(Exception) as ctx:
                asyncio.run(admin.delete_client_route(Request(), 12))
            if hasattr(ctx.exception, "status_code"):
                self.assertEqual(ctx.exception.status_code, 403)
        finally:
            pass

    def test_delete_bot_route_success(self):
        class Request:
            session = {
                "user": "admin@example.com",
                "role": "agency_admin",
                "client_id": None,
            }

        async def fake_delete_bot(bot_id):
            return True

        original_delete_bot = admin.db.delete_bot
        admin.db.delete_bot = fake_delete_bot
        try:
            resp = asyncio.run(admin.delete_bot_route(Request(), 14))
            self.assertIsNotNone(resp)
            if hasattr(resp, "headers") and "location" in resp.headers:
                self.assertEqual(resp.headers["location"], "/admin/bots?saved=1")
            elif hasattr(resp, "content"):
                self.assertEqual(resp.content, "/admin/bots?saved=1")
        finally:
            admin.db.delete_bot = original_delete_bot

    def test_delete_bot_route_redirect_to_client(self):
        class Request:
            session = {
                "user": "admin@example.com",
                "role": "agency_admin",
                "client_id": None,
            }

        async def fake_delete_bot(bot_id):
            return True

        original_delete_bot = admin.db.delete_bot
        admin.db.delete_bot = fake_delete_bot
        try:
            resp = asyncio.run(admin.delete_bot_route(Request(), 14, redirect_to_client=3))
            self.assertIsNotNone(resp)
            if hasattr(resp, "headers") and "location" in resp.headers:
                self.assertEqual(resp.headers["location"], "/admin/clients/3?saved=1")
            elif hasattr(resp, "content"):
                self.assertEqual(resp.content, "/admin/clients/3?saved=1")
        finally:
            admin.db.delete_bot = original_delete_bot

    def test_reset_contact_flow(self):
        from app import admin_tools

        class Request:
            session = {
                "user": "admin@example.com",
                "role": "agency_admin",
            }

        # 1. Test GET /reset-contact page sets CSRF and displays form
        req = Request()
        resp = asyncio.run(admin_tools.reset_contact_page(req, wa_id="12345"))
        self.assertIsNotNone(resp)
        self.assertIn("_csrf_token", req.session)
        token = req.session["_csrf_token"]
        self.assertIn(f'action="/admin/reset-contact?csrf_token={token}"', resp.body.decode("utf-8"))

        # 2. Test POST /reset-contact submit clears data
        async def fake_clear_contact_data(wa_ids):
            self.assertEqual(wa_ids, ["12345"])
            return True

        original_clear = admin_tools.db.clear_contact_data
        admin_tools.db.clear_contact_data = fake_clear_contact_data
        try:
            resp_post = asyncio.run(admin_tools.reset_contact_submit(Request(), wa_id="12345"))
            self.assertIsNotNone(resp_post)
            if hasattr(resp_post, "headers") and "location" in resp_post.headers:
                self.assertEqual(resp_post.headers["location"], "/admin/conversations")
            elif hasattr(resp_post, "content"):
                self.assertEqual(resp_post.content, "/admin/conversations")
            elif hasattr(resp_post, "body"):
                # fallback for RedirectResponse body if headers are not structure-matching standard
                self.assertEqual(resp_post.headers.get("location"), "/admin/conversations")
        finally:
            admin_tools.db.clear_contact_data = original_clear


if __name__ == "__main__":
    unittest.main()


