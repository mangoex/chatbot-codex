import unittest
import sys
import types


class _DummyRouter:
    def __init__(self, *args, **kwargs):
        self.routes = []

    def api_route(self, path, methods=None, *args, **kwargs):
        self.routes.append({"path": path, "methods": tuple(methods or ())})
        return lambda fn: fn


class _DummyResponse:
    def __init__(self, content="", *args, **kwargs):
        self.content = content


sys.modules["fastapi"] = types.SimpleNamespace(APIRouter=_DummyRouter, Request=object)
sys.modules["fastapi.responses"] = types.SimpleNamespace(HTMLResponse=_DummyResponse)

from app import public_pages


class PublicPagesTests(unittest.TestCase):
    def test_privacy_page_identifies_app_and_business_owner(self):
        response = public_pages._page("/privacy")
        content = response.content

        self.assertIn("Asistto by Humanio", content)
        self.assertIn("Asistto-chatbot", content)
        self.assertIn("Humanio es el negocio responsable", content)
        self.assertIn("bot.humanio.digital", content)
        self.assertIn("contacto@humanio.digital", content)

    def test_public_pages_accept_head_for_review_tools(self):
        routes = {route["path"]: route["methods"] for route in public_pages.router.routes}
        for path in ("/", "/privacy", "/terms", "/support", "/data-deletion", "/ai-data-policy"):
            with self.subTest(path=path):
                self.assertEqual(routes[path], ("GET", "HEAD"))

    def test_landing_page_content(self):
        # We can call the landing_page endpoint directly by passing a dummy request
        class DummyRequest:
            pass
        import asyncio
        response = asyncio.run(public_pages.landing_page(DummyRequest()))
        self.assertIn("Asistto", response.content)
        self.assertIn("Meta Tech Provider", response.content)
        self.assertIn("Google Calendar", response.content)


if __name__ == "__main__":
    unittest.main()
