import asyncio
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app import prompt_changes as pc, prompt_assistant
from tests.test_single_prompt import VALID_SINGLE_PROMPT
from tests.test_pbd_validation import VALID_MASTER


FACTS = "Horario: lunes a viernes de 9 a 18.\nDirección: Calle Uno 10.\nServicios: diagnóstico."
ORIGINAL = VALID_SINGLE_PROMPT.replace("## Reglas y flujos\n", "## Reglas y flujos\n" + FACTS + "\n")
REQUEST = "Los sábados también atendemos de 9 a 14; agrega el servicio de instalación."


def context():
    return {"bot": {"id": 7, "client_id": 44, "name": "Demo"},
            "previous": {"id": 12, "version": 3, "content": ORIGINAL,
                         "pbd_constitution": "CON-001: No inventar ni ofrecer descuentos.",
                         "pbd_specs": "SPEC-001: Consultar fuentes oficiales.",
                         "pbd_test_suite": "TEST-001: Relevo silencioso."},
            "knowledge": [], "integrations": [], "skills": []}


def edits():
    return [
        {"before": "Horario: lunes a viernes de 9 a 18.",
         "after": "Horario: lunes a viernes de 9 a 18; sábados de 9 a 14.",
         "occurrence": 1, "request_quote": "Los sábados también atendemos de 9 a 14"},
        {"before": "Servicios: diagnóstico.", "after": "Servicios: diagnóstico e instalación.",
         "occurrence": 1, "request_quote": "agrega el servicio de instalación"},
    ]


def proposal(changes=None):
    return {"changes": edits() if changes is None else changes,
            "summary": "Agrega el horario del sábado y el servicio de instalación.", "blocked_reason": ""}


def verdict(ctx=None, changes=None, **overrides):
    result = {"approved": True, "reason": "Compatible con reglas y fuentes.", "dependencies": [],
              "approved_changes": list(range(len(edits() if changes is None else changes))),
              "checked_sources": pc.source_ids(ctx or context())}
    result.update(overrides)
    return result


