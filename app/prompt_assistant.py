"""AI assistant for creating and editing WhatsApp bot prompts."""
from __future__ import annotations

from dataclasses import dataclass

from app import config, pbd_validation

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_CURRENT_PROMPT_CHARS = 30000
MAX_KNOWLEDGE_CHARS = 35000
PBD_SKILL_SOURCE = "mangoex/pbd-whatsapp-skill-starter"
PBD_SKILL_COMMIT = "241e4eeee4ceff4b8c2ef9f2da64beebe7e8e6c9"


class PromptAssistantError(Exception):
    """Safe, user-facing prompt assistant error."""


@dataclass(frozen=True)
class PromptAssistantSettings:
    provider: str
    provider_label: str
    api_key: str
    base_url: str
    model: str


@dataclass(frozen=True)
class ModelResponse:
    text: str
    finish_reason: str | None = None


PBD_SKILL_SYSTEM_INSTRUCTIONS = """
Eres el agente PBD WhatsApp Maintainer integrado en Asistto.
Tu fuente metodológica es la habilidad `mangoex/pbd-whatsapp-skill-starter`
(`pbd-whatsapp-maintainer`), fijada al commit
`241e4eeee4ceff4b8c2ef9f2da64beebe7e8e6c9`. Tu trabajo es diseñar, auditar y mantener el
comportamiento conversacional de bots de WhatsApp con Prompt Behavior Design
(PBD), bajo la filosofía: "El Prompt es Código".

Mantienes cuatro documentos lógicos:
1. 01-constitution.md: Constitución, verdad superior, identidad, misión,
   tono, guardrails, privacidad, fuentes autorizadas y reglas de handoff.
2. 02-behavior-specs.md: historias, especificaciones, flujos, fallbacks,
   integraciones, memoria, formato WhatsApp y trazabilidad.
3. 03-test-suite.md: pruebas DADO/CUANDO/ENTONCES/Y NO DEBE para proteger
   regresiones, incluyendo happy paths, edge cases, guardrails, prompt
   injection, fallos de integración y handoff.
4. 04-master-prompt.md: prompt maestro ejecutable, conciso, copy-ready y en XML.

ORDEN DE AUTORIDAD
1. Reglas de seguridad del sistema.
2. 01-constitution.md.
3. Solicitud actual del usuario.
4. 02-behavior-specs.md.
5. Comportamiento existente en 04-master-prompt.md.
6. Evidencia en base de conocimiento, configuración o contexto del bot.
7. Inferencias conservadoras.

PUERTA DE CONTRADICCIÓN
Si la solicitud contradice la Constitución:
- No modifiques specs, test suite ni master prompt.
- Devuelve un reporte dentro de <blocked_change>...</blocked_change>.
- Explica la regla constitucional afectada, el riesgo y alternativas compatibles.
- No debilites ni borres guardrails en silencio.

REGLAS DE ACTUALIZACIÓN E INTEGRACIÓN DE CONOCIMIENTO (CRÍTICO)
- MODO AUTO: si faltan documentos, reconstruye los faltantes con evidencia
  confirmada primero e inferencias conservadoras marcadas como pendientes.
- CUANDO EL USUARIO SOLICITE AGREGAR O CONSULTAR UN TEMA O ARCHIVO DE LA BASE DE CONOCIMIENTO
  (ej. menús del comedor, políticas, horarios, vacantes, catálogos, enlaces, etc.):
  1. EN `02-behavior-specs.md`: Agrega la nueva User Story (`US-XXX`), especificación (`SPEC-XXX`) y flujo (`FLOW-XXX`) detallando la lógica de atención para esa consulta.
  2. EN `03-test-suite.md`: Agrega los casos de prueba (`TEST-XXX`) correspondientes para validar que el bot responda con precisión a consultas sobre ese tema.
  3. EN `04-master-prompt.md`: Incorpora obligatoriamente el nuevo flujo en `<flujos>`, la referencia al archivo o tema en `<fuentes_autorizadas>`, y las instrucciones de respuesta en `<criterios_de_respuesta>` y `<guardrails>`.
- Si el usuario pide explícitamente cambiar una regla constitucional, identidad o guardrail, actualiza también `01-constitution.md`.
- Nunca inventes precios, horarios, promociones, políticas, productos,
  integraciones ni reglas de negocio. Usa `[TBD: requiere validación del propietario]`.
- Clasifica reglas relevantes como CONFIRMADO, INFERIDO, NO ENCONTRADO,
  CONTRADICTORIO o PENDIENTE DE DECISIÓN.

CONTRATO DE DOCUMENTOS
- Usa IDs estables y no renumeres reglas existentes:
  CON-001, US-001, SPEC-001, FLOW-001, FB-001, AC-001, TEST-001.
- El Master Prompt debe incluir XML con al menos:
  <rol>, <contexto_negocio>, <mision>, <jerarquia_de_reglas>, <guardrails>,
  <fuentes_autorizadas>, <estados_conversacionales>, <flujos>, <fallbacks>,
  <transferencia_humana>, <uso_de_herramientas>, <memoria_y_contexto>,
  <formato_whatsapp>, <criterios_de_respuesta>, <ejemplos>, <autoverificacion>.
- El XML ejecutable debe ser un único documento bien formado. Agrupa todas las
  secciones dentro de una sola raíz `<sistema>...</sistema>`.
- El master prompt no debe incluir notas de auditoría, secretos o afirmaciones
  de acciones ejecutadas si solo fueron planificadas.

FORMATO DE SALIDA OBLIGATORIO
Devuelve siempre los documentos finales completos dentro de estas etiquetas
exactas, sin markdown fuera de ellas:

<constitution_doc>
contenido completo de 01
</constitution_doc>
<specs_doc>
contenido completo de 02
</specs_doc>
<test_suite_doc>
contenido completo de 03
</test_suite_doc>
<master_prompt_doc>
contenido completo de 04
</master_prompt_doc>

Si hay bloqueo constitucional, usa solamente:
<blocked_change>
BLOCKED CHANGE
...
BLOCKED CHANGE - MASTER PROMPT NOT MODIFIED
</blocked_change>
""".strip()


