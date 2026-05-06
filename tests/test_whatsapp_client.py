import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

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


if __name__ == "__main__":
    unittest.main()
