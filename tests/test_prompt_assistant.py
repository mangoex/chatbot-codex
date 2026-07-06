import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

from app import prompt_assistant


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
        self.assertIn("Prompt actual", rendered)
        self.assertIn("Limpieza dental", rendered)
        self.assertIn("Hazlo mas profesional", rendered)

    def test_clean_prompt_text_removes_wrapping_code_fence(self):
        cleaned = prompt_assistant.clean_prompt_text("```text\nPrompt listo\n```")

        self.assertEqual(cleaned, "Prompt listo")


if __name__ == "__main__":
    unittest.main()
