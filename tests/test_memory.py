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

import types
import unittest
from unittest.mock import AsyncMock, patch

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import db, leads, openai_client


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_context_injects_lead_info(self):
        lead_info = {"nombre": "Miguel Gonzales", "negocio": "Consultor de IA"}
        context = openai_client._runtime_context(lead_info)
        
        self.assertIn("- Nombre del cliente: Miguel Gonzales", context)
        self.assertIn("- Negocio/Giro del cliente: Consultor de IA", context)

    def test_runtime_context_empty_when_no_lead_info(self):
        context = openai_client._runtime_context(None)
        self.assertNotIn("Nombre del cliente", context)
        self.assertNotIn("Negocio/Giro del cliente", context)

    @patch("app.db.upsert_lead", new_callable=AsyncMock)
    async def test_process_reply_does_not_pass_none_values(self, mock_upsert_lead):
        history = [
            {"role": "user", "content": "Hola"}
        ]
        
        await leads.process_reply(
            wa_id="wa-123",
            reply="Hola, ¿cómo estás?",
            history=history,
            bot_id=1
        )
        
        # It should not pass 'nombre' or 'negocio' keys if they were not extracted (they are None)
        mock_upsert_lead.assert_called_once()
        args, kwargs = mock_upsert_lead.call_args
        self.assertEqual(kwargs.get("qualification_status"), "en_progreso")
        self.assertNotIn("nombre", kwargs)
        self.assertNotIn("negocio", kwargs)

    @patch("app.db.upsert_lead", new_callable=AsyncMock)
    async def test_process_reply_passes_extracted_values(self, mock_upsert_lead):
        history = [
            {"role": "user", "content": "Mi nombre es Miguel Gonzales"}
        ]
        
        await leads.process_reply(
            wa_id="wa-123",
            reply="Mucho gusto Miguel",
            history=history,
            bot_id=1
        )
        
        mock_upsert_lead.assert_called_once()
        args, kwargs = mock_upsert_lead.call_args
        self.assertEqual(kwargs.get("nombre"), "Miguel Gonzales")
        self.assertNotIn("negocio", kwargs)


if __name__ == "__main__":
    unittest.main()
