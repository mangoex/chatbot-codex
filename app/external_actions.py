from __future__ import annotations
"""Runtime actions for bot-specific external integrations."""
import json
import logging
import re
import ipaddress
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app import db, secure_store, skill_runtime

log = logging.getLogger("external-actions")

_MARKER_RE = re.compile(
    r"\[\[(WEBHOOK_POST|EXTERNAL_API_REQUEST|CRM_LEAD|EASYBROKER_LEAD):\s*(\{.*?\})\s*\]\]",
    re.DOTALL,
)

_ACTION_MAP = {
    "WEBHOOK_POST": "webhook_post",
    "EXTERNAL_API_REQUEST": "external_api_request",
    "CRM_LEAD": "crm_lead",
    "EASYBROKER_LEAD": "easybroker_lead",
}

_INTEGRATION_BY_ACTION = {
    "webhook_post": "webhook",
    "external_api_request": "external_api",
    "crm_lead": "crm",
    "easybroker_lead": "easybroker",
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


def _is_safe_host(hostname: str) -> bool:
    if not hostname or hostname in {"localhost", "metadata.google.internal"}:
        return False
    try:
        ip = ipaddress.ip_address(hostname)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        return True


def _allowed_hosts(config_data: dict) -> set[str]:
    configured = config_data.get("allowed_hosts") or []
    hosts = {str(h).lower().strip() for h in configured if str(h).strip()}
    for key in ("base_url", "url"):
        parsed = urlparse(str(config_data.get(key) or ""))
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    return hosts


def _validate_url(url: str, config_data: dict) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not _is_safe_host(host):
        return ""
    allowed = _allowed_hosts(config_data)
    if allowed and host not in allowed:
        return ""
    return url


def _request_url(config_data: dict, action_payload: dict, *, allow_config_url: bool = False) -> str:
    if action_payload.get("url"):
        return ""
    direct_url = str(config_data.get("url") or "").strip()
    if allow_config_url and direct_url:
        return _validate_url(direct_url, config_data)
    base_url = str(config_data.get("base_url") or "").strip()
    path = str(action_payload.get("path") or "").strip()
    if not base_url or urlparse(path).scheme:
        return ""
    return _validate_url(urljoin(base_url.rstrip("/") + "/", path.lstrip("/")), config_data)


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


def _interpolate(obj: Any, secrets: dict[str, str]) -> Any:
    if isinstance(obj, str):
        result = obj
        for k, v in secrets.items():
            if f"{{{k}}}" in result:
                result = result.replace(f"{{{k}}}", v)
        return result
    elif isinstance(obj, dict):
        return {k: _interpolate(v, secrets) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_interpolate(v, secrets) for v in obj]
    return obj


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
        if not operation:
            log.warning("Accion de API externa rechazada: falta operation declarada.")
            return None
        method = str(
            operation.get("method")
            or config_data.get("method")
            or "GET"
        ).upper()
        request_json = _merge_dict(operation.get("json"), payload.get("json"))

    allowed_methods = {str(item).upper() for item in config_data.get("allowed_methods", ["GET", "POST"])}
    if method not in allowed_methods:
        log.warning("Metodo no permitido para accion externa: %s", method)
        return None

    request_payload = {**operation, **payload} if operation else payload
    url = _request_url(config_data, request_payload, allow_config_url=action_type in {"webhook_post", "crm_lead"})
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


def _redact_request(request_data: dict[str, Any] | None) -> dict[str, Any]:
    if not request_data:
        return {}
    redacted = {k: v for k, v in request_data.items() if k != "headers"}
    if "headers" in request_data:
        redacted["headers"] = {
            str(k): "[redacted]" if str(k).lower() in {"authorization", "x-api-key", "x-asistto-secret-token"} else str(v)
            for k, v in (request_data.get("headers") or {}).items()
        }
    return redacted


async def _skill_on(bot_id: int | None, integration_type: str) -> bool:
    if integration_type == "webhook":
        return await skill_runtime.webhook_skill_enabled(bot_id)
    if integration_type == "external_api":
        return await skill_runtime.external_api_skill_enabled(bot_id)
    if integration_type == "crm":
        return await skill_runtime.crm_skill_enabled(bot_id)
    if integration_type == "easybroker":
        if not bot_id:
            return False
        integ = await db.get_active_bot_integration(bot_id, "easybroker")
        return bool(integ and integ.get("enabled"))
    return False


async def _execute_action(bot_id: int | None, wa_id: str, action: dict[str, Any]) -> bool:
    action_type = str(action.get("action_type") or "")
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    operation = str(payload.get("operation") or "").strip() or None
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

    if action_type == "easybroker_lead":
        api_key = secrets.get("api_key") or ""
        from app import easybroker_client
        ok = await easybroker_client.send_contact_request(api_key, payload)
        await db.record_external_action_run(
            bot_id=bot_id,
            wa_id=wa_id,
            action_type=action_type,
            integration_id=int(integration["id"]),
            operation="contact_request",
            status="success" if ok else "failed",
            request_data=_redact_request({"payload": payload}),
            error_message="" if ok else "Fallo al enviar a Easybroker",
        )
        return ok

    request_data = build_request(action, integration, secrets)
    if not request_data:
        await db.record_external_action_run(
            bot_id=bot_id,
            wa_id=wa_id,
            action_type=action_type,
            integration_id=int(integration["id"]),
            operation=operation,
            status="rejected",
            error_message="Request rejected by safety policy",
        )
        return False

    timeout = int((integration.get("config") or {}).get("timeout_seconds") or 20)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            method = request_data.pop("method")
            url = request_data.pop("url")
            response = await client.request(
                method,
                url,
                **request_data,
            )
            response.raise_for_status()
        await db.record_external_action_run(
            bot_id=bot_id,
            wa_id=wa_id,
            action_type=action_type,
            integration_id=int(integration["id"]),
            operation=operation,
            status="success",
            request_data=_redact_request({"method": method, "url": url, **request_data}),
            response_data={"status_code": getattr(response, "status_code", None)},
        )
    except Exception as exc:
        log.exception(
            "Fallo ejecutando accion externa %s para bot %s",
            action_type,
            bot_id,
        )
        await db.record_external_action_run(
            bot_id=bot_id,
            wa_id=wa_id,
            action_type=action_type,
            integration_id=int(integration["id"]),
            operation=operation,
            status="failed",
            request_data=_redact_request(request_data),
            error_message=str(exc)[:500],
        )
        return False
    return True


async def process_reply(wa_id: str, reply: str, bot_id: int | None = None) -> str:
    clean, actions = extract_actions(reply)
    for action in actions:
        await _execute_action(bot_id, wa_id, action)
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
    if await _skill_on(bot_id, "easybroker"):
        parts.append(
            "- Easybroker CRM: cuando el prospecto muestre interés en una propiedad o comparta sus datos de contacto, "
            'agrega al final [[EASYBROKER_LEAD: {"name": "Nombre", "phone": "Teléfono", "email": "Email opcional", "property_id": "EB-ID opcional", "message": "Resumen del interés"}]].'
        )
        
    try:
        hours_skill = await db.get_bot_skill(bot_id, "business_hours")
        if hours_skill:
            cfg = hours_skill.get("config") or {}
            if cfg:
                days_translated = []
                for day, data in cfg.items():
                    if data.get("open"):
                        days_translated.append(f"{day.capitalize()}: {data.get('start', '')} a {data.get('end', '')}")
                    else:
                        days_translated.append(f"{day.capitalize()}: Cerrado")
                if days_translated:
                    parts.append(
                        "- Horarios de atencion del negocio:\n  " + "\n  ".join(days_translated) + 
                        "\n  Usa esta informacion si el usuario pregunta por horarios de apertura o cierre."
                    )
                    
        escalation_skill = await db.get_bot_skill(bot_id, "escalation")
        if escalation_skill and escalation_skill.get("enabled", True):
            keywords = escalation_skill.get("config", {}).get("keywords", [])
            if keywords:
                parts.append(
                    "- Reglas de escalado: Si el usuario usa las palabras clave: " + ", ".join(keywords) + 
                    ", o si detectas urgencia extrema o daño fisico del producto, infórmale de manera amable que lo vas a comunicar "
                    "con un humano o asesor del equipo."
                )
    except Exception:
        log.exception("Error consultando skills de contexto para bot %s", bot_id)

    if not parts:
        return ""
    return (
        "--- habilidades_externas ---\n"
        "REGLA MUY IMPORTANTE: SIEMPRE debes terminar tu oración y dar una respuesta completa, lógica y natural al usuario PRIMERO. "
        "NO dejes oraciones incompletas. Una vez terminada tu respuesta, si necesitas usar un marcador, ponlo en una LÍNEA NUEVA al final.\n"
        "No expliques los marcadores y no los muestres como parte visible de la respuesta.\n"
        + "\n".join(parts)
    )
