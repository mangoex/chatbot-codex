from __future__ import annotations
import asyncio
import unittest


from unittest.mock import AsyncMock, patch, MagicMock

from app import audio_transcriber, bots, config


class AudioTranscriberUnitTests(unittest.TestCase):
    def test_determine_audio_extension_and_content_type(self):
        ext, ctype = audio_transcriber._get_audio_metadata("audio/ogg; codecs=opus")
        self.assertEqual(ext, "audio.ogg")
        self.assertEqual(ctype, "audio/ogg")

        ext, ctype = audio_transcriber._get_audio_metadata("audio/mp4")
        self.assertEqual(ext, "audio.m4a")
        self.assertEqual(ctype, "audio/mp4")

        ext, ctype = audio_transcriber._get_audio_metadata("audio/aac")
        self.assertEqual(ext, "audio.aac")
        self.assertEqual(ctype, "audio/aac")

        ext, ctype = audio_transcriber._get_audio_metadata("audio/mpeg")
        self.assertEqual(ext, "audio.mp3")
        self.assertEqual(ctype, "audio/mpeg")

    @patch("app.audio_transcriber._get_client")
    def test_transcribe_audio_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_transcriptions = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "Hola, me gustaría agendar una cita mañana a las 4pm"
        mock_transcriptions.create.return_value = mock_response
        mock_client.audio.transcriptions = mock_transcriptions
        mock_get_client.return_value = mock_client

        text = asyncio.run(
            audio_transcriber.transcribe_audio(
                audio_bytes=b"FAKE_OGG_BYTES",
                mime_type="audio/ogg; codecs=opus",
            )
        )

        self.assertEqual(text, "Hola, me gustaría agendar una cita mañana a las 4pm")
        mock_transcriptions.create.assert_awaited_once()

    @patch("app.audio_transcriber._get_client")
    def test_transcribe_audio_empty_bytes(self, mock_get_client):
        text = asyncio.run(
            audio_transcriber.transcribe_audio(
                audio_bytes=b"",
                mime_type="audio/ogg",
            )
        )
        self.assertEqual(text, "")
        mock_get_client.assert_not_called()

    @patch("app.audio_transcriber._get_client")
    def test_transcribe_audio_api_error_returns_empty(self, mock_get_client):
        mock_client = MagicMock()
        mock_transcriptions = AsyncMock()
        mock_transcriptions.create.side_effect = Exception("Whisper API Error")
        mock_client.audio.transcriptions = mock_transcriptions
        mock_get_client.return_value = mock_client

        text = asyncio.run(
            audio_transcriber.transcribe_audio(
                audio_bytes=b"FAKE_AUDIO_DATA",
                mime_type="audio/ogg",
            )
        )
        self.assertEqual(text, "")


class AudioWebhookIntegrationTests(unittest.TestCase):
    @patch("app.leads.process_reply", new_callable=AsyncMock, return_value="¡Hola! Con gusto te agendo.")
    @patch("app.main._send_and_track", new_callable=AsyncMock)
    @patch("app.skill_runtime.calendar_skill_enabled", new_callable=AsyncMock, return_value=False)
    @patch("app.db.is_chatwoot_handoff_active", new_callable=AsyncMock, return_value=False)
    @patch("app.openai_client.complete", new_callable=AsyncMock, return_value="¡Hola! Con gusto te agendo.")
    @patch("app.audio_transcriber.transcribe_audio", new_callable=AsyncMock, return_value="Hola, quiero agendar")
    @patch("app.whatsapp_client.download_media", new_callable=AsyncMock, return_value=(b"OGG_BINARY", "audio/ogg"))
    @patch("app.db.get_history", new_callable=AsyncMock, return_value=[])
    @patch("app.db.was_processed", new_callable=AsyncMock, return_value=False)
    @patch("app.db.mark_processed", new_callable=AsyncMock, return_value=True)
    @patch("app.db.get_active_bot_integration", new_callable=AsyncMock, return_value=None)
    @patch("app.follow_ups.cancel", new_callable=AsyncMock)
    @patch("app.db.save_message", new_callable=AsyncMock)
    @patch("app.bots.resolve_by_phone_number_id")
    def test_process_audio_message_transcribes_and_replies_via_ai(
        self,
        mock_resolve_bot,
        mock_save_msg,
        mock_cancel_follow,
        mock_get_integration,
        mock_mark_proc,
        mock_was_proc,
        mock_get_history,
        mock_download_media,
        mock_transcribe,
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

        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone_10"},
                                "messages": [
                                    {
                                        "id": "msg_audio_1",
                                        "from": "5216861112233",
                                        "type": "audio",
                                        "audio": {
                                            "id": "media_audio_id_1",
                                            "mime_type": "audio/ogg; codecs=opus",
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        msg = main.whatsapp_client.extract_message(payload)
        asyncio.run(main._process_message_impl(msg, payload))

        # Media downloaded and transcribed
        mock_download_media.assert_awaited_once_with("media_audio_id_1", access_token="token_10", max_bytes=unittest.mock.ANY)
        mock_transcribe.assert_awaited_once_with(b"OGG_BINARY", "audio/ogg; codecs=opus")


        # OpenAI complete called with the transcribed text
        mock_openai_complete.assert_awaited_once()
        self.assertEqual(mock_openai_complete.call_args[0][0], "Hola, quiero agendar")

        # Replied via send_and_track
        mock_send_and_track.assert_awaited_once()

    @patch("app.db.is_chatwoot_handoff_active", new_callable=AsyncMock, return_value=False)
    @patch("app.whatsapp_client.send_text", new_callable=AsyncMock)
    @patch("app.audio_transcriber.transcribe_audio", new_callable=AsyncMock, return_value="")
    @patch("app.whatsapp_client.download_media", new_callable=AsyncMock, return_value=(b"OGG_BINARY", "audio/ogg"))
    @patch("app.db.get_history", new_callable=AsyncMock, return_value=[])
    @patch("app.db.was_processed", new_callable=AsyncMock, return_value=False)
    @patch("app.db.mark_processed", new_callable=AsyncMock, return_value=True)
    @patch("app.db.get_active_bot_integration", new_callable=AsyncMock, return_value=None)
    @patch("app.follow_ups.cancel", new_callable=AsyncMock)
    @patch("app.db.save_message", new_callable=AsyncMock)
    @patch("app.bots.resolve_by_phone_number_id")
    def test_process_audio_inaudible_sends_fallback_reply(
        self,
        mock_resolve_bot,
        mock_save_msg,
        mock_cancel_follow,
        mock_get_integration,
        mock_mark_proc,
        mock_was_proc,
        mock_get_history,
        mock_download_media,
        mock_transcribe,
        mock_send_text,
        mock_is_handoff,
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
                                        "id": "msg_audio_2",
                                        "from": "5216861112233",
                                        "type": "audio",
                                        "audio": {
                                            "id": "media_audio_id_2",
                                            "mime_type": "audio/ogg; codecs=opus",
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        msg = main.whatsapp_client.extract_message(payload)
        asyncio.run(main._process_message_impl(msg, payload))

        mock_send_text.assert_awaited_once()
        sent_body = mock_send_text.call_args[0][1]
        self.assertTrue("mensaje de voz" in sent_body.lower() or "audio" in sent_body.lower())
