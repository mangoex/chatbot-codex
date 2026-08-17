from __future__ import annotations

import sys

# Save mock httpx if it exists
mock_httpx = sys.modules.get("httpx")
if mock_httpx is not None:
    # Temporarily remove mock httpx from sys.modules
    del sys.modules["httpx"]
    
    # Import the real httpx
    import httpx as real_httpx
    
    # Copy all public attributes of the real httpx to the mock httpx SimpleNamespace if missing
    for attr in dir(real_httpx):
        if not attr.startswith("__") and not hasattr(mock_httpx, attr):
            setattr(mock_httpx, attr, getattr(real_httpx, attr))
            
    # Restore the mock httpx in sys.modules
    sys.modules["httpx"] = mock_httpx

import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

# Import app modules normally (they will see the mock httpx in sys.modules)
from app import main, db, bots


class RoutingRulesTests(unittest.TestCase):
    @patch.object(main.httpx, "AsyncClient")
    def test_forward_payload_to_external_webhook(self, mock_client):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance
        
        # Call function
        payload = {"entry": []}
        asyncio.run(
            main.forward_payload_to_external_webhook(
                "https://api.test.com/webhook",
                payload,
                "secret-token-123"
            )
        )
        
        # Verify post parameters
        mock_client_instance.post.assert_called_once_with(
            "https://api.test.com/webhook",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Asistto-Secret-Token": "secret-token-123"
            }
        )

    @patch.object(main.db, "was_processed", return_value=False)
    @patch.object(main.db, "mark_processed")
    @patch.object(main.db, "get_active_bot_integration")
    @patch.object(main.db, "get_integration_secret_values")
    @patch.object(main.follow_ups, "cancel")
    @patch.object(main.db, "save_message")
    @patch.object(main.bots, "resolve_by_phone_number_id")
    @patch.object(main, "forward_payload_to_external_webhook")
    @patch.object(main.db, "get_history")
    def test_process_message_with_bypass_matched(
        self,
        mock_get_history,
        mock_forward,
        mock_resolve,
        mock_save_msg,
        mock_cancel_follow_ups,
        mock_secrets,
        mock_get_integration,
        mock_mark_processed,
        mock_was_processed,
    ):
        # 1. Setup mocks
        mock_bot = MagicMock()
        mock_bot.id = 43
        mock_bot.whatsapp_phone_number_id = "w1"
        mock_bot.whatsapp_access_token = "t1"
        mock_resolve.return_value = mock_bot
        
        # Whitelisted phone
        mock_get_integration.return_value = {
            "id": 100,
            "config": {
                "rules": [
                    {
                        "action": "forward_and_bypass",
                        "webhook_url": "https://external.webhook/url",
                        "phone_numbers": ["5216861234567"],
                        "save_history": True
                    }
                ]
            }
        }
        
        mock_secrets.return_value = {"webhook_auth_token": "my-secret-token"}
        
        # Incoming payload from whitelisted phone
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "w1",
                                },
                                "messages": [
                                    {
                                        "from": "5216861234567",
                                        "id": "wamid.msg1",
                                        "type": "text",
                                        "text": {"body": "Hola desde ventas"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        
        # 2. Run test
        with patch.object(
            main.db,
            "is_chatwoot_handoff_active",
            new=AsyncMock(return_value=False),
        ):
            asyncio.run(main._process_message(payload))
        
        # 3. Assertions
        mock_was_processed.assert_called_once_with("wamid.msg1")
        mock_mark_processed.assert_called_once_with("wamid.msg1", bot_id=43)
        mock_cancel_follow_ups.assert_called_once_with("5216861234567", 43)
        
        # Verify webhook was scheduled for forwarding
        mock_forward.assert_called_once_with(
            "https://external.webhook/url",
            payload,
            "my-secret-token"
        )
        
        # Since save_history is True, it should save message to db
        mock_save_msg.assert_called_once_with("5216861234567", "user", "Hola desde ventas", bot_id=43)
        
        # OpenAI or normal processing should NOT have run (so get_history is not called)
        mock_get_history.assert_not_called()

    @patch.object(main.db, "was_processed", return_value=False)
    @patch.object(main.db, "mark_processed")
    @patch.object(main.db, "get_active_bot_integration")
    @patch.object(main.db, "get_integration_secret_values")
    @patch.object(main.follow_ups, "cancel")
    @patch.object(main.db, "save_message")
    @patch.object(main.bots, "resolve_by_phone_number_id")
    @patch.object(main, "forward_payload_to_external_webhook")
    @patch.object(main.db, "get_history")
    def test_process_message_with_bypass_matched_no_save_history(
        self,
        mock_get_history,
        mock_forward,
        mock_resolve,
        mock_save_msg,
        mock_cancel_follow_ups,
        mock_secrets,
        mock_get_integration,
        mock_mark_processed,
        mock_was_processed,
    ):
        mock_bot = MagicMock()
        mock_bot.id = 43
        mock_resolve.return_value = mock_bot
        
        # save_history = False
        mock_get_integration.return_value = {
            "id": 100,
            "config": {
                "rules": [
                    {
                        "action": "forward_and_bypass",
                        "webhook_url": "https://external.webhook/url",
                        "phone_numbers": ["5216861234567"],
                        "save_history": False
                    }
                ]
            }
        }
        mock_secrets.return_value = {}
        
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "w1",
                                },
                                "messages": [
                                    {
                                        "from": "5216861234567",
                                        "id": "wamid.msg1",
                                        "type": "text",
                                        "text": {"body": "Hola ventas no guardado"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        
        asyncio.run(main._process_message(payload))
        
        mock_forward.assert_called_once_with(
            "https://external.webhook/url",
            payload,
            ""
        )
        
        # save_message should NOT be called since save_history is False
        mock_save_msg.assert_not_called()
        mock_get_history.assert_not_called()

    @patch.object(main.db, "was_processed", return_value=False)
    @patch.object(main.db, "mark_processed")
    @patch.object(main.db, "get_active_bot_integration")
    @patch.object(main.follow_ups, "cancel")
    @patch.object(main.db, "save_message")
    @patch.object(main.bots, "resolve_by_phone_number_id")
    @patch.object(main, "forward_payload_to_external_webhook")
    @patch.object(main.db, "get_history")
    def test_process_message_with_bypass_matched_empty_webhook_url(
        self,
        mock_get_history,
        mock_forward,
        mock_resolve,
        mock_save_msg,
        mock_cancel_follow_ups,
        mock_get_integration,
        mock_mark_processed,
        mock_was_processed,
    ):
        mock_bot = MagicMock()
        mock_bot.id = 43
        mock_resolve.return_value = mock_bot
        
        # Whitelisted phone with empty webhook_url (pure silent omission mode)
        mock_get_integration.return_value = {
            "id": 100,
            "config": {
                "rules": [
                    {
                        "action": "forward_and_bypass",
                        "webhook_url": "",
                        "phone_numbers": ["5216861234567"],
                        "save_history": True
                    }
                ]
            }
        }
        
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "w1",
                                },
                                "messages": [
                                    {
                                        "from": "5216861234567",
                                        "id": "wamid.msg_empty_url",
                                        "type": "text",
                                        "text": {"body": "Mensaje de familiar / agente"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        
        with patch.object(
            main.db,
            "is_chatwoot_handoff_active",
            new=AsyncMock(return_value=False),
        ):
            asyncio.run(main._process_message(payload))
        
        mock_cancel_follow_ups.assert_called_once_with("5216861234567", 43)
        mock_forward.assert_not_called()
        mock_save_msg.assert_called_once_with("5216861234567", "user", "Mensaje de familiar / agente", bot_id=43)
        mock_get_history.assert_not_called()

    @patch.object(main.db, "was_processed", return_value=False)
    @patch.object(main.db, "mark_processed")
    @patch.object(main.db, "get_active_bot_integration")
    @patch.object(main.follow_ups, "cancel")
    @patch.object(main.db, "save_message")
    @patch.object(main.bots, "resolve_by_phone_number_id")
    @patch.object(main, "forward_payload_to_external_webhook")
    @patch.object(main.db, "get_history")
    def test_process_message_with_bypass_prefix_variations(
        self,
        mock_get_history,
        mock_forward,
        mock_resolve,
        mock_save_msg,
        mock_cancel_follow_ups,
        mock_get_integration,
        mock_mark_processed,
        mock_was_processed,
    ):
        mock_bot = MagicMock()
        mock_bot.id = 43
        mock_resolve.return_value = mock_bot
        
        # Configured with 10 digits without country code
        mock_get_integration.return_value = {
            "id": 100,
            "config": {
                "rules": [
                    {
                        "action": "forward_and_bypass",
                        "webhook_url": "",
                        "phone_numbers": ["6861234567"],
                        "save_history": False
                    }
                ]
            }
        }
        
        # Incoming from Meta with 521 prefix
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "w1",
                                },
                                "messages": [
                                    {
                                        "from": "5216861234567",
                                        "id": "wamid.msg_var1",
                                        "type": "text",
                                        "text": {"body": "Mensaje desde 521"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        
        with patch.object(
            main.db,
            "is_chatwoot_handoff_active",
            new=AsyncMock(return_value=False),
        ):
            asyncio.run(main._process_message(payload))
        
        # Should be bypassed
        mock_cancel_follow_ups.assert_called_once_with("5216861234567", 43)
        mock_get_history.assert_not_called()

    def test_is_phone_in_list_normalization(self):
        from app.bot_control import is_phone_in_list

        whitelist = ["6861234567", "+52 1 555 987 6543"]

        self.assertTrue(is_phone_in_list("5216861234567", whitelist))
        self.assertTrue(is_phone_in_list("526861234567", whitelist))
        self.assertTrue(is_phone_in_list("6861234567", whitelist))
        self.assertTrue(is_phone_in_list("525559876543", whitelist))
        self.assertTrue(is_phone_in_list("5215559876543", whitelist))

        self.assertFalse(is_phone_in_list("5216869999999", whitelist))
        self.assertFalse(is_phone_in_list("", whitelist))
        self.assertFalse(is_phone_in_list("123", whitelist))

    @patch.object(main.db, "was_processed", return_value=False)
    @patch.object(main.db, "mark_processed")
    @patch.object(main.db, "get_active_bot_integration")
    @patch.object(main.db, "get_integration_secret_values")
    @patch.object(main.follow_ups, "cancel")
    @patch.object(main.db, "save_message")
    @patch.object(main.bots, "resolve_by_phone_number_id")
    @patch.object(main, "forward_payload_to_external_webhook")
    @patch.object(main.db, "get_history")
    @patch.object(main.openai_client, "complete", new_callable=AsyncMock)
    @patch.object(main.leads, "process_reply", new_callable=AsyncMock)
    @patch.object(main.agenda_guard, "maybe_handle", new_callable=AsyncMock, return_value=(None, False))
    @patch.object(main, "_send_and_track", new_callable=AsyncMock)
    def test_process_message_no_bypass_if_number_not_whitelisted(
        self,
        mock_send_and_track,
        mock_agenda_reply,
        mock_lead_reply,
        mock_openai,
        mock_get_history,
        mock_forward,
        mock_resolve,
        mock_save_msg,
        mock_cancel_follow_ups,
        mock_secrets,
        mock_get_integration,
        mock_mark_processed,
        mock_was_processed,
    ):
        mock_bot = MagicMock()
        mock_bot.id = 43
        mock_bot.status = "active"
        mock_resolve.return_value = mock_bot
        
        # Whitelist does NOT contain the incoming phone number "5219999999999"
        mock_get_integration.return_value = {
            "id": 100,
            "config": {
                "rules": [
                    {
                        "action": "forward_and_bypass",
                        "webhook_url": "https://external.webhook/url",
                        "phone_numbers": ["5216861234567"]
                    }
                ]
            }
        }
        
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "w1",
                                },
                                "messages": [
                                    {
                                        "from": "5219999999999",
                                        "id": "wamid.msg1",
                                        "type": "text",
                                        "text": {"body": "Mensaje de cliente regular"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        
        mock_get_history.return_value = []
        mock_openai.return_value = "Respuesta de la IA"
        mock_lead_reply.return_value = "Respuesta de la IA"
        
        with patch.object(
            main.db,
            "is_chatwoot_handoff_active",
            new=AsyncMock(return_value=False),
        ):
            asyncio.run(main._process_message(payload))

        # Webhook should NOT have been forwarded
        mock_forward.assert_not_called()
        
        # Save message should be called (once for user message, once for bot reply)
        self.assertGreaterEqual(mock_save_msg.call_count, 1)
        
        # History should be fetched for regular processing
        mock_get_history.assert_called_once()
        mock_openai.assert_called_once()

    def test_disabled_bot_all_media_preserves_historical_reply_without_payment_effects(self):
        bot = MagicMock()
        bot.id = 23
        bot.status = "active"
        bot.whatsapp_phone_number_id = "phone-23"
        bot.whatsapp_access_token = "token-23"
        save = AsyncMock()
        send = AsyncMock()
        order_media = AsyncMock(return_value=None)
        with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)), \
             patch.object(main.db, "was_processed", AsyncMock(return_value=False)), \
             patch.object(main.db, "mark_processed", AsyncMock(return_value=True)), \
             patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=None)), \
             patch.object(main.follow_ups, "cancel", AsyncMock()), \
             patch.object(main.follow_ups, "schedule", AsyncMock()), \
             patch.object(main.db, "get_history", AsyncMock(return_value=[])), \
             patch.object(main.db, "save_message", save), \
             patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=False)), \
             patch.object(main.order_payments, "handle_incoming_media", order_media), \
             patch.object(main.whatsapp_client, "send_text", send), \
             patch.object(main.escalations, "record_if_escalated", AsyncMock()):
            for index, (media_type, mime) in enumerate((
                ("image", "image/jpeg"),
                ("video", "video/mp4"),
                ("document", "application/pdf"),
            )):
                msg = {
                    "wa_id": "5216000000023",
                    "message_id": f"wamid.media-disabled-{index}",
                    "type": media_type,
                    "text": "",
                    "media_id": f"media-23-{index}",
                    "media_mime": mime,
                }
                asyncio.run(main._process_message_impl(msg, {}))

        self.assertEqual(order_media.await_count, 3)
        self.assertEqual(send.await_count, 3)
        self.assertTrue(all(call.args[1] == main.MEDIA_REPLY for call in send.await_args_list))
        assistant_saves = [call for call in save.await_args_list if call.args[1] == "assistant"]
        self.assertEqual([call.args[2] for call in assistant_saves], [main.MEDIA_REPLY] * 3)
