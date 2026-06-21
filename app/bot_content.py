from __future__ import annotations
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


async def system_prompt_for_bot(bot_id: int | None = None, query: str | None = None) -> str:
    bot_name = "Asistto"
    if bot_id and bot_id != 1:
        try:
            bot_data = await db.get_bot(bot_id)
            if bot_data and bot_data.get("name"):
                bot_name = bot_data["name"]
        except Exception:
            pass

    fallback = config.SYSTEM_PROMPT
    if bot_name != "Asistto":
        fallback = fallback.replace("Asistto", bot_name).replace("asistto", bot_name.lower())

    if not bot_id:
        return fallback
    try:
        prompt_row = await db.get_active_bot_prompt(bot_id)
        # RAG Semantic search if query is provided
        rag_chunks = []
        if query:
            from app import rag
            async with db._pool.acquire() as conn:
                rag_chunks = await rag.search_knowledge(conn, bot_id, query, limit=3)
        
        if query and rag_chunks:
            knowledge_docs = [{"title": f"Fragmento de conocimiento {i+1}", "content": chunk, "status": "active"} for i, chunk in enumerate(rag_chunks)]
        else:
            knowledge_docs = await db.list_bot_knowledge(bot_id, active_only=True)
    except Exception:
        log.exception("No se pudo cargar prompt/conocimiento del bot %s", bot_id)
        return fallback

    log.info(
        "Cargando prompt para bot_id=%s. ¿Se encontró row activo?: %s, Documentos de conocimiento: %d, RAG usado: %s",
        bot_id,
        prompt_row is not None,
        len(knowledge_docs),
        bool(query and rag_chunks),
    )
    base_prompt = (prompt_row or {}).get("content") or fallback
    return combine_prompt(base_prompt, knowledge_docs)

