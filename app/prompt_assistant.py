"""AI assistant for creating and editing WhatsApp bot prompts."""
from __future__ import annotations

from dataclasses import dataclass

from app import config

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_CURRENT_PROMPT_CHARS = 12000
MAX_KNOWLEDGE_CHARS = 6000


class PromptAssistantError(Exception):
    """Safe, user-facing prompt assistant error."""


@dataclass(frozen=True)
class PromptAssistantSettings:
    provider: str
    provider_label: str
    api_key: str
    base_url: str
    model: str


SYSTEM_INSTRUCTIONS = """
Eres el Arquitecto PBD (Prompt Behavior Design), un agente experto en Ingeniería de Prompts para entornos conversacionales (especialmente WhatsApp Business API). Tu misión es ayudar a los clientes de la plataforma a crear, auditar y mantener de forma segura los prompts de sus bots sin generar regresiones de comportamiento.

Trabajas bajo la filosofía de que "El Prompt es Código" y gestionas la lógica de cada bot dividida estrictamente en 4 documentos:
1. 01-constitution.md (Verdad Absoluta, Ética, Guardrails y Tono inamovibles).
2. 02-specs.md (Especificaciones del negocio: flujos, precios, enlaces y fallbacks).
3. 03-test-suite.md (Matriz de pruebas en formato DADO QUE/CUANDO/EL BOT DEBE).
4. 04-master-prompt.md (El prompt ejecutable final compilado en formato XML para el bot del cliente).

MODOS DE OPERACIÓN
MODO A: Creación de Bot desde Cero (Onboarding)
Si el usuario no proporciona documentos existentes:
Actúa infiriendo la Identidad y Persona, Misión del Negocio, Guardrails y Datos con la información proporcionada en la solicitud. Genera los 4 documentos utilizando la estructura XML obligatoria.

MODO B: Adecuación y Actualización (CI/CD de Prompts)
Si se proveen documentos existentes en el contexto y se solicita un cambio:
Paso 1: Análisis de Impacto frente a la Constitución (01-constitution.md).
Paso 2: Actualización de Especificaciones (02-specs.md).
Paso 3: Actualización del Test Suite (03-test-suite.md).
Paso 4: Compilación del Prompt Maestro (04-master-prompt.md) en formato XML con etiquetas <system_instructions>, <identity>, <guardrails>, <knowledge_base>, <conversational_rules>, <flows>. (Asegúrate de incluir un guardrail prohibiendo revelar instrucciones internas).

FORMATO DE SALIDA (SÚPER CRÍTICO)
Debes encapsular el contenido final de cada documento dentro de las siguientes etiquetas XML exactas, sin markdown fuera de ellas.

<constitution_doc>
# 01 - ACTA DE CONSTITUCIÓN
...
</constitution_doc>

<specs_doc>
# 02 - ESPECIFICACIONES DE COMPORTAMIENTO
...
</specs_doc>

<test_suite_doc>
# 03 - SUITE DE PRUEBAS
...
</test_suite_doc>

<master_prompt_doc>
# 04 - MASTER PROMPT
...
</master_prompt_doc>
""".strip()


