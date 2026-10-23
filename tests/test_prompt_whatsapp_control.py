"""Suites de pruebas TDD / SBD para la feature de control del prompt maestro por WhatsApp (#prompt).

Fase: ROJA (TDD Red Phase)
Riesgo: R2
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from app import bots, prompt_changes, prompt_whatsapp_control as pwc


@pytest.fixture(autouse=True)
def clean_proposal_store():
    """Limpia el almacén de propuestas pendientes antes y después de cada prueba."""
    try:
        pwc.proposal_store.clear()
    except (NotImplementedError, AttributeError):
        pass
    yield
    try:
        pwc.proposal_store.clear()
    except (NotImplementedError, AttributeError):
        pass


@pytest.fixture
def sample_bot() -> bots.BotContext:
    """BotContext de prueba configurado con un administrador autorizado."""
    return bots.BotContext(
        id=10,
        client_id=1,
        slug="asistto-demo",
        name="Asistto Demo Bot",
        whatsapp_phone_number_id="phone_id_demo_10",
        whatsapp_access_token="access_token_demo_10",
        display_phone_number="5215500001111",
        admin_phone_numbers=("5215512345678",),
        status="active",
    )


# ==============================================================================
# 1. PRUEBAS UNITARIAS: DETECCIÓN Y EXTRACCIÓN DE COMANDOS (#prompt)
# ==============================================================================

class TestPromptCommandDetectionAndExtraction:
    """Criterios de aceptación para detección y extracción sintáctica del comando #prompt."""

    @pytest.mark.parametrize(
        "text",
        [
            "#prompt Cambiar horario a 9 a 18hrs",
            "#PROMPT Actualizar política de garantía",
            "#Prompt Modificar saludo inicial",
            "  #prompt   Añadir servicio de cerrajería  ",
            "#prompt\nRegla 1: Atención 24/7\nRegla 2: Sin anticipo",
            "#prompt",
            "   #prompt   ",
            "#PROMPT",
        ],
    )
    def test_is_prompt_command_positive_cases(self, text: str):
        """Dado un texto que inicia con el prefijo '#prompt' (insensible a mayúsculas y espacios).

        Cuando se verifica con is_prompt_command.
        Entonces debe retornar True.
        """
        assert pwc.is_prompt_command(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "#prompter cambiar horario",
            "hola #prompt",
            "prompt cambiar horario",
            "¿Puedes revisar el #prompt?",
            "# prompt con espacio",
            "",
            "   ",
            None,
        ],
    )
    def test_is_prompt_command_negative_cases(self, text: str | None):
        """Dado un texto que NO inicia con el prefijo canónico '#prompt'.

        Cuando se verifica con is_prompt_command.
        Entonces debe retornar False.
        """
        assert pwc.is_prompt_command(text) is False

    def test_extract_prompt_instruction_basic(self):
        """Dado '#prompt Cambiar horario de lunes a viernes a 9 a 18hrs'.

        Cuando se extrae la instrucción.
        Entonces retorna la instrucción limpia y sin espacios extra.
        """
        cmd = "#prompt Cambiar horario de lunes a viernes a 9 a 18hrs"
        assert pwc.extract_prompt_instruction(cmd) == "Cambiar horario de lunes a viernes a 9 a 18hrs"

    def test_extract_prompt_instruction_with_double_quotes(self):
        """Dado '#prompt \"Actualizar dirección a Av. Insurgentes 123\"'.

        Cuando se extrae la instrucción con comillas dobles externas.
        Entonces retorna el contenido sin las comillas envolventes.
        """
        cmd = '#prompt "Actualizar dirección a Av. Insurgentes 123"'
        assert pwc.extract_prompt_instruction(cmd) == "Actualizar dirección a Av. Insurgentes 123"

    def test_extract_prompt_instruction_with_single_quotes(self):
        """Dado \"#prompt 'Agregar teléfono de emergencias 555-9999'\".

        Cuando se extrae la instrucción con comillas simples externas.
        Entonces retorna el contenido sin las comillas envolventes.
        """
        cmd = "#prompt 'Agregar teléfono de emergencias 555-9999'"
        assert pwc.extract_prompt_instruction(cmd) == "Agregar teléfono de emergencias 555-9999"

    def test_extract_prompt_instruction_multiline(self):
        """Dado un comando multilínea con saltos de línea.

        Cuando se extrae la instrucción.
        Entonces preserva la estructura de múltiples líneas íntegra.
        """
        cmd = (
            "#prompt\n"
            "Horario: 9 a 18hrs lunes a viernes.\n"
            "Sábados: 10 a 14hrs previa cita."
        )
        expected = (
            "Horario: 9 a 18hrs lunes a viernes.\n"
            "Sábados: 10 a 14hrs previa cita."
        )
        assert pwc.extract_prompt_instruction(cmd) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "#prompt",
            "#prompt   ",
            "#PROMPT",
            "#prompt ''",
            '#prompt ""',
            None,
        ],
    )
    def test_extract_prompt_instruction_empty(self, text: str | None):
        """Dado un comando #prompt sin texto de instrucción.

        Cuando se extrae la instrucción.
        Entonces retorna una cadena vacía.
        """
        assert pwc.extract_prompt_instruction(text) == ""


