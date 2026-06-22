from __future__ import annotations
"""Cliente OpenAI con control de tokens."""
from datetime import datetime
from zoneinfo import ZoneInfo

import tiktoken
from openai import AsyncOpenAI
from app import bot_content, config, db, external_actions

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        headers = {}
        if config.OPENAI_BASE_URL:
            headers = {
                "HTTP-Referer": config.OPENROUTER_SITE_URL,
                "X-OpenRouter-Title": config.OPENROUTER_APP_NAME,
            }
        _client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL or None,
            default_headers=headers or None,
            timeout=config.OPENAI_TIMEOUT_SECONDS,
        )
    return _client


async def get_embedding(text: str) -> list[float]:
    """Genera embeddings utilizando el modelo text-embedding-3-small de OpenAI."""
    client = _get_client()
    resp = await client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return resp.data[0].embedding


def _encoder():
    """Siempre usar cl100k_base: funciona para gpt-4o/4o-mini y es un proxy razonable
    para modelos nuevos. El control de tokens no necesita ser exacto, solo acotado."""
    try:
        return tiktoken.encoding_for_model(config.OPENAI_MODEL)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def _runtime_context(lead_info: dict | None = None) -> str:
    tz_name = config.GOOGLE_CALENDAR_TIMEZONE or "America/Chihuahua"
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        tz_name = "America/Chihuahua"
        now = datetime.now(ZoneInfo(tz_name))
    calendar_state = "activo" if config.GOOGLE_CALENDAR_ENABLED else "inactivo"
    
    lead_context = ""
    if lead_info:
        parts = []
        if lead_info.get("nombre"):
            parts.append(f"- Nombre del cliente: {lead_info['nombre']}")
        if lead_info.get("negocio"):
            parts.append(f"- Negocio/Giro del cliente: {lead_info['negocio']}")
        if parts:
            lead_context = "\n".join(parts) + "\n"
            
    return (
        "Contexto operativo actual:\n"
        f"{lead_context}"
        f"- Fecha y hora actual: {now.isoformat(timespec='minutes')}\n"
        f"- Zona horaria: {tz_name}\n"
        f"- Google Calendar: {calendar_state}\n"
        f"- Duracion por defecto de llamada: {config.GOOGLE_APPOINTMENT_DURATION_MINUTES} minutos\n"
        "- Responde muy breve para WhatsApp."
    )


async def _system_prompt(bot_id: int | None = None, query: str | None = None, lead_info: dict | None = None) -> str:
    prompt = await bot_content.system_prompt_for_bot(bot_id, query)
    extra = await external_actions.system_instructions(bot_id)
    runtime = _runtime_context(lead_info)
    if extra:
        return f"{prompt}\n\n--- contexto_runtime ---\n{runtime}\n\n{extra}"
    return f"{prompt}\n\n--- contexto_runtime ---\n{runtime}"


def _safe_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    if status:
        return f"HTTP {status}: {body or str(exc)}"[:700]
    return str(exc)[:700]


def count_tokens(messages: list[dict]) -> int:
    enc = _encoder()
    total = 0
    for m in messages:
        total += len(enc.encode(m.get("content", ""))) + 4  # overhead por mensaje
    return total + 2


def fit_history(system: str, history: list[dict], user_msg: str,
                max_tokens: int) -> list[dict]:
    """Dropea los mensajes más viejos hasta caber en max_tokens."""
    kept = list(history)
    while True:
        msgs = [{"role": "system", "content": system}] + kept + \
               [{"role": "user", "content": user_msg}]
        if count_tokens(msgs) <= max_tokens or not kept:
            return kept
        kept.pop(0)


async def _chat(messages: list[dict], model: str | None = None) -> str:
    kwargs = {
        "model": model or config.OPENAI_MODEL,
        "messages": messages,
    }
    if config.OPENAI_MAX_TOKENS > 0:
        kwargs["max_tokens"] = config.OPENAI_MAX_TOKENS
    try:
        resp = await _get_client().chat.completions.create(**kwargs)
    except Exception:
        # Algunos proveedores/modelos compatibles no aceptan max_tokens. Reintentamos una vez.
        if "max_tokens" not in kwargs:
            raise
        kwargs.pop("max_tokens", None)
        resp = await _get_client().chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


async def complete(
    user_message: str,
    history: list[dict],
    bot_id: int | None = None,
    openai_model: str | None = None,
    wa_id: str | None = None,
) -> str:
    lead_info = None
    if wa_id:
        try:
            lead_info = await db.get_lead(wa_id, bot_id)
        except Exception:
            pass

    system = await _system_prompt(bot_id, query=user_message, lead_info=lead_info)
    fitted = fit_history(system, history, user_message, config.MAX_PROMPT_TOKENS)
    messages = (
        [{"role": "system", "content": system}]
        + fitted
        + [{"role": "user", "content": user_message}]
    )
    import logging
    logger = logging.getLogger("whatsapp-bot")
    logger.info(
        "Llamada completada a OpenAI. bot_id=%s, model=%s, largo_system_prompt=%d, mensajes_historial=%d, preview_system_prompt=%r",
        bot_id,
        openai_model or config.OPENAI_MODEL,
        len(system),
        len(fitted),
        system[:300]
    )
    return await _chat(messages, model=openai_model)


async def diagnostics() -> dict:
    result = {
        "OPENAI_API_KEY": bool(config.OPENAI_API_KEY),
        "OPENAI_BASE_URL": config.OPENAI_BASE_URL or "OpenAI directo",
        "OPENAI_MODEL": config.OPENAI_MODEL,
        "OPENAI_TIMEOUT_SECONDS": config.OPENAI_TIMEOUT_SECONDS,
        "OPENAI_MAX_TOKENS": config.OPENAI_MAX_TOKENS,
        "ok": False,
    }
    if not config.OPENAI_API_KEY:
        result["error"] = "Falta OPENAI_API_KEY."
        return result
    try:
        reply = await _chat([
            {"role": "system", "content": "Responde solo OK."},
            {"role": "user", "content": "ping"},
        ])
        result["ok"] = True
        result["reply"] = reply[:120]
    except Exception as exc:
        result["error"] = _safe_error(exc)
    return result


async def summarize_conversation(history: list[dict], lead: dict | None = None) -> str:
    transcript = "\n".join(
        f"{'Cliente' if item.get('role') == 'user' else 'Bot'}: {item.get('content', '')}"
        for item in history[-24:]
    )
    lead_context = ""
    if lead:
        lead_context = (
            f"Nombre: {lead.get('nombre') or '-'}\n"
            f"Negocio: {lead.get('negocio') or '-'}\n"
        )
    messages = [
        {
            "role": "system",
            "content": (
                "Resume la conversacion comercial en espanol neutro. "
                "Entrega un resumen breve y accionable en 5 lineas maximo."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Datos del lead:\n{lead_context}\n"
                f"Conversacion:\n{transcript}"
            ),
        },
    ]
    return await _chat(messages)
