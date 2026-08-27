from __future__ import annotations
import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from app import bot_control, bots, config


class BotControlUnitTests(unittest.TestCase):
    def test_normalize_command(self):
        self.assertEqual(bot_control.normalize_command("  ¡Pausa!  "), "pausa")
        self.assertEqual(bot_control.normalize_command("PAUSAR..."), "pausar")
        self.assertEqual(bot_control.normalize_command("¿Seguir?"), "seguir")
        self.assertEqual(bot_control.normalize_command("Reanúdar"), "reanudar")
        self.assertEqual(bot_control.normalize_command("Detener"), "detener")

    def test_detect_control_command(self):
        # Pause variants
        self.assertEqual(bot_control.detect_control_command("Pausa"), "pause")
        self.assertEqual(bot_control.detect_control_command("pausar"), "pause")
        self.assertEqual(bot_control.detect_control_command("detener"), "pause")
        self.assertEqual(bot_control.detect_control_command("stop"), "pause")
        self.assertEqual(bot_control.detect_control_command("apagar bot"), "pause")
        self.assertEqual(bot_control.detect_control_command("pausa bot"), "pause")
        self.assertEqual(bot_control.detect_control_command("apagate"), "pause")
        self.assertEqual(bot_control.detect_control_command("apágate"), "pause")
        self.assertEqual(bot_control.detect_control_command("apaga"), "pause")
        self.assertEqual(bot_control.detect_control_command("paúsate"), "pause")

        # Resume variants
        self.assertEqual(bot_control.detect_control_command("Seguir"), "resume")
        self.assertEqual(bot_control.detect_control_command("sigue"), "resume")
        self.assertEqual(bot_control.detect_control_command("continuar"), "resume")
        self.assertEqual(bot_control.detect_control_command("reanudar"), "resume")
        self.assertEqual(bot_control.detect_control_command("start"), "resume")
        self.assertEqual(bot_control.detect_control_command("iniciar"), "resume")
        self.assertEqual(bot_control.detect_control_command("seguir bot"), "resume")
        self.assertEqual(bot_control.detect_control_command("prender bot"), "resume")
        self.assertEqual(bot_control.detect_control_command("encender"), "resume")
        self.assertEqual(bot_control.detect_control_command("enciende"), "resume")
        self.assertEqual(bot_control.detect_control_command("enciéndete"), "resume")
        self.assertEqual(bot_control.detect_control_command("enciendete"), "resume")
        self.assertEqual(bot_control.detect_control_command("prende"), "resume")

        # Sync Easybroker properties variants
        self.assertEqual(bot_control.detect_control_command("actualizar propiedades"), "sync_properties")
        self.assertEqual(bot_control.detect_control_command("actualizar catalogo"), "sync_properties")
        self.assertEqual(bot_control.detect_control_command("actualizar catálogo"), "sync_properties")
        self.assertEqual(bot_control.detect_control_command("sync easybroker"), "sync_properties")
        self.assertEqual(bot_control.detect_control_command("sincronizar propiedades"), "sync_properties")
        self.assertEqual(bot_control.detect_control_command("actualizar inmuebles"), "sync_properties")

        # Sync Google Drive variants
        self.assertEqual(bot_control.detect_control_command("sincronizar drive"), "sync_drive")
        self.assertEqual(bot_control.detect_control_command("sync drive"), "sync_drive")
        self.assertEqual(bot_control.detect_control_command("sincronizar google drive"), "sync_drive")
        self.assertEqual(bot_control.detect_control_command("actualizar drive"), "sync_drive")
        self.assertEqual(bot_control.detect_control_command("actualizar documentos"), "sync_drive")
        self.assertEqual(bot_control.detect_control_command("actualizar conocimiento"), "sync_drive")


        # Regular messages that should not trigger control
        self.assertIsNone(bot_control.detect_control_command("Hola, quiero agendar"))
        self.assertIsNone(bot_control.detect_control_command("Haremos una pausa comercial para el evento"))
        self.assertIsNone(bot_control.detect_control_command("¿Podemos seguir con la llamada mañana?"))
        self.assertIsNone(bot_control.detect_control_command(""))

    def test_is_authorized_admin_global_config(self):
        bot = bots.BotContext(
            id=1,
            client_id=1,
            slug="test-bot",
            name="Test Bot",
            whatsapp_phone_number_id="12345",
            whatsapp_access_token="token",
            display_phone_number="5216860000000",
            status="active",
        )
        with patch.object(bot_control.config, "ADMIN_PHONE_NUMBERS", ["5216861234567", "5215559876543"]):
            # Matches normalized numbers
            self.assertTrue(bot_control.is_authorized_admin("+52 1 686 123 4567", bot))
            self.assertTrue(bot_control.is_authorized_admin("5216861234567", bot))
            self.assertTrue(bot_control.is_authorized_admin("5215559876543", bot))

            # Unauthorized
            self.assertFalse(bot_control.is_authorized_admin("5219991112233", bot))

    def test_is_authorized_admin_display_phone(self):
        bot = bots.BotContext(
            id=2,
            client_id=1,
            slug="test-bot",
            name="Test Bot",
            whatsapp_phone_number_id="12345",
            whatsapp_access_token="token",
            display_phone_number="+52 (686) 555-4433",
            status="active",
        )
        with patch.object(bot_control.config, "ADMIN_PHONE_NUMBERS", []):
            self.assertTrue(bot_control.is_authorized_admin("5216865554433", bot))
            self.assertTrue(bot_control.is_authorized_admin("526865554433", bot))
            self.assertTrue(bot_control.is_authorized_admin("6865554433", bot))
            self.assertFalse(bot_control.is_authorized_admin("5219991112233", bot))

    def test_is_authorized_admin_mexico_10_digits_variants(self):
        # Bot configured with +52 1 667 102 0672
        bot = bots.BotContext(
            id=170,
            client_id=1,
            slug="mobi",
            name="Mobi Muebles",
            whatsapp_phone_number_id="12345",
            whatsapp_access_token="token",
            display_phone_number="+52 1 667 102 0672",
            status="active",
        )
        with patch.object(bot_control.config, "ADMIN_PHONE_NUMBERS", []):
            # Incoming from 5216671020672
            self.assertTrue(bot_control.is_authorized_admin("5216671020672", bot))
            # Incoming from 526671020672
            self.assertTrue(bot_control.is_authorized_admin("526671020672", bot))
            # Incoming from 16671020672
            self.assertTrue(bot_control.is_authorized_admin("16671020672", bot))
            # Incoming from 6671020672
            self.assertTrue(bot_control.is_authorized_admin("6671020672", bot))
            # Fallback to extra_phone metadata
            self.assertTrue(bot_control.is_authorized_admin("5216671020672", bot=None, extra_phone="16671020672"))


    @patch("app.db.update_bot_status", new_callable=AsyncMock)
    @patch("app.db.save_message", new_callable=AsyncMock)
    @patch("app.whatsapp_client.send_text", new_callable=AsyncMock)
    @patch("app.follow_ups.cancel", new_callable=AsyncMock)
    def test_handle_pause_command(
        self, mock_follow_up_cancel, mock_send_text, mock_save_message, mock_update_status
    ):
        bot = bots.BotContext(
            id=5,
            client_id=1,
            slug="test-bot",
            name="Asistto Test",
            whatsapp_phone_number_id="phone_id_1",
            whatsapp_access_token="token_1",
            status="active",
        )

        res = asyncio.run(
            bot_control.handle_control_command(
                bot=bot,
                wa_id="5216861234567",
                command="pause",
            )
        )

        self.assertEqual(res["action"], "paused")
        mock_update_status.assert_awaited_once_with(5, "paused")
        mock_follow_up_cancel.assert_awaited_once_with("5216861234567", 5)
        mock_save_message.assert_awaited_once()
        mock_send_text.assert_awaited_once()
        self.assertIn("pausado", mock_send_text.call_args[0][1].lower())

    @patch("app.db.update_bot_status", new_callable=AsyncMock)
    @patch("app.db.save_message", new_callable=AsyncMock)
    @patch("app.whatsapp_client.send_text", new_callable=AsyncMock)
    def test_handle_resume_command(
        self, mock_send_text, mock_save_message, mock_update_status
    ):
        bot = bots.BotContext(
            id=5,
            client_id=1,
            slug="test-bot",
            name="Asistto Test",
            whatsapp_phone_number_id="phone_id_1",
            whatsapp_access_token="token_1",
            status="paused",
        )

        res = asyncio.run(
            bot_control.handle_control_command(
                bot=bot,
                wa_id="5216861234567",
                command="resume",
            )
        )

        self.assertEqual(res["action"], "resumed")
        mock_update_status.assert_awaited_once_with(5, "active")
        mock_save_message.assert_awaited_once()
        mock_send_text.assert_awaited_once()
        self.assertIn("reanudado", mock_send_text.call_args[0][1].lower())

    @patch("app.db.get_active_bot_integration", new_callable=AsyncMock)
    @patch("app.db.get_integration_secret_values", new_callable=AsyncMock)
    @patch("app.secure_store.decrypt_secret", return_value="eb_api_key_123")
    @patch("app.easybroker_client.sync_properties_to_bot_knowledge", new_callable=AsyncMock)
    @patch("app.db.save_message", new_callable=AsyncMock)
    @patch("app.whatsapp_client.send_text", new_callable=AsyncMock)
    def test_handle_sync_properties_command_success(
        self,
        mock_send_text,
        mock_save_message,
        mock_sync_props,
        mock_decrypt,
        mock_get_secrets,
        mock_get_integ,
    ):
        bot = bots.BotContext(
            id=7,
            client_id=1,
            slug="real-estate-bot",
            name="Inmobiliaria Bot",
            whatsapp_phone_number_id="phone_id_7",
            whatsapp_access_token="token_7",
            status="active",
        )
        mock_get_integ.return_value = {"id": 10, "enabled": True}
        mock_get_secrets.return_value = {"api_key": "enc_key"}
        mock_sync_props.return_value = {"success": True, "synced_count": 12}

        res = asyncio.run(
            bot_control.handle_control_command(
                bot=bot,
                wa_id="5216861234567",
                command="sync_properties",
            )
        )

        self.assertEqual(res["action"], "properties_synced")
        mock_sync_props.assert_awaited_once_with(7, "eb_api_key_123")
        mock_save_message.assert_awaited_once()
        mock_send_text.assert_awaited_once()
        self.assertIn("12", mock_send_text.call_args[0][1])

    @patch("app.db.get_active_bot_integration", new_callable=AsyncMock, return_value=None)
    @patch("app.db.save_message", new_callable=AsyncMock)
    @patch("app.whatsapp_client.send_text", new_callable=AsyncMock)
    def test_handle_sync_properties_command_not_active(
        self, mock_send_text, mock_save_message, mock_get_integ
    ):
        bot = bots.BotContext(
            id=8,
            client_id=1,
            slug="no-eb-bot",
            name="Normal Bot",
            whatsapp_phone_number_id="phone_id_8",
            whatsapp_access_token="token_8",
            status="active",
        )

        res = asyncio.run(
            bot_control.handle_control_command(
                bot=bot,
                wa_id="5216861234567",
                command="sync_properties",
            )
        )

        self.assertEqual(res["action"], "easybroker_not_active")
        mock_send_text.assert_awaited_once()
        self.assertIn("no está activa", mock_send_text.call_args[0][1].lower())


