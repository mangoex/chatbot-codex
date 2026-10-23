"""Control administrativo del prompt maestro mediante comandos de WhatsApp (#prompt).

Fase Verde TDD: Implementación completa del flujo asistido en dos pasos con TTL.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app import bot_control, bots, db, prompt_change_store, prompt_changes, whatsapp_client

log = logging.getLogger("whatsapp-bot")

PROMPT_COMMAND_PREFIX = "#prompt"
CONFIRMATION_WORDS = frozenset({"confirmar", "confirm", "si", "sí"})
CANCELLATION_WORDS = frozenset({"cancelar", "cancel", "no"})
DEFAULT_PROPOSAL_TTL_SECONDS = 1800  # 30 minutos

HELP_EMPTY_INSTRUCTION = (
    "ℹ️ *Comando #prompt*: Por favor incluye la instrucción del cambio que deseas realizar.\n\n"
    "*Ejemplo*: `#prompt Cambiar horario a lunes a viernes de 9 a 18hrs`"
)

PROPOSAL_CONFIRMATION_TEMPLATE = (
    "📝 *Propuesta de actualización del prompt*:\n"
    "{summary}\n\n"
    "¿Deseas aplicar este cambio? Responde *Confirmar* o *Cancelar*."
)

MSG_PROMPT_PUBLISHED = "✅ El nuevo prompt maestro ha sido publicado y está activo."
MSG_PROMPT_CANCELLED = "❌ Propuesta de cambio cancelada. No se aplicó ningún cambio al prompt."
MSG_PROPOSAL_EXPIRED = (
    "⏳ La propuesta ha expirado o no hay cambios pendientes. "
    "Envía nuevamente el comando #prompt con tu instrucción."
)


@dataclass
class PendingPromptProposal:
    bot_id: int
    admin_wa_id: str
    summary: str
    candidate_prompt: str
    review_receipt: str | None = None
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = DEFAULT_PROPOSAL_TTL_SECONDS

    def is_expired(self, current_time: float | None = None) -> bool:
        now = time.time() if current_time is None else current_time
        return (now - self.created_at) > self.ttl_seconds


class ProposalStore:
    """Almacén en memoria de propuestas pendientes indexadas por (bot_id, admin_wa_id)."""

    def __init__(self) -> None:
        self._proposals: dict[tuple[int, str], PendingPromptProposal] = {}

    def set(
        self,
        proposal_or_bot_id: PendingPromptProposal | int,
        wa_id: str | None = None,
        proposal: PendingPromptProposal | None = None,
    ) -> None:
        if isinstance(proposal_or_bot_id, PendingPromptProposal):
            p = proposal_or_bot_id
            self._proposals[(p.bot_id, p.admin_wa_id)] = p
        elif wa_id is not None and proposal is not None:
            self._proposals[(int(proposal_or_bot_id), wa_id)] = proposal
        elif isinstance(proposal, PendingPromptProposal):
            self._proposals[(proposal.bot_id, proposal.admin_wa_id)] = proposal

    def peek(self, bot_id: int, admin_wa_id: str) -> PendingPromptProposal | None:
        """Retorna la propuesta almacenada sin verificar expiración ni desalojar."""
        return self._proposals.get((bot_id, admin_wa_id))

    def get(
        self,
        bot_id: int,
        admin_wa_id: str,
        current_time: float | None = None,
    ) -> PendingPromptProposal | None:
        """Obtiene la propuesta pendiente. Si ha expirado, la desaloja y devuelve None."""
        key = (bot_id, admin_wa_id)
        prop = self._proposals.get(key)
        if prop is None:
            return None
        if prop.is_expired(current_time):
            self._proposals.pop(key, None)
            return None
        return prop

    def remove(self, bot_id: int, admin_wa_id: str) -> PendingPromptProposal | None:
        return self._proposals.pop((bot_id, admin_wa_id), None)

    def delete(self, bot_id: int, admin_wa_id: str) -> PendingPromptProposal | None:
        return self.remove(bot_id, admin_wa_id)

    def clear(self) -> None:
        self._proposals.clear()


proposal_store = ProposalStore()


def _normalize_word(text: str | None) -> str:
    if not text or not isinstance(text, str):
        return ""
    normalized = unicodedata.normalize("NFKD", text.strip())
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    cleaned = re.sub(r"^[¡!¿?.,:;\-_()\[\]\s]+|[¡!¿?.,:;\-_()\[\]\s]+$", "", without_accents.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


_CONFIRMATION_NORMALIZED = frozenset({"confirmar", "confirm", "si"})
_CANCELLATION_NORMALIZED = frozenset({"cancelar", "cancel", "no"})


def is_prompt_command(text: str | None) -> bool:
    """Verifica si el texto corresponde a un comando #prompt."""
    if not text or not isinstance(text, str):
        return False
    return bool(re.match(r"^\s*#prompt(?:\s|$)", text, re.IGNORECASE))


