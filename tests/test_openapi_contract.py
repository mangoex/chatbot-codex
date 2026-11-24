"""Comprueba respuestas vivas contra el OpenAPI generado por la app.

No cambia rutas. El handshake de Meta responde text/plain y el esquema
generado lo anuncia como JSON vacío: esa brecha queda nombrada y no se
“arregla” en el arnés, porque cambiar el contrato publicado es otro cambio.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app import db, main

# (método, ruta OpenAPI, status) cuya respuesta real no es el JSON anunciado.
BRECHAS_CONOCIDAS = {
    ("get", "/webhooks/whatsapp", 200),
    ("get", "/webhook", 200),
}


def _resolver(nodo, spec, profundidad=0):
    if profundidad > 30:
        raise AssertionError("Referencia OpenAPI demasiado profunda")
    if isinstance(nodo, dict):
        if set(nodo) == {"$ref"}:
            ref = nodo["$ref"]
            if not ref.startswith("#/"):
                raise AssertionError(f"Referencia externa no soportada: {ref}")
            actual = spec
            for parte in ref[2:].split("/"):
                actual = actual[parte]
            return _resolver(actual, spec, profundidad + 1)
        return {clave: _resolver(valor, spec, profundidad + 1) for clave, valor in nodo.items()}
    if isinstance(nodo, list):
        return [_resolver(item, spec, profundidad + 1) for item in nodo]
    return nodo


def validar_respuesta(spec: dict, metodo: str, ruta: str, response) -> None:
    operacion = spec["paths"][ruta][metodo]
    codigo = str(response.status_code)
    assert codigo in operacion["responses"], f"{metodo} {ruta} no documenta {codigo}"
    contenido = (operacion["responses"][codigo].get("content") or {})
    tipo = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if (metodo, ruta, response.status_code) in BRECHAS_CONOCIDAS and tipo != "application/json":
        return
    assert "application/json" in contenido, f"{metodo} {ruta} {codigo} no documenta JSON"
    esquema = _resolver(contenido["application/json"].get("schema") or {}, spec)
    Draft202012Validator(esquema).validate(response.json())


def test_salud_y_webhook_cumplen_el_esquema(monkeypatch):
    async def sano():
        return True

    monkeypatch.setattr(db, "check_health", sano)
    monkeypatch.setattr(main.config, "VERIFY_TOKEN", "token-ficticio-webhook")
    monkeypatch.setattr(main.config, "META_APP_SECRET", "")
    spec = main.app.openapi()
    cliente = TestClient(main.app)

    salud = cliente.get("/health")
    validar_respuesta(spec, "get", "/health", salud)
    assert salud.json()["status"] == "ok"

    aceptado = cliente.post(
        "/webhooks/whatsapp",
        json={"object": "whatsapp_business_account", "entry": []},
    )
    validar_respuesta(spec, "post", "/webhooks/whatsapp", aceptado)

    reto = cliente.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-ficticio-webhook",
            "hub.challenge": "reto-ficticio-123",
        },
    )
    validar_respuesta(spec, "get", "/webhooks/whatsapp", reto)
    assert reto.text == "reto-ficticio-123"

    invalido = cliente.get("/api/v1/bots/no-es-numero/ping")
    validar_respuesta(spec, "get", "/api/v1/bots/{bot_id}/ping", invalido)
    assert invalido.status_code == 422


def test_el_documento_incluye_las_rutas_publicas_del_webhook():
    rutas = main.app.openapi()["paths"]
    for ruta in ("/health", "/webhook", "/webhooks/whatsapp", "/api/v1/bots/{bot_id}/ping"):
        assert ruta in rutas
