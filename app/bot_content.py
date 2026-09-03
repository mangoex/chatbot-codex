from __future__ import annotations
"""Prompt and knowledge composition for bot-specific runtime behavior."""
import csv
import io
import logging
import re
import unicodedata

from app import config, db
from app.knowledge_privacy import is_private_directory_title

log = logging.getLogger("whatsapp-bot")


class BotPromptUnavailable(RuntimeError):
    """Raised when a tenant bot cannot load its own active prompt safely."""

    def __init__(self, bot_id: int | None, reason: str):
        self.bot_id = bot_id
        self.reason = reason
        super().__init__(f"Prompt unavailable for bot_id={bot_id}: {reason}")


def combine_prompt(base_prompt: str, knowledge_docs: list[dict]) -> str:
    prompt = (base_prompt or "").strip()
    active_docs = [
        doc for doc in knowledge_docs
        if (doc.get("content") or "").strip()
           and doc.get("status", "active") == "active"
           and not is_private_directory_title(doc.get("title"))
    ]
    if not active_docs:
        return prompt

    sections = [prompt, "--- knowledge_base ---"]
    for doc in active_docs:
        title = (doc.get("title") or "Documento").strip()
        content = (doc.get("content") or "").strip()
        sections.append(f"## {title}\n{content}")
    return "\n\n".join(section for section in sections if section)


def build_retrieval_query(user_message: str, history: list[dict]) -> str:
    """Build a conservative retrieval query from user-authored context only."""
    current = re.sub(r"\s+", " ", user_message or "").strip()
    normalized = unicodedata.normalize("NFKD", current.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"^[^a-z0-9]+", "", normalized)
    starts_as_followup = bool(re.match(
        r"^(?:y\s+para|y\s+en|y\s+si|tambien|cual(?:es)?\s+de\s+(?:esos|esas)|en\s+ese\s+caso|eso\b|esa\b)",
        normalized,
    ))
    # Users commonly repair a failed policy answer with deictic wording such
    # as "ahí viene" or "ahí dice". It is contextual even when the marker is
    # not the first word of the message.
    has_deictic_reference = bool(re.search(
        r"\b(?:ahi|aqui|alli)\b|\b(?:eso|esa)\s+(?:dice|indica|menciona|viene)\b",
        normalized,
    ))
    is_followup = (starts_as_followup or has_deictic_reference) and len(current) <= 240
    # "Cuando puedo gastar" is a frequent typo for "Cuánto puedo gastar".
    # Keep the original text but add a semantic hint unless explicit temporal
    # markers make the literal "cuándo" interpretation more likely.
    has_amount_verb = bool(re.search(
        r"\b(?:gastar|gasto|pagar|pago|costar|cuesta|costo)\b",
        normalized,
    ))
    has_temporal_marker = bool(re.search(
        r"\b(?:antes|despues|fecha|momento|hora|autorizacion|iniciar|inicio|terminar|regresar)\b",
        normalized,
    ))
    likely_amount_typo = (
        "cuando" in normalized.split()
        and has_amount_verb
        and not has_temporal_marker
    )
    lines = []
    if is_followup:
        recent_users = [
            re.sub(r"\s+", " ", str(item.get("content") or "")).strip()[:600]
            for item in history[-config.RETRIEVAL_HISTORY_MESSAGES:]
            if item.get("role") == "user" and (item.get("content") or "").strip()
        ]
        for item in recent_users[-2:]:
            lines.append(f"Contexto de usuario: {item}")
    if likely_amount_typo:
        lines.append("Intención probable: consulta de monto o límite (cuánto).")
    lines.append(f"Pregunta actual: {current}")
    rendered = "\n".join(lines)
    if len(rendered) <= config.RETRIEVAL_QUERY_MAX_CHARS:
        return rendered
    # Keep the newest context and the complete current question.
    return rendered[-config.RETRIEVAL_QUERY_MAX_CHARS:]


