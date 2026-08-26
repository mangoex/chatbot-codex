"""Deterministic validation for PBD documents and compiled Master Prompts."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import xml.etree.ElementTree as ET


REQUIRED_MASTER_SECTIONS = (
    "rol",
    "contexto_negocio",
    "mision",
    "jerarquia_de_reglas",
    "guardrails",
    "fuentes_autorizadas",
    "estados_conversacionales",
    "flujos",
    "fallbacks",
    "transferencia_humana",
    "uso_de_herramientas",
    "memoria_y_contexto",
    "formato_whatsapp",
    "criterios_de_respuesta",
    "ejemplos",
    "autoverificacion",
)

DOCUMENT_ID_REQUIREMENTS = {
    "01-constitution.md": ("CON",),
    "02-behavior-specs.md": ("US", "SPEC", "FLOW", "FB"),
    "03-test-suite.md": ("AC", "TEST"),
}

TRUNCATION_MARKERS = ("...[recortado]", "[truncated]", "…[recortado]")
TEST_CLAUSE_ALIASES = {
    "GIVEN/DADO": (r"\bGIVEN\b", r"\bDADO(?:\s+QUE)?\b"),
    "WHEN/CUANDO": (r"\bWHEN\b", r"\bCUANDO\b"),
    "THEN/ENTONCES": (r"\bTHEN\b", r"\bENTONCES\b"),
    "AND MUST NOT/Y NO DEBE": (r"\bAND\s+MUST\s+NOT\b", r"\bY\s+NO\s+DEBE\b"),
}


@dataclass
class PBDValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    master_xml: str = ""

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "master_sections": list(REQUIRED_MASTER_SECTIONS),
        }


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _normalized(value: str | None) -> str:
    return "\n".join(line.rstrip() for line in _clean(value).splitlines()).strip()


def _ids(value: str | None, prefix: str) -> set[str]:
    return set(re.findall(rf"\b{re.escape(prefix)}-\d{{3,}}\b", value or "", re.IGNORECASE))


def extract_master_xml(master_prompt: str | None) -> str:
    """Return the single XML document embedded in a Markdown or raw prompt."""
    text = _clean(master_prompt)
    if not text:
        return ""

    fenced = re.search(r"```xml\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1).strip() if fenced else text
    start = candidate.find("<")
    end = candidate.rfind(">")
    if start < 0 or end < start:
        return ""
    return candidate[start : end + 1].strip()


def _validate_document_ids(name: str, content: str, report: PBDValidationReport) -> None:
    for prefix in DOCUMENT_ID_REQUIREMENTS[name]:
        if not _ids(content, prefix):
            report.errors.append(f"{name} no contiene un ID obligatorio {prefix}-NNN.")


def _validate_test_contract(content: str, report: PBDValidationReport) -> None:
    for label, aliases in TEST_CLAUSE_ALIASES.items():
        if not any(re.search(pattern, content, re.IGNORECASE) for pattern in aliases):
            report.errors.append(
                f"03-test-suite.md no contiene la cláusula obligatoria {label}."
            )

    coverage_types = {
        "caso positivo": ("happy path", "camino feliz", "caso positivo"),
        "caso negativo o extremo": ("negative", "negativo", "edge", "extremo"),
        "prueba de regresión": ("regression", "regresión"),
    }
    lowered = content.lower()
    for label, markers in coverage_types.items():
        if not any(marker in lowered for marker in markers):
            report.errors.append(f"03-test-suite.md no declara {label}.")


def _validate_preserved_ids(
    name: str,
    previous: str | None,
    current: str,
    prefixes: tuple[str, ...],
    report: PBDValidationReport,
) -> None:
    if not _clean(previous):
        return
    for prefix in prefixes:
        removed = sorted(_ids(previous, prefix) - _ids(current, prefix))
        if removed:
            report.errors.append(
                f"{name} eliminó IDs estables existentes: {', '.join(removed)}."
            )


def validate_pbd_bundle(
    constitution: str | None,
    specs: str | None,
    test_suite: str | None,
    master_prompt: str | None,
    *,
    previous_constitution: str | None = None,
    previous_specs: str | None = None,
    previous_test_suite: str | None = None,
    allow_constitution_change: bool = False,
    for_publish: bool = False,
) -> PBDValidationReport:
    """Validate completeness, stable IDs, XML structure and publication safety."""
    report = PBDValidationReport()
    documents = {
        "01-constitution.md": _clean(constitution),
        "02-behavior-specs.md": _clean(specs),
        "03-test-suite.md": _clean(test_suite),
        "04-master-prompt.md": _clean(master_prompt),
    }

    for name, content in documents.items():
        if not content:
            report.errors.append(f"{name} está vacío.")
            continue
        if any(marker.lower() in content.lower() for marker in TRUNCATION_MARKERS):
            report.errors.append(f"{name} contiene una marca de truncamiento.")

    for name in DOCUMENT_ID_REQUIREMENTS:
        content = documents[name]
        if content:
            _validate_document_ids(name, content, report)
    if documents["03-test-suite.md"]:
        _validate_test_contract(documents["03-test-suite.md"], report)

    _validate_preserved_ids(
        "01-constitution.md",
        previous_constitution,
        documents["01-constitution.md"],
        ("CON",),
        report,
    )
    _validate_preserved_ids(
        "02-behavior-specs.md",
        previous_specs,
        documents["02-behavior-specs.md"],
        ("US", "SPEC", "FLOW", "FB"),
        report,
    )
    _validate_preserved_ids(
        "03-test-suite.md",
        previous_test_suite,
        documents["03-test-suite.md"],
        ("AC", "TEST"),
        report,
    )

    if (
        _clean(previous_constitution)
        and _normalized(previous_constitution) != _normalized(constitution)
        and not allow_constitution_change
    ):
        report.errors.append(
            "01-constitution.md cambió sin autorización constitucional explícita."
        )

    pending = any(
        marker in "\n".join(documents.values()).lower()
        for marker in ("[tbd", "pending decision", "pendiente de decisión")
    )
    if pending:
        message = "El paquete contiene decisiones pendientes o marcadores TBD."
        if for_publish:
            report.errors.append(message + " No puede publicarse.")
        else:
            report.warnings.append(message)

    master_xml = extract_master_xml(master_prompt)
    report.master_xml = master_xml
    if documents["04-master-prompt.md"]:
        if not master_xml:
            report.errors.append("04-master-prompt.md no contiene XML ejecutable.")
        else:
            try:
                root = ET.fromstring(master_xml)
            except ET.ParseError as exc:
                report.errors.append(f"04-master-prompt.md contiene XML inválido: {exc}.")
            else:
                present = {element.tag.split("}")[-1] for element in root.iter()}
                missing = [tag for tag in REQUIRED_MASTER_SECTIONS if tag not in present]
                if missing:
                    report.errors.append(
                        "04-master-prompt.md no contiene secciones obligatorias: "
                        + ", ".join(missing)
                        + "."
                    )

    return report


def validation_error_message(report: PBDValidationReport) -> str:
    return "Validación PBD fallida: " + " ".join(report.errors)
