from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app import bots, client, config, db, grok_client, meta_provider, secure_store

log = logging.getLogger("api-v1")
router = APIRouter(prefix="/api/v1", tags=["External Integration API"])


# --- PYDANTIC SCHEMAS ---

class ContactInput(BaseModel):
    wa_id: str = Field(
        ...,
        description="Número de WhatsApp en formato internacional (ej. '+52 1 55 1234 5678' o '5215512345678')",
        examples=["5215512345678"],
    )
    name: str | None = Field(
        None,
        description="Nombre completo o de pila del prospecto",
        examples=["Carlos Mendoza"],
    )
    business: str | None = Field(
        None,
        description="Nombre de la empresa o giro comercial del prospecto",
        examples=["Restaurante La Central"],
    )
    tags: list[str] | str | None = Field(
        None,
        description="Etiquetas de segmentación (ej. ['prospecto_grok', 'vip'])",
        examples=[["prospecto_grok", "campaña_octubre"]],
    )
    notes: str | None = Field(
        None,
        description="Notas u observaciones internas sobre el contacto",
    )
    qualification_status: Literal["en_progreso", "calificado", "descalificado"] = Field(
        "en_progreso",
        description="Estado inicial del prospecto en el CRM",
    )


class ContactsBatchInput(BaseModel):
    contacts: list[ContactInput] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Lista de contactos o prospectos para subir o actualizar en lote",
    )


class AudienceInput(BaseModel):
    type: Literal["all", "tag", "recipients"] = Field(
        "all",
        description="Tipo de audiencia: 'all' (todos los contactos), 'tag' (filtrar por etiqueta) o 'recipients' (lista explícita de destinatarios)",
    )
    tag: str | None = Field(
        None,
        description="Etiqueta si type es 'tag' (ej. 'prospecto_grok')",
        examples=["prospecto_grok"],
    )
    recipients: list[ContactInput] | None = Field(
        None,
        description="Lista directa de destinatarios si type es 'recipients'",
    )


class VariableMappingInput(BaseModel):
    var_idx: int = Field(
        ...,
        ge=1,
        description="Índice de la variable de la plantilla de WhatsApp (1 para {{1}}, 2 para {{2}}...)",
        examples=[1],
    )
    type: Literal["fixed", "name", "business", "wa_id"] = Field(
        "fixed",
        description="Origen del valor: 'name' (nombre del contacto), 'business' (negocio), 'wa_id' (teléfono), o 'fixed' (texto estático)",
    )
    value: str = Field(
        "",
        description="Valor fijo cuando type es 'fixed'",
        examples=["20% de descuento"],
    )


class CampaignCreateInput(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Nombre descriptivo de la campaña para trazabilidad y métricas",
        examples=["Campaña Grok Prospección Octubre"],
    )
    template_name: str = Field(
        ...,
        description="Nombre exacto de la plantilla aprobada en WhatsApp Cloud API",
        examples=["promocion_reactivacion_v1"],
    )
    language_code: str = Field(
        "es_MX",
        description="Código de idioma de la plantilla (ej. 'es_MX', 'es')",
        examples=["es_MX"],
    )
    audience: AudienceInput = Field(
        default_factory=AudienceInput,
        description="Definición de destinatarios a los que se enviará la plantilla",
    )
    variable_mappings: list[VariableMappingInput] = Field(
        default_factory=list,
        description="Mapeo de variables dinámicas de la plantilla",
    )
    scheduled_at: datetime | None = Field(
        None,
        description="Fecha y hora para envío programado futuro (ISO-8601 UTC). Si es null se dispara inmediatamente.",
        examples=[None],
    )


# --- HELPERS ---

def clean_phone_number(raw_phone: str) -> str:
    """Limpia el número telefónico dejando únicamente los dígitos numéricos."""
    return "".join(filter(str.isdigit, str(raw_phone or "")))


def normalize_tags(raw_tags: list[str] | str | None) -> str | None:
    """Normaliza las etiquetas a una cadena separada por comas."""
    if not raw_tags:
        return None
    if isinstance(raw_tags, list):
        items = [str(t).strip() for t in raw_tags if str(t).strip()]
        return ", ".join(items) if items else None
    return str(raw_tags).strip()


# --- AUTHENTICATION DEPENDENCY ---

