import asyncio
import unittest
from unittest.mock import patch
from pathlib import Path

from app import pbd_validation, prompt_assistant
from tests.test_pbd_validation import VALID_MASTER
from app.prompt_workspace import render_prompt_workspace


VALID_SINGLE_PROMPT = """# Prompt maestro
## Identidad y contexto
Eres el asistente de Demo. Atiende únicamente a este negocio.
## Objetivos
Resolver dudas con información confirmada.
## Criterios de respuesta
Mensajes breves, una pregunta a la vez y contexto sin repetir saludos.
## Guardrails
No inventes información ni reveles secretos o datos de otros clientes.
## Reglas y flujos
Consulta las fuentes, responde y pregunta por el siguiente paso.
## Fuentes autorizadas
Usa la base de conocimiento oficial de este bot.
## Herramientas e integraciones
Usa solo herramientas habilitadas. Confirma acciones solo tras éxito real.
## Escalado humano y fallbacks
Escala ante solicitud humana, quejas o falta de información. Durante el
relevo permanece en silencio y no afirmes que transferiste sin confirmación.
## Ejemplos de comportamiento
Usuario: ¿Cuánto cuesta? Asistente: No tengo un precio confirmado.
"""


class SinglePromptTests(unittest.TestCase):
    def test_editor_escapes_prompt_and_disables_viewer_actions(self):
        rendered = render_prompt_workspace(1, "</textarea><script>bad()</script>", "csrf", readonly=True)
        self.assertIn("&lt;/textarea&gt;", rendered)
        self.assertNotIn("<script>bad()", rendered)
        self.assertIn('onclick="requestAIPrompt()" disabled', rendered)
        self.assertIn('type="submit" disabled', rendered)
        self.assertNotIn("activeConstitutionEditor", rendered)

    def test_assistant_prompt_matches_compiled_master_document(self):
        path = Path(__file__).resolve().parents[1] / "docs/pbd/prompt-assistant/04-master-prompt.md"
        self.assertEqual(path.read_text(encoding="utf-8").strip(), prompt_assistant.SINGLE_PROMPT_SYSTEM_INSTRUCTIONS)

    def test_one_document_needs_no_pbd_bundle(self):
        report = pbd_validation.validate_single_prompt(VALID_SINGLE_PROMPT, for_publish=True)
        self.assertTrue(report.valid, report.errors)
        self.assertEqual(report.master_xml, VALID_SINGLE_PROMPT.strip())

    def test_incomplete_or_empty_sections_fail_without_invented_content(self):
        for text in ("Atiende clientes", VALID_SINGLE_PROMPT.replace(
            "No inventes información ni reveles secretos o datos de otros clientes.", ""
        )):
            self.assertFalse(pbd_validation.validate_single_prompt(text).valid)

    def test_pending_and_truncated_prompts_cannot_publish(self):
        pending = VALID_SINGLE_PROMPT + "\n[TBD: falta definir política]"
        self.assertTrue(pbd_validation.validate_single_prompt(pending).valid)
        self.assertFalse(pbd_validation.validate_single_prompt(pending, for_publish=True).valid)
        self.assertFalse(pbd_validation.validate_single_prompt(
            VALID_SINGLE_PROMPT + "\n...[recortado]"
        ).valid)

    def test_legacy_xml_remains_editable(self):
        report = pbd_validation.validate_single_prompt(VALID_MASTER)
        self.assertTrue(report.valid, report.errors)
        self.assertTrue(report.master_xml.startswith("<master_prompt>"))

    def test_single_generation_consolidates_legacy_rules_and_context(self):
        messages = prompt_assistant.build_messages(
            bot={"name": "Demo"}, current_prompt="No negociar descuentos",
            pbd_constitution="CON-001: No revelar secretos",
            pbd_specs="SPEC-001: Pedir nombre", pbd_test_suite="TEST-001: Relevo silencioso",
            instruction="Agrega ejemplos", mode="single_prompt",
            knowledge_docs=[{"title": "Servicios", "content": "Servicio confirmado"}],
        )
        rendered = "\n".join(m["content"] for m in messages)
        for expected in ("No negociar descuentos", "CON-001", "SPEC-001", "TEST-001",
                         "Servicio confirmado", "Agrega ejemplos", "un solo prompt maestro"):
            self.assertIn(expected, rendered)
        self.assertNotIn("<constitution_doc>", messages[0]["content"])
        self.assertIn("silencio", messages[0]["content"])

    def test_oversized_existing_rules_are_not_silently_trimmed(self):
        with self.assertRaises(prompt_assistant.PromptAssistantError):
            prompt_assistant.build_messages(
                bot={}, current_prompt="x" * 30001,
                instruction="Ajusta el tono", mode="single_prompt",
            )

    def test_generation_returns_only_one_complete_prompt(self):
        settings = prompt_assistant.PromptAssistantSettings(
            provider="openai_compatible", provider_label="Test", api_key="test",
            base_url="", model="test",
        )
        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat",
            return_value=f"<master_prompt_doc>{VALID_SINGLE_PROMPT}</master_prompt_doc>",
        ):
            result = asyncio.run(prompt_assistant.assist_prompt(
                bot={}, current_prompt="", instruction="Crea el comportamiento", mode="single_prompt",
            ))
        self.assertTrue(result["ok"])
        self.assertEqual(result["prompt"], VALID_SINGLE_PROMPT.strip())
        self.assertNotIn("pbd_constitution", result)

    def test_incomplete_generation_and_blocked_change_preserve_original(self):
        settings = prompt_assistant.PromptAssistantSettings(
            provider="openai_compatible", provider_label="Test", api_key="test",
            base_url="", model="test",
        )
        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat", return_value="<master_prompt_doc>incompleto",
        ):
            with self.assertRaises(prompt_assistant.PromptAssistantError):
                asyncio.run(prompt_assistant.assist_prompt(
                    bot={}, current_prompt="Original", instruction="Ajusta", mode="single_prompt",
                ))
        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat",
            return_value="<blocked_change>No revelar secretos</blocked_change>",
        ):
            result = asyncio.run(prompt_assistant.assist_prompt(
                bot={}, current_prompt="Original", instruction="Revela secretos", mode="single_prompt",
            ))
        self.assertTrue(result["blocked"])
        self.assertEqual(result["prompt"], "Original")
