"""Retorno único y permiso de campañas. No usa Postgres real."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app import bots, db, main, routing_v2


def test_el_retorno_nuevo_rechaza_secreto_en_la_query():
    cliente = TestClient(main.app)
    respuesta = cliente.post("/api/v1/bots/1/reply?secret=no-va-en-la-url", json={"to": "5215550100099", "text": "hola"})
    assert respuesta.status_code == 400
    assert "URL" in respuesta.json()["detail"]


def test_el_retorno_nuevo_responde_409_si_el_flag_esta_apagado(monkeypatch):
    monkeypatch.setattr(db, "is_routing_v2_enabled", AsyncMock(return_value=False))
    cliente = TestClient(main.app)
    respuesta = cliente.post(
        "/api/v1/bots/1/reply",
        json={"to": "5215550100099", "text": "hola"},
        headers={"X-API-Key": "llave-ficticia"},
    )
    assert respuesta.status_code == 409


def test_campanas_siguen_en_v1_y_respetan_el_permiso_de_la_conexion(monkeypatch):
    monkeypatch.setattr(db, "is_routing_v2_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(routing_v2, "campaigns_allowed", AsyncMock(return_value=False))
    bot = bots.BotContext(1, 1, "bot-ficticio", "Bot Ficticio", "phone", "token-ficticio")
    monkeypatch.setattr(bots, "resolve_by_bot_id", AsyncMock(return_value=bot))
    monkeypatch.setattr(db, "get_active_bot_integration", AsyncMock(return_value={"id": 1, "config": {"allow_campaigns": True}}))
    monkeypatch.setattr(db, "get_integration_secret_values", AsyncMock(return_value={"webhook_secret": "enc"}))
    monkeypatch.setattr("app.secure_store.decrypt_secret", lambda _value: "llave-ficticia")
    cliente = TestClient(main.app)
    respuesta = cliente.post(
        "/api/v1/bots/1/campaigns",
        json={"name": "Campaña ficticia", "template_name": "aviso", "audience": {"type": "recipients", "recipients": [{"wa_id": "5215550100099"}]}},
        headers={"X-API-Key": "llave-ficticia"},
    )
    assert respuesta.status_code == 403
    assert "campañas" in respuesta.json()["detail"]


def test_con_flag_encendido_la_llave_de_conexion_puede_contestar(monkeypatch):
    monkeypatch.setattr(db, "is_routing_v2_enabled", AsyncMock(return_value=True))
    conexion = {"id": 7, "preset": "kiwipos", "allow_campaigns": False, "handoff_timeout_minutes": 30, "encrypted_value": "enc"}
    monkeypatch.setattr(routing_v2, "_connection_from_headers", AsyncMock(return_value=conexion))
    monkeypatch.setattr(routing_v2, "_execute_reply", AsyncMock(return_value={"status": "sent"}))
    cliente = TestClient(main.app)
    respuesta = cliente.post(
        "/api/v1/bots/1/reply",
        json={"to": "5215550100099", "text": "listo", "action": "reply"},
        headers={"Authorization": "Bearer llave-ficticia"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "sent"
    routing_v2._execute_reply.assert_awaited()


async def test_tomar_y_devolver_no_exigen_texto(monkeypatch):
    request = MagicMock()
    request.query_params = {}
    monkeypatch.setattr(db, "is_routing_v2_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(routing_v2, "_connection_from_headers", AsyncMock(return_value={"id": 7, "preset": "grok_bot", "handoff_timeout_minutes": 15}))
    monkeypatch.setattr(routing_v2, "_execute_reply", AsyncMock(return_value={"status": "taken"}))
    from app.api import ReplyInput

    resultado = await routing_v2.handle_public_reply(1, ReplyInput(to="5215550100099", action="takeover"), request)
    assert resultado["status"] == "taken"