# ==============================================================================
# 2. PRUEBAS UNITARIAS: RESPUESTAS DE CONFIRMACIÓN Y CANCELACIÓN
# ==============================================================================

class TestConfirmationAndCancellationWords:
    """Criterios de aceptación para palabras afirmativas y de cancelación."""

    @pytest.mark.parametrize(
        "word",
        [
            "confirmar",
            "Confirmar",
            "CONFIRMAR",
            "confirm",
            "Confirm",
            "si",
            "sí",
            "Si",
            "Sí",
            "SI",
            "SÍ",
            "  sí  ",
            "¡Confirmar!",
            "confirmar.",
        ],
    )
    def test_is_confirmation_response_positive(self, word: str):
        """Dado un mensaje de confirmación permitido ('confirmar', 'confirm', 'si', 'sí').

        Cuando se evalúa con is_confirmation_response.
        Entonces debe retornar True.
        """
        assert pwc.is_confirmation_response(word) is True

    @pytest.mark.parametrize(
        "word",
        [
            "cancelar",
            "no",
            "confirmar cita de mañana",
            "siempre no",
            "si por favor enviar catalogo",
            "hola",
            "",
            None,
        ],
    )
    def test_is_confirmation_response_negative(self, word: str | None):
        """Dado un mensaje que no es una confirmación aislada.

        Cuando se evalúa con is_confirmation_response.
        Entonces debe retornar False.
        """
        assert pwc.is_confirmation_response(word) is False

    @pytest.mark.parametrize(
        "word",
        [
            "cancelar",
            "Cancelar",
            "CANCELAR",
            "cancel",
            "Cancel",
            "no",
            "No",
            "NO",
            "  no  ",
            "¡Cancelar!",
            "cancelar.",
        ],
    )
    def test_is_cancellation_response_positive(self, word: str):
        """Dado un mensaje de cancelación permitido ('cancelar', 'cancel', 'no').

        Cuando se evalúa con is_cancellation_response.
        Entonces debe retornar True.
        """
        assert pwc.is_cancellation_response(word) is True

    @pytest.mark.parametrize(
        "word",
        [
            "confirmar",
            "si",
            "no tengo dudas",
            "cancelar suscripción premium",
            "gracias",
            "",
            None,
        ],
    )
    def test_is_cancellation_response_negative(self, word: str | None):
        """Dado un mensaje que no es una cancelación aislada.

        Cuando se evalúa con is_cancellation_response.
        Entonces debe retornar False.
        """
        assert pwc.is_cancellation_response(word) is False


# ==============================================================================
# 3. PRUEBAS UNITARIAS: MODELO DE PROPUESTA PENDIENTE Y STORE CON TTL
# ==============================================================================

