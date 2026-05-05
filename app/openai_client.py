"""Cliente OpenAI con control de tokens."""
import tiktoken
from openai import AsyncOpenAI
from app import config

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
        )
    return _client


def _encoder():
    """Siempre usar cl100k_base: funciona para gpt-4o/4o-mini y es un proxy razonable
    para modelos nuevos. El control de tokens no necesita ser exacto, solo acotado."""
    try:
        return tiktoken.encoding_for_model(config.OPENAI_MODEL)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


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


async def complete(user_message: str, history: list[dict]) -> str:
    fitted = fit_history(
        config.SYSTEM_PROMPT, history, user_message, config.MAX_PROMPT_TOKENS
    )
    messages = (
        [{"role": "system", "content": config.SYSTEM_PROMPT}]
        + fitted
        + [{"role": "user", "content": user_message}]
    )
    resp = await _get_client().chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=messages,
    )
    return resp.choices[0].message.content or ""


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
    resp = await _get_client().chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=messages,
    )
    return resp.choices[0].message.content or "Sin resumen disponible."
