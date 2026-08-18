from __future__ import annotations
"""Cliente asíncrono para Easybroker API (v1).

Permite verificar credenciales, descargar catálogo de propiedades,
transformarlas a documentos para RAG y enviar solicitudes de contacto (leads).
"""
import logging
from typing import Any
import httpx

from app import db, secure_store

log = logging.getLogger("easybroker-client")

EASYBROKER_API_BASE = "https://api.easybroker.com/v1"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "X-Authorization": str(api_key).strip(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def verify_api_key(api_key: str) -> tuple[bool, str]:
    """Verifica si una API Key de Easybroker es válida consultando 1 propiedad."""
    if not api_key or not str(api_key).strip():
        return False, "La API Key no puede estar vacía."

    url = f"{EASYBROKER_API_BASE}/properties"
    params = {"limit": 1}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=_headers(api_key), params=params)
            resp.raise_for_status()
            return True, "Conexión con Easybroker verificada con éxito."
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            return False, "API Key de Easybroker no válida o no autorizada (HTTP 401/403)."
        return False, f"Error al verificar Easybroker (HTTP {status}): {exc.response.text[:200]}"
    except Exception as exc:
        log.exception("Error al verificar API Key de Easybroker")
        return False, f"Error de conexión con Easybroker: {str(exc)[:200]}"


def format_property_doc(prop: dict[str, Any]) -> tuple[str, str]:
    """Convierte un objeto de propiedad de Easybroker en un título y contenido para RAG."""
    public_id = str(prop.get("public_id") or "EB-N/A").strip()
    title = str(prop.get("title") or "Propiedad sin título").strip()
    doc_title = f"[Easybroker] {title} ({public_id})"

    ptype = str(prop.get("property_type") or "Inmueble").strip()
    description = str(prop.get("description") or "Sin descripción detallada.").strip()
    location = str(prop.get("location") or "Ubicación no especificada").strip()
    url = str(prop.get("public_url") or "").strip()

    operations = prop.get("operations") or []
    ops_lines = []
    for op in operations:
        if not isinstance(op, dict):
            continue
        op_type = "Venta" if op.get("type") == "sale" else "Renta" if op.get("type") == "rental" else str(op.get("type", "")).capitalize()
        formatted = op.get("formatted_amount")
        amount = op.get("amount")
        currency = op.get("currency") or "MXN"
        if formatted:
            ops_lines.append(f"- Precio de {op_type}: {formatted}")
        elif amount is not None:
            ops_lines.append(f"- Precio de {op_type}: ${amount:,.2f} {currency}")

    features = []
    if prop.get("bedrooms") is not None:
        features.append(f"Recámaras: {prop['bedrooms']}")
    if prop.get("bathrooms") is not None:
        features.append(f"Baños: {prop['bathrooms']}")
    if prop.get("parking_spaces") is not None:
        features.append(f"Estacionamientos: {prop['parking_spaces']}")
    if prop.get("construction_size") is not None:
        features.append(f"Construcción: {prop['construction_size']} m²")
    if prop.get("lot_size") is not None:
        features.append(f"Terreno: {prop['lot_size']} m²")

    content_parts = [
        f"Tipo de Inmueble: {ptype}",
        f"Código / ID: {public_id}",
        f"Título: {title}",
        f"Ubicación: {location}",
    ]

    if ops_lines:
        content_parts.append("\nOperación y Precios:\n" + "\n".join(ops_lines))

    if features:
        content_parts.append("Características:\n- " + "\n- ".join(features))

    if url:
        content_parts.append(f"Ficha técnica / Enlace público: {url}")

    if description:
        content_parts.append(f"\nDescripción:\n{description}")

    return doc_title, "\n\n".join(content_parts)