async def verify_bot_auth(
    bot_id: int,
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_grok_secret: str | None = Header(None, alias="X-Grok-Secret"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> bots.BotContext:
    """
    Verifica las credenciales de acceso para interactuar con un bot específico.
    Acepta el token mediante:
      1. Header X-API-Key
      2. Header X-Grok-Secret
      3. Header Authorization: Bearer <token>
    Valida contra:
      - Secreto configurado en la integración Grok Bot (webhook_secret).
      - Secreto configurado en la integración API Key (api_key).
    """
    bot = await bots.resolve_by_bot_id(bot_id)
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bot con id {bot_id} no encontrado",
        )

    # 1. Extraer token proporcionado
    received_secret = (x_api_key or x_grok_secret or "").strip() or None
    if not received_secret and authorization:
        auth_str = authorization.strip()
        if auth_str.lower().startswith("bearer "):
            received_secret = auth_str[7:].strip()
        else:
            received_secret = auth_str

    if not received_secret:
        # Fallback a grok_client.extract_secret_from_request
        received_secret = grok_client.extract_secret_from_request(
            headers=dict(request.headers),
            query_params=dict(request.query_params),
        )

    if not received_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key or Secret. Provide X-API-Key, X-Grok-Secret, or Authorization: Bearer <token>",
        )

    # 2. Validar contra integración grok_bot si está activa
    grok_integration = await db.get_active_bot_integration(bot_id, "grok_bot")
    if grok_integration:
        enc_secrets = await db.get_integration_secret_values(int(grok_integration["id"]))
        stored_grok_secret = secure_store.decrypt_secret(enc_secrets.get("webhook_secret", ""))
        if stored_grok_secret and grok_client.validate_grok_secret(received_secret, stored_grok_secret):
            return bot

    # 3. Validar contra integración api_key si está activa
    api_key_integration = await db.get_active_bot_integration(bot_id, "api_key")
    if api_key_integration:
        enc_secrets = await db.get_integration_secret_values(int(api_key_integration["id"]))
        stored_api_key = secure_store.decrypt_secret(enc_secrets.get("api_key", ""))
        if stored_api_key and grok_client.validate_grok_secret(received_secret, stored_api_key):
            return bot

    # 4. Si ninguna credencial coincide
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key or Secret for this bot",
    )


# --- ENDPOINTS ---

@router.get(
    "/bots/{bot_id}/ping",
    summary="Verificar conectividad y autenticación del bot",
)
async def api_ping(
    bot_id: int,
    bot: bots.BotContext = Depends(verify_bot_auth),
):
    """Verifica que el token sea válido y que el bot esté listo para recibir peticiones."""
    return {
        "status": "ok",
        "bot_id": bot.id,
        "bot_name": bot.name,
        "bot_slug": bot.slug,
        "phone_configured": bool(bot.whatsapp_phone_number_id),
    }


@router.post(
    "/bots/{bot_id}/contacts",
    summary="Registrar o actualizar un prospecto individual",
)
async def api_create_contact(
    bot_id: int,
    data: ContactInput,
    bot: bots.BotContext = Depends(verify_bot_auth),
):
    """
    Crea o actualiza un contacto en el directorio del bot y sincroniza su estado de lead en el CRM.
    Permite segmentar con etiquetas (tags) para futuras campañas.
    """
    clean_wa = clean_phone_number(data.wa_id)
    if not clean_wa or len(clean_wa) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Número de teléfono (wa_id) inválido",
        )

    tag_str = normalize_tags(data.tags)

    # 1. Guardar en directorio de contactos
    await db.upsert_contact(
        bot_id=bot_id,
        wa_id=clean_wa,
        name=data.name.strip() if data.name else None,
        business=data.business.strip() if data.business else None,
        tags=tag_str,
    )

    # 2. Guardar en tabla de leads (CRM)
    await db.upsert_lead(
        clean_wa,
        bot_id=bot_id,
        nombre=data.name.strip() if data.name else None,
        negocio=data.business.strip() if data.business else None,
        qualification_status=data.qualification_status,
    )

    return {
        "status": "success",
        "bot_id": bot_id,
        "wa_id": clean_wa,
        "name": data.name,
        "business": data.business,
        "tags": tag_str,
    }


