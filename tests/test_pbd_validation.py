import unittest

from app import pbd_validation


VALID_CONSTITUTION = """# Constitución

- CON-001 [CONFIRMED]: No inventar información.
- CON-002 [CONFIRMED]: Proteger datos privados.
"""

VALID_SPECS = """# Especificaciones

- US-001 [CONFIRMED]: Consultar información autorizada.
- SPEC-001 [Constitution: CON-001]: Responder solo con fuentes activas.
- FLOW-001 [Constitution: CON-001]: Consultar, responder o fallar de forma segura.
- FB-001 [Constitution: CON-001]: Declarar cuando falta información.
"""

VALID_TESTS = """# Suite

### AC-001 - Consulta autorizada
Status: DEFINED

GIVEN existe una fuente autorizada
WHEN el usuario consulta información
THEN el bot responde con esa fuente
AND MUST NOT inventar datos

### TEST-001 - Happy path
- Status: DEFINED
- Covers: US-001, SPEC-001, FLOW-001, CON-001

### TEST-002 - Negative or edge case
- Status: DEFINED
- Covers: FB-001, CON-001

### TEST-003 - Regression
- Status: DEFINED
- Covers: CON-001
"""

VALID_MASTER = """# Prompt Maestro

```xml
<master_prompt>
  <rol>Asistente de prueba.</rol>
  <contexto_negocio>Contexto confirmado.</contexto_negocio>
  <mision>Ayudar sin inventar.</mision>
  <jerarquia_de_reglas>Seguridad antes que negocio.</jerarquia_de_reglas>
  <guardrails>No inventar.</guardrails>
  <fuentes_autorizadas>Base activa.</fuentes_autorizadas>
  <estados_conversacionales>inicio</estados_conversacionales>
  <flujos><flujo id="FLOW-001">Responder.</flujo></flujos>
  <fallbacks>Declarar datos faltantes.</fallbacks>
  <transferencia_humana>Escalar cuando corresponda.</transferencia_humana>
  <uso_de_herramientas>Usar solo herramientas activas.</uso_de_herramientas>
  <memoria_y_contexto>Conservar solo contexto útil.</memoria_y_contexto>
  <formato_whatsapp>Mensajes breves.</formato_whatsapp>
  <criterios_de_respuesta>Responder con evidencia.</criterios_de_respuesta>
  <ejemplos><ejemplo>Hola.</ejemplo></ejemplos>
  <autoverificacion>Revisar seguridad y fuentes.</autoverificacion>
</master_prompt>
```
"""


class PBDValidationTests(unittest.TestCase):
    def test_valid_bundle_passes_and_extracts_xml(self):
        report = pbd_validation.validate_pbd_bundle(
            VALID_CONSTITUTION,
            VALID_SPECS,
            VALID_TESTS,
            VALID_MASTER,
        )

        self.assertTrue(report.valid)
        self.assertEqual(report.errors, [])
        self.assertTrue(report.master_xml.startswith("<master_prompt>"))
        self.assertNotIn("```", report.master_xml)

    def test_missing_document_fails_closed(self):
        report = pbd_validation.validate_pbd_bundle(
            VALID_CONSTITUTION,
            VALID_SPECS,
            "",
            VALID_MASTER,
        )

        self.assertFalse(report.valid)
        self.assertIn("03-test-suite.md está vacío", " ".join(report.errors))

    def test_invalid_or_incomplete_master_prompt_fails(self):
        report = pbd_validation.validate_pbd_bundle(
            VALID_CONSTITUTION,
            VALID_SPECS,
            VALID_TESTS,
            "<master_prompt><rol>Sin cierre",
        )

        self.assertFalse(report.valid)
        self.assertIn("XML", " ".join(report.errors))

    def test_missing_required_master_section_fails(self):
        master = VALID_MASTER.replace(
            "<uso_de_herramientas>Usar solo herramientas activas.</uso_de_herramientas>",
            "",
        )

        report = pbd_validation.validate_pbd_bundle(
            VALID_CONSTITUTION,
            VALID_SPECS,
            VALID_TESTS,
            master,
        )

        self.assertFalse(report.valid)
        self.assertIn("uso_de_herramientas", " ".join(report.errors))

    def test_incomplete_behavior_test_contract_fails(self):
        report = pbd_validation.validate_pbd_bundle(
            VALID_CONSTITUTION,
            VALID_SPECS,
            "AC-001 TEST-001",
            VALID_MASTER,
        )

        self.assertFalse(report.valid)
        self.assertIn("GIVEN/DADO", " ".join(report.errors))
        self.assertIn("prueba de regresión", " ".join(report.errors))

    def test_removed_stable_id_fails(self):
        report = pbd_validation.validate_pbd_bundle(
            VALID_CONSTITUTION.replace("CON-002", "CON-003"),
            VALID_SPECS,
            VALID_TESTS,
            VALID_MASTER,
            previous_constitution=VALID_CONSTITUTION,
        )

        self.assertFalse(report.valid)
        self.assertIn("CON-002", " ".join(report.errors))

    def test_unapproved_constitution_change_fails(self):
        report = pbd_validation.validate_pbd_bundle(
            VALID_CONSTITUTION + "\n- CON-003 [CONFIRMED]: Regla nueva.\n",
            VALID_SPECS,
            VALID_TESTS,
            VALID_MASTER,
            previous_constitution=VALID_CONSTITUTION,
            allow_constitution_change=False,
        )

        self.assertFalse(report.valid)
        self.assertIn("autorización constitucional", " ".join(report.errors))

    def test_pending_decision_blocks_publication_but_not_draft(self):
        constitution = VALID_CONSTITUTION + "\n- CON-003 [PENDING DECISION]: [TBD: requiere validación del propietario]\n"

        draft = pbd_validation.validate_pbd_bundle(
            constitution,
            VALID_SPECS,
            VALID_TESTS,
            VALID_MASTER,
            allow_constitution_change=True,
        )
        publish = pbd_validation.validate_pbd_bundle(
            constitution,
            VALID_SPECS,
            VALID_TESTS,
            VALID_MASTER,
            allow_constitution_change=True,
            for_publish=True,
        )

        self.assertTrue(draft.valid)
        self.assertTrue(draft.warnings)
        self.assertFalse(publish.valid)


if __name__ == "__main__":
    unittest.main()