def _trim(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 20:
        return text[:limit].rstrip()
    return text[: limit - 18].rstrip() + "\n...[recortado]"


def _normalize_provider(provider: str | None) -> str:
    clean = (provider or config.PROMPT_ASSISTANT_PROVIDER or "openai_compatible")
    clean = clean.strip().lower().replace("-", "_")
    if clean in {"openai", "chatgpt", "gpt", "openai_compatible", "compatible"}:
        return "openai_compatible"
    if clean in {"openrouter", "open_router"}:
        return "openrouter"
    if clean in {"anthropic", "claude"}:
        return "anthropic"
    return "openai_compatible"


def resolve_settings(
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> PromptAssistantSettings:
    normalized = _normalize_provider(provider)
    provided_key = (api_key or "").strip()
    provided_base_url = (base_url or "").strip().rstrip("/")
    provided_model = (model or "").strip()

    if normalized == "anthropic":
        key = (
            provided_key
            or config.PROMPT_ASSISTANT_API_KEY
            or config.ANTHROPIC_API_KEY
        )
        if not key:
            raise PromptAssistantError(
                "Falta ANTHROPIC_API_KEY o una API key temporal para Claude."
            )
        return PromptAssistantSettings(
            provider="anthropic",
            provider_label="Claude",
            api_key=key,
            base_url=provided_base_url or config.ANTHROPIC_BASE_URL,
            model=(
                provided_model
                or config.PROMPT_ASSISTANT_MODEL
                or config.ANTHROPIC_MODEL
            ),
        )

    key = provided_key or config.PROMPT_ASSISTANT_API_KEY or config.OPENAI_API_KEY
    if not key:
        raise PromptAssistantError(
            "Falta OPENAI_API_KEY, PROMPT_ASSISTANT_API_KEY o una API key temporal."
        )

    fallback_base_url = (
        config.PROMPT_ASSISTANT_BASE_URL
        or config.OPENAI_BASE_URL
        or (OPENROUTER_BASE_URL if normalized == "openrouter" else "")
    )
    final_base_url = provided_base_url or fallback_base_url
    label = (
        "OpenRouter"
        if normalized == "openrouter" or "openrouter.ai" in final_base_url
        else "OpenAI compatible"
    )
    return PromptAssistantSettings(
        provider=normalized,
        provider_label=label,
        api_key=key,
        base_url=final_base_url.rstrip("/"),
        model=provided_model or config.PROMPT_ASSISTANT_MODEL or config.OPENAI_MODEL,
    )


def _knowledge_context(knowledge_docs: list[dict]) -> str:
    if not knowledge_docs:
        return "Sin documentos activos en la Base de Conocimiento."

    doc_titles = [f"{idx}. {(d.get('title') or 'Doc').strip()}" for idx, d in enumerate(knowledge_docs, start=1)]
    titles_summary = "Documentos indexados en la Base de Conocimiento:\n" + "\n".join(doc_titles)

    chunks: list[str] = [titles_summary]
    remaining = MAX_KNOWLEDGE_CHARS
    for index, doc in enumerate(knowledge_docs[:30], start=1):
        title = (doc.get("title") or f"Documento {index}").strip()
        content = _trim(str(doc.get("content") or ""), min(2500, remaining))
        if not content:
            continue
        block = f"### [{index}] {title}\n{content}"
        chunks.append(block)
        remaining -= len(block)
        if remaining <= 0:
            break
    return "\n\n".join(chunks)



def _integrations_context(integrations: list[dict] | None, skills: list[dict] | None) -> str:
    lines: list[str] = []
    if integrations:
        for it in integrations:
            itype = it.get("integration_type") or "desconocida"
            active = "activa" if it.get("enabled", True) else "inactiva"
            lines.append(f"- Integración: {itype} ({active})")
    if skills:
        for sk in skills:
            stype = sk.get("skill_type") or "desconocida"
            active = "habilitada" if sk.get("enabled", True) else "deshabilitada"
            lines.append(f"- Skill: {stype} ({active})")
    return "\n".join(lines) if lines else "Sin integraciones configuradas."


def build_messages(
    *,
    bot: dict,
    current_prompt: str,
    pbd_constitution: str = "",
    pbd_specs: str = "",
    pbd_test_suite: str = "",
    instruction: str,
    knowledge_docs: list[dict] | None = None,
    integrations: list[dict] | None = None,
    skills: list[dict] | None = None,
    mode: str = "auto",
    allow_constitution_change: bool = False,
) -> list[dict]:
    clean_instruction = (instruction or "").strip()
    if not clean_instruction:
        raise PromptAssistantError("Escribe qué comportamiento deseas crear, editar o actualizar.")

    bot_context = "\n".join(
        [
            f"Nombre del bot: {bot.get('name') or '-'}",
            f"Cliente: {bot.get('client_name') or '-'}",
            "Teléfono WhatsApp: "
            f"{bot.get('display_phone_number') or bot.get('phone_number_id') or '-'}",
            f"Descripción: {bot.get('description') or '-'}",
        ]
    )
    
    clean_mode = (mode or "auto").strip().lower()
    mode_instructions = {
        "bootstrap": "MODO BOOTSTRAP EXPLICITO: Reconstruye desde cero los 4 documentos PBD (01-constitution.md, 02-behavior-specs.md, 03-test-suite.md y 04-master-prompt.md) basándote en la descripción y base de conocimiento.",
        "update": "MODO UPDATE EXPLICITO: Compara la solicitud contra la Constitución (01). Si no hay contradicción, actualiza Specs (02), Test Suite (03) y compila Master Prompt (04) al final conservando los IDs estables.",
        "auto": "MODO AUTO: Si 01, 02 y 03 existen, ejecuta UPDATE respetando la Constitución. Si faltan documentos, ejecuta BOOTSTRAP reconstruyendo los faltantes con evidencia confirmada e inferencias conservadoras.",
    }.get(clean_mode, "MODO AUTO: Analiza el contexto y procede según la metodología PBD.")

    user_message = f"""
Contexto del bot:
{bot_context}

Integraciones y herramientas del bot:
{_integrations_context(integrations, skills)}

Master Prompt actual (04):
{_trim(current_prompt, MAX_CURRENT_PROMPT_CHARS) or "Vacío"}

Constitución actual (01):
{_trim(pbd_constitution, MAX_CURRENT_PROMPT_CHARS) or "Vacío"}

Especificaciones actuales (02):
{_trim(pbd_specs, MAX_CURRENT_PROMPT_CHARS) or "Vacío"}

Test Suite actual (03):
{_trim(pbd_test_suite, MAX_CURRENT_PROMPT_CHARS) or "Vacío"}

Base de conocimiento activa:
{_knowledge_context(knowledge_docs or [])}

Solicitud del usuario:
{clean_instruction}

Instrucciones de ejecución del agente PBD (OBLIGATORIAS):
- Modo seleccionado: {clean_mode.upper()}
- {mode_instructions}
- La Constitución (01) debe conservarse sin cambios, salvo que la solicitud
  incluya autorización constitucional explícita: {"SÍ" if allow_constitution_change else "NO"}.
- Mantén IDs estables: CON-001.., US-001.., SPEC-001.., FLOW-001.., FB-001.., AC-001.., TEST-001..
- CRÍTICO: REGLA DE COMPILACIÓN DEL MASTER PROMPT (04):
  El Master Prompt (04) NUNCA debe dejarse intacto cuando se agrega o modifica un requerimiento.
  DEBES EDITAR OBLIGATORIAMENTE las secciones dentro del XML de 04:
  1. `<fuentes_autorizadas>`: Agregar las fuentes o archivos mencionados (ej. Menu_Agosto_2026_Mobi.md, políticas, etc.).
  2. `<flujos>`: Agregar o actualizar el `<flujo id="...">` detallando paso a paso cómo responder a la consulta del usuario (ej. cómo desglosar el menú según día de la semana y semana del mes usando el conocimiento oficial).
  3. `<criterios_de_respuesta>` y `<guardrails>`: Definir las reglas estrictas de fidelidad a la información oficial.
- Devuelve los 4 documentos completos encapsulados en sus etiquetas correspondientes: <constitution_doc>, <specs_doc>, <test_suite_doc>, <master_prompt_doc>.
- No omitas, recortes ni dejes sin cerrar ninguna de las cuatro etiquetas.
- Si detectas una contradicción constitucional insalvable con la solicitud, devuelve obligatoriamente el reporte dentro de <blocked_change>...</blocked_change>.
""".strip()
    return [
        {"role": "system", "content": PBD_SKILL_SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": user_message},
    ]


def clean_prompt_text(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def safe_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    if status:
        return f"HTTP {status}: {body or str(exc)}"[:700]
    return str(exc)[:700]


async def _openai_compatible_chat(
    settings: PromptAssistantSettings,
    messages: list[dict],
) -> ModelResponse:
    from openai import AsyncOpenAI

    headers = {}
    if settings.provider == "openrouter" or "openrouter.ai" in settings.base_url:
        headers = {
            "HTTP-Referer": config.OPENROUTER_SITE_URL,
            "X-OpenRouter-Title": config.OPENROUTER_APP_NAME,
        }
    client = AsyncOpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url or None,
        default_headers=headers or None,
        timeout=max(config.OPENAI_TIMEOUT_SECONDS, 150),
    )
    kwargs = {
        "model": settings.model,
        "messages": messages,
    }
    if config.PROMPT_ASSISTANT_MAX_TOKENS > 0:
        kwargs["max_tokens"] = config.PROMPT_ASSISTANT_MAX_TOKENS
    response = await client.chat.completions.create(**kwargs)
    choice = response.choices[0]
    return ModelResponse(
        text=choice.message.content or "",
        finish_reason=getattr(choice, "finish_reason", None),
    )


async def _anthropic_chat(
    settings: PromptAssistantSettings,
    messages: list[dict],
) -> ModelResponse:
    import httpx

    system = next((m["content"] for m in messages if m.get("role") == "system"), "")
    user = "\n\n".join(m["content"] for m in messages if m.get("role") == "user")
    payload = {
        "model": settings.model,
        "max_tokens": max(config.PROMPT_ASSISTANT_MAX_TOKENS, 1024),
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": settings.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=max(config.OPENAI_TIMEOUT_SECONDS, 150)) as client:
        response = await client.post(
            f"{settings.base_url.rstrip('/')}/messages",
            json=payload,
            headers=headers,
        )
    if response.status_code >= 400:
        raise PromptAssistantError(
            f"Claude respondió HTTP {response.status_code}: {response.text[:500]}"
        )
    data = response.json()
    blocks = data.get("content") or []
    return ModelResponse(
        text="\n".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ),
        finish_reason=data.get("stop_reason"),
    )



async def assist_prompt(
    *,
    bot: dict,
    current_prompt: str,
    pbd_constitution: str = "",
    pbd_specs: str = "",
    pbd_test_suite: str = "",
    instruction: str,
    knowledge_docs: list[dict] | None = None,
    integrations: list[dict] | None = None,
    skills: list[dict] | None = None,
    mode: str = "auto",
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    allow_constitution_change: bool = False,
) -> dict:
    settings = resolve_settings(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    messages = build_messages(
        bot=bot,
        current_prompt=current_prompt,
        pbd_constitution=pbd_constitution,
        pbd_specs=pbd_specs,
        pbd_test_suite=pbd_test_suite,
        instruction=instruction,
        knowledge_docs=knowledge_docs or [],
        integrations=integrations or [],
        skills=skills or [],
        mode=mode,
        allow_constitution_change=allow_constitution_change,
    )
    if settings.provider == "anthropic":
        model_response = await _anthropic_chat(settings, messages)
    else:
        model_response = await _openai_compatible_chat(settings, messages)

    if isinstance(model_response, str):
        raw = model_response
        finish_reason = None
    else:
        raw = model_response.text
        finish_reason = model_response.finish_reason

    if (finish_reason or "").lower() in {"length", "max_tokens"}:
        raise PromptAssistantError(
            "La respuesta del modelo quedó truncada por límite de tokens. "
            "No se aplicó ni publicó ningún documento."
        )

    import re

    def parse_pbd_response(text: str) -> tuple[bool, str, str, str, str, str]:
        """
        Parse the exact PBD response contract. Incomplete output fails closed.
        """
        clean_raw = (text or "").strip()
        
        # 1. Check for blocked change
        blocked_match = re.search(
            r"<(blocked_change|blocked|cambio_bloqueado)>(.*?)(?:</\1>|\Z)",
            clean_raw,
            re.DOTALL | re.IGNORECASE,
        )
        if blocked_match:
            return True, clean_prompt_text(blocked_match.group(2).strip()), "", "", "", ""
        if "BLOCKED CHANGE - MASTER PROMPT NOT MODIFIED" in clean_raw:
            return True, clean_prompt_text(clean_raw), "", "", "", ""

        documents: list[str] = []
        for tag in (
            "constitution_doc",
            "specs_doc",
            "test_suite_doc",
            "master_prompt_doc",
        ):
            matches = re.findall(
                rf"<{tag}>(.*?)</{tag}>",
                clean_raw,
                re.DOTALL | re.IGNORECASE,
            )
            if len(matches) != 1 or not matches[0].strip():
                raise PromptAssistantError(
                    "El modelo no devolvió los cuatro documentos completos con "
                    "sus etiquetas obligatorias. No se aplicó ningún cambio."
                )
            documents.append(clean_prompt_text(matches[0].strip()))

        return False, "", *documents

    is_blocked, blocked_reason, constitution, specs, test_suite, prompt = parse_pbd_response(raw)

    if is_blocked:
        return {
            "ok": False,
            "blocked": True,
            "error": blocked_reason,
            "blocked_reason": blocked_reason,
            "prompt": current_prompt,
            "pbd_constitution": pbd_constitution,
            "pbd_specs": pbd_specs,
            "pbd_test_suite": pbd_test_suite,
            "provider": settings.provider,
            "provider_label": settings.provider_label,
            "model": settings.model,
        }

    report = pbd_validation.validate_pbd_bundle(
        constitution,
        specs,
        test_suite,
        prompt,
        previous_constitution=pbd_constitution,
        previous_specs=pbd_specs,
        previous_test_suite=pbd_test_suite,
        allow_constitution_change=allow_constitution_change,
        for_publish=False,
    )
    if not report.valid:
        raise PromptAssistantError(pbd_validation.validation_error_message(report))

    return {
        "ok": True,
        "blocked": False,
        "prompt": report.master_xml,
        "pbd_constitution": constitution,
        "pbd_specs": specs,
        "pbd_test_suite": test_suite,
        "provider": settings.provider,
        "provider_label": settings.provider_label,
        "model": settings.model,
        "validation": report.to_dict(),
    }
