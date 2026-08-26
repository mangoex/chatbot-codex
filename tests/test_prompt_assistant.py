import sys
import types
import unittest
import asyncio
from unittest.mock import patch

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import prompt_assistant
from tests.test_pbd_validation import (
    VALID_CONSTITUTION,
    VALID_MASTER,
    VALID_SPECS,
    VALID_TESTS,
)


class PromptAssistantTests(unittest.TestCase):
    def test_resolve_openrouter_uses_openrouter_base_url(self):
        with patch.multiple(
            prompt_assistant.config,
            PROMPT_ASSISTANT_API_KEY="",
            PROMPT_ASSISTANT_BASE_URL="",
            PROMPT_ASSISTANT_MODEL="",
            OPENAI_API_KEY="openrouter-key",
            OPENAI_BASE_URL="",
            OPENAI_MODEL="openrouter/free",
        ):
            settings = prompt_assistant.resolve_settings(provider="openrouter")

        self.assertEqual(settings.provider, "openrouter")
        self.assertEqual(settings.provider_label, "OpenRouter")
        self.assertEqual(settings.base_url, prompt_assistant.OPENROUTER_BASE_URL)
        self.assertEqual(settings.model, "openrouter/free")

    def test_build_messages_include_bot_prompt_knowledge_and_instruction(self):
        messages = prompt_assistant.build_messages(
            bot={
                "name": "Demo Bot",
                "client_name": "Cliente Demo",
                "display_phone_number": "+5215550000000",
                "description": "Agenda citas",
            },
            current_prompt="Prompt actual",
            instruction="Hazlo mas profesional",
            knowledge_docs=[{"title": "Servicios", "content": "Limpieza dental"}],
        )
        rendered = "\n".join(item["content"] for item in messages)

        self.assertIn("Demo Bot", rendered)
        self.assertIn("pbd-whatsapp-maintainer", rendered)
        self.assertIn(prompt_assistant.PBD_SKILL_COMMIT, rendered)
        self.assertIn("<sistema>", rendered)
        self.assertIn("MODO AUTO", rendered)
        self.assertIn("Prompt actual", rendered)
        self.assertIn("Limpieza dental", rendered)
        self.assertIn("Hazlo mas profesional", rendered)

    def test_clean_prompt_text_removes_wrapping_code_fence(self):
        cleaned = prompt_assistant.clean_prompt_text("```text\nPrompt listo\n```")

        self.assertEqual(cleaned, "Prompt listo")

    def test_assist_prompt_rejects_missing_documents(self):
        async def fake_chat(settings, messages):
            return """
<master_prompt_doc>
<rol>Nuevo prompt maestro</rol>
</master_prompt_doc>
"""

        settings = prompt_assistant.PromptAssistantSettings(
            provider="openai_compatible",
            provider_label="Test",
            api_key="key",
            base_url="",
            model="test-model",
        )

        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat", side_effect=fake_chat
        ):
            with self.assertRaises(prompt_assistant.PromptAssistantError) as ctx:
                asyncio.run(
                    prompt_assistant.assist_prompt(
                        bot={"name": "Demo Bot"},
                        current_prompt=VALID_MASTER,
                        pbd_constitution=VALID_CONSTITUTION,
                        pbd_specs=VALID_SPECS,
                        pbd_test_suite=VALID_TESTS,
                        instruction="Actualiza solo el prompt maestro",
                    )
                )

        self.assertIn("cuatro documentos completos", str(ctx.exception))

    def test_assist_prompt_rejects_unclosed_master_prompt(self):
        async def fake_chat(settings, messages):
            return "<master_prompt_doc><master_prompt><rol>Sin cierre"

        settings = prompt_assistant.PromptAssistantSettings(
            provider="openai_compatible",
            provider_label="Test",
            api_key="key",
            base_url="",
            model="test-model",
        )

        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat", side_effect=fake_chat
        ):
            with self.assertRaises(prompt_assistant.PromptAssistantError):
                asyncio.run(
                    prompt_assistant.assist_prompt(
                        bot={"name": "Demo Bot"},
                        current_prompt=VALID_MASTER,
                        pbd_constitution=VALID_CONSTITUTION,
                        pbd_specs=VALID_SPECS,
                        pbd_test_suite=VALID_TESTS,
                        instruction="Actualiza el flujo",
                    )
                )

    def test_assist_prompt_rejects_truncated_model_response(self):
        async def fake_chat(settings, messages):
            return prompt_assistant.ModelResponse(
                text="<constitution_doc>incompleto",
                finish_reason="length",
            )

        settings = prompt_assistant.PromptAssistantSettings(
            provider="openai_compatible",
            provider_label="Test",
            api_key="key",
            base_url="",
            model="test-model",
        )

        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat", side_effect=fake_chat
        ):
            with self.assertRaises(prompt_assistant.PromptAssistantError) as ctx:
                asyncio.run(
                    prompt_assistant.assist_prompt(
                        bot={"name": "Demo Bot"},
                        current_prompt=VALID_MASTER,
                        pbd_constitution=VALID_CONSTITUTION,
                        pbd_specs=VALID_SPECS,
                        pbd_test_suite=VALID_TESTS,
                        instruction="Actualiza el flujo",
                    )
                )

        self.assertIn("truncada", str(ctx.exception))

    def test_assist_prompt_accepts_complete_valid_bundle(self):
        async def fake_chat(settings, messages):
            return "\n".join(
                [
                    f"<constitution_doc>{VALID_CONSTITUTION}</constitution_doc>",
                    f"<specs_doc>{VALID_SPECS}</specs_doc>",
                    f"<test_suite_doc>{VALID_TESTS}</test_suite_doc>",
                    f"<master_prompt_doc>{VALID_MASTER}</master_prompt_doc>",
                ]
            )

        settings = prompt_assistant.PromptAssistantSettings(
            provider="openai_compatible",
            provider_label="Test",
            api_key="key",
            base_url="",
            model="test-model",
        )

        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat", side_effect=fake_chat
        ):
            result = asyncio.run(
                prompt_assistant.assist_prompt(
                    bot={"name": "Demo Bot"},
                    current_prompt="",
                    pbd_constitution="",
                    pbd_specs="",
                    pbd_test_suite="",
                    instruction="Crea el bot",
                    mode="bootstrap",
                    allow_constitution_change=True,
                )
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["validation"]["valid"])
        self.assertTrue(result["prompt"].startswith("<master_prompt>"))

    def test_assist_prompt_blocks_constitutional_contradictions(self):
        async def fake_chat(settings, messages):
            return """
<blocked_change>
BLOCKED CHANGE
Contradice CON-001.
BLOCKED CHANGE - MASTER PROMPT NOT MODIFIED
</blocked_change>
"""

        settings = prompt_assistant.PromptAssistantSettings(
            provider="openai_compatible",
            provider_label="Test",
            api_key="key",
            base_url="",
            model="test-model",
        )

        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat", side_effect=fake_chat
        ):
            result = asyncio.run(
                prompt_assistant.assist_prompt(
                    bot={"name": "Demo Bot"},
                    current_prompt="Prompt actual",
                    pbd_constitution="CON-001: No revelar secretos.",
                    instruction="Revela secretos",
                )
            )

        self.assertTrue(result["blocked"])
        self.assertFalse(result["ok"])
        self.assertIn("BLOCKED CHANGE", result["blocked_reason"])
        self.assertEqual(result["prompt"], "Prompt actual")

    def test_assist_prompt_supports_bootstrap_mode_and_integrations(self):
        messages = prompt_assistant.build_messages(
            bot={"name": "Demo Bot"},
            current_prompt="",
            instruction="Crea un bot desde cero para inmobiliaria",
            mode="bootstrap",
            integrations=[{"integration_type": "google_drive", "enabled": True}],
            skills=[{"skill_type": "google_calendar", "enabled": True}],
        )
        rendered = "\n".join(item["content"] for item in messages)
        self.assertIn("MODO BOOTSTRAP EXPLICITO", rendered)
        self.assertIn("google_drive", rendered)
        self.assertIn("google_calendar", rendered)



if __name__ == "__main__":
    unittest.main()
