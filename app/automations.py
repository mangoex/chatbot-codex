from __future__ import annotations
"""Motor de automatizaciones y disparadores de plantillas de WhatsApp."""
import asyncio
import logging
from typing import Any

from app import db, meta_provider

log = logging.getLogger("automations")


def _resolve_parameters(
    mappings: list[dict],
    contact_name: str | None,
    contact_business: str | None,
    wa_id: str,
) -> list[str]:
    """Resuelve los parámetros dinámicos para una plantilla según el mapeo configurado."""
    params = []
    for m in mappings or []:
        m_type = m.get("type")
        m_val = m.get("value") or ""
        if m_type == "fixed":
            params.append(str(m_val))
        elif m_type == "name":
            params.append(str(contact_name or ""))
        elif m_type == "business":
            params.append(str(contact_business or ""))
        elif m_type == "wa_id":
            params.append(str(wa_id))
        else:
            params.append(str(m_val))
    return params


async def process_scheduled_campaigns() -> None:
    """Procesa campañas masivas programadas cuya fecha/hora programada ya llegó."""
    try:
        from app import client
        due_campaigns = await db.get_due_scheduled_broadcasts(limit=10)
        for campaign in due_campaigns:
            broadcast_id = int(campaign["id"])
            bot_id = int(campaign["bot_id"])
            log.info("Disparando campaña programada %s para bot %s", broadcast_id, bot_id)
            asyncio.create_task(client.process_broadcast_queue(broadcast_id, bot_id))
    except Exception as exc:
        log.error("Error al procesar campañas programadas: %s", exc)


async def evaluate_inactivity_triggers() -> None:
    """Evalúa los disparadores de inactividad para todos los bots activos."""
    try:
        triggers = await db.list_active_template_triggers_by_type("inactivity_hours")
        for t in triggers:
            trigger_id = int(t["id"])
            bot_id = int(t["bot_id"])
            config_data = t.get("trigger_config") or {}
            inactivity_hours = int(config_data.get("inactivity_hours") or 24)
            template_name = t["template_name"]
            language_code = t.get("language_code") or "es_MX"
            mappings = t.get("variable_mappings") or []

            inactive_convs = await db.get_inactive_conversations_for_trigger(
                bot_id=bot_id,
                inactivity_hours=inactivity_hours,
                limit=30,
            )

            for conv in inactive_convs:
                wa_id = conv["wa_id"]
                # Evitar envíos repetidos dentro de la misma ventana de horas
                already_sent = await db.has_recent_trigger_execution(
                    trigger_id=trigger_id,
                    wa_id=wa_id,
                    within_hours=inactivity_hours,
                )
                if already_sent:
                    continue

                params = _resolve_parameters(
                    mappings=mappings,
                    contact_name=conv.get("contact_name"),
                    contact_business=conv.get("contact_business"),
                    wa_id=wa_id,
                )

                try:
                    await meta_provider.send_template_message(
                        bot_id=bot_id,
                        to_wa_id=wa_id,
                        template_name=template_name,
                        language_code=language_code,
                        parameters=params,
                    )
                    await db.record_trigger_execution(
                        trigger_id=trigger_id,
                        bot_id=bot_id,
                        wa_id=wa_id,
                        status="sent",
                    )
                    log.info(
                        "Disparador de inactividad %s ejecutado para %s (bot %s)",
                        trigger_id,
                        wa_id,
                        bot_id,
                    )
                except Exception as exc:
                    log.error(
                        "Fallo al ejecutar disparador %s para %s: %s",
                        trigger_id,
                        wa_id,
                        exc,
                    )
                    await db.record_trigger_execution(
                        trigger_id=trigger_id,
                        bot_id=bot_id,
                        wa_id=wa_id,
                        status="failed",
                        error_message=str(exc),
                    )
                await asyncio.sleep(0.1)
    except Exception as exc:
        log.error("Error en evaluate_inactivity_triggers: %s", exc)


async def trigger_crm_status_change(
    bot_id: int,
    wa_id: str,
    new_status: str,
    old_status: str | None = None,
) -> None:
    """Dispara las plantillas asociadas a un cambio de estado en el CRM de leads."""
    if not bot_id or not wa_id or not new_status:
        return
    try:
        triggers = await db.list_active_template_triggers_by_type(
            "crm_status_changed", bot_id=bot_id
        )
        target_status = new_status.strip().lower()

        # Obtener información del contacto para variables dinámicas
        contact = await db.get_contact_by_wa_id(bot_id, wa_id)
        contact_name = contact.get("name") if contact else ""
        contact_business = contact.get("business") if contact else ""

        for t in triggers:
            cfg = t.get("trigger_config") or {}
            rule_status = (cfg.get("crm_status") or "").strip().lower()
            if rule_status == target_status:
                trigger_id = int(t["id"])
                template_name = t["template_name"]
                language_code = t.get("language_code") or "es_MX"
                mappings = t.get("variable_mappings") or []

                params = _resolve_parameters(
                    mappings=mappings,
                    contact_name=contact_name,
                    contact_business=contact_business,
                    wa_id=wa_id,
                )

                try:
                    await meta_provider.send_template_message(
                        bot_id=bot_id,
                        to_wa_id=wa_id,
                        template_name=template_name,
                        language_code=language_code,
                        parameters=params,
                    )
                    await db.record_trigger_execution(
                        trigger_id=trigger_id,
                        bot_id=bot_id,
                        wa_id=wa_id,
                        status="sent",
                    )
                    log.info(
                        "Disparador CRM %s enviado a %s por cambio a estado '%s'",
                        trigger_id,
                        wa_id,
                        new_status,
                    )
                except Exception as exc:
                    log.error(
                        "Error al disparar plantilla CRM %s para %s: %s",
                        trigger_id,
                        wa_id,
                        exc,
                    )
                    await db.record_trigger_execution(
                        trigger_id=trigger_id,
                        bot_id=bot_id,
                        wa_id=wa_id,
                        status="failed",
                        error_message=str(exc),
                    )
    except Exception as exc:
        log.error("Error en trigger_crm_status_change para bot %s: %s", bot_id, exc)


async def run_automation_loop() -> None:
    """Loop perpetuo en segundo plano para campañas programadas y disparadores periódicos."""
    log.info("Iniciando loop de automatizaciones de WhatsApp...")
    while True:
        await asyncio.sleep(60)
        try:
            await process_scheduled_campaigns()
            await evaluate_inactivity_triggers()
        except Exception:
            log.exception("Error en automations.run_automation_loop")
