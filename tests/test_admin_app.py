import unittest
import sys
import types


class _DummyRouter:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda fn: fn

    def post(self, *args, **kwargs):
        return lambda fn: fn


class _DummyResponse:
    def __init__(self, *args, **kwargs):
        pass


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
sys.modules.setdefault(
    "cryptography.fernet",
    types.SimpleNamespace(Fernet=object, InvalidToken=Exception),
)

from app import admin


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


if __name__ == "__main__":
    unittest.main()
