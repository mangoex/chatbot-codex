from __future__ import annotations
"""Motor de automatizaciones y disparadores de plantillas de WhatsApp."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app import db, meta_provider

log = logging.getLogger("automations")

# Mapeo de día de semana en Python a formato estándar
_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


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


async def resolve_trigger_recipients(
    bot_id: int,
    audience_type: str = "all",
    audience_val: str | None = None,
) -> list[dict]:
    """Resuelve la lista de destinatarios según la segmentación de audiencia configurada."""
    audience_type = (audience_type or "all").strip().lower()
    recipients = []

    if audience_type == "tag" and audience_val:
        contacts = await db.list_contacts(bot_id, tag=audience_val.strip(), limit=10000)
        for c in contacts:
            recipients.append({
                "wa_id": c["wa_id"],
                "name": c.get("name"),
                "business": c.get("business"),
            })
    elif audience_type == "crm_status" and audience_val:
        leads = await db.list_leads(status=audience_val.strip().lower(), limit=10000, bot_id=bot_id)
        for ld in leads:
            recipients.append({
                "wa_id": ld["wa_id"],
                "name": ld.get("nombre"),
                "business": ld.get("negocio"),
            })
    else:  # "all"
        contacts = await db.list_contacts(bot_id, limit=10000)
        for c in contacts:
            recipients.append({
                "wa_id": c["wa_id"],
                "name": c.get("name"),
                "business": c.get("business"),
            })

    return recipients


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


async def evaluate_time_based_triggers() -> None:
    """Evalúa disparadores temporales (fecha específica, diarios y semanales)."""
    now = datetime.now(timezone.utc)
    current_time_str = now.strftime("%H:%M")
    current_weekday_str = _WEEKDAYS[now.weekday()]

    time_types = ["scheduled_date", "recurring_daily", "recurring_weekly"]
    for t_type in time_types:
        try:
            triggers = await db.list_active_template_triggers_by_type(t_type)
            for t in triggers:
                trigger_id = int(t["id"])
                bot_id = int(t["bot_id"])
                cfg = t.get("trigger_config") or {}
                template_name = t["template_name"]
                language_code = t.get("language_code") or "es_MX"
                mappings = t.get("variable_mappings") or []
                audience_type = cfg.get("audience_type", "all")
                audience_val = cfg.get("audience_val")

                should_fire = False

                if t_type == "scheduled_date":
                    target_dt_str = cfg.get("scheduled_datetime")
                    if target_dt_str:
                        try:
                            target_dt = datetime.fromisoformat(target_dt_str)
                            if target_dt.tzinfo is None:
                                target_dt = target_dt.replace(tzinfo=timezone.utc)
                            if now >= target_dt:
                                should_fire = True
                        except Exception:
                            pass

                elif t_type == "recurring_daily":
                    rule_time = cfg.get("time_of_day", "09:00")
                    if current_time_str == rule_time:
                        should_fire = True

                elif t_type == "recurring_weekly":
                    days_list = [d.lower() for d in cfg.get("days_of_week", [])]
                    rule_time = cfg.get("time_of_day", "09:00")
                    if current_weekday_str in days_list and current_time_str == rule_time:
                        should_fire = True

                if not should_fire:
                    continue

                # Resolver destinatarios de la audiencia
                recipients = await resolve_trigger_recipients(
                    bot_id=bot_id,
                    audience_type=audience_type,
                    audience_val=audience_val,
                )

                dispatched_any = False
                for r in recipients:
                    wa_id = r["wa_id"]
                    # Evitar duplicar en la misma jornada (últimas 20 horas) o si ya se ejecutó para scheduled_date
                    check_hours = 999999 if t_type == "scheduled_date" else 20
                    already_sent = await db.has_recent_trigger_execution(
                        trigger_id=trigger_id,
                        wa_id=wa_id,
                        within_hours=check_hours,
                    )
                    if already_sent:
                        continue

                    params = _resolve_parameters(
                        mappings=mappings,
                        contact_name=r.get("name"),
                        contact_business=r.get("business"),
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
                        dispatched_any = True
                        log.info(
                            "Disparador temporal %s (%s) enviado a %s (bot %s)",
                            trigger_id,
                            t_type,
                            wa_id,
                            bot_id,
                        )
                    except Exception as exc:
                        log.error(
                            "Error disparador temporal %s para %s: %s",
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

                # Si era de fecha única y ya se procesó, desactivarlo automáticamente
                if t_type == "scheduled_date" and dispatched_any:
                    await db.update_template_trigger_status(trigger_id, bot_id, False)

        except Exception as exc:
            log.error("Error al evaluar disparadores temporales tipo %s: %s", t_type, exc)


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
            await evaluate_time_based_triggers()
        except Exception:
            log.exception("Error en automations.run_automation_loop")