PBD_SKILL_SYSTEM_INSTRUCTIONS = """
Eres el agente PBD WhatsApp Maintainer integrado en Asistto.
Tu fuente metodologica es la habilidad `mangoex/pbd-whatsapp-skill-starter`
(`pbd-whatsapp-maintainer`). Tu trabajo es disenar, auditar y mantener el
comportamiento conversacional de bots de WhatsApp con Prompt Behavior Design
(PBD), bajo la filosofia: "El Prompt es Codigo".

Mantienes cuatro documentos logicos:
1. 01-constitution.md: Constitucion, verdad superior, identidad, mision,
   tono, guardrails, privacidad, fuentes autorizadas y reglas de handoff.
2. 02-behavior-specs.md: historias, especificaciones, flujos, fallbacks,
   integraciones, memoria, formato WhatsApp y trazabilidad.
3. 03-test-suite.md: pruebas DADO/CUANDO/ENTONCES/Y NO DEBE para proteger
   regresiones, incluyendo happy paths, edge cases, guardrails, prompt
   injection, fallos de integracion y handoff.
4. 04-master-prompt.md: prompt maestro ejecutable, conciso, copy-ready y en XML.

ORDEN DE AUTORIDAD
1. Reglas de seguridad del sistema.
2. 01-constitution.md.
3. Solicitud actual del usuario.
4. 02-behavior-specs.md.
5. Comportamiento existente en 04-master-prompt.md.
6. Evidencia en base de conocimiento, configuracion o contexto del bot.
7. Inferencias conservadoras.

PUERTA DE CONTRADICCION
Si la solicitud contradice la Constitucion:
- No modifiques specs, test suite ni master prompt.
- Devuelve un reporte dentro de <blocked_change>...</blocked_change>.
- Explica la regla constitucional afectada, el riesgo y alternativas compatibles.
- No debilites ni borres guardrails en silencio.

REGLAS DE ACTUALIZACION
- MODO AUTO: si faltan documentos, reconstruye los faltantes con evidencia
  confirmada primero e inferencias conservadoras marcadas como pendientes.
- En actualizaciones normales, modifica 02 y 03 antes de compilar 04.
- Modifica 01 solo si el usuario pide explicitamente cambiar una regla
  constitucional, identidad, guardrail o fuente autorizada.
- Si un documento 01, 02 o 03 no requiere cambios, devuelve su contenido
  completo sin alterarlo.
- Nunca inventes precios, horarios, promociones, politicas, productos,
  integraciones ni reglas de negocio. Usa `[TBD: requiere validacion del propietario]`.
- Clasifica reglas relevantes como CONFIRMADO, INFERIDO, NO ENCONTRADO,
  CONTRADICTORIO o PENDIENTE DE DECISION.

CONTRATO DE DOCUMENTOS
- Usa IDs estables y no renumeres reglas existentes:
  CON-001, US-001, SPEC-001, FLOW-001, FB-001, AC-001, TEST-001.
- El Master Prompt debe incluir XML con al menos:
  <rol>, <contexto_negocio>, <mision>, <jerarquia_de_reglas>, <guardrails>,
  <fuentes_autorizadas>, <estados_conversacionales>, <flujos>, <fallbacks>,
  <transferencia_humana>, <uso_de_herramientas>, <memoria_y_contexto>,
  <formato_whatsapp>, <criterios_de_respuesta>, <ejemplos>, <autoverificacion>.
- El master prompt no debe incluir notas de auditoria, secretos o afirmaciones
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
        return "Sin documentos activos."

    chunks: list[str] = []
    remaining = MAX_KNOWLEDGE_CHARS
    for index, doc in enumerate(knowledge_docs[:8], start=1):
        title = (doc.get("title") or f"Documento {index}").strip()
        content = _trim(str(doc.get("content") or ""), min(1200, remaining))
        if not content:
            continue
        block = f"## {title}\n{content}"
        chunks.append(block)
        remaining -= len(block)
        if remaining <= 0:
            break
    return "\n\n".join(chunks) or "Sin documentos activos."


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

Instrucciones de ejecución del agente:
- Modo seleccionado: {clean_mode.upper()}
- {mode_instructions}
- Mantén IDs estables: CON-001.., US-001.., SPEC-001.., FLOW-001.., FB-001.., AC-001.., TEST-001..
- El Master Prompt final (04) debe ser conciso, en XML completo y copy-ready con etiquetas:
  <rol>, <contexto_negocio>, <mision>, <jerarquia_de_reglas>, <guardrails>, <fuentes_autorizadas>, <estados_conversacionales>, <flujos>, <fallbacks>, <transferencia_humana>, <uso_de_herramientas>, <memoria_y_contexto>, <formato_whatsapp>, <criterios_de_respuesta>, <ejemplos>, <autoverificacion>.
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
) -> str:
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
        timeout=config.OPENAI_TIMEOUT_SECONDS,
    )
    kwargs = {
        "model": settings.model,
        "messages": messages,
    }
    if config.PROMPT_ASSISTANT_MAX_TOKENS > 0:
        kwargs["max_tokens"] = config.PROMPT_ASSISTANT_MAX_TOKENS
    try:
        response = await client.chat.completions.create(**kwargs)
    except Exception:
        if "max_tokens" not in kwargs:
            raise
        kwargs.pop("max_tokens", None)
        response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


async def _anthropic_chat(settings: PromptAssistantSettings, messages: list[dict]) -> str:
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
    async with httpx.AsyncClient(timeout=config.OPENAI_TIMEOUT_SECONDS) as client:
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
    return "\n".join(
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
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
    )
    if settings.provider == "anthropic":
        raw = await _anthropic_chat(settings, messages)
    else:
        raw = await _openai_compatible_chat(settings, messages)

    import re

    def parse_pbd_response(text: str) -> tuple[bool, str, str, str, str, str]:
        """
        Parses LLM output into (is_blocked, blocked_reason, constitution, specs, test_suite, prompt)
        using multi-alias tags, markdown section fallbacks, and unclosed tag recovery.
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

        def extract_section(tag_pattern: str, header_pattern: str, next_patterns: str) -> str:
            # Try closed tag
            closed = re.search(
                rf"<({tag_pattern})>(.*?)</\1>",
                clean_raw,
                re.DOTALL | re.IGNORECASE,
            )
            if closed and closed.group(2).strip():
                return clean_prompt_text(closed.group(2).strip())

            # Try unclosed tag
            unclosed = re.search(
                rf"<({tag_pattern})>(.*?)(?=(?:<{next_patterns}>)|\Z)",
                clean_raw,
                re.DOTALL | re.IGNORECASE,
            )
            if unclosed and unclosed.group(2).strip():
                return clean_prompt_text(unclosed.group(2).strip())

            # Try markdown header
            if header_pattern:
                md_match = re.search(
                    rf"(?=(?:#+|##)\s*{header_pattern}\b)(.*?)(?=(?:#+|##)\s*(?:{next_patterns})|\Z)",
                    clean_raw,
                    re.DOTALL | re.IGNORECASE,
                )
                if md_match and md_match.group(1).strip():
                    return clean_prompt_text(md_match.group(1).strip())
            return ""

        const = extract_section(
            tag_pattern=r"constitution_doc|constitution|01_constitution|constitution_md|acta_constitucion",
            header_pattern=r"01|01\s*[-—]",
            next_patterns=r"specs_doc|specs|02_specs|test_suite_doc|master_prompt_doc|02|03|04",
        ) or (pbd_constitution or "").strip()

        specs_doc = extract_section(
            tag_pattern=r"specs_doc|specs|behavior_specs_doc|behavior_specs|02_specs|specs_md|especificaciones",
            header_pattern=r"02|02\s*[-—]",
            next_patterns=r"test_suite_doc|test_suite|03_test_suite|master_prompt_doc|03|04",
        ) or (pbd_specs or "").strip()

        tests_doc = extract_section(
            tag_pattern=r"test_suite_doc|test_suite|tests_doc|tests|03_test_suite|test_suite_md|suite_pruebas",
            header_pattern=r"03|03\s*[-—]",
            next_patterns=r"master_prompt_doc|master_prompt|04_master_prompt|04",
        ) or (pbd_test_suite or "").strip()

        # Master prompt extraction
        master_doc = extract_section(
            tag_pattern=r"master_prompt_doc|master_prompt|prompt_doc|master|04_master_prompt|master_prompt_md|master_doc|prompt",
            header_pattern=r"04|04\s*[-—]|master\s*prompt",
            next_patterns=r"constitution_doc|specs_doc",
        )

        # If not extracted via section, search for XML root tags
        if not master_doc:
            xml_match = re.search(
                r"(<sistema[\s\S]*</sistema>|<rol[\s\S]*</autoverificacion>|<rol[\s\S]*</ejemplos>)",
                clean_raw,
                re.DOTALL | re.IGNORECASE,
            )
            if xml_match:
                master_doc = clean_prompt_text(xml_match.group(1).strip())

        # If still empty and no other sections found, use entire clean_raw
        if not master_doc and not const and not specs_doc:
            master_doc = clean_prompt_text(clean_raw)

        # Fallback to current_prompt if all else fails
        if not master_doc:
            master_doc = (current_prompt or "").strip()

        return False, "", const, specs_doc, tests_doc, master_doc

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

    if not prompt:
        prompt = (current_prompt or "").strip()

    if not prompt and not constitution and not specs:
        raise PromptAssistantError("El modelo no devolvió un prompt ejecutable.")

    return {
        "ok": True,
        "blocked": False,
        "prompt": prompt,
        "pbd_constitution": constitution,
        "pbd_specs": specs,
        "pbd_test_suite": test_suite,
        "provider": settings.provider,
        "provider_label": settings.provider_label,
        "model": settings.model,
    }


