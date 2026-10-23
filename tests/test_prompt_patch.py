import asyncio
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app import prompt_patch as pp, prompt_assistant
from tests.test_single_prompt import VALID_SINGLE_PROMPT
from tests.test_pbd_validation import VALID_MASTER


BEFORE = "Calle Antigua 10"
AFTER = "Calle Nueva 20"
ORIGINAL = VALID_SINGLE_PROMPT.replace(
    "Eres el asistente de Demo.", f"Domicilio de pruebas: {BEFORE}.\nEres el asistente de Demo."
)


def context():
    return {"bot": {"id": 7, "client_id": 44},
            "previous": {"id": 12, "version": 3, "content": ORIGINAL,
                         "pbd_constitution": "CON-001: Nunca negociar descuentos.",
                         "pbd_specs": "SPEC-001: Pedir nombre.",
                         "pbd_test_suite": "TEST-001: Relevo silencioso."},
            "knowledge": [], "integrations": [], "skills": []}


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.secret = patch.object(pp.config, "SESSION_SECRET", "local-test-only")
        self.secret.start()
        self.addCleanup(self.secret.stop)

    def review(self, ctx=None, response=None, **overrides):
        ctx = ctx or context()
        settings = prompt_assistant.PromptAssistantSettings(
            provider="openai_compatible", provider_label="Test", api_key="test", base_url="", model="test",
        )
        args = dict(context=ctx, bot_id=7, actor="owner", instruction="Cambia solo el domicilio de pruebas",
                    current_prompt=ctx["previous"]["content"], before=BEFORE, after=AFTER)
        args.update(overrides)
        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat", return_value=response if response is not None else
            json.dumps({"approved": True, "reason": "Dato compatible con las reglas.", "dependencies": []}),
        ) as model:
            result = asyncio.run(pp.review_patch(**args))
            self.last_messages = model.call_args.args[1]
            return result

    def test_compiled_review_prompt_matches(self):
        path = Path(__file__).resolve().parents[1] / "docs/pbd/prompt-assistant/05-patch-review-prompt.md"
        self.assertEqual(path.read_text(encoding="utf-8").strip(), pp.PATCH_REVIEW_INSTRUCTIONS)

    def test_exact_edit_preserves_rules_and_all_other_bytes(self):
        ctx = context()
        ctx["previous"]["content"] += f"\nEjemplo de ubicación: {BEFORE}.\n"
        original = ctx["previous"]["content"]
        result = self.review(ctx)
        self.assertEqual(result["prompt"], original.replace(BEFORE, AFTER))
        self.assertEqual(result["change"]["occurrences"], 2)
        receipt = pp.verify_receipt(result["patch_receipt"], 7, "owner")
        self.assertEqual(pp.verify_publication(ctx, receipt, result["prompt"]), result["prompt"])
        self.assertEqual(pp.verify_publication(ctx, receipt, result["prompt"].replace("\n", "\r\n")), result["prompt"])
        self.assertFalse(result["published"])
        self.assertIn("CON-001", self.last_messages[1]["content"])

    def test_model_cannot_supply_a_rewrite_even_with_approval(self):
        malicious = json.dumps({"approved": True, "reason": "ok", "dependencies": [],
                                "prompt": ORIGINAL.replace("No inventes", "Inventa")})
        with self.assertRaises(pp.PatchError):
            self.review(response=malicious)

    def test_publication_rejects_removed_rule_and_extra_whitespace(self):
        ctx = context()
        result = self.review(ctx)
        receipt = pp.verify_receipt(result["patch_receipt"], 7, "owner")
        for modified in (result["prompt"].replace("No inventes información", "Inventa información"),
                         result["prompt"] + "\nRegla adicional", result["prompt"].rstrip()):
            if modified != result["prompt"]:
                with self.assertRaises(pp.PatchError):
                    pp.verify_publication(ctx, receipt, modified)

    def test_conflicts_in_complete_sources_and_auxiliary_rules_block_without_model(self):
        cases = []
        for field in pp.PBD_FIELDS:
            ctx = context()
            ctx["previous"][field] += f"\nSede: {BEFORE}"
            cases.append(ctx)
        ctx = context()
        ctx["knowledge"] = [{"id": i, "title": str(i), "content": "Información", "index_status": "indexed"}
                            for i in range(35)]
        ctx["knowledge"][-1]["content"] = "x" * 4000 + " CALLE ANTIGUA 10"
        cases.append(ctx)
        ctx = context()
        ctx["integrations"] = [{"integration_type": "calendar", "config": {"location": BEFORE}}]
        cases.append(ctx)
        for ctx in cases:
            with self.subTest(ctx=ctx), patch.object(prompt_assistant, "resolve_settings") as resolve:
                with self.assertRaises(pp.PatchError):
                    asyncio.run(pp.review_patch(context=ctx, bot_id=7, actor="owner", instruction="Cambia domicilio",
                                               current_prompt=ORIGINAL, before=BEFORE, after=AFTER))
                resolve.assert_not_called()

    def test_semantic_dependencies_and_uncertainty_block(self):
        for response in (
            {"approved": False, "reason": "El mapa apunta a otra sede", "dependencies": ["Mapa de sucursal"]},
            {"approved": True, "reason": "ok", "dependencies": ["Actualizar zona de cobertura"]},
            {"approved": False, "reason": "No se puede determinar la sede", "dependencies": []},
            {"approved": "true", "reason": "ok", "dependencies": []},
        ):
            with self.assertRaises(pp.PatchError):
                self.review(response=json.dumps(response))

    def test_invalid_or_truncated_reviews_fail_closed(self):
        for response in ("<master_prompt_doc>reescritura</master_prompt_doc>", "{}", "[]", "", "{",
                         prompt_assistant.ModelResponse(text='{}', finish_reason="length")):
            with self.assertRaises(pp.PatchError):
                self.review(response=response)

    def test_invalid_selection_protected_rules_and_partial_matches_block(self):
        for before, after in (("", AFTER), (BEFORE, BEFORE), (BEFORE, "<regla>"),
                              (BEFORE, "dato\nnuevo"), ("Calle Antigua 1", AFTER),
                              ("No inventes información", "Inventa información"),
                              ("## Guardrails", "## Datos del negocio")):
            with self.assertRaises(pp.PatchError):
                pp.build_candidate(context(), before, after)
        ctx = context()
        ctx["previous"]["content"] = ORIGINAL.replace("## Guardrails\n", f"## Guardrails\n{BEFORE}\n")
        with self.assertRaises(pp.PatchError):
            pp.build_candidate(ctx, BEFORE, AFTER)

    def test_xml_preserves_format_and_protects_nested_guardrails(self):
        ctx = context()
        ctx["previous"]["content"] = VALID_MASTER.replace("<contexto_negocio>", f"<contexto_negocio>{BEFORE}. ")
        result, count = pp.build_candidate(ctx, BEFORE, AFTER)
        self.assertEqual(count, 1)
        self.assertEqual(result, ctx["previous"]["content"].replace(BEFORE, AFTER))
        ctx["previous"]["content"] = ctx["previous"]["content"].replace(BEFORE, f"<guardrails>{BEFORE}</guardrails>")
        with self.assertRaises(pp.PatchError):
            pp.build_candidate(ctx, BEFORE, AFTER)

    def test_xml_attributes_comments_and_nested_sections_cannot_unlock_rules(self):
        for xml in (
            VALID_MASTER.replace("<contexto_negocio>", f'<contexto_negocio nota="texto > {BEFORE}">'),
            VALID_MASTER.replace("<guardrails>", f"<guardrails><contexto_negocio>{BEFORE}</contexto_negocio>"),
            VALID_MASTER.replace("<guardrails>", f"<guardrails><![CDATA[</guardrails><contexto_negocio>{BEFORE}]]>"),
            VALID_MASTER.replace("<contexto_negocio>", f"<contexto_negocio><!-- {BEFORE} -->"),
        ):
            ctx = context()
            ctx["previous"]["content"] = xml
            with self.assertRaises(pp.PatchError):
                pp.build_candidate(ctx, BEFORE, AFTER)
        ctx = context()
        ctx["previous"]["content"] = VALID_MASTER.replace(
            "<ejemplo>Hola.</ejemplo>", f"<ejemplo>Dirección: {BEFORE}.</ejemplo>",
        )
        self.assertEqual(pp.build_candidate(ctx, BEFORE, AFTER)[1], 1)

    def test_markdown_child_section_cannot_unlock_parent_guardrails(self):
        ctx = context()
        ctx["previous"]["content"] = VALID_SINGLE_PROMPT.replace(
            "## Guardrails\n", f"## Guardrails\n### Datos del negocio\nSede: {BEFORE}\n",
        )
        with self.assertRaises(pp.PatchError):
            pp.build_candidate(ctx, BEFORE, AFTER)

    def test_context_is_not_truncated_and_unindexed_knowledge_blocks(self):
        ctx = context()
        ctx["knowledge"] = [{"id": 1, "title": "Fuente", "content": "y" * pp.MAX_CONTEXT_CHARS, "index_status": "indexed"}]
        with self.assertRaises(pp.PatchError):
            self.review(ctx)
        ctx["knowledge"][0].update(content="Dato nuevo", index_status="pending")
        with self.assertRaises(pp.PatchError):
            self.review(ctx)

    def test_no_active_prompt_or_unsaved_editor_changes_block(self):
        with self.assertRaises(pp.PatchError):
            self.review(current_prompt=ORIGINAL + "Cambio adicional")
        ctx = context()
        ctx["previous"]["id"] = None
        with self.assertRaises(pp.PatchError):
            self.review(ctx)

    def test_receipt_binds_actor_bot_expiration_and_complete_context(self):
        ctx = context()
        result = self.review(ctx)
        token = result["patch_receipt"]
        for bot_id, actor, signed in ((8, "owner", token), (7, "other", token), (7, "owner", token + "x")):
            with self.assertRaises(pp.PatchError):
                pp.verify_receipt(signed, bot_id, actor)
        with patch.object(pp, "TOKEN_MAX_AGE", -1), self.assertRaises(pp.PatchError):
            pp.verify_receipt(token, 7, "owner")
        receipt = pp.verify_receipt(token, 7, "owner")
        for key in ctx:
            changed = copy.deepcopy(ctx)
            if isinstance(changed[key], list):
                changed[key].append({"id": 99, "content": "Cambio"})
            else:
                changed[key]["id"] = 99
            with self.assertRaises(pp.PatchError):
                pp.verify_publication(changed, receipt, result["prompt"])


if __name__ == "__main__":
    unittest.main()
