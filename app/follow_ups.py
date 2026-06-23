from __future__ import annotations
"""Follow-up suave y personalizado: un mensaje generado por IA si el lead no responde en un intervalo."""
import asyncio
import logging
from app import db, whatsapp_client, config, bots, openai_client, bot_content

log = logging.getLogger("follow_ups")

DEFAULT_FOLLOW_UP_MESSAGE = (
    "¡Hola! Solo quería saber si tienes alguna pregunta o si puedo ayudarte en algo más. 😊"
)


async def schedule(wa_id: str, bot_id: int | None = None) -> None:
    """Programa un follow-up para este wa_id con su bot correspondiente. Reprograma si existe."""
    if not config.ENABLE_FOLLOW_UPS:
        return
    delay = int(getattr(config, "FOLLOW_UP_MINUTES", 10))
    await db.upsert_follow_up(wa_id, delay, bot_id)


async def cancel(wa_id: str, bot_id: int) -> None:
    """Cancela el follow-up cuando el usuario escribe antes de que se dispare."""
    await db.cancel_follow_up(wa_id, bot_id)


async def _process_due() -> None:
    if not config.ENABLE_FOLLOW_UPS:
        cleared = await db.mark_all_follow_ups_sent()
        if cleared:
            log.info("Follow-ups pendientes desactivados: %s", cleared)
        return
    due = await db.get_due_follow_ups()
    for row in due:
        wa_id = row["wa_id"]
        bot_id = row.get("bot_id")
        try:
            bot = await bots.resolve_by_bot_id(bot_id)
            if bot is None:
                log.warning("Follow-up omitido para %s: bot_id %s no existe.", wa_id, bot_id)
                await db.mark_follow_up_sent(row["id"])
                continue
            if bot.status != "active":
                log.info("Follow-up omitido para %s: el bot %s está pausado.", wa_id, bot.id)
                await db.mark_follow_up_sent(row["id"])
                continue

            # Fetch conversation history to see context
            history = await db.get_history(wa_id, limit=20, bot_id=bot.id)
            if not history or history[-1].get("role") != "assistant":
                log.info("Follow-up omitido para %s: el último mensaje no es del asistente.", wa_id)
                await db.mark_follow_up_sent(row["id"])
                continue

            # Try generating a personalized follow-up message using OpenAI
            follow_up_message = DEFAULT_FOLLOW_UP_MESSAGE
            try:
                system_prompt = await bot_content.system_prompt_for_bot(bot.id)
                messages = [
                    {
                        "role": "system",
                        "content": (
                            f"{system_prompt}\n\n"
                            "Instrucción de Seguimiento: Analiza el historial de chat con el lead. "
                            "Escribe un único mensaje de seguimiento muy breve (máximo 2 líneas, amigable y natural) para retomar la conversación, "
                            "abordando su última duda o invitándolo amablemente al siguiente paso. "
                            "Responde ÚNICAMENTE con el texto del mensaje para enviar. No añadas notas ni explicaciones."
                        )
                    }
                ] + history[-5:]
                ai_response = await openai_client._chat(messages, model=bot.openai_model)
                if ai_response and ai_response.strip():
                    follow_up_message = ai_response.strip().strip('"').strip("'")
            except Exception as e:
                log.warning("No se pudo generar follow-up personalizado por IA, usando por defecto: %s", e)

            # Send using bot credentials
            await whatsapp_client.send_text(
                wa_id,
                follow_up_message,
                phone_number_id=bot.whatsapp_phone_number_id,
                access_token=bot.whatsapp_access_token,
            )
            await db.mark_follow_up_sent(row["id"])
            log.info("Follow-up enviado a %s para bot %s: %r", wa_id, bot.id, follow_up_message)
        except Exception:
            log.exception("Error enviando follow-up a %s para bot %s", wa_id, bot_id)


async def run_loop() -> None:
    """Loop perpetuo. Se lanza como background task al arrancar la app."""
    while True:
        await asyncio.sleep(60)
        try:
            await _process_due()
        except Exception:
            log.exception("Error en follow_ups.run_loop")
