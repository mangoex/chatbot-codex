"""Escenarios ejecutables del webhook de WhatsApp. No abren Postgres."""
from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, scenarios, then, when
from pytest_bdd.parsers import parse

from app import config, main

scenarios("../../features/webhook_whatsapp.feature")

pytestmark = pytest.mark.bdd

CUERPO_VACIO = b'{"object":"whatsapp_business_account","entry":[]}'


@pytest.fixture
def ctx():
    return {}


@pytest.fixture
def cliente(monkeypatch):
    async def _noop(*_args, **_kwargs):
        return None

    # El TestClient no entra al lifespan: ahí se abre el pool y arrancan
    # tareas de fondo. El contrato del webhook se prueba sin esa base.
    monkeypatch.setattr(main, "_process_inbound_messages_safe", _noop)
    monkeypatch.setattr(main, "_process_human_message_echoes", _noop)
    return TestClient(main.app)


@given(parse('el token de verificación "{token}"'))
def token_de_verificacion(token: str, monkeypatch):
    monkeypatch.setattr(config, "VERIFY_TOKEN", token)


@given("que META_APP_SECRET no está configurado")
def sin_secreto_de_aplicacion(monkeypatch):
    monkeypatch.setattr(config, "META_APP_SECRET", "")


@given(parse('el secreto de aplicación "{secreto}"'))
def con_secreto_de_aplicacion(secreto: str, monkeypatch):
    monkeypatch.setattr(config, "META_APP_SECRET", secreto)


@when(parse('Meta consulta el webhook con el reto "{reto}"'))
def consulta_con_token_configurado(reto: str, cliente: TestClient, ctx: dict):
    ctx["response"] = cliente.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": config.VERIFY_TOKEN,
            "hub.challenge": reto,
        },
    )


@when(parse('Meta consulta el webhook con el token "{token}" y el reto "{reto}"'))
def consulta_con_token_explicito(token: str, reto: str, cliente: TestClient, ctx: dict):
    ctx["response"] = cliente.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": token,
            "hub.challenge": reto,
        },
    )


def _post_evento(cliente: TestClient, ctx: dict, firma: str | None) -> None:
    headers = {"Content-Type": "application/json"}
    if firma is not None:
        headers["X-Hub-Signature-256"] = firma
    ctx["response"] = cliente.post("/webhooks/whatsapp", content=CUERPO_VACIO, headers=headers)


@when("Meta entrega un evento de mensajes vacío")
def entrega_sin_firma(cliente: TestClient, ctx: dict):
    _post_evento(cliente, ctx, None)


@when("Meta entrega un evento de mensajes vacío con firma válida")
def entrega_con_firma_valida(cliente: TestClient, ctx: dict):
    firma = "sha256=" + hmac.new(
        config.META_APP_SECRET.encode("utf-8"),
        CUERPO_VACIO,
        hashlib.sha256,
    ).hexdigest()
    _post_evento(cliente, ctx, firma)


@when(parse('Meta entrega un evento de mensajes vacío con la firma "{firma}"'))
def entrega_con_firma_invalida(firma: str, cliente: TestClient, ctx: dict):
    _post_evento(cliente, ctx, firma)


@then(parse("el estado HTTP es {codigo:d}"))
def estado_http(codigo: int, ctx: dict):
    assert ctx["response"].status_code == codigo


@then(parse('el cuerpo de texto es "{texto}"'))
def cuerpo_de_texto(texto: str, ctx: dict):
    assert ctx["response"].text == texto


@then(parse('el JSON incluye status "{status}"'))
def json_incluye_status(status: str, ctx: dict):
    assert ctx["response"].json()["status"] == status
