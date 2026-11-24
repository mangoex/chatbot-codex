from __future__ import annotations

import asyncio
import types
import unittest
from unittest.mock import AsyncMock, patch

from app import admin, auth, mailer


def _fake_request(base_url: str = "https://asistto.bots2.me/") -> types.SimpleNamespace:
    return types.SimpleNamespace(session={}, base_url=base_url)


class PasswordResetTests(unittest.TestCase):
    def test_reset_token_generation_and_hashing(self):
        token = auth.generate_reset_token()
        self.assertGreaterEqual(len(token), 32)
        self.assertNotEqual(token, auth.hash_reset_token(token))
        self.assertEqual(auth.hash_reset_token(token), auth.hash_reset_token(f"  {token}  "))

    def test_login_page_has_password_eye_toggle_and_forgot_link(self):
        resp = asyncio.run(admin.login_page(_fake_request()))
        body = resp.body.decode("utf-8") if isinstance(resp.body, (bytes, bytearray)) else str(resp.body)
        self.assertIn('data-password-toggle="pw-password"', body)
        self.assertIn('href="/admin/forgot-password"', body)
        self.assertIn("Recuperar contrasena", body)

    def test_forgot_password_requires_email_configuration(self):
        with patch.object(mailer, "is_configured", return_value=False):
            resp = asyncio.run(admin.forgot_password_submit(_fake_request(), email="user@example.com"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/forgot-password?error=", resp.headers["location"])

    def test_forgot_password_dispatches_email_for_existing_user(self):
        send_mock = AsyncMock(return_value=True)
        create_mock = AsyncMock()
        user_mock = AsyncMock(return_value={"user_id": 7, "email": "user@example.com", "name": "Hanna"})
        with (
            patch.object(mailer, "is_configured", return_value=True),
            patch.object(mailer, "send_email", send_mock),
            patch.object(admin.db, "get_active_user_by_email", user_mock),
            patch.object(admin.db, "create_password_reset_token", create_mock),
            patch.object(admin.config, "WEBHOOK_DOMAIN", "https://asistto.bots2.me"),
        ):
            resp = asyncio.run(admin.forgot_password_submit(_fake_request(), email="USER@example.com"))

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/forgot-password?ok=", resp.headers["location"])
        create_mock.assert_awaited_once()
        send_mock.assert_awaited_once()
        sent_to, subject, text_body, html_body = send_mock.call_args.args
        self.assertEqual(sent_to, "user@example.com")
        self.assertIn("Recuperar", subject)
        self.assertIn("https://asistto.bots2.me/admin/reset-password?token=", text_body)
        self.assertIn("https://asistto.bots2.me/admin/reset-password?token=", html_body)

    def test_forgot_password_returns_generic_ok_for_unknown_email(self):
        send_mock = AsyncMock(return_value=True)
        with (
            patch.object(mailer, "is_configured", return_value=True),
            patch.object(mailer, "send_email", send_mock),
            patch.object(admin.db, "get_active_user_by_email", AsyncMock(return_value=None)),
        ):
            resp = asyncio.run(admin.forgot_password_submit(_fake_request(), email="nobody@example.com"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/forgot-password?ok=", resp.headers["location"])
        send_mock.assert_not_awaited()

    def test_reset_password_page_rejects_invalid_token(self):
        with patch.object(admin.db, "get_valid_password_reset_token", AsyncMock(return_value=None)):
            resp = asyncio.run(admin.reset_password_page(_fake_request(), token="invalid"))
        self.assertEqual(resp.status_code, 400)

    def test_reset_password_page_renders_form_with_eye_toggles(self):
        record = {"id": 1, "user_id": 7, "email": "user@example.com", "name": "Hanna"}
        with patch.object(admin.db, "get_valid_password_reset_token", AsyncMock(return_value=record)):
            resp = asyncio.run(admin.reset_password_page(_fake_request(), token="valid-token"))
        self.assertEqual(resp.status_code, 200)
        body = resp.body.decode("utf-8") if isinstance(resp.body, (bytes, bytearray)) else str(resp.body)
        self.assertIn('data-password-toggle="pw-password"', body)
        self.assertIn('data-password-toggle="pw-confirm_password"', body)
        self.assertIn("user@example.com", body)

    def test_reset_password_submit_validates_and_updates_password(self):
        short_resp = asyncio.run(
            admin.reset_password_submit(token="tok", password="short", confirm_password="short")
        )
        self.assertIn("error=", short_resp.headers["location"])

        mismatch_resp = asyncio.run(
            admin.reset_password_submit(token="tok", password="Password123", confirm_password="Password999")
        )
        self.assertIn("error=", mismatch_resp.headers["location"])

        consume_mock = AsyncMock(return_value=True)
        with patch.object(admin.db, "consume_password_reset_token", consume_mock):
            ok_resp = asyncio.run(
                admin.reset_password_submit(
                    token="valid-token",
                    password="NewSecurePassword123",
                    confirm_password="NewSecurePassword123",
                )
            )
        self.assertEqual(ok_resp.status_code, 302)
        self.assertIn("/admin/login?ok=", ok_resp.headers["location"])
        consume_mock.assert_awaited_once()
        token_hash, new_hash = consume_mock.call_args.args
        self.assertEqual(token_hash, auth.hash_reset_token("valid-token"))
        self.assertTrue(auth.verify_password("NewSecurePassword123", new_hash))


if __name__ == "__main__":
    unittest.main()
