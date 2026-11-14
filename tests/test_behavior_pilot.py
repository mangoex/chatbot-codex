"""Comportamientos observables del webhook y de la API.

WhatsApp, Meta y el modelo están doblados. La base de estos casos es un
directorio en memoria: lo que se afirma es la respuesta HTTP, el texto que
recibiría WhatsApp y los mensajes que quedan guardados. El directorio de
contactos no se llena con un mensaje entrante; esa unicidad vive en Postgres
(`tests/integration/test_contact_upsert.py`).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import bots, config, db, main, rate_limit, signature

BOT_ID = 77
PHONE_ID = "phone-ficticio-piloto"
WA_ID = "5215550199001"
TEXTO = "Hola, quiero información del servicio"
RESPUESTA = "Claro, con gusto te ayudo."
LLAVE = "llave-ficticia-piloto"


class _Memoria:
    def __init__(self) -> None:
        self.processed: set[str] = set()
        self.messages: list[dict] = []

    async def was_processed(self, message_id: str) -> bool:
        return message_id in self.processed

    async def mark_processed(self, message_id: str, bot_id: int | None = None) -> bool:
        if message_id in self.processed:
            return False
        self.processed.add(message_id)
        return True

    async def save_message(self, wa_id, role, content, bot_id=None, sync_chatwoot=True) -> None:
        self.messages.append(
            {"wa_id": wa_id, "role": role, "content": content, "bot_id": bot_id}
        )

    async def get_history(self, wa_id, limit, bot_id=None):
        filas = [
            {"role": item["role"], "content": item["content"]}
            for item in self.messages
            if item["wa_id"] == wa_id and item["bot_id"] == bot_id
        ]
        return filas[-limit:]

    async def get_active_bot_integration(self, bot_id, integration_type):
        return None

    async def cancel_follow_up(self, wa_id, bot_id) -> None:
        return None

    async def upsert_lead(self, *args, **kwargs) -> None:
        return None

    async def get_lead(self, *args, **kwargs):
        return {"qualification_status": "calificado"}


def _bot() -> bots.BotContext:
    return bots.BotContext(
        id=BOT_ID,
        client_id=1,
        slug="bot-piloto-ficticio",
        name="Bot Piloto",
        whatsapp_phone_number_id=PHONE_ID,
        whatsapp_access_token="token-ficticio-wa",
        display_phone_number="5215550100000",
        status="active",
    )


def _payload(message_id: str, text: str = TEXTO) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5215550100000",
                                "phone_number_id": PHONE_ID,
                            },
                            "contacts": [
                                {"profile": {"name": "Cliente Ficticio"}, "wa_id": WA_ID}
                            ],
                            "messages": [
                                {
                                    "from": WA_ID,
                                    "id": message_id,
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }


@pytest.fixture
def memoria(monkeypatch):
    store = _Memoria()
    enviados: list[dict] = []

    async def send_text(to_wa_id, body, phone_number_id=None, access_token=None, **kwargs):
        enviados.append(
            {
                "to": to_wa_id,
                "body": body,
                "phone_number_id": phone_number_id,
                "access_token": access_token,
            }
        )
        return {"messages": [{"id": "wamid.salida.ficticia"}]}

    async def complete(*args, **kwargs):
        return RESPUESTA

    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "was_processed", store.was_processed)
    monkeypatch.setattr(db, "mark_processed", store.mark_processed)
    monkeypatch.setattr(db, "save_message", store.save_message)
    monkeypatch.setattr(db, "get_history", store.get_history)
    monkeypatch.setattr(db, "get_active_bot_integration", store.get_active_bot_integration)
    monkeypatch.setattr(db, "cancel_follow_up", store.cancel_follow_up)
    monkeypatch.setattr(db, "upsert_lead", store.upsert_lead)
    monkeypatch.setattr(db, "get_lead", store.get_lead)
    monkeypatch.setattr(bots, "resolve_by_phone_number_id", _resolver)
    monkeypatch.setattr(main.openai_client, "complete", complete)
    monkeypatch.setattr(main.whatsapp_client, "send_text", send_text)
    monkeypatch.setattr(config, "META_APP_SECRET", "")
    monkeypatch.setattr(config, "WHATSAPP_SIGNATURE_STRICT", False)
    monkeypatch.setattr(config, "ADMIN_PHONE_NUMBERS", ())
    signature._warned_modes.clear()
    main._processing_message_ids.clear()
    return store, enviados


async def _resolver(phone_number_id):
    if phone_number_id == PHONE_ID:
        return _bot()
    return None


def _post(cliente: TestClient, message_id: str, headers: dict | None = None):
    return cliente.post(
        "/webhooks/whatsapp",
        content=json.dumps(_payload(message_id)),
        headers={"Content-Type": "application/json", **(headers or {})},
    )


def test_un_mensaje_nuevo_guarda_la_conversacion_y_envia_la_respuesta(memoria, caplog):
    store, enviados = memoria
    cliente = TestClient(main.app)
    with caplog.at_level("ERROR"):
        respuesta = _post(cliente, "wamid.piloto.nuevo")

    assert "Error procesando mensajes entrantes" not in caplog.text
    assert respuesta.status_code == 200
    assert respuesta.json()["status"] == "received"
    assert [item["content"] for item in store.messages] == [TEXTO, RESPUESTA]
    assert enviados == [
        {
            "to": WA_ID,
            "body": RESPUESTA,
            "phone_number_id": PHONE_ID,
            "access_token": "token-ficticio-wa",
        }
    ]


def test_el_mismo_mensaje_no_se_responde_dos_veces(memoria, caplog):
    store, enviados = memoria
    cliente = TestClient(main.app)
    with caplog.at_level("ERROR"):
        primera = _post(cliente, "wamid.piloto.duplicado")
        segunda = _post(cliente, "wamid.piloto.duplicado")

    assert "Error procesando mensajes entrantes" not in caplog.text
    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert len(enviados) == 1
    assert [item["role"] for item in store.messages] == ["user", "assistant"]


def test_firma_invalida_con_verificacion_estricta_no_procesa_el_mensaje(memoria, monkeypatch):
    store, enviados = memoria
    monkeypatch.setattr(config, "META_APP_SECRET", "")
    monkeypatch.setattr(config, "WHATSAPP_SIGNATURE_STRICT", True)
    cliente = TestClient(main.app)
    respuesta = _post(
        cliente,
        "wamid.piloto.firma",
        headers={"X-Hub-Signature-256": "sha256=" + "0" * 64},
    )

    assert respuesta.status_code == 403
    assert store.messages == []
    assert enviados == []


def test_con_routing_v2_apagado_la_regla_anterior_sigue_reenviando(memoria, monkeypatch, caplog):
    """forward_all es el camino legado. Con el flag apagado no entra el contrato nuevo."""
    _store, enviados = memoria
    reenvios: list[tuple] = []

    async def reenviar(webhook_url, payload, auth_token):
        reenvios.append((webhook_url, payload, auth_token))
        return True

    async def integracion(bot_id, integration_type):
        if integration_type == "routing_rules":
            return {
                "id": 9,
                "config": {
                    "forward_all": True,
                    "webhook_url": "https://externo.ejemplo/webhook",
                    "save_history": False,
                },
            }
        return None

    async def secretos(_integration_id):
        return {"webhook_auth_token": ""}

    monkeypatch.setattr(db, "get_active_bot_integration", integracion)
    monkeypatch.setattr(db, "get_integration_secret_values", secretos)
    monkeypatch.setattr(main, "forward_payload_to_external_webhook", reenviar)
    cliente = TestClient(main.app)

    assert db._pool is None
    with caplog.at_level("ERROR"):
        respuesta = _post(cliente, "wamid.piloto.legado")

    assert "Error procesando mensajes entrantes" not in caplog.text
    assert respuesta.status_code == 200
    assert len(reenvios) == 1
    assert reenvios[0][0] == "https://externo.ejemplo/webhook"
    assert reenvios[0][1]["entry"][0]["changes"][0]["value"]["messages"][0]["id"] == "wamid.piloto.legado"
    assert enviados == []


def test_api_sin_llave_valida_responde_401(monkeypatch):
    rate_limit.reset()
    monkeypatch.setattr(bots, "resolve_by_bot_id", _resolver_bot)
    monkeypatch.setattr(db, "get_active_bot_integration", _sin_integracion)
    cliente = TestClient(main.app)

    sin_llave = cliente.get(f"/api/v1/bots/{BOT_ID}/ping")
    llave_incorrecta = cliente.get(
        f"/api/v1/bots/{BOT_ID}/ping",
        headers={"X-API-Key": "llave-ficticia-incorrecta"},
    )

    assert sin_llave.status_code == 401
    assert llave_incorrecta.status_code == 401
    assert "Bot Piloto" not in sin_llave.text
    assert "Bot Piloto" not in llave_incorrecta.text
    assert sin_llave.json().get("status") != "ok"
    assert llave_incorrecta.json().get("status") != "ok"


async def _resolver_bot(bot_id):
    if bot_id == BOT_ID:
        return _bot()
    return None


async def _sin_integracion(*_args, **_kwargs):
    return None