class BotControlWebhookIntegrationTests(unittest.TestCase):
    @patch("app.db.get_history", new_callable=AsyncMock, return_value=[])
    @patch("app.db.was_processed", new_callable=AsyncMock, return_value=False)
    @patch("app.db.mark_processed", new_callable=AsyncMock, return_value=True)
    @patch("app.db.get_active_bot_integration", new_callable=AsyncMock, return_value=None)
    @patch("app.follow_ups.cancel", new_callable=AsyncMock)
    @patch("app.db.save_message", new_callable=AsyncMock)
    @patch("app.bots.resolve_by_phone_number_id")
    @patch("app.whatsapp_client.send_text", new_callable=AsyncMock)
    @patch("app.db.update_bot_status", new_callable=AsyncMock)
    def test_process_message_admin_pause_command(
        self,
        mock_update_status,
        mock_send_text,
        mock_resolve_bot,
        mock_save_msg,
        mock_cancel_follow,
        mock_get_integration,
        mock_mark_proc,
        mock_was_proc,
        mock_get_history,
    ):
        from app import main

        mock_bot = MagicMock()
        mock_bot.id = 10
        mock_bot.name = "Bot Demo"
        mock_bot.status = "active"
        mock_bot.whatsapp_phone_number_id = "phone_10"
        mock_bot.whatsapp_access_token = "token_10"
        mock_bot.display_phone_number = "5216869999999"
        mock_resolve_bot.return_value = mock_bot

        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone_10"},
                                "messages": [
                                    {
                                        "id": "msg_cmd_1",
                                        "from": "5216861234567",
                                        "type": "text",
                                        "text": {"body": "Pausa"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        with patch.object(bot_control.config, "ADMIN_PHONE_NUMBERS", ["5216861234567"]), \
             patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=False)):
            msg = main.whatsapp_client.extract_message(payload)
            asyncio.run(main._process_message_impl(msg, payload))

        mock_update_status.assert_awaited_once_with(10, "paused")
        mock_send_text.assert_awaited()
        sent_body = mock_send_text.call_args[0][1]
        self.assertIn("pausado", sent_body.lower())

    @patch("app.db.get_history", new_callable=AsyncMock, return_value=[])
    @patch("app.db.was_processed", new_callable=AsyncMock, return_value=False)
    @patch("app.db.mark_processed", new_callable=AsyncMock, return_value=True)
    @patch("app.db.get_active_bot_integration", new_callable=AsyncMock, return_value=None)
    @patch("app.follow_ups.cancel", new_callable=AsyncMock)
    @patch("app.db.save_message", new_callable=AsyncMock)
    @patch("app.bots.resolve_by_phone_number_id")
    @patch("app.whatsapp_client.send_text", new_callable=AsyncMock)
    @patch("app.db.update_bot_status", new_callable=AsyncMock)
    def test_process_message_admin_resume_command_when_bot_was_paused(
        self,
        mock_update_status,
        mock_send_text,
        mock_resolve_bot,
        mock_save_msg,
        mock_cancel_follow,
        mock_get_integration,
        mock_mark_proc,
        mock_was_proc,
        mock_get_history,
    ):
        from app import main

        mock_bot = MagicMock()
        mock_bot.id = 10
        mock_bot.name = "Bot Demo"
        mock_bot.status = "paused"
        mock_bot.whatsapp_phone_number_id = "phone_10"
        mock_bot.whatsapp_access_token = "token_10"
        mock_bot.display_phone_number = "5216869999999"
        mock_resolve_bot.return_value = mock_bot

        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone_10"},
                                "messages": [
                                    {
                                        "id": "msg_cmd_2",
                                        "from": "5216861234567",
                                        "type": "text",
                                        "text": {"body": "Seguir"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        with patch.object(bot_control.config, "ADMIN_PHONE_NUMBERS", ["5216861234567"]), \
             patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=False)):
            msg = main.whatsapp_client.extract_message(payload)
            asyncio.run(main._process_message_impl(msg, payload))

        mock_update_status.assert_awaited_once_with(10, "active")
        mock_send_text.assert_awaited()
        sent_body = mock_send_text.call_args[0][1]
        self.assertIn("reanudado", sent_body.lower())

    @patch("app.leads.process_reply", new_callable=AsyncMock, return_value="Respuesta final")
    @patch("app.main._send_and_track", new_callable=AsyncMock)
    @patch("app.skill_runtime.calendar_skill_enabled", new_callable=AsyncMock, return_value=False)
    @patch("app.db.is_chatwoot_handoff_active", new_callable=AsyncMock, return_value=False)
    @patch("app.openai_client.complete", new_callable=AsyncMock, return_value="Respuesta de IA normal")
    @patch("app.db.get_history", new_callable=AsyncMock, return_value=[])
    @patch("app.db.was_processed", new_callable=AsyncMock, return_value=False)
    @patch("app.db.mark_processed", new_callable=AsyncMock, return_value=True)
    @patch("app.db.get_active_bot_integration", new_callable=AsyncMock, return_value=None)
    @patch("app.follow_ups.cancel", new_callable=AsyncMock)
    @patch("app.db.save_message", new_callable=AsyncMock)
    @patch("app.bots.resolve_by_phone_number_id")
    @patch("app.whatsapp_client.send_text", new_callable=AsyncMock)
    @patch("app.db.update_bot_status", new_callable=AsyncMock)
    def test_process_message_unauthorized_user_saying_pausa_does_not_pause(
        self,
        mock_update_status,
        mock_send_text,
        mock_resolve_bot,
        mock_save_msg,
        mock_cancel_follow,
        mock_get_integration,
        mock_mark_proc,
        mock_was_proc,
        mock_get_history,
        mock_openai_complete,
        mock_is_handoff,
        mock_cal_enabled,
        mock_send_and_track,
        mock_leads_process,
    ):
        from app import main

        mock_bot = MagicMock()
        mock_bot.id = 10
        mock_bot.name = "Bot Demo"
        mock_bot.status = "active"
        mock_bot.whatsapp_phone_number_id = "phone_10"
        mock_bot.whatsapp_access_token = "token_10"
        mock_bot.display_phone_number = "5216869999999"
        mock_bot.openai_model = "gpt-4o-mini"
        mock_resolve_bot.return_value = mock_bot

        # Customer sends "Pausa", but is not an admin
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone_10"},
                                "messages": [
                                    {
                                        "id": "msg_customer_1",
                                        "from": "5219998887766",
                                        "type": "text",
                                        "text": {"body": "Pausa"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        with patch.object(bot_control.config, "ADMIN_PHONE_NUMBERS", ["5216861234567"]):
            msg = main.whatsapp_client.extract_message(payload)
            asyncio.run(main._process_message_impl(msg, payload))

        # Status must NOT be updated
        mock_update_status.assert_not_called()
        # Normal complete was called
        mock_openai_complete.assert_awaited_once()
        mock_send_and_track.assert_awaited_once()

    @patch("app.whatsapp_client.send_text", new_callable=AsyncMock)
    @patch("app.db.save_message", new_callable=AsyncMock)
    @patch("app.google_drive_client.sync_google_drive_to_bot_knowledge", new_callable=AsyncMock)
    @patch("app.secure_store.decrypt_secret")
    @patch("app.db.get_integration_secret_values", new_callable=AsyncMock)
    @patch("app.db.get_active_bot_integration", new_callable=AsyncMock)
    def test_handle_control_command_sync_drive(
        self,
        mock_get_integ,
        mock_get_secrets,
        mock_decrypt,
        mock_sync_drive,
        mock_save_msg,
        mock_send_text,
    ):
        mock_bot = bots.BotContext(
            id=170,
            client_id=1,
            slug="mobibot",
            name="Mobibot",
            whatsapp_phone_number_id="phone_170",
            whatsapp_access_token="token_170",
            display_phone_number="5216671020672",
            status="active",
        )
        mock_get_integ.return_value = {
            "id": 12,
            "enabled": True,
            "config": {"folder_id": "1folderDrive123"},
        }
        mock_get_secrets.return_value = {"service_account_json": "enc_sa_json"}
        mock_decrypt.return_value = '{"type": "service_account"}'
        mock_sync_drive.return_value = {"ok": True, "synced_count": 8}

        res = asyncio.run(bot_control.handle_control_command(mock_bot, "5216671020672", "sync_drive"))
        self.assertEqual(res["action"], "google_drive_synced")
        self.assertIn("8 documentos actualizados", res["reply"])
        mock_sync_drive.assert_awaited_once_with(170, "1folderDrive123", '{"type": "service_account"}')
        mock_send_text.assert_awaited_once()