class TestProposalStoreAndTTL:
    """Criterios de aceptación para almacenamiento de propuesta y cálculo de TTL (30 minutos)."""

    def test_pending_proposal_ttl_calculation(self):
        """Dado un objeto PendingPromptProposal creado en t0 con TTL de 1800 segundos.

        Cuando han pasado 1000 segundos, is_expired debe ser False.
        Cuando han pasado 1801 segundos, is_expired debe ser True.
        """
        now = time.time()
        proposal = pwc.PendingPromptProposal(
            bot_id=10,
            admin_wa_id="5215512345678",
            summary="Horario modificado",
            candidate_prompt="PROMPT CANDIDATO",
            created_at=now,
            ttl_seconds=1800,
        )
        assert proposal.is_expired(current_time=now + 1000) is False
        assert proposal.is_expired(current_time=now + 1801) is True

    def test_proposal_store_set_get_remove(self):
        """Dado ProposalStore.

        Cuando se guarda una propuesta, se puede recuperar por (bot_id, admin_wa_id).
        Cuando se remueve, ya no está disponible.
        """
        store = pwc.ProposalStore()
        proposal = pwc.PendingPromptProposal(
            bot_id=10,
            admin_wa_id="5215512345678",
            summary="Cambio de precio",
            candidate_prompt="PROMPT CANDIDATO",
            created_at=time.time(),
        )
        store.set(proposal)
        retrieved = store.get(10, "5215512345678")
        assert retrieved is not None
        assert retrieved.summary == "Cambio de precio"

        removed = store.remove(10, "5215512345678")
        assert removed == proposal
        assert store.get(10, "5215512345678") is None

    def test_proposal_store_expired_item_returns_none(self):
        """Dado ProposalStore con una propuesta expirada (antigüedad > 1800s).

        Cuando se consulta con get().
        Entonces retorna None y desaloja la propuesta expirada.
        """
        store = pwc.ProposalStore()
        created_time = time.time() - 2000
        proposal = pwc.PendingPromptProposal(
            bot_id=10,
            admin_wa_id="5215512345678",
            summary="Expirado",
            candidate_prompt="PROMPT",
            created_at=created_time,
            ttl_seconds=1800,
        )
        store.set(proposal)
        assert store.get(10, "5215512345678", current_time=time.time()) is None


# ==============================================================================
# 4. PRUEBAS DE INTEGRACIÓN: FLUJO COMPLETO WHATSAPP (#prompt)
# ==============================================================================

