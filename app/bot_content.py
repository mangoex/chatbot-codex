"""Prompt and knowledge composition for bot-specific runtime behavior."""
import logging

from app import config, db

log = logging.getLogger("whatsapp-bot")


def combine_prompt(base_prompt: str, knowledge_docs: list[dict]) -> str:
    prompt = (base_prompt or "").strip()
    active_docs = [
        doc for doc in knowledge_docs
        if (doc.get("content") or "").strip()
           and doc.get("status", "active") == "active"
    ]
    if not active_docs:
        return prompt

    sections = [prompt, "--- knowledge_base ---"]
    for doc in active_docs:
        title = (doc.get("title") or "Documento").strip()
        content = (doc.get("content") or "").strip()
        sections.append(f"## {title}\n{content}")
    return "\n\n".join(section for section in sections if section)


async def system_prompt_for_bot(bot_id: int | None = None) -> str:
    if not bot_id:
        return config.SYSTEM_PROMPT
    try:
        prompt_row = await db.get_active_bot_prompt(bot_id)
        knowledge_docs = await db.list_bot_knowledge(bot_id, active_only=True)
    except Exception:
        log.exception("No se pudo cargar prompt/conocimiento del bot %s", bot_id)
        return config.SYSTEM_PROMPT

    base_prompt = (prompt_row or {}).get("content") or config.SYSTEM_PROMPT
    return combine_prompt(base_prompt, knowledge_docs)

