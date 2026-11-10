"""Flags de firma, documentación y límite. El default conserva el comportamiento actual."""
from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi.testclient import TestClient

from unittest.mock import AsyncMock

from app import bots, config, db, main, rate_limit, signature

CUERPO = b'{"object":"whatsapp_business_account","entry":[]}'


def setup_function():
    signature._warned_modes.clear()
    rate_limit.reset()


def _firma(secreto: str, cuerpo: bytes = CUERPO) -> str:
    return "sha256=" + hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()


def test_sin_secreto_y_flag_apagado_acepta_y_avisa(caplog, monkeypatch):
    monkeypatch.setattr(config, "META_APP_SECRET", "")
    monkeypatch.setattr(config, "WHATSAPP_SIGNATURE_STRICT", False)
    with caplog.at_level(logging.WARNING, logger="whatsapp-bot"):
        assert signature.verify(None, CUERPO) is True
    assert "META_APP_SECRET no está configurado" in caplog.text
    assert "se acepta" in caplog.text


def test_sin_secreto_y_flag_encendido_rechaza_y_avisa(caplog, monkeypatch):
    monkeypatch.setattr(config, "META_APP_SECRET", "")
    monkeypatch.setattr(config, "WHATSAPP_SIGNATURE_STRICT", True)
    with caplog.at_level(logging.WARNING, logger="whatsapp-bot"):
        assert signature.verify(None, CUERPO) is False
    assert "rechaza el webhook" in caplog.text


def test_con_secreto_la_firma_sigue_siendo_obligatoria_aunque_el_flag_este_apagado(monkeypatch):
    monkeypatch.setattr(config, "META_APP_SECRET", "secreto-ficticio-meta")
    monkeypatch.setattr(config, "WHATSAPP_SIGNATURE_STRICT", False)
    assert signature.verify(None, CUERPO) is False
    assert signature.verify("sha256=0000", CUERPO) is False
    assert signature.verify(_firma("secreto-ficticio-meta"), CUERPO) is True


def test_webhook_http_respeta_el_flag(monkeypatch):
    monkeypatch.setattr(config, "META_APP_SECRET", "")
    monkeypatch.setattr(config, "WHATSAPP_SIGNATURE_STRICT", False)
    cliente = TestClient(main.app)
    abierto = cliente.post("/webhooks/whatsapp", content=CUERPO, headers={"Content-Type": "application/json"})
    assert abierto.status_code == 200

    monkeypatch.setattr(config, "WHATSAPP_SIGNATURE_STRICT", True)
    cerrado = cliente.post("/webhooks/whatsapp", content=CUERPO, headers={"Content-Type": "application/json"})
    assert cerrado.status_code == 403

    monkeypatch.setattr(config, "META_APP_SECRET", "secreto-ficticio-meta")
    firmado = cliente.post(
        "/webhooks/whatsapp",
        content=CUERPO,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": _firma("secreto-ficticio-meta")},
    )
    assert firmado.status_code == 200


def test_docs_apagadas_por_default_y_encendidas_con_el_flag(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_API_DOCS", False)
    cliente = TestClient(main.app)
    for ruta in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(ruta).status_code == 404

    monkeypatch.setattr(config, "ENABLE_API_DOCS", True)
    assert cliente.get("/openapi.json").status_code == 200
    assert cliente.get("/openapi.json").json()["openapi"]
    assert cliente.get("/docs").status_code == 200
    assert cliente.get("/redoc").status_code == 200


def test_limite_por_ip_y_por_llave_y_flag_apagado(monkeypatch):
    bot = bots.BotContext(
        id=1,
        client_id=1,
        slug="bot-ficticio",
        name="Bot Ficticio",
        whatsapp_phone_number_id="phone-ficticio",
        whatsapp_access_token="token-ficticio",
    )
    monkeypatch.setattr(bots, "resolve_by_bot_id", AsyncMock(return_value=bot))
    monkeypatch.setattr(db, "get_active_bot_integration", AsyncMock(return_value=None))
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(config, "RATE_LIMIT_IP_PER_MINUTE", 100)
    monkeypatch.setattr(config, "RATE_LIMIT_KEY_PER_MINUTE", 2)
    cliente = TestClient(main.app)
    headers = {"X-API-Key": "llave-ficticia-uno"}
    assert cliente.get("/api/v1/bots/1/ping", headers=headers).status_code == 401
    assert cliente.get("/api/v1/bots/1/ping", headers=headers).status_code == 401
    assert cliente.get("/api/v1/bots/1/ping", headers=headers).status_code == 429
    otra = cliente.get("/api/v1/bots/1/ping", headers={"X-API-Key": "llave-ficticia-dos"})
    assert otra.status_code == 401

    rate_limit.reset()
    monkeypatch.setattr(config, "RATE_LIMIT_IP_PER_MINUTE", 2)
    monkeypatch.setattr(config, "RATE_LIMIT_KEY_PER_MINUTE", 100)
    assert cliente.get("/api/v1/bots/1/ping").status_code == 401
    assert cliente.get("/api/v1/bots/1/ping").status_code == 401
    bloqueada = cliente.get("/api/v1/bots/1/ping")
    assert bloqueada.status_code == 429
    assert bloqueada.headers["retry-after"] == "60"

    rate_limit.reset()
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(config, "RATE_LIMIT_IP_PER_MINUTE", 1)
    for _ in range(4):
        assert cliente.get("/api/v1/bots/1/ping").status_code == 401


def test_el_webhook_de_meta_no_entra_al_limite_y_el_retorno_si(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(config, "RATE_LIMIT_IP_PER_MINUTE", 1)
    monkeypatch.setattr(config, "META_APP_SECRET", "")
    monkeypatch.setattr(config, "WHATSAPP_SIGNATURE_STRICT", False)
    cliente = TestClient(main.app)
    primero = cliente.post("/webhooks/whatsapp", content=CUERPO)
    segundo = cliente.post("/webhooks/whatsapp", content=CUERPO)
    assert primero.status_code == 200
    assert segundo.status_code == 200

    rate_limit.reset()
    monkeypatch.setattr(db, "get_active_bot_integration", AsyncMock(return_value=None))
    retorno = cliente.post("/webhooks/grok/1", json={"text": "hola"})
    otra_vez = cliente.post("/webhooks/grok/1", json={"text": "hola"})
    assert retorno.status_code != 429
    assert otra_vez.status_code == 429
