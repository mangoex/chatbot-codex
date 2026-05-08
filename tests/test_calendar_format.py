import sys
import types
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
sys.modules.setdefault(
    "httpx",
    types.SimpleNamespace(HTTPStatusError=Exception, AsyncClient=object),
)
sys.modules.setdefault("cryptography", types.SimpleNamespace())
sys.modules.setdefault(
    "cryptography.fernet",
    types.SimpleNamespace(
        Fernet=lambda key: None,
        InvalidToken=Exception,
    ),
)

from app import calendar_client


class CalendarFormatTests(unittest.TestCase):
    def test_format_dt_uses_natural_spanish_date(self):
        dt = datetime(2026, 5, 11, 10, 0, tzinfo=ZoneInfo("America/Chihuahua"))

        self.assertEqual(
            calendar_client._format_dt(dt),
            "lunes 11 de mayo de 2026 a las 10:00",
        )


if __name__ == "__main__":
    unittest.main()