class TestPromptWhatsAppControlIntegration:
    """Pruebas de integración del flujo de WhatsApp para el comando #prompt."""

    @pytest.mark.asyncio
    async def test_unauthorized_sender_is_not_intercepted(self, sample_bot):
        """Dado un mensaje '#prompt Cambiar horario' enviado por un usuario NO administrador.

        Cuando se procesa el mensaje.
        Entonces no es interceptado (handled=False), no envía WhatsApp y no llama a IA ni BD.
        """
        unauthorized_wa = "5215599990000"
        with patch("app.prompt_changes.assist_changes") as mock_assist, \
             patch("app.whatsapp_client.send_text") as mock_send:
            res = await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=unauthorized_wa,
                text="#prompt Cambiar horario a 9 a 18hrs",
            )
            assert res.get("handled") is False
            mock_assist.assert_not_called()
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_instruction_sends_help_message(self, sample_bot):
        """Dado un administrador autorizado que envía únicamente '#prompt'.

        Cuando se procesa el mensaje.
        Entonces responde con la ayuda y el ejemplo de uso, sin generar propuesta.
        """
        admin_wa = "5215512345678"
        with patch("app.prompt_changes.assist_changes") as mock_assist, \
             patch("app.whatsapp_client.send_text", new_callable=AsyncMock) as mock_send, \
             patch("app.db.save_message", new_callable=AsyncMock) as mock_save:
            res = await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=admin_wa,
                text="#prompt",
            )
            assert res.get("handled") is True
            assert res.get("action") == "help"
            mock_assist.assert_not_called()
            mock_send.assert_awaited_once()
            sent_text = mock_send.call_args[0][1]
            assert "#prompt" in sent_text
            assert "Ejemplo" in sent_text or "ejemplo" in sent_text
            mock_save.assert_awaited_once_with(admin_wa, "assistant", sent_text, bot_id=sample_bot.id)

    @pytest.mark.asyncio
    async def test_valid_prompt_command_generates_and_stores_pending_proposal(self, sample_bot):
        """Dado un administrador autorizado que envía '#prompt Cambiar horario a 9 a 18hrs'.

        Cuando se procesa el mensaje.
        Entonces:
          1. Genera la propuesta con assist_changes.
          2. Almacena la propuesta en proposal_store con TTL de 30m.
          3. Envía WhatsApp solicitando confirmación con el formato estipulado.
        """
        admin_wa = "5215512345678"
        instruction = "Cambiar horario a 9 a 18hrs"
        summary_text = "Se amplió el horario de atención de 9 a 18 horas de lunes a viernes."
        candidate_content = "<master_prompt_doc>NUEVO PROMPT VIGENTE</master_prompt_doc>"

        mock_assist_result = {
            "ok": True,
            "blocked": False,
            "prompt": candidate_content,
            "review_receipt": "receipt_signature_token",
            "summary": summary_text,
            "changes": [],
            "published": False,
        }

        with patch("app.prompt_changes.assist_changes", new_callable=AsyncMock, return_value=mock_assist_result) as mock_assist, \
             patch("app.prompt_change_store.get_context", new_callable=AsyncMock, return_value={"bot": {"id": 10}, "previous": {}}), \
             patch("app.whatsapp_client.send_text", new_callable=AsyncMock) as mock_send, \
             patch("app.db.save_message", new_callable=AsyncMock) as mock_save:

            res = await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=admin_wa,
                text=f"#prompt {instruction}",
            )

            assert res.get("handled") is True
            assert res.get("action") == "proposal_created"
            assert res.get("summary") == summary_text
            mock_assist.assert_awaited_once()
            mock_save.assert_awaited()

            # Verifica propuesta almacenada en store
            pending = pwc.proposal_store.get(sample_bot.id, admin_wa)
            assert pending is not None
            assert pending.candidate_prompt == candidate_content
            assert pending.summary == summary_text

            # Verifica mensaje enviado al admin
            mock_send.assert_awaited_once()
            sent_msg = mock_send.call_args[0][1]
            assert "Propuesta de actualización del prompt" in sent_msg
            assert summary_text in sent_msg
            assert "Confirmar" in sent_msg or "*Confirmar*" in sent_msg
            assert "Cancelar" in sent_msg or "*Cancelar*" in sent_msg

    @pytest.mark.asyncio
    async def test_confirm_flow_publishes_prompt_and_cleans_pending_proposal(self, sample_bot):
        """Dado que existe una propuesta pendiente activa en el store.

        Cuando el administrador responde 'Confirmar' (o 'sí', 'confirm').
        Entonces:
          1. Publica el nuevo prompt en la base de datos (db.publish_bot_prompt).
          2. Limpia la propuesta del almacén.
          3. Envía el mensaje de éxito de publicación.
        """
        admin_wa = "5215512345678"
        proposal = pwc.PendingPromptProposal(
            bot_id=sample_bot.id,
            admin_wa_id=admin_wa,
            summary="Horario actualizado",
            candidate_prompt="<master_prompt_doc>PROMPT PUBLICADO</master_prompt_doc>",
            review_receipt="token_123",
            created_at=time.time(),
        )
        pwc.proposal_store.set(proposal)

        with patch("app.db.publish_bot_prompt", new_callable=AsyncMock, return_value=5) as mock_publish, \
             patch("app.whatsapp_client.send_text", new_callable=AsyncMock) as mock_send, \
             patch("app.db.save_message", new_callable=AsyncMock) as mock_save:

            res = await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=admin_wa,
                text="Confirmar",
            )

            assert res.get("handled") is True
            assert res.get("action") == "published"

            # Debe haber invocado la publicación en base de datos
            mock_publish.assert_awaited_once()
            assert mock_publish.call_args[0][0] == sample_bot.id
            assert mock_publish.call_args[0][1] == "<master_prompt_doc>PROMPT PUBLICADO</master_prompt_doc>"

            mock_save.assert_awaited()

            # La propuesta debe haber sido eliminada del almacén
            assert pwc.proposal_store.get(sample_bot.id, admin_wa) is None

            # Debe notificar éxito al admin
            mock_send.assert_awaited_once()
            assert "publicado y está activo" in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("confirm_word", ["confirmar", "confirm", "si", "sí", "SI", "Confirm"])
    async def test_confirm_variants_all_trigger_publication(self, sample_bot, confirm_word: str):
        """Dado que existe una propuesta pendiente.

        Cuando el admin envía variantes como 'confirmar', 'confirm', 'si', 'sí', 'SI'.
        Entonces todas deben desencadenar la publicación del nuevo prompt.
        """
        admin_wa = "5215512345678"
        proposal = pwc.PendingPromptProposal(
            bot_id=sample_bot.id,
            admin_wa_id=admin_wa,
            summary="Ajuste",
            candidate_prompt="PROMPT Válido",
            created_at=time.time(),
        )
        pwc.proposal_store.set(proposal)

        with patch("app.db.publish_bot_prompt", new_callable=AsyncMock, return_value=6) as mock_publish, \
             patch("app.whatsapp_client.send_text", new_callable=AsyncMock), \
             patch("app.db.save_message", new_callable=AsyncMock):

            res = await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=admin_wa,
                text=confirm_word,
            )
            assert res.get("handled") is True
            assert res.get("action") == "published"
            mock_publish.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cancel_word", ["cancelar", "cancel", "no", "NO", "Cancelar"])
    async def test_cancel_flow_discards_proposal_without_publishing(self, sample_bot, cancel_word: str):
        """Dado que existe una propuesta pendiente en el store.

        Cuando el administrador responde 'Cancelar' (o 'no', 'cancel').
        Entonces:
          1. NO publica nada en la BD.
          2. Limpia la propuesta del almacén.
          3. Envía confirmación de cancelación.
        """
        admin_wa = "5215512345678"
        proposal = pwc.PendingPromptProposal(
            bot_id=sample_bot.id,
            admin_wa_id=admin_wa,
            summary="Cambio no deseado",
            candidate_prompt="PROMPT DESCARTADO",
            created_at=time.time(),
        )
        pwc.proposal_store.set(proposal)

        with patch("app.db.publish_bot_prompt", new_callable=AsyncMock) as mock_publish, \
             patch("app.whatsapp_client.send_text", new_callable=AsyncMock) as mock_send, \
             patch("app.db.save_message", new_callable=AsyncMock):

            res = await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=admin_wa,
                text=cancel_word,
            )

            assert res.get("handled") is True
            assert res.get("action") == "cancelled"

            # Nunca debe publicar
            mock_publish.assert_not_called()

            # Propuesta eliminada
            assert pwc.proposal_store.get(sample_bot.id, admin_wa) is None

            # Notificación de cancelación enviada
            mock_send.assert_awaited_once()
            assert "cancelada" in mock_send.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_expired_proposal_is_rejected_on_confirm(self, sample_bot):
        """Dado que una propuesta fue generada hace más de 30 minutos (TTL superado).

        Cuando el administrador responde 'Confirmar'.
        Entonces:
          1. NO publica el prompt en BD.
          2. Limpia la propuesta expirada.
          3. Responde que la propuesta ha expirado.
        """
        admin_wa = "5215512345678"
        proposal = pwc.PendingPromptProposal(
            bot_id=sample_bot.id,
            admin_wa_id=admin_wa,
            summary="Propuesta vieja",
            candidate_prompt="PROMPT VIEJO",
            created_at=time.time() - 2500,  # > 1800s
            ttl_seconds=1800,
        )
        pwc.proposal_store.set(proposal)

        with patch("app.db.publish_bot_prompt", new_callable=AsyncMock) as mock_publish, \
             patch("app.whatsapp_client.send_text", new_callable=AsyncMock) as mock_send, \
             patch("app.db.save_message", new_callable=AsyncMock):

            res = await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=admin_wa,
                text="Confirmar",
            )

            assert res.get("handled") is True
            assert res.get("action") == "expired"
            mock_publish.assert_not_called()
            assert pwc.proposal_store.get(sample_bot.id, admin_wa) is None
            mock_send.assert_awaited_once()
            assert "expirado" in mock_send.call_args[0][1].lower()

    @pytest.mark.asyncio
    async def test_new_prompt_command_replaces_prior_pending_proposal(self, sample_bot):
        """Dado que ya existe una propuesta pendiente A.

        Cuando el administrador envía un nuevo comando '#prompt <instrucción B>'.
        Entonces la propuesta A es reemplazada por la propuesta B.
        Y cuando responde 'Confirmar', se publica la propuesta B.
        """
        admin_wa = "5215512345678"
        prop_a = pwc.PendingPromptProposal(
            bot_id=sample_bot.id,
            admin_wa_id=admin_wa,
            summary="Propuesta A (antigua)",
            candidate_prompt="PROMPT A",
            created_at=time.time(),
        )
        pwc.proposal_store.set(prop_a)

        mock_assist_result_b = {
            "ok": True,
            "blocked": False,
            "prompt": "PROMPT B (NUEVO)",
            "summary": "Propuesta B (nueva)",
            "review_receipt": "token_b",
        }

        with patch("app.prompt_changes.assist_changes", new_callable=AsyncMock, return_value=mock_assist_result_b), \
             patch("app.prompt_change_store.get_context", new_callable=AsyncMock, return_value={"bot": {"id": 10}, "previous": {}}), \
             patch("app.whatsapp_client.send_text", new_callable=AsyncMock), \
             patch("app.db.save_message", new_callable=AsyncMock):

            # Admin envía comando para propuesta B
            await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=admin_wa,
                text="#prompt Cambiar a B",
            )

            # Verifica reemplazo en store
            current = pwc.proposal_store.get(sample_bot.id, admin_wa)
            assert current is not None
            assert current.summary == "Propuesta B (nueva)"
            assert current.candidate_prompt == "PROMPT B (NUEVO)"

        # Ahora confirma y verifica que se publica B
        with patch("app.db.publish_bot_prompt", new_callable=AsyncMock) as mock_publish, \
             patch("app.whatsapp_client.send_text", new_callable=AsyncMock), \
             patch("app.db.save_message", new_callable=AsyncMock):

            await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=admin_wa,
                text="Confirmar",
            )
            mock_publish.assert_awaited_once_with(sample_bot.id, "PROMPT B (NUEVO)")

    @pytest.mark.asyncio
    async def test_normal_messages_without_pending_proposal_are_not_intercepted(self, sample_bot):
        """Dado que NO existe ninguna propuesta pendiente en el almacén.

        Cuando el administrador escribe 'Confirmar' o 'Cancelar' o 'Hola'.
        Entonces el manejador devuelve handled=False para no interferir con la conversación normal.
        """
        admin_wa = "5215512345678"
        with patch("app.whatsapp_client.send_text") as mock_send:
            res = await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=admin_wa,
                text="Confirmar",
            )
            assert res.get("handled") is False
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_assist_changes_error_sends_explanation_and_stores_nothing(self, sample_bot):
        """Dado que assist_changes genera una excepción ChangeError (ej. regla bloqueada).

        Cuando se procesa el comando #prompt.
        Entonces envía al admin el mensaje de error y no guarda propuesta pendiente.
        """
        admin_wa = "5215512345678"
        with patch("app.prompt_changes.assist_changes", new_callable=AsyncMock, side_effect=prompt_changes.ChangeError("Conflicto con la regla de negocio CON-001")), \
             patch("app.prompt_change_store.get_context", new_callable=AsyncMock, return_value={"bot": {"id": 10}, "previous": {}}), \
             patch("app.whatsapp_client.send_text", new_callable=AsyncMock) as mock_send, \
             patch("app.db.save_message", new_callable=AsyncMock):

            res = await pwc.handle_prompt_whatsapp_message(
                bot=sample_bot,
                wa_id=admin_wa,
                text="#prompt Eliminar garantía obligatoria",
            )

            assert res.get("handled") is True
            assert res.get("action") == "error"
            assert pwc.proposal_store.get(sample_bot.id, admin_wa) is None
            mock_send.assert_awaited_once()
            sent_msg = mock_send.call_args[0][1]
            assert "CON-001" in sent_msg or "Conflicto" in sent_msg

    @pytest.mark.asyncio
    async def test_webhook_main_process_message_intercepts_prompt(self, sample_bot):
        """Dado un webhook entrante con '#prompt Actualizar horario'.

        Cuando main._process_message_impl procesa el mensaje de un admin.
        Entonces se intercepta, guarda mensaje y no invoca openai_client.complete.
        """
        from app import main

        msg = {
            "wa_id": "5215512345678",
            "phone_number_id": "phone_id_demo_10",
            "display_phone_number": "5215500001111",
            "message_id": "prompt_webhook_test_1",
            "type": "text",
            "text": "#prompt Actualizar horario a 9 a 18hrs",
        }

        mock_assist_result = {
            "ok": True,
            "blocked": False,
            "prompt": "<prompt>Nuevo</prompt>",
            "summary": "Horario actualizado",
            "review_receipt": "receipt_token",
        }

        with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=sample_bot)), \
             patch.object(main.db, "was_processed", AsyncMock(return_value=False)), \
             patch.object(main.db, "mark_processed", AsyncMock(return_value=True)), \
             patch.object(main.db, "save_message", AsyncMock()) as mock_save, \
             patch.object(main.follow_ups, "cancel", AsyncMock()) as mock_cancel, \
             patch("app.prompt_changes.assist_changes", new_callable=AsyncMock, return_value=mock_assist_result), \
             patch("app.prompt_change_store.get_context", new_callable=AsyncMock, return_value={"bot": {"id": 10}, "previous": {}}), \
             patch("app.whatsapp_client.send_text", new_callable=AsyncMock) as mock_send, \
             patch.object(main.openai_client, "complete", AsyncMock()) as mock_openai:

            await main._process_message_impl(msg, {})

            mock_cancel.assert_awaited_once_with("5215512345678", sample_bot.id)
            mock_save.assert_awaited()
            mock_send.assert_awaited()
            mock_openai.assert_not_called()