class NaturalChangeTests(unittest.TestCase):
    def setUp(self):
        self.secret = patch.object(pc.config, "SESSION_SECRET", "local-test-only")
        self.secret.start()
        self.addCleanup(self.secret.stop)

    def assist(self, ctx=None, plan=None, review=None, **overrides):
        ctx = ctx or context()
        settings = prompt_assistant.PromptAssistantSettings(
            provider="openai_compatible", provider_label="Test", api_key="test", base_url="", model="test")
        args = dict(context=ctx, bot_id=7, actor="owner", current_prompt=ctx["previous"].get("content", ""),
                    instruction=REQUEST, receipt="")
        args.update(overrides)
        responses = [json.dumps(plan if plan is not None else proposal()),
                     json.dumps(review if review is not None else verdict(ctx))]
        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat", side_effect=responses,
        ) as chat:
            result = asyncio.run(pc.assist_changes(**args))
            self.calls = chat.call_args_list
            return result

    def test_natural_hours_and_services_preserve_every_other_character(self):
        result = self.assist()
        expected = ORIGINAL
        for edit in edits():
            expected = expected.replace(edit["before"], edit["after"])
        self.assertEqual(result["prompt"], expected)
        self.assertFalse(result["published"])
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn("summary", json.loads(self.calls[1].args[1][1]["content"]))
        receipt = pc.read_receipt(result["review_receipt"], 7, "owner")
        self.assertEqual(pc.verify_publication(context(), receipt, expected), expected)

    def test_address_request_needs_no_old_value_from_owner(self):
        changes = [{"before": "Calle Uno 10", "after": "Avenida Dos 20", "occurrence": 1,
                    "request_quote": "La dirección ahora es Avenida Dos 20"}]
        result = self.assist(plan=proposal(changes), review=verdict(changes=changes),
                             instruction="La dirección ahora es Avenida Dos 20")
        self.assertEqual(result["prompt"], ORIGINAL.replace("Calle Uno 10", "Avenida Dos 20"))

    def test_core_rule_changes_and_extra_model_fields_are_blocked(self):
        changes = [{"before": "No inventes información", "after": "Inventa información", "occurrence": 1,
                    "request_quote": "agrega el servicio de instalación"}]
        with self.assertRaises(pc.ChangeError):
            self.assist(plan=proposal(changes))
        plan = proposal()
        plan["prompt"] = "Una reescritura completa"
        with self.assertRaises(pc.ChangeError):
            self.assist(plan=plan)

    def test_reviewer_blocks_unrequested_business_rule_change(self):
        extra = {"before": "Consulta las fuentes, responde y pregunta por el siguiente paso.",
                 "after": "Ofrece descuentos automáticamente.", "occurrence": 1,
                 "request_quote": "agrega el servicio de instalación"}
        with self.assertRaisesRegex(pc.ChangeError, "descuentos"):
            self.assist(plan=proposal(edits() + [extra]), review=verdict(
                changes=edits() + [extra], approved=False, reason="Descuento no solicitado: no ofrecer descuentos."))

    def test_ambiguity_dependencies_in_knowledge_and_constitution_block(self):
        with self.assertRaisesRegex(pc.ChangeError, "horario"):
            self.assist(plan={"changes": [], "summary": "", "blocked_reason": "Indica el horario nuevo."},
                        instruction="Cambia el horario")
        ctx = context()
        ctx["knowledge"] = [{"id": i, "title": f"Fuente {i}", "content": "Información", "index_status": "indexed"}
                            for i in range(35)]
        ctx["knowledge"][-1]["content"] = "x" * 3000 + "No se atiende los sábados."
        with self.assertRaisesRegex(pc.ChangeError, "Fuente 34"):
            self.assist(ctx, review=verdict(ctx, approved=False, dependencies=["Fuente 34: horario incompatible"]))
        ctx = context()
        ctx["previous"]["pbd_constitution"] += " No ofrecer instalaciones."
        with self.assertRaises(pc.ChangeError):
            self.assist(ctx, review=verdict(ctx, approved=False, reason="Conflicto constitucional"))

    def test_missing_source_or_change_coverage_cannot_be_approved(self):
        for changes in ({"checked_sources": []}, {"approved_changes": [0]},
                        {"dependencies": ["Actualizar calendario"]}, {"approved": "true"}):
            with self.assertRaises(pc.ChangeError):
                self.assist(review=verdict(**changes))

    def test_both_model_calls_receive_complete_evidence_and_untrusted_data_rules(self):
        ctx = context()
        ctx["knowledge"] = [{"id": i, "title": f"Fuente {i}", "content": "Información", "index_status": "indexed"}
                            for i in range(35)]
        ctx["knowledge"][-1]["content"] = "x" * 3000 + "ULTIMO_DATO_CONFIRMADO"
        ctx["integrations"] = [{"id": 5, "integration_type": "calendar", "enabled": True,
                                "config": {"location": "Sede"}, "config_digest": "not-for-model"}]
        self.assist(ctx)
        for call in self.calls:
            self.assertIn("ULTIMO_DATO_CONFIRMADO", call.args[1][1]["content"])
            self.assertIn("CON-001", call.args[1][1]["content"])
            self.assertIn("Fuente 34", call.args[1][1]["content"])
            self.assertNotIn("not-for-model", call.args[1][1]["content"])
            self.assertIn("incrustadas", call.args[1][0]["content"])

    def test_overlaps_missing_fragments_and_unquoted_scope_fail_closed(self):
        for change in (
            {**edits()[0], "before": "No existe"}, {**edits()[0], "occurrence": 20},
            {**edits()[0], "request_quote": "Descuento autorizado"},
            {**edits()[0], "occurrence": True}, {**edits()[0], "before": ""},
        ):
            with self.assertRaises(pc.ChangeError):
                pc.apply_changes(ORIGINAL, [change], REQUEST)
        with self.assertRaises(pc.ChangeError):
            pc.apply_changes(ORIGINAL, [edits()[0], edits()[0]], REQUEST)

    def test_repeated_service_removal_changes_only_selected_occurrence(self):
        text = ORIGINAL.replace("Servicios: diagnóstico.", "Sucursal A: diagnóstico.\nSucursal B: diagnóstico.")
        change = {"before": "diagnóstico", "after": "instalación", "occurrence": 2,
                  "request_quote": "Cambia el servicio de la sucursal B a instalación"}
        result = pc.apply_changes(text, [change], change["request_quote"])
        self.assertIn("Sucursal A: diagnóstico.", result)
        self.assertIn("Sucursal B: instalación.", result)

    def test_xml_preserves_format_and_protects_attributes_and_nested_guardrails(self):
        text = VALID_MASTER.replace("Contexto confirmado.", "Dirección: Calle Uno 10.")
        change = {"before": "Calle Uno 10", "after": "Calle Dos 20", "occurrence": 1,
                  "request_quote": "Cambia la dirección a Calle Dos 20"}
        self.assertEqual(pc.apply_changes(text, [change], change["request_quote"]),
                         text.replace("Calle Uno 10", "Calle Dos 20"))
        for xml in (
            VALID_MASTER.replace("<contexto_negocio>", '<contexto_negocio nota="texto > Calle Uno 10">'),
            VALID_MASTER.replace("<guardrails>", "<guardrails><contexto_negocio>Calle Uno 10</contexto_negocio>"),
            VALID_MASTER.replace("<guardrails>", "<guardrails><![CDATA[</guardrails><contexto_negocio>Calle Uno 10]]>"),
        ):
            with self.assertRaises(pc.ChangeError):
                pc.apply_changes(xml, [change], change["request_quote"])

    def test_markdown_nesting_cannot_unlock_guardrails(self):
        text = ORIGINAL.replace("## Guardrails\n", "## Guardrails\n### Datos del negocio\nCalle Uno 10\n")
        change = {"before": "Calle Uno 10", "after": "Calle Dos 20", "occurrence": 1,
                  "request_quote": "Cambia la dirección a Calle Dos 20"}
        with self.assertRaises(pc.ChangeError):
            pc.apply_changes(text, [change], change["request_quote"])

    def test_bad_second_review_does_not_return_candidate(self):
        settings = prompt_assistant.PromptAssistantSettings("openai_compatible", "Test", "test", "", "test")
        for raw in ("{}", "<master_prompt_doc>rewrite</master_prompt_doc>",
                    prompt_assistant.ModelResponse(json.dumps(verdict()), "length")):
            with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
                prompt_assistant, "_openai_compatible_chat", side_effect=[json.dumps(proposal()), raw],
            ), self.assertRaises(pc.ChangeError):
                asyncio.run(pc.assist_changes(context=context(), bot_id=7, actor="owner",
                                             current_prompt=ORIGINAL, instruction=REQUEST))

    def test_signed_draft_can_receive_another_natural_request(self):
        first = self.assist()
        changes = [{"before": "Calle Uno 10", "after": "Calle Dos 20", "occurrence": 1,
                    "request_quote": "Ahora cambia la dirección a Calle Dos 20"}]
        second = self.assist(plan=proposal(changes), review=verdict(changes=changes),
                             current_prompt=first["prompt"], receipt=first["review_receipt"],
                             instruction=changes[0]["request_quote"])
        self.assertEqual(second["prompt"], first["prompt"].replace("Calle Uno 10", "Calle Dos 20"))
        with self.assertRaises(pc.ChangeError):
            self.assist(current_prompt=first["prompt"] + " Otra regla", receipt=first["review_receipt"])

    def test_stale_context_wrong_actor_expiry_and_modified_result_block_save(self):
        result = self.assist()
        signed = result["review_receipt"]
        receipt = pc.read_receipt(signed, 7, "owner")
        for bot, actor in ((8, "owner"), (7, "other")):
            with self.assertRaises(pc.ChangeError):
                pc.read_receipt(signed, bot, actor)
        with patch.object(pc, "REVIEW_TTL", -1), self.assertRaises(pc.ChangeError):
            pc.read_receipt(signed, 7, "owner")
        with self.assertRaises(pc.ChangeError):
            pc.verify_publication(context(), receipt, result["prompt"].replace("No inventes", "Inventa"))
        for key in context():
            ctx = copy.deepcopy(context())
            if isinstance(ctx[key], list):
                ctx[key].append({"id": 99})
            else:
                ctx[key]["id"] = 99
            with self.assertRaises(pc.ChangeError):
                pc.verify_publication(ctx, receipt, result["prompt"])

    def test_large_context_and_unindexed_sources_do_not_get_truncated(self):
        ctx = context()
        ctx["knowledge"] = [{"id": 1, "title": "Fuente", "content": "x" * pc.MAX_CONTEXT_CHARS, "index_status": "indexed"}]
        with self.assertRaises(pc.ChangeError):
            self.assist(ctx)
        ctx["knowledge"][0].update(content="Información", index_status="pending")
        with self.assertRaises(pc.ChangeError):
            self.assist(ctx)

    def test_creation_with_full_context_is_reviewed_and_signed(self):
        ctx = context()
        ctx["previous"] = {}
        settings = prompt_assistant.PromptAssistantSettings("openai_compatible", "Test", "test", "", "test")
        with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
            prompt_assistant, "_openai_compatible_chat", side_effect=[
                f"<master_prompt_doc>{VALID_SINGLE_PROMPT}</master_prompt_doc>",
                json.dumps(verdict(ctx, changes=[])),
            ],
        ) as chat:
            result = asyncio.run(pc.assist_changes(context=ctx, bot_id=7, actor="owner", current_prompt="",
                                                   instruction="Crea un asistente para mi negocio"))
        self.assertEqual(chat.call_count, 2)
        self.assertTrue(result["review_receipt"])
        self.assertEqual(result["prompt"], VALID_SINGLE_PROMPT.strip())

    def test_truncation_invalid_json_and_duplicate_fields_fail_closed(self):
        settings = prompt_assistant.PromptAssistantSettings("openai_compatible", "Test", "test", "", "test")
        for response in ("{}", "[]", "{", '{"changes":[],"changes":[]}',
                         prompt_assistant.ModelResponse("{}", "length")):
            with patch.object(prompt_assistant, "resolve_settings", return_value=settings), patch.object(
                prompt_assistant, "_openai_compatible_chat", return_value=response,
            ), self.assertRaises(pc.ChangeError):
                asyncio.run(pc.assist_changes(context=context(), bot_id=7, actor="owner",
                                             current_prompt=ORIGINAL, instruction=REQUEST))

    def test_service_removal_can_delete_a_line_without_changing_other_rules(self):
        text = ORIGINAL.replace("Servicios: diagnóstico.", "Servicios: diagnóstico.\nServicio de entrega.\n")
        change = {"before": "Servicio de entrega.\n", "after": "", "occurrence": 1,
                  "request_quote": "Retira el servicio de entrega"}
        self.assertEqual(pc.apply_changes(text, [change], change["request_quote"]),
                         text.replace("Servicio de entrega.\n", ""))

    def test_expired_signed_draft_can_be_reviewed_again_but_not_published(self):
        first = self.assist()
        change = {"before": "Calle Uno 10", "after": "Calle Dos 20", "occurrence": 1,
                  "request_quote": "Cambia la dirección a Calle Dos 20"}
        with patch.object(pc, "REVIEW_TTL", -1):
            with self.assertRaises(pc.ChangeError):
                pc.read_receipt(first["review_receipt"], 7, "owner")
            result = self.assist(plan=proposal([change]), review=verdict(changes=[change]),
                                 current_prompt=first["prompt"], receipt=first["review_receipt"],
                                 instruction=change["request_quote"])
        self.assertIn("Calle Dos 20", result["prompt"])

    def test_already_applied_request_can_renew_review_without_rewriting(self):
        first = self.assist()
        result = self.assist(plan=proposal([]), review=verdict(changes=[]),
                             current_prompt=first["prompt"], receipt=first["review_receipt"])
        self.assertEqual(result["prompt"], first["prompt"])

    def test_compiled_prompts_match(self):
        base = Path(__file__).resolve().parents[1] / "docs/pbd/prompt-assistant"
        for filename, value in (("05-change-planner.md", pc.PLANNER_INSTRUCTIONS),
                                ("06-change-reviewer.md", pc.REVIEWER_INSTRUCTIONS)):
            self.assertEqual((base / filename).read_text(encoding="utf-8").strip(), value)