async def fetch_all_properties(api_key: str, limit: int = 100) -> list[dict[str, Any]]:
    """Descarga propiedades publicadas desde Easybroker usando paginación."""
    all_properties: list[dict[str, Any]] = []
    page = 1
    url = f"{EASYBROKER_API_BASE}/properties"

    async with httpx.AsyncClient(timeout=25) as client:
        while len(all_properties) < limit:
            params = {
                "page": page,
                "limit": min(50, limit - len(all_properties)),
                "search[statuses][]": "published",
            }
            try:
                resp = await client.get(url, headers=_headers(api_key), params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                log.warning("Error descargando página %s de Easybroker: %s", page, exc)
                break

            content = data.get("content") or []
            if not content:
                break

            all_properties.extend(content)
            pagination = data.get("pagination") or {}
            next_page = pagination.get("next_page")
            if not next_page:
                break
            page += 1

    return all_properties


async def sync_properties_to_bot_knowledge(
    bot_id: int,
    api_key: str,
    max_properties: int = 100,
) -> dict[str, Any]:
    """Descarga y sincroniza las propiedades de Easybroker en la base de conocimiento del bot."""
    props = await fetch_all_properties(api_key, limit=max_properties)
    if not props:
        return {
            "success": True,
            "synced_count": 0,
            "bot_id": bot_id,
            "message": "No se encontraron propiedades publicadas en tu cuenta de Easybroker.",
        }

    async with db._pool.acquire() as conn:
        # 1. Eliminar documentos anteriores generados por Easybroker para este bot
        await conn.execute(
            "DELETE FROM bot_knowledge WHERE bot_id = $1 AND title LIKE '[Easybroker]%'",
            bot_id,
        )

        # 2. Insertar cada ficha de propiedad formateada
        synced_count = 0
        for p in props:
            doc_title, doc_content = format_property_doc(p)
            await conn.fetchrow(
                """
                INSERT INTO bot_knowledge (bot_id, title, content, status, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', NOW(), NOW())
                RETURNING id
                """,
                bot_id,
                doc_title,
                doc_content,
            )
            synced_count += 1

    # Actualizar metadatos en la configuración de la integración
    integration = await db.get_active_bot_integration(bot_id, "easybroker")
    if integration:
        cfg = integration.get("config") or {}
        cfg["properties_count"] = synced_count
        from datetime import datetime, timezone
        cfg["last_synced_at"] = datetime.now(timezone.utc).isoformat()
        await db.update_bot_integration(
            bot_id=bot_id,
            integration_id=int(integration["id"]),
            integration_type="easybroker",
            name="Easybroker",
            config_data=cfg,
            enabled=True,
        )

    log.info("Sincronizadas %d propiedades de Easybroker para bot %d", synced_count, bot_id)
    return {
        "success": True,
        "synced_count": synced_count,
        "bot_id": bot_id,
        "message": f"Se sincronizaron exitosamente {synced_count} propiedades en la Base de Conocimiento.",
    }


async def send_contact_request(api_key: str, lead_data: dict[str, Any]) -> bool:
    """Envía un prospecto a Easybroker vía POST /contact_requests."""
    if not api_key:
        return False

    url = f"{EASYBROKER_API_BASE}/contact_requests"
    payload = {
        "name": lead_data.get("name") or lead_data.get("nombre") or "Prospecto WhatsApp",
        "phone": lead_data.get("phone") or lead_data.get("telefono") or "",
        "email": lead_data.get("email") or "",
        "message": lead_data.get("message") or lead_data.get("mensaje") or "Prospecto generado por Asistto WhatsApp Bot",
        "source": "asistto_whatsapp_bot",
    }
    prop_id = lead_data.get("property_id") or lead_data.get("public_id")
    if prop_id:
        payload["property_id"] = str(prop_id).strip()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=_headers(api_key), json=payload)
            resp.raise_for_status()
            log.info("Lead enviado a Easybroker exitosamente: %s", payload["name"])
            return True
    except Exception as exc:
        log.warning("Fallo al enviar prospecto a Easybroker: %s", exc)
        return False
