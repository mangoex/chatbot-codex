import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

# Mock asyncpg and cryptography before imports
import sys
import types
sys.modules.setdefault("asyncpg", types.SimpleNamespace(Pool=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))
sys.modules.setdefault("httpx", types.SimpleNamespace(HTTPStatusError=Exception, AsyncClient=object))
sys.modules.setdefault("cryptography", types.SimpleNamespace())
sys.modules.setdefault("cryptography.fernet", types.SimpleNamespace(Fernet=lambda key: None, InvalidToken=Exception))

from app import calendar_client, escalations

class TestClientPanelFeatures:
    
    @pytest.mark.asyncio
    @patch("app.db.get_bot_skill")
    async def test_business_hours_validation(self, mock_get_skill):
        # Mock business hours config: open Mon-Fri 09:00-18:00, Sat closed
        mock_get_skill.return_value = {
            "enabled": True,
            "config": {
                "lunes": {"open": True, "start": "09:00", "end": "18:00"},
                "martes": {"open": True, "start": "09:00", "end": "18:00"},
                "miercoles": {"open": True, "start": "09:00", "end": "18:00"},
                "jueves": {"open": True, "start": "09:00", "end": "18:00"},
                "viernes": {"open": True, "start": "09:00", "end": "18:00"},
                "sabado": {"open": False, "start": "09:00", "end": "13:00"},
                "domingo": {"open": False, "start": "00:00", "end": "00:00"}
            }
        }
        
        # Test Case 1: Monday 10:00 AM (Valid)
        # Weekday: Monday = 0
        dt_monday_ok = datetime(2026, 6, 1, 10, 0, tzinfo=ZoneInfo("America/Chihuahua"))
        is_ok, err = await calendar_client._is_within_business_hours(1, dt_monday_ok)
        assert is_ok is True
        assert err == ""
        
        # Test Case 2: Monday 9:00 PM (Invalid - Outside Hours)
        dt_monday_late = datetime(2026, 6, 1, 21, 0, tzinfo=ZoneInfo("America/Chihuahua"))
        is_ok, err = await calendar_client._is_within_business_hours(1, dt_monday_late)
        assert is_ok is False
        assert "fuera de nuestra jornada" in err.lower()
        
        # Test Case 3: Saturday 11:00 AM (Invalid - Day Closed)
        # Weekday: Saturday = 5
        dt_saturday = datetime(2026, 6, 6, 11, 0, tzinfo=ZoneInfo("America/Chihuahua"))
        is_ok, err = await calendar_client._is_within_business_hours(1, dt_saturday)
        assert is_ok is False
        assert "no laboramos los días sabado" in err.lower()

    @pytest.mark.asyncio
    @patch("app.db.get_bot_skill")
    async def test_custom_escalation_rules(self, mock_get_skill):
        # Mock escalation config: keywords triggers enabled
        mock_get_skill.return_value = {
            "enabled": True,
            "config": {
                "keywords": ["hablar con miguel", "reclamar reembolso"],
                "escalate_on_media": True
            }
        }
        
        # Test Case 1: normal text - no escalation
        reason = await escalations.detect_reason("hola, me gustaria agendar una cita", "con gusto", "text", bot_id=1)
        assert reason is None
        
        # Test Case 2: trigger custom keyword "hablar con miguel"
        reason = await escalations.detect_reason("quiero hablar con miguel por favor", "si claro", "text", bot_id=1)
        assert reason is not None
        assert reason[0] == "cliente_solicito_humano"
        assert "palabra clave personalizada" in reason[1].lower()
        
        # Test Case 3: media escalation with toggle off
        mock_get_skill.return_value = {
            "enabled": True,
            "config": {
                "keywords": [],
                "escalate_on_media": False
            }
        }
        reason = await escalations.detect_reason("", "", "image", bot_id=1)
        assert reason is None
        
        # Test Case 4: media escalation with toggle on (default)
        mock_get_skill.return_value = {
            "enabled": True,
            "config": {
                "keywords": [],
                "escalate_on_media": True
            }
        }
        reason = await escalations.detect_reason("", "", "image", bot_id=1)
        assert reason is not None
        assert reason[0] == "media_recibida"
