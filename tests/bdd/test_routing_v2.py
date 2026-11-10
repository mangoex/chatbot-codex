"""Escenarios del ruteo unificado sobre la decisión pura."""
from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, then, when
from pytest_bdd.parsers import parse

from app.routing_decision import BotSnapshot, IntegrationView, decide, legacy_handler, materialize, translate

scenarios("../../features/routing_v2.feature")

pytestmark = pytest.mark.bdd


def _view(identifier: int, kind: str, **config) -> IntegrationView:
    return IntegrationView(identifier, kind, True, config)


@pytest.fixture
def ctx():
    return {}


@given("un bot ficticio con KiwiPOS y Grok atendiendo inbound")
def bot_con_ambos(ctx):
    ctx["snapshot"] = BotSnapshot(
        1,
        external=_view(3, "external_agent", webhook_url="https://kiwi.example/hook", handle_inbound=True),
        grok=_view(2, "grok_bot", webhook_url="https://grok.example/hook", handle_inbound=True),
    )


@given(parse('una política ficticia con administrador "{admin}" y default KiwiPOS'))
def politica(admin: str, ctx):
    ctx["snapshot"] = BotSnapshot(
        1,
        attention=_view(
            1,
            "attention_policy",
            version=1,
            default_handler="external_agent",
            admin_grok_enabled=True,
            admin_phone_numbers=[admin],
        ),
        external=_view(3, "external_agent", webhook_url="https://kiwi.example/hook"),
        grok=_view(2, "grok_bot", webhook_url="https://grok.example/hook", handle_inbound=False),
    )


@when(parse('el cliente "{wa_id}" escribe'))
def escribe(wa_id: str, ctx):
    snapshot = ctx["snapshot"]
    reglas, conexiones = materialize(*translate(snapshot))
    ctx["legado"] = legacy_handler(snapshot, wa_id)
    ctx["nuevo"] = decide(reglas, conexiones, wa_id).handler


@then(parse('el legado y el camino nuevo eligen "{handler}"'))
def eligen(handler: str, ctx):
    assert ctx["legado"] == handler
    assert ctx["nuevo"] == handler
