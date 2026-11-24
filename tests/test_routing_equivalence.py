"""El camino traducido elige el mismo responsable que el legado, con datos ficticios."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.routing_decision import (
    Assignment,
    BotSnapshot,
    IntegrationView,
    decide,
    legacy_handler,
    materialize,
    sign_body,
    translate,
)

ADMIN = "5216671000001"
ADMIN_CANONICO = "526671000001"
CLIENTE = "5216672000002"
EQUIPO = "5216673000003"
EQUIPO_CORTO = "6673000003"


def view(identifier: int, kind: str, enabled: bool = True, **config) -> IntegrationView:
    return IntegrationView(identifier, kind, enabled, config)


def ambos(snapshot: BotSnapshot, wa_id: str) -> tuple[str, str]:
    legado = legacy_handler(snapshot, wa_id)
    reglas, conexiones = materialize(*translate(snapshot))
    nuevo = decide(reglas, conexiones, wa_id).handler
    return legado, nuevo


CASOS = []


def caso(nombre: str, snapshot: BotSnapshot, esperado: dict[str, str]) -> None:
    CASOS.append((nombre, snapshot, esperado))


caso(
    "politica: admin Grok, default KiwiPOS, equipo al webhook",
    BotSnapshot(
        1,
        attention=view(1, "attention_policy", version=1, default_handler="external_agent", admin_grok_enabled=True, admin_phone_numbers=[ADMIN]),
        grok=view(2, "grok_bot", webhook_url="https://grok.example/hook", handle_inbound=False, allow_campaigns=True),
        external=view(3, "external_agent", webhook_url="https://kiwi.example/hook", handle_inbound=True),
        routing=view(4, "routing_rules", forward_all=True, webhook_url="https://app.example/hook", rules=[{"action": "forward_and_bypass", "webhook_url": "https://app.example/equipo", "phone_numbers": [EQUIPO]}]),
    ),
    {ADMIN: "grok_bot", ADMIN_CANONICO: "grok_bot", EQUIPO: "routing_webhook", CLIENTE: "external_agent"},
)
caso(
    "politica apagada en admin y default Asistto, aunque forward_all siga guardado",
    BotSnapshot(
        1,
        attention=view(1, "attention_policy", version=1, default_handler="asistto", admin_grok_enabled=False, admin_phone_numbers=[ADMIN]),
        routing=view(4, "routing_rules", forward_all=True, webhook_url="https://app.example/hook"),
        grok=view(2, "grok_bot", webhook_url="https://grok.example/hook", handle_inbound=True),
    ),
    {ADMIN: "asistto", CLIENTE: "asistto"},
)
caso(
    "sin politica, forward_all se lleva a todos",
    BotSnapshot(1, routing=view(4, "routing_rules", forward_all=True, webhook_url="https://app.example/hook", save_history=False)),
    {ADMIN: "routing_webhook", CLIENTE: "routing_webhook", EQUIPO: "routing_webhook"},
)
caso(
    "sin politica, el equipo queda en silencio y el cliente en Asistto",
    BotSnapshot(1, routing=view(4, "routing_rules", phone_numbers=[EQUIPO], webhook_url="")),
    {EQUIPO: "silence", EQUIPO_CORTO: "silence", CLIENTE: "asistto"},
)
caso(
    "sin politica, el equipo va al webhook y el resto a KiwiPOS, Grok no gana",
    BotSnapshot(
        1,
        routing=view(4, "routing_rules", rules=[{"action": "forward_and_bypass", "webhook_url": "https://app.example/equipo", "phone_numbers": [EQUIPO]}]),
        external=view(3, "external_agent", webhook_url="https://kiwi.example/hook", handle_inbound=True),
        grok=view(2, "grok_bot", webhook_url="https://grok.example/hook", handle_inbound=True, allow_campaigns=False),
    ),
    {EQUIPO: "routing_webhook", CLIENTE: "external_agent"},
)
caso(
    "solo Grok con handle_inbound",
    BotSnapshot(1, grok=view(2, "grok_bot", webhook_url="https://grok.example/hook", handle_inbound=True)),
    {CLIENTE: "grok_bot"},
)
caso(
    "Grok con handle_inbound en false se queda en Asistto",
    BotSnapshot(1, grok=view(2, "grok_bot", webhook_url="https://grok.example/hook", handle_inbound=False)),
    {CLIENTE: "asistto"},
)
caso(
    "KiwiPOS apagado en inbound y Grok encendido",
    BotSnapshot(
        1,
        external=view(3, "external_agent", webhook_url="https://kiwi.example/hook", handle_inbound=False),
        grok=view(2, "grok_bot", webhook_url="https://grok.example/hook", handle_inbound=True),
    ),
    {CLIENTE: "grok_bot"},
)
caso(
    "sin integraciones",
    BotSnapshot(1),
    {CLIENTE: "asistto"},
)
caso(
    "politica sin version se trata como legado",
    BotSnapshot(1, attention=view(1, "attention_policy", default_handler="asistto"), grok=view(2, "grok_bot", webhook_url="https://grok.example/hook", handle_inbound=True)),
    {CLIENTE: "grok_bot"},
)


def test_equivalencia_de_los_cuatro_modos(capsys):
    lineas = ["caso | contacto | legado | nuevo"]
    for nombre, snapshot, esperado in CASOS:
        for wa_id, handler in esperado.items():
            legado, nuevo = ambos(snapshot, wa_id)
            lineas.append(f"{nombre} | {wa_id} | {legado} | {nuevo}")
            assert legado == handler, lineas[-1]
            assert nuevo == legado, lineas[-1]
    print("\n".join(lineas))
    captured = capsys.readouterr()
    assert "politica: admin Grok" in captured.out


def test_etiqueta_y_relevo_no_cambian_la_equivalencia_base():
    snapshot = BotSnapshot(1, grok=view(2, "grok_bot", webhook_url="https://grok.example/hook", handle_inbound=False))
    reglas, conexiones = materialize(*translate(snapshot))
    reglas.append(
        type(reglas[0])(
            position=5,
            match_kind="tag",
            match_value="vip",
            handler="external_agent",
            connection_id=None,
            applies_to="text",
            record_history=True,
            webhook_url="https://kiwi.example/vip",
        )
    )
    assert decide(reglas, conexiones, CLIENTE, tags={"vip"}).handler == "external_agent"
    assert decide(reglas, conexiones, CLIENTE, tags=set()).handler == "asistto"
    futuro = datetime.now(timezone.utc) + timedelta(hours=1)
    pasado = datetime.now(timezone.utc) - timedelta(minutes=1)
    tomado = Assignment("connection", 1, futuro)
    # La conexión 1 de esta foto es Grok, aunque el default sea Asistto.
    assert decide(reglas, conexiones, CLIENTE, assignment=tomado).handler == "grok_bot"
    assert decide(reglas, conexiones, CLIENTE, assignment=Assignment("connection", 1, pasado)).handler == "asistto"


def test_la_firma_hmac_cubre_timestamp_y_cuerpo_y_no_mete_tokens():
    firma = sign_body("secreto-ficticio", b'{"hola":1}', "1700000000")
    assert firma.startswith("sha256=")
    assert len(firma) == len("sha256=") + 64
    from app.routing_decision import Decision, LiveConnection, build_outbound

    cuerpo = build_outbound(
        bot_id=1,
        wa_id=CLIENTE,
        message_id="wamid.ficticio",
        message_type="text",
        text="dos tacos",
        name="Cliente Ficticio",
        tags=["demo"],
        decision=Decision("external_agent", "default", 1, "https://kiwi.example/hook", "text", True),
        connection=LiveConnection(1, "kiwipos", True, "https://kiwi.example/hook", False),
    )
    plano = str(cuerpo)
    assert "access_token" not in plano
    assert "EAA" not in plano
    assert cuerpo["event"] == "message_received"
    assert cuerpo["connection"]["preset"] == "kiwipos"