def _normalized_header(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def _phone10(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


def _identity_from_directory(content: str, wa_id: str) -> dict | None:
    target = _phone10(wa_id)
    if len(target) != 10:
        return None
    sample = (content or "")[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content or ""), dialect=dialect)
    fields = {
        _normalized_header(field): field
        for field in (reader.fieldnames or [])
        if field
    }
    name_field = fields.get("nombre") or fields.get("name")
    area_field = fields.get("area") or fields.get("departamento") or fields.get("department")
    phone_field = fields.get("telefono") or fields.get("phone") or fields.get("whatsapp")
    if not name_field or not phone_field:
        return None
    for row in reader:
        if _phone10(row.get(phone_field)) != target:
            continue
        identity = {"nombre": (row.get(name_field) or "").strip()}
        if area_field and (row.get(area_field) or "").strip():
            identity["area"] = (row.get(area_field) or "").strip()
        return identity if identity["nombre"] else None
    return None


async def directory_identity_for_bot(bot_id: int, wa_id: str) -> dict | None:
    """Return only the sender's exact directory row, strictly scoped to one bot."""
    docs = await db.list_bot_knowledge(bot_id, active_only=True)
    for doc in docs:
        if not is_private_directory_title(doc.get("title")):
            continue
        identity = _identity_from_directory(doc.get("content") or "", wa_id)
        if identity:
            return identity
    return None


async def system_prompt_for_bot(
    bot_id: int | None = None,
    query: str | None = None,
    lexical_query: str | None = None,
) -> str:
    if not bot_id or bot_id < 1:
        raise BotPromptUnavailable(bot_id, "missing tenant context")

    # The file-based prompt belongs exclusively to Asistto (bot 1). Tenant
    # bots must never inherit it or receive a name-replaced derivative.
    default_prompt = (config.SYSTEM_PROMPT or "").strip()
    try:
        prompt_row = await db.get_active_bot_prompt(bot_id)
        # Cargar todos los documentos de conocimiento primero
        all_docs = [
            doc for doc in await db.list_bot_knowledge(bot_id, active_only=True)
            if not is_private_directory_title(doc.get("title"))
        ]
        total_chars = sum(len(doc.get("content") or "") for doc in all_docs)
        
        # RAG Semantic search solo si se provee consulta y la base de conocimiento es grande
        rag_chunks = []
        retrieval_diagnostics: list[dict] = []
        uses_rag = total_chars > config.RAG_FULL_CONTEXT_MAX_CHARS
        if uses_rag and (query or "").strip():
            from app import rag
            async with db._pool.acquire() as conn:
                rag_chunks = await rag.search_knowledge(
                    conn,
                    bot_id,
                    query,
                    lexical_query=lexical_query,
                    limit=config.RAG_FINAL_CHUNKS,
                    diagnostics=retrieval_diagnostics,
                )
        
        if uses_rag and rag_chunks:
            knowledge_docs = [{"title": f"Fragmento de conocimiento {i+1}", "content": chunk, "status": "active"} for i, chunk in enumerate(rag_chunks)]
        elif uses_rag:
            # A retrieval miss must not turn a large base into an unbounded
            # system prompt.  The model receives no unverified document text.
            knowledge_docs = []
        else:
            knowledge_docs = all_docs
    except Exception as exc:
        log.exception("No se pudo cargar prompt/conocimiento del bot %s", bot_id)
        if bot_id == 1 and default_prompt:
            log.warning("Bot 1 usara el prompt local de Asistto por error de carga.")
            return default_prompt
        raise BotPromptUnavailable(bot_id, "prompt or knowledge load failed") from exc

    base_prompt = ((prompt_row or {}).get("content") or "").strip()
    if not base_prompt:
        if bot_id == 1 and default_prompt:
            base_prompt = default_prompt
        else:
            log.error("Bot tenant sin prompt activo; respuesta de IA bloqueada. bot_id=%s", bot_id)
            raise BotPromptUnavailable(bot_id, "no active prompt")

    if 'uses_rag' in locals() and uses_rag:
        if rag_chunks:
            base_prompt += (
                "\n\nLos fragmentos recuperados son candidatos de búsqueda. "
                "Si no contienen la respuesta exacta solicitada, eso no demuestra que el dato esté ausente "
                "de las políticas. No afirmes que no existe o que no está documentado; indica que no pudiste "
                "localizar el apartado exacto, pide una precisión útil y ofrece consultar a Capital Humano."
            )
        else:
            base_prompt += (
                "\n\nNo se encontró evidencia recuperada para esta consulta. "
                "No inventes información de la base de conocimiento. "
                "No afirmes que la información no existe o que no está documentada: "
                "indica únicamente que no pudiste localizar el apartado exacto en este momento "
                "y pide al usuario precisar el concepto o consultar a Capital Humano."
            )

    if 'retrieval_diagnostics' in locals() and retrieval_diagnostics:
        log.info(
            "RAG retrieval selected metadata. bot_id=%s selected=%d diagnostics=%s",
            bot_id,
            len(retrieval_diagnostics),
            retrieval_diagnostics,
        )

    if 'uses_rag' in locals() and uses_rag:
        # Machine-readable scope for deterministic output grounding. This is
        # intentionally separate from the tenant-authored prompt.
        base_prompt += "\n\n--- rag_grounding_required ---"

    log.info(
        "Cargando prompt para bot_id=%s. ¿Se encontró row activo?: %s, Documentos de conocimiento: %d, RAG usado: %s",
        bot_id,
        prompt_row is not None,
        len(knowledge_docs),
        bool(query and rag_chunks),
    )
    combined = combine_prompt(base_prompt, knowledge_docs)
    if 'uses_rag' in locals() and uses_rag and not rag_chunks:
        # Preserve an explicit, empty evidence boundary so downstream safety
        # checks can reject amounts copied from stale assistant history.
        combined += "\n\n--- knowledge_base ---\n\n[Sin evidencia oficial recuperada para esta consulta.]"
    return combined