@router.post(
    "/bots/{bot_id}/contacts/batch",
    summary="Carga masiva de prospectos",
)
async def api_create_contacts_batch(
    bot_id: int,
    payload: ContactsBatchInput,
    bot: bots.BotContext = Depends(verify_bot_auth),
):
    """
    Sube o actualiza una lista de hasta 1000 prospectos en una sola llamada.
    Ideal para conectores de Grok Bot, scraping, CRMs externos o webhooks.
    """
    success_count = 0
    failed_items = []

    for idx, item in enumerate(payload.contacts):
        clean_wa = clean_phone_number(item.wa_id)
        if not clean_wa or len(clean_wa) < 8:
            failed_items.append({"index": idx, "wa_id": item.wa_id, "error": "Número inválido"})
            continue

        tag_str = normalize_tags(item.tags)
        try:
            await db.upsert_contact(
                bot_id=bot_id,
                wa_id=clean_wa,
                name=item.name.strip() if item.name else None,
                business=item.business.strip() if item.business else None,
                tags=tag_str,
            )
            await db.upsert_lead(
                clean_wa,
                bot_id=bot_id,
                nombre=item.name.strip() if item.name else None,
                negocio=item.business.strip() if item.business else None,
                qualification_status=item.qualification_status,
            )
            success_count += 1
        except Exception as exc:
            log.error("Error al procesar contacto %s en lote: %s", clean_wa, exc)
            failed_items.append({"index": idx, "wa_id": clean_wa, "error": str(exc)})

    return {
        "status": "success",
        "bot_id": bot_id,
        "total_received": len(payload.contacts),
        "success_count": success_count,
        "failed_count": len(failed_items),
        "failed_items": failed_items,
    }


@router.get(
    "/bots/{bot_id}/contacts",
    summary="Listar contactos y prospectos con filtros",
)
async def api_list_contacts(
    bot_id: int,
    tag: str | None = Query(None, description="Filtrar por etiqueta (ej. 'prospecto_grok')"),
    search: str | None = Query(None, description="Búsqueda por nombre, teléfono o negocio"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    bot: bots.BotContext = Depends(verify_bot_auth),
):
    """Obtiene la lista de contactos registrados para el bot con paginación y filtros opcionales."""
    contacts = await db.list_contacts(bot_id=bot_id, search=search, tag=tag, limit=limit, offset=offset)
    total = await db.count_contacts(bot_id=bot_id, search=search, tag=tag)
    return {
        "bot_id": bot_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "contacts": contacts,
    }


@router.get(
    "/bots/{bot_id}/templates",
    summary="Listar plantillas de WhatsApp aprobadas en Meta",
)
async def api_list_templates(
    bot_id: int,
    bot: bots.BotContext = Depends(verify_bot_auth),
):
    """
    Consulta en tiempo real las plantillas registradas y aprobadas en WhatsApp Cloud API.
    Permite a Grok Bot saber qué nombres de plantilla y qué componentes están disponibles.
    """
    try:
        raw_res = await meta_provider.list_message_templates(bot_id)
        templates_data = raw_res.get("data", []) if isinstance(raw_res, dict) else []
        return {
            "bot_id": bot_id,
            "total_templates": len(templates_data),
            "templates": templates_data,
        }
    except Exception as exc:
        log.error("Error al consultar plantillas de WhatsApp para bot %s: %s", bot_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudieron consultar las plantillas de Meta: {exc}",
        )


@router.post(
    "/bots/{bot_id}/campaigns",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crear y lanzar campaña de WhatsApp",
)
async def api_create_campaign(
    bot_id: int,
    payload: CampaignCreateInput,
    background_tasks: BackgroundTasks,
    bot: bots.BotContext = Depends(verify_bot_auth),
):
    """
    Crea y lanza (o programa) una campaña masiva de WhatsApp utilizando una plantilla aprobada por Meta.
    Grok Bot puede especificar la audiencia por tag, por lista directa o a todos los contactos.
    """
    recipients_list: list[dict[str, Any]] = []

    # 1. Resolver destinatarios según el tipo de audiencia
    aud_type = payload.audience.type
    if aud_type == "recipients" and payload.audience.recipients:
        for r in payload.audience.recipients:
            clean_wa = clean_phone_number(r.wa_id)
            if clean_wa and len(clean_wa) >= 8:
                recipients_list.append({
                    "wa_id": clean_wa,
                    "name": r.name,
                    "business": r.business,
                })
    elif aud_type == "tag" and payload.audience.tag:
        contacts = await db.list_contacts(bot_id=bot_id, tag=payload.audience.tag, limit=10000)
        recipients_list = [
            {"wa_id": c["wa_id"], "name": c.get("name"), "business": c.get("business")}
            for c in contacts
        ]
    elif aud_type == "all":
        contacts = await db.list_contacts(bot_id=bot_id, limit=10000)
        recipients_list = [
            {"wa_id": c["wa_id"], "name": c.get("name"), "business": c.get("business")}
            for c in contacts
        ]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audiencia no válida o incompleta para tipo '{aud_type}'",
        )

    if not recipients_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se encontraron destinatarios válidos para la campaña",
        )

    if len(recipients_list) > config.CAMPAIGN_MAX_RECIPIENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La cantidad de destinatarios ({len(recipients_list)}) excede el límite permitido ({config.CAMPAIGN_MAX_RECIPIENTS})",
        )

    # 2. Formatear mapeo de variables
    var_mappings = [
        {"var_idx": vm.var_idx, "type": vm.type, "value": vm.value}
        for vm in payload.variable_mappings
    ]

    # 3. Comprobar si está programada para el futuro
    is_future = False
    if payload.scheduled_at:
        dt = payload.scheduled_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt > datetime.now(timezone.utc):
            is_future = True

    try:
        broadcast_kwargs = {
            "bot_id": bot_id,
            "name": payload.name.strip(),
            "template_name": payload.template_name.strip(),
            "language_code": payload.language_code.strip(),
            "variable_mappings": var_mappings,
            "recipients": recipients_list,
        }
        if payload.scheduled_at:
            broadcast_kwargs["scheduled_at"] = payload.scheduled_at

        broadcast_id = await db.create_broadcast(**broadcast_kwargs)
    except Exception as exc:
        log.error("Error al registrar campaña masiva en BD: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar la campaña: {exc}",
        )

    # 4. Si es inmediata, encolar el proceso en segundo plano
    if not is_future:
        background_tasks.add_task(client.process_broadcast_queue, broadcast_id, bot_id)

    return {
        "status": "scheduled" if is_future else "queued",
        "campaign_id": broadcast_id,
        "name": payload.name,
        "template_name": payload.template_name,
        "recipients_count": len(recipients_list),
        "scheduled_at": payload.scheduled_at.isoformat() if payload.scheduled_at else None,
    }


