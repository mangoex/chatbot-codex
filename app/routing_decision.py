"""Decisión pura del ruteo. No abre base ni red.

El camino legado y la traducción a reglas viven juntos para poder compararlos
sin encender ROUTING_V2.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from app import attention_routing, bot_control

ORIGIN = "chg-012"
PRESETS = ("grok_bot", "kiwipos", "webhook_custom")
HANDLER_BY_PRESET = {
    "grok_bot": "grok_bot",
    "kiwipos": "external_agent",
    "webhook_custom": "routing_webhook",
}


@dataclass(frozen=True)
class IntegrationView:
    id: int
    type: str
    enabled: bool
    config: dict


@dataclass(frozen=True)
class BotSnapshot:
    bot_id: int
    attention: IntegrationView | None = None
    routing: IntegrationView | None = None
    grok: IntegrationView | None = None
    external: IntegrationView | None = None


@dataclass(frozen=True)
class ConnectionDraft:
    preset: str
    name: str
    enabled: bool
    webhook_url: str
    allow_campaigns: bool
    legacy_integration_type: str
    legacy_integration_id: int
    handoff_timeout_minutes: int = 1440


@dataclass(frozen=True)
class RuleDraft:
    position: int
    match_kind: str
    match_value: str
    handler: str
    applies_to: str
    record_history: bool
    webhook_url: str = ""
    legacy_integration_type: str | None = None


@dataclass(frozen=True)
class LiveConnection:
    id: int
    preset: str
    enabled: bool
    webhook_url: str
    allow_campaigns: bool
    handoff_timeout_minutes: int = 1440


@dataclass(frozen=True)
class LiveRule:
    position: int
    match_kind: str
    match_value: str
    handler: str
    connection_id: int | None
    applies_to: str
    record_history: bool
    webhook_url: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class Assignment:
    attendant: str
    connection_id: int | None
    handoff_until: datetime | None


@dataclass(frozen=True)
class Decision:
    handler: str
    reason: str
    connection_id: int | None
    webhook_url: str
    applies_to: str
    record_history: bool
    handoff_until: datetime | None = None


def _active(view: IntegrationView | None) -> IntegrationView | None:
    if view and view.enabled:
        return view
    return None


def _policy(snapshot: BotSnapshot) -> dict | None:
    attention = _active(snapshot.attention)
    if not attention:
        return None
    config = attention.config or {}
    if config.get("version") != 1:
        return None
    return config


def _routing_rules(config: dict) -> list[dict]:
    rules = list(config.get("rules") or [])
    if not rules and (config.get("webhook_url") or config.get("phone_numbers")):
        rules = [
            {
                "action": "forward_and_bypass",
                "webhook_url": config.get("webhook_url", ""),
                "phone_numbers": config.get("phone_numbers", []),
                "save_history": config.get("save_history", False),
            }
        ]
    return rules


def _forwards(view: IntegrationView | None) -> str:
    active = _active(view)
    if not active:
        return ""
    config = active.config or {}
    handle = config.get("handle_inbound")
    should = True if handle is None else bool(handle)
    url = str(config.get("webhook_url") or "").strip()
    if should and url:
        return url
    return ""


def legacy_handler(snapshot: BotSnapshot, wa_id: str) -> str:
    """Responsable que elige el pipeline actual, sin pausa ni relevo humano."""
    policy = _policy(snapshot)
    routing = _active(snapshot.routing)
    if policy is not None:
        routing_arg = {"config": routing.config or {}} if routing else None
        return attention_routing.select_route(policy, wa_id, routing_arg)[0]

    if routing:
        config = routing.config or {}
        webhook_url = str(config.get("webhook_url") or "").strip()
        rules = _routing_rules(config)
        if bool(config.get("forward_all")) and webhook_url:
            return "routing_webhook"
        for rule in rules:
            phones = rule.get("phone_numbers") or []
            if rule.get("action") == "forward_and_bypass" and bot_control.is_phone_in_list(wa_id, phones):
                url = str(rule.get("webhook_url") or "").strip()
                return "routing_webhook" if url else "silence"

    if _forwards(snapshot.external):
        return "external_agent"
    if _forwards(snapshot.grok):
        return "grok_bot"
    return "asistto"


def _campaigns(preset: str, config: dict) -> bool:
    if preset == "webhook_custom":
        return config.get("allow_campaigns") is True
    return config.get("allow_campaigns") is not False


def translate(snapshot: BotSnapshot) -> tuple[list[ConnectionDraft], list[RuleDraft]]:
    """Copia la configuración actual a conexiones y reglas equivalentes."""
    connections: list[ConnectionDraft] = []
    for view, preset, name in (
        (snapshot.grok, "grok_bot", "Grok Bot"),
        (snapshot.external, "kiwipos", "KiwiPOS"),
        (snapshot.routing, "webhook_custom", "Webhook"),
    ):
        if view is None:
            continue
        config = view.config or {}
        connections.append(
            ConnectionDraft(
                preset=preset,
                name=name,
                enabled=bool(view.enabled),
                webhook_url=str(config.get("webhook_url") or "").strip(),
                allow_campaigns=_campaigns(preset, config),
                legacy_integration_type=view.type,
                legacy_integration_id=int(view.id),
            )
        )

    rules: list[RuleDraft] = []
    position = 10
    policy = _policy(snapshot)
    routing = _active(snapshot.routing)
    routing_config = (routing.config or {}) if routing else {}

    if policy is not None:
        if policy.get("admin_grok_enabled"):
            for phone in policy.get("admin_phone_numbers") or []:
                rules.append(
                    RuleDraft(
                        position=position,
                        match_kind="admin_phone",
                        match_value=attention_routing.canonical_phone(str(phone)),
                        handler="grok_bot",
                        applies_to="all",
                        record_history=True,
                        webhook_url=str(((_active(snapshot.grok).config or {}).get("webhook_url") if _active(snapshot.grok) else "") or "").strip(),
                        legacy_integration_type="grok_bot",
                    )
                )
                position += 10
        for rule in _routing_rules(routing_config):
            if rule.get("action") != "forward_and_bypass":
                continue
            url = str(rule.get("webhook_url") or "").strip()
            handler = "routing_webhook" if url else "silence"
            for phone in rule.get("phone_numbers") or []:
                rules.append(
                    RuleDraft(
                        position=position,
                        match_kind="phone",
                        match_value=str(phone),
                        handler=handler,
                        applies_to="all",
                        record_history=bool(rule.get("save_history")),
                        webhook_url=url,
                        legacy_integration_type="routing_rules" if url else None,
                    )
                )
                position += 10
        default = str(policy.get("default_handler") or "asistto")
        rules.append(_default_rule(snapshot, position, default, applies_to="all", record_history=True))
        return connections, rules

    if routing and bool(routing_config.get("forward_all")) and str(routing_config.get("webhook_url") or "").strip():
        rules_src = _routing_rules(routing_config)
        record = bool(routing_config.get("save_history") or (rules_src and rules_src[0].get("save_history")))
        rules.append(
            RuleDraft(
                position=position,
                match_kind="default",
                match_value="",
                handler="routing_webhook",
                applies_to="all",
                record_history=record,
                webhook_url=str(routing_config.get("webhook_url") or "").strip(),
                legacy_integration_type="routing_rules",
            )
        )
        return connections, rules

    if routing:
        for rule in _routing_rules(routing_config):
            if rule.get("action") != "forward_and_bypass":
                continue
            url = str(rule.get("webhook_url") or "").strip()
            for phone in rule.get("phone_numbers") or []:
                rules.append(
                    RuleDraft(
                        position=position,
                        match_kind="phone",
                        match_value=str(phone),
                        handler="routing_webhook" if url else "silence",
                        applies_to="all",
                        record_history=bool(rule.get("save_history")),
                        webhook_url=url,
                        legacy_integration_type="routing_rules" if url else None,
                    )
                )
                position += 10

    external_url = _forwards(snapshot.external)
    grok_url = _forwards(snapshot.grok)
    if external_url:
        rules.append(_default_rule(snapshot, position, "external_agent", "text", True))
    elif grok_url:
        rules.append(_default_rule(snapshot, position, "grok_bot", "text", True))
    else:
        rules.append(RuleDraft(position, "default", "", "asistto", "text", False))
    return connections, rules


def _default_rule(snapshot: BotSnapshot, position: int, handler: str, applies_to: str, record_history: bool) -> RuleDraft:
    kind = {
        "grok_bot": "grok_bot",
        "external_agent": "external_agent",
        "routing_webhook": "routing_rules",
    }.get(handler)
    view = {"grok_bot": snapshot.grok, "external_agent": snapshot.external, "routing_rules": snapshot.routing}.get(kind or "")
    url = str(((view.config or {}).get("webhook_url") if view else "") or "").strip()
    return RuleDraft(
        position=position,
        match_kind="default",
        match_value="",
        handler=handler,
        applies_to=applies_to,
        record_history=record_history,
        webhook_url=url if handler != "asistto" else "",
        legacy_integration_type=kind,
    )


def materialize(
    connections: list[ConnectionDraft], rules: list[RuleDraft]
) -> tuple[list[LiveRule], dict[int, LiveConnection]]:
    """Asigna ids estables de prueba. La migración real usa los ids de Postgres."""
    by_type: dict[str, LiveConnection] = {}
    live: dict[int, LiveConnection] = {}
    for index, draft in enumerate(connections, start=1):
        item = LiveConnection(
            id=index,
            preset=draft.preset,
            enabled=draft.enabled,
            webhook_url=draft.webhook_url,
            allow_campaigns=draft.allow_campaigns,
            handoff_timeout_minutes=draft.handoff_timeout_minutes,
        )
        by_type[draft.legacy_integration_type] = item
        live[item.id] = item
    live_rules = []
    for rule in rules:
        connection = by_type.get(rule.legacy_integration_type or "")
        live_rules.append(
            LiveRule(
                position=rule.position,
                match_kind=rule.match_kind,
                match_value=rule.match_value,
                handler=rule.handler,
                connection_id=connection.id if connection and rule.handler not in {"asistto", "silence"} else None,
                applies_to=rule.applies_to,
                record_history=rule.record_history,
                webhook_url=rule.webhook_url,
            )
        )
    return live_rules, live


def decide(
    rules: list[LiveRule],
    connections: dict[int, LiveConnection],
    wa_id: str,
    tags: set[str] | None = None,
    assignment: Assignment | None = None,
    now: datetime | None = None,
) -> Decision:
    moment = now or datetime.now(timezone.utc)
    ordered = sorted(rules, key=lambda rule: rule.position)
    tagset = {tag.strip().lower() for tag in (tags or set()) if str(tag).strip()}

    for rule in ordered:
        if rule.enabled and rule.match_kind == "admin_phone":
            if attention_routing.canonical_phone(wa_id) == attention_routing.canonical_phone(rule.match_value):
                return _decision(rule, connections, "admin_phone")

    if assignment and assignment.attendant == "connection" and assignment.connection_id:
        fresh = assignment.handoff_until is None or _as_utc(assignment.handoff_until) > _as_utc(moment)
        connection = connections.get(assignment.connection_id)
        if fresh and connection and connection.enabled:
            return Decision(
                handler=HANDLER_BY_PRESET.get(connection.preset, "external_agent"),
                reason="handoff",
                connection_id=connection.id,
                webhook_url=connection.webhook_url,
                applies_to="all",
                record_history=True,
                handoff_until=assignment.handoff_until,
            )

    for rule in ordered:
        if rule.enabled and rule.match_kind == "phone" and bot_control.is_phone_in_list(wa_id, [rule.match_value]):
            return _decision(rule, connections, "phone")
    for rule in ordered:
        if rule.enabled and rule.match_kind == "tag" and rule.match_value.strip().lower() in tagset:
            return _decision(rule, connections, "tag")
    for rule in ordered:
        if rule.enabled and rule.match_kind == "default":
            return _decision(rule, connections, "default")
    return Decision("asistto", "default", None, "", "text", False)


def _decision(rule: LiveRule, connections: dict[int, LiveConnection], reason: str) -> Decision:
    connection = connections.get(rule.connection_id) if rule.connection_id else None
    url = rule.webhook_url or (connection.webhook_url if connection else "")
    return Decision(
        handler=rule.handler,
        reason=reason,
        connection_id=connection.id if connection else rule.connection_id,
        webhook_url=url,
        applies_to=rule.applies_to,
        record_history=rule.record_history,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def snapshot_hash(snapshot: BotSnapshot) -> str:
    payload = {
        "attention": _public(snapshot.attention),
        "routing": _public(snapshot.routing),
        "grok": _public(snapshot.grok),
        "external": _public(snapshot.external),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _public(view: IntegrationView | None) -> dict | None:
    if view is None:
        return None
    return {"id": view.id, "enabled": view.enabled, "config": view.config or {}}


def sign_body(secret: str, body: bytes, timestamp: str) -> str:
    signed = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return "sha256=" + digest


def build_outbound(
    *,
    bot_id: int,
    wa_id: str,
    message_id: str,
    message_type: str,
    text: str,
    name: str,
    tags: list[str],
    decision: Decision,
    connection: LiveConnection | None,
) -> dict:
    """Contrato único. No incluye tokens de WhatsApp ni secretos."""
    return {
        "event": "message_received",
        "bot_id": bot_id,
        "connection": {
            "id": connection.id if connection else None,
            "preset": connection.preset if connection else None,
        },
        "contact": {"wa_id": wa_id, "name": name, "tags": tags},
        "message": {
            "id": message_id,
            "from": wa_id,
            "type": message_type or "text",
            "text": text,
        },
        "routing": {
            "handler": decision.handler,
            "reason": decision.reason,
            "attendant": "asistto" if decision.handler == "asistto" else "connection",
        },
    }
