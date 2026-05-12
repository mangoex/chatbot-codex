"""Runtime actions for bot-specific external integrations."""
import json
import logging
import re
from typing import Any
from urllib.parse import urljoin

import httpx

from app import db, secure_store, skill_runtime

log = logging.getLogger("external-actions")

_MARKER_RE = re.compile(
    r"\[\[(WEBHOOK_POST|EXTERNAL_API_REQUEST|CRM_LEAD):\s*(\{.*?\})\s*\]\]",
    re.DOTALL,
)

_ACTION_MAP = {
    "WEBHOOK_POST": "webhook_post",
    "EXTERNAL_API_REQUEST": "external_api_request",
    "CRM_LEAD": "crm_lead",
}

_INTEGRATION_BY_ACTION = {
    "webhook_post": "webhook",
    "external_api_request": "external_api",
    "crm_lead": "crm",
}


def _clean_visible_reply(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines).strip()


def extract_actions(reply: str) -> tuple[str, list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []

    def collect(match: re.Match) -> str:
        marker_type = match.group(1)
        raw_json = match.group(2)
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            log.warning("Marcador externo ignorado por JSON invalido: %s", marker_type)
            return ""
        if isinstance(payload, dict):
            actions.append({
                "action_type": _ACTION_MAP[marker_type],
                "payload": payload,
            })
        return ""

    clean = _clean_visible_reply(_MARKER_RE.sub(collect, reply or ""))
    if actions and not clean:
        clean = "Listo."
    return clean, actions


def _first_secret(secrets: dict[str, str], *names: str) -> str:
    for name in names:
        value = secrets.get(name)
        if value:
            return value
    return ""


def _headers(config_data: dict, secrets: dict[str, str]) -> dict[str, str]:
    headers = {
        str(key): str(value)
        for key, value in (config_data.get("headers") or {}).items()
        if key and value is not None
    }
    token = _first_secret(secrets, "access_token", "api_key", "bearer_token", "token")
    if token and not any(key.lower() == "authorization" for key in headers):
        auth_header = str(config_data.get("auth_header") or "Authorization").strip()
        auth_scheme = str(config_data.get("auth_scheme") or "Bearer").strip()
        headers[auth_header] = f"{auth_scheme} {token}".strip()
    return headers


def _request_url(config_data: dict, action_payload: dict) -> str:
    direct_url = str(action_payload.get("url") or config_data.get("url") or "").strip()
    if direct_url:
        return direct_url
    base_url = str(config_data.get("base_url") or "").strip()
    path = str(action_payload.get("path") or "").strip()
    if not base_url:
        return ""
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _operation_config(config_data: dict, operation_name: str | None) -> dict:
    if not operation_name:
        return {}
    operations = config_data.get("operations") or []
    if not isinstance(operations, list):
        return {}
    for operation in operations:
        if not isinstance(operation, dict):
            continue
        if str(operation.get("name") or "").strip() == operation_name:
            return operation
    return {}


def _merge_dict(base: Any, override: Any) -> dict | None:
    merged = {}
    if isinstance(base, dict):
        merged.update(base)
    if isinstance(override, dict):
        merged.update(override)
    return merged or None


def build_request(
    action: dict[str, Any],
    integration: dict[str, Any],
    secrets: dict[str, str],
) -> dict[str, Any] | None:
    action_type = action.get("action_type")
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    config_data = integration.get("config") or {}
    operation = _operation_config(config_data, str(payload.get("operation") or "").strip())

    if action_type == "webhook_post":
        method = str(config_data.get("method") or "POST").upper()
        request_json = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    elif action_type == "crm_lead":
        method = str(config_data.get("method") or "POST").upper()
        request_json = payload
    else:
        method = str(
            payload.get("method")
            or operation.get("method")
            or config_data.get("method")
            or "GET"
        ).upper()
        request_json = _merge_dict(operation.get("json"), payload.get("json"))

    allowed_methods = {str(item).upper() for item in config_data.get("allowed_methods", ["GET", "POST"])}
    if method not in allowed_methods:
        log.warning("Metodo no permitido para accion externa: %s", method)
        return None

    request_payload = {**operation, **payload} if operation else payload
    url = _request_url(config_data, request_payload)
    if not url:
        log.warning("Accion externa sin URL configurada: %s", action_type)
        return None

    request_data: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": _headers(config_data, secrets),
    }
    params = _merge_dict(operation.get("params"), payload.get("params"))
    if params:
        request_data["params"] = params
    if request_json is not None:
        request_data["json"] = request_json
    data = _merge_dict(operation.get("data"), payload.get("data"))
    if data and request_json is None:
        request_data["data"] = data
    return request_data


