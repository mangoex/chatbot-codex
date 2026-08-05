import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=None))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import whatsapp_client


class WhatsAppClientTests(unittest.TestCase):
    def test_extract_message_includes_phone_number_metadata(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "1234567890",
                                },
                                "messages": [
                                    {
                                        "from": "5216671234567",
                                        "id": "wamid.test",
                                        "type": "text",
                                        "text": {"body": "Hola"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        msg = whatsapp_client.extract_message(payload)

        self.assertEqual(msg["wa_id"], "5216671234567")
        self.assertEqual(msg["message_id"], "wamid.test")
        self.assertEqual(msg["text"], "Hola")
        self.assertEqual(msg["phone_number_id"], "1234567890")
        self.assertEqual(msg["display_phone_number"], "15551234567")

    def test_send_text_can_use_bot_specific_number_and_token(self):
        response = AsyncMock()
        response.raise_for_status = lambda: None
        response.json = lambda: {"messages": [{"id": "sent"}]}

        client = AsyncMock()
        client.__aenter__.return_value.post.return_value = response

        with patch("httpx.AsyncClient", return_value=client):
            result = asyncio.run(
                whatsapp_client.send_text(
                    "5216671234567",
                    "Hola",
                    phone_number_id="999",
                    access_token="bot-token",
                )
            )

        post = client.__aenter__.return_value.post
        url = post.call_args.args[0]
        headers = post.call_args.kwargs["headers"]
        self.assertIn("/999/messages", url)
        self.assertEqual(headers["Authorization"], "Bearer bot-token")
        self.assertEqual(result["messages"][0]["id"], "sent")

    def test_download_media_uses_bot_token_and_streams_bytes(self):
        metadata_response = AsyncMock()
        metadata_response.raise_for_status = lambda: None
        metadata_response.json = lambda: {
            "url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/test",
            "mime_type": "image/jpeg",
        }

        media_response = MagicMock()
        media_response.raise_for_status = lambda: None
        media_response.headers = {}

        async def chunks():
            yield b"image-"
            yield b"bytes"

        media_response.aiter_bytes = chunks

        stream = MagicMock()
        stream.__aenter__ = AsyncMock(return_value=media_response)
        stream.__aexit__ = AsyncMock(return_value=None)

        client_instance = MagicMock()
        client_instance.get = AsyncMock(return_value=metadata_response)
        client_instance.stream.return_value = stream
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client_instance)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=client):
            content, mime = asyncio.run(
                whatsapp_client.download_media(
                    "media-123",
                    access_token="bot-token",
                    max_bytes=1024,
                )
            )

        self.assertEqual(content, b"image-bytes")
        self.assertEqual(mime, "image/jpeg")
        calls = client_instance.get.call_args_list
        self.assertEqual(calls[0].kwargs["headers"]["Authorization"], "Bearer bot-token")
        self.assertEqual(client_instance.stream.call_args.kwargs["headers"]["Authorization"], "Bearer bot-token")

    def test_download_media_rejects_untrusted_download_host(self):
        metadata_response = AsyncMock()
        metadata_response.raise_for_status = lambda: None
        metadata_response.json = lambda: {
            "url": "https://example.net/private",
            "mime_type": "image/jpeg",
        }

        client_instance = MagicMock()
        client_instance.get = AsyncMock(return_value=metadata_response)
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client_instance)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=client):
            with self.assertRaises(ValueError):
                asyncio.run(
                    whatsapp_client.download_media(
                        "media-123",
                        access_token="bot-token",
                    )
                )

        client_instance.stream.assert_not_called()

    def test_download_media_aborts_when_stream_exceeds_limit(self):
        metadata_response = MagicMock()
        metadata_response.raise_for_status = lambda: None
        metadata_response.json.return_value = {
            "url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/test",
            "mime_type": "image/jpeg",
        }
        media_response = MagicMock()
        media_response.raise_for_status = lambda: None
        media_response.headers = {}

        async def chunks():
            yield b"abc"
            yield b"def"

        media_response.aiter_bytes = chunks
        stream = MagicMock()
        stream.__aenter__ = AsyncMock(return_value=media_response)
        stream.__aexit__ = AsyncMock(return_value=None)
        client_instance = MagicMock()
        client_instance.get = AsyncMock(return_value=metadata_response)
        client_instance.stream.return_value = stream
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client_instance)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=client):
            with self.assertRaisesRegex(ValueError, "media_too_large"):
                asyncio.run(
                    whatsapp_client.download_media(
                        "media-123", access_token="bot-token", max_bytes=5,
                    )
                )

    def test_download_media_rejects_metadata_mime_before_download(self):
        metadata_response = MagicMock()
        metadata_response.raise_for_status = lambda: None
        metadata_response.json.return_value = {
            "url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/test",
            "mime_type": "application/pdf",
        }
        client_instance = MagicMock()
        client_instance.get = AsyncMock(return_value=metadata_response)
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client_instance)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=client):
            with self.assertRaisesRegex(ValueError, "unsupported_media_mime"):
                asyncio.run(
                    whatsapp_client.download_media(
                        "media-123", access_token="bot-token", allowed_mime_types=("image/jpeg",),
                    )
                )

        client_instance.stream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