def extract_prompt_instruction(text: str | None) -> str:
    """Extrae la instrucción de un comando #prompt, removiendo comillas y espacios externos."""
    if not text or not isinstance(text, str):
        return ""
    match = re.match(r"^\s*#prompt(?:\s+(.*)|\s*$)", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    instruction = (match.group(1) or "").strip()
    if not instruction:
        return ""
    if (instruction.startswith('"') and instruction.endswith('"') and len(instruction) >= 2) or \
       (instruction.startswith("'") and instruction.endswith("'") and len(instruction) >= 2):
        instruction = instruction[1:-1].strip()
    return instruction


def is_confirmation_response(text: str | None) -> bool:
    """Verifica si el texto es una respuesta afirmativa de confirmación (confirmar, si, sí, etc.)."""
    return _normalize_word(text) in _CONFIRMATION_NORMALIZED


def is_cancellation_response(text: str | None) -> bool:
    """Verifica si el texto es una respuesta de cancelación (cancelar, no, cancel)."""
    return _normalize_word(text) in _CANCELLATION_NORMALIZED


async def handle_prompt_whatsapp_message(
    bot: bots.BotContext,
    wa_id: str,
    text: str,
    extra_phone: str | None = None,
    metadata_display_phone: str | None = None,
) -> dict[str, Any]:
    """Procesa mensajes relacionados con el comando #prompt o sus confirmaciones/cancelaciones."""
    effective_extra = extra_phone or metadata_display_phone
    if not bot_control.is_authorized_admin(wa_id, bot=bot, extra_phone=effective_extra):
        return {"handled": False}

    # 1. Caso: El mensaje es un comando #prompt
    if is_prompt_command(text):
        instruction = extract_prompt_instruction(text)
        if not instruction:
            await whatsapp_client.send_text(
                wa_id,
                HELP_EMPTY_INSTRUCTION,
                phone_number_id=bot.whatsapp_phone_number_id,
                access_token=bot.whatsapp_access_token,
            )
            await db.save_message(wa_id, "assistant", HELP_EMPTY_INSTRUCTION, bot_id=bot.id)
            return {"handled": True, "action": "help", "text": HELP_EMPTY_INSTRUCTION}

        try:
            context = await prompt_change_store.get_context(bot.id)
            current_prompt = (context.get("previous") or {}).get("content") or ""
            assist_result = await prompt_changes.assist_changes(
                context=context,
                bot_id=bot.id,
                actor=wa_id,
                current_prompt=current_prompt,
                instruction=instruction,
            )
        except (prompt_changes.ChangeError, Exception) as exc:
            log.warning("Error asistiendo cambios de prompt para bot=%s wa_id=%s: %s", bot.id, wa_id, exc)
            error_msg = str(exc)
            reply = f"⚠️ No se pudo procesar la propuesta de cambio: {error_msg}"
            await whatsapp_client.send_text(
                wa_id,
                reply,
                phone_number_id=bot.whatsapp_phone_number_id,
                access_token=bot.whatsapp_access_token,
            )
            await db.save_message(wa_id, "assistant", reply, bot_id=bot.id)
            return {"handled": True, "action": "error", "error": error_msg}

        summary = assist_result.get("summary") or "Propuesta de cambio al prompt maestro."
        candidate_prompt = assist_result.get("prompt") or ""
        review_receipt = assist_result.get("review_receipt")

        proposal = PendingPromptProposal(
            bot_id=bot.id,
            admin_wa_id=wa_id,
            summary=summary,
            candidate_prompt=candidate_prompt,
            review_receipt=review_receipt,
            created_at=time.time(),
        )
        proposal_store.set(proposal)

        reply = PROPOSAL_CONFIRMATION_TEMPLATE.format(summary=summary)
        await whatsapp_client.send_text(
            wa_id,
            reply,
            phone_number_id=bot.whatsapp_phone_number_id,
            access_token=bot.whatsapp_access_token,
        )
        await db.save_message(wa_id, "assistant", reply, bot_id=bot.id)
        return {
            "handled": True,
            "action": "proposal_created",
            "summary": summary,
            "candidate_prompt": candidate_prompt,
        }

    # 2. Caso: No es #prompt, verificar si hay propuesta pendiente
    pending = proposal_store.peek(bot.id, wa_id)
    if pending is None:
        return {"handled": False}

    # Si hay propuesta pero ya expiró
    if pending.is_expired():
        proposal_store.remove(bot.id, wa_id)
        if is_confirmation_response(text) or is_cancellation_response(text):
            await whatsapp_client.send_text(
                wa_id,
                MSG_PROPOSAL_EXPIRED,
                phone_number_id=bot.whatsapp_phone_number_id,
                access_token=bot.whatsapp_access_token,
            )
            await db.save_message(wa_id, "assistant", MSG_PROPOSAL_EXPIRED, bot_id=bot.id)
            return {"handled": True, "action": "expired", "text": MSG_PROPOSAL_EXPIRED}
        return {"handled": False}

    # Propuesta activa y vigente: Confirmar
    if is_confirmation_response(text):
        await db.publish_bot_prompt(bot.id, pending.candidate_prompt)
        proposal_store.remove(bot.id, wa_id)
        try:
            await db.record_bot_control_event(
                bot.id,
                bot_control.extract_10_digits(wa_id)[-4:],
                "prompt",
                "published",
            )
        except Exception:
            log.exception("No se pudo registrar auditoría de control para bot_id=%s", bot.id)

        await whatsapp_client.send_text(
            wa_id,
            MSG_PROMPT_PUBLISHED,
            phone_number_id=bot.whatsapp_phone_number_id,
            access_token=bot.whatsapp_access_token,
        )
        await db.save_message(wa_id, "assistant", MSG_PROMPT_PUBLISHED, bot_id=bot.id)
        return {
            "handled": True,
            "action": "published",
            "candidate_prompt": pending.candidate_prompt,
        }

    # Propuesta activa y vigente: Cancelar
    if is_cancellation_response(text):
        proposal_store.remove(bot.id, wa_id)
        try:
            await db.record_bot_control_event(
                bot.id,
                bot_control.extract_10_digits(wa_id)[-4:],
                "prompt",
                "cancelled",
            )
        except Exception:
            log.exception("No se pudo registrar auditoría de control para bot_id=%s", bot.id)

        await whatsapp_client.send_text(
            wa_id,
            MSG_PROMPT_CANCELLED,
            phone_number_id=bot.whatsapp_phone_number_id,
            access_token=bot.whatsapp_access_token,
        )
        await db.save_message(wa_id, "assistant", MSG_PROMPT_CANCELLED, bot_id=bot.id)
        return {"handled": True, "action": "cancelled"}

    # Mensaje no reconocido mientras hay una propuesta pendiente activa
    reminder = (
        "⚠️ Tienes una propuesta de actualización de prompt pendiente.\n"
        "Responde *Confirmar* para aplicarla o *Cancelar* para descartarla."
    )
    await whatsapp_client.send_text(
        wa_id,
        reminder,
        phone_number_id=bot.whatsapp_phone_number_id,
        access_token=bot.whatsapp_access_token,
    )
    await db.save_message(wa_id, "assistant", reminder, bot_id=bot.id)
    return {"handled": True, "action": "pending_reminder", "text": reminder}