def _operation_instruction_lines(config_data: dict) -> list[str]:
    operations = config_data.get("operations") or []
    if not isinstance(operations, list):
        return []
    lines = []
    for operation in operations[:8]:
        if not isinstance(operation, dict):
            continue
        name = str(operation.get("name") or "").strip()
        path = str(operation.get("path") or operation.get("url") or "").strip()
        method = str(operation.get("method") or config_data.get("method") or "GET").upper()
        description = str(operation.get("description") or "").strip()
        if not name or not path:
            continue
        label = f"{name}: {method} {path}"
        if description:
            label += f" - {description}"
        lines.append(label)
    return lines


def _decrypt_secrets(encrypted_values: dict[str, str]) -> dict[str, str]:
    decrypted = {}
    for name, encrypted in encrypted_values.items():
        value = secure_store.decrypt_secret(encrypted)
        if value:
            decrypted[name] = value
    return decrypted


async def _skill_on(bot_id: int | None, integration_type: str) -> bool:
    if integration_type == "webhook":
        return await skill_runtime.webhook_skill_enabled(bot_id)
    if integration_type == "external_api":
        return await skill_runtime.external_api_skill_enabled(bot_id)
    if integration_type == "crm":
        return await skill_runtime.crm_skill_enabled(bot_id)
    return False


async def _execute_action(bot_id: int | None, action: dict[str, Any]) -> bool:
    action_type = str(action.get("action_type") or "")
    integration_type = _INTEGRATION_BY_ACTION.get(action_type)
    if not integration_type or not await _skill_on(bot_id, integration_type):
        return False
    if not bot_id:
        return False

    integration = await db.get_active_bot_integration(bot_id, integration_type)
    if not integration:
        log.info("Sin integracion activa para accion %s en bot %s", action_type, bot_id)
        return False

    encrypted = await db.get_integration_secret_values(int(integration["id"]))
    secrets = _decrypt_secrets(encrypted)
    request_data = build_request(action, integration, secrets)
    if not request_data:
        return False

    timeout = int((integration.get("config") or {}).get("timeout_seconds") or 20)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                request_data.pop("method"),
                request_data.pop("url"),
                **request_data,
            )
            response.raise_for_status()
    except Exception:
        log.exception(
            "Fallo ejecutando accion externa %s para bot %s",
            action_type,
            bot_id,
        )
        return False
    return True


async def process_reply(wa_id: str, reply: str, bot_id: int | None = None) -> str:
    del wa_id  # Reserved for future payload enrichment without changing the public API.
    clean, actions = extract_actions(reply)
    for action in actions:
        await _execute_action(bot_id, action)
    return clean


async def system_instructions(bot_id: int | None = None) -> str:
    if not bot_id:
        return ""
    parts: list[str] = []
    if await skill_runtime.webhook_skill_enabled(bot_id):
        parts.append(
            "- Webhook: cuando debas enviar una notificacion o datos a un sistema externo, "
            'agrega al final [[WEBHOOK_POST: {"payload": {"campo": "valor"}}]].'
        )
    if await skill_runtime.external_api_skill_enabled(bot_id):
        detail = ""
        integration = await db.get_active_bot_integration(bot_id, "external_api")
        if integration:
            operation_lines = _operation_instruction_lines(integration.get("config") or {})
            if operation_lines:
                detail = "\nOperaciones disponibles:\n" + "\n".join(f"  - {line}" for line in operation_lines)
        parts.append(
            "- API externa: cuando debas consultar o enviar datos a una API configurada, "
            'agrega [[EXTERNAL_API_REQUEST: {"method": "GET", "path": "/ruta", "params": {}}]] '
            'o [[EXTERNAL_API_REQUEST: {"operation": "nombre_operacion", "params": {}, "json": {}}]].'
            + detail
        )
    if await skill_runtime.crm_skill_enabled(bot_id):
        parts.append(
            "- CRM: cuando el usuario comparta datos de lead o cliente que deban guardarse, "
            'agrega [[CRM_LEAD: {"name": "", "phone": "", "status": "new", "notes": ""}]].'
        )
    if not parts:
        return ""
    return (
        "--- habilidades_externas ---\n"
        "Puedes usar estos marcadores internos solo cuando sea necesario. "
        "No expliques los marcadores y no los muestres como parte visible de la respuesta.\n"
        + "\n".join(parts)
    )