@router.get(
    "/bots/{bot_id}/campaigns",
    summary="Listar campañas recientes del bot",
)
async def api_list_campaigns(
    bot_id: int,
    limit: int = Query(50, ge=1, le=200),
    bot: bots.BotContext = Depends(verify_bot_auth),
):
    """Devuelve las campañas masivas creadas para este bot y sus estados."""
    campaigns = await db.list_broadcasts(bot_id=bot_id, limit=limit)
    return {
        "bot_id": bot_id,
        "campaigns": campaigns,
    }


@router.get(
    "/bots/{bot_id}/campaigns/{campaign_id}/status",
    summary="Consultar estado y métricas de una campaña",
)
async def api_get_campaign_status(
    bot_id: int,
    campaign_id: int,
    bot: bots.BotContext = Depends(verify_bot_auth),
):
    """Consulta las métricas en tiempo real de una campaña: total de destinatarios, enviados y fallidos."""
    campaign = await db.get_broadcast(broadcast_id=campaign_id, bot_id=bot_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaña {campaign_id} no encontrada para este bot",
        )

    return {
        "campaign_id": campaign["id"],
        "bot_id": campaign["bot_id"],
        "name": campaign["name"],
        "template_name": campaign["template_name"],
        "language_code": campaign["language_code"],
        "status": campaign["status"],
        "total_recipients": campaign["total_recipients"],
        "sent_count": campaign["sent_count"],
        "failed_count": campaign["failed_count"],
        "created_at": campaign["created_at"].isoformat() if campaign.get("created_at") else None,
        "updated_at": campaign["updated_at"].isoformat() if campaign.get("updated_at") else None,
        "scheduled_at": campaign["scheduled_at"].isoformat() if campaign.get("scheduled_at") else None,
    }
