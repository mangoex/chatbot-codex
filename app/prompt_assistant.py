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


def build_messages(
    *,
    bot: dict,
    current_prompt: str,
    pbd_constitution: str = "",
    pbd_specs: str = "",
    pbd_test_suite: str = "",
    instruction: str,
    knowledge_docs: list[dict] | None = None,
) -> list[dict]:
    clean_instruction = (instruction or "").strip()
    if not clean_instruction:
        raise PromptAssistantError("Escribe que quieres crear, editar o corregir.")

    bot_context = "\n".join(
        [
            f"Nombre del bot: {bot.get('name') or '-'}",
            f"Cliente: {bot.get('client_name') or '-'}",
            "Telefono WhatsApp: "
            f"{bot.get('display_phone_number') or bot.get('phone_number_id') or '-'}",
            f"Descripcion: {bot.get('description') or '-'}",
        ]
    )
    user_message = f"""
Contexto del bot:
{bot_context}

Master Prompt actual (04):
{_trim(current_prompt, MAX_CURRENT_PROMPT_CHARS) or "Vacio"}

Constitución actual (01):
{_trim(pbd_constitution, MAX_CURRENT_PROMPT_CHARS) or "Vacio"}

Especificaciones actuales (02):
{_trim(pbd_specs, MAX_CURRENT_PROMPT_CHARS) or "Vacio"}

Test Suite actual (03):
{_trim(pbd_test_suite, MAX_CURRENT_PROMPT_CHARS) or "Vacio"}

Base de conocimiento activa:
{_knowledge_context(knowledge_docs or [])}

Solicitud del usuario:
{clean_instruction}

Instrucciones de ejecucion del agente:
- Trabaja en MODO AUTO.
- Si 01, 02 o 03 existen, respetalos como documentos fuente.
- Si el cambio no requiere modificar 01, 02 o 03, devuelvelos completos sin alterarlos.
- Si actualizas el comportamiento, actualiza primero 02 y 03, y compila 04 al final.
- Si detectas contradiccion constitucional, devuelve solo <blocked_change>.
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
            f"Claude respondio HTTP {response.status_code}: {response.text[:500]}"
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
    )
    if settings.provider == "anthropic":
        raw = await _anthropic_chat(settings, messages)
    else:
        raw = await _openai_compatible_chat(settings, messages)

    import re

    def extract_tag(text: str, tag: str) -> str:
        match = re.search(f"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
        if match:
            return clean_prompt_text(match.group(1).strip())
        return ""

    blocked = extract_tag(raw, "blocked_change")
    if blocked:
        raise PromptAssistantError(blocked)

    constitution = extract_tag(raw, "constitution_doc") or (pbd_constitution or "").strip()
    specs = extract_tag(raw, "specs_doc") or (pbd_specs or "").strip()
    test_suite = extract_tag(raw, "test_suite_doc") or (pbd_test_suite or "").strip()
    prompt = extract_tag(raw, "master_prompt_doc")

    # Si por alguna razon el modelo no uso las etiquetas, devolver raw como prompt fallback
    if not prompt and not constitution and not specs:
        prompt = clean_prompt_text(raw)

    if not prompt:
        raise PromptAssistantError("El modelo no devolvio un prompt util.")
    return {
        "ok": True,
        "prompt": prompt,
        "pbd_constitution": constitution,
        "pbd_specs": specs,
        "pbd_test_suite": test_suite,
        "provider": settings.provider,
        "provider_label": settings.provider_label,
        "model": settings.model,
    }
