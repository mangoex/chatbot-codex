from __future__ import annotations

import logging
import re
import unicodedata
from hashlib import sha256

from app import config
from app.knowledge_privacy import is_private_directory_title

log = logging.getLogger("whatsapp-bot")

_PRIVATE_DIRECTORY_TITLE_RE = (
    r"(^|[ /])(?:colaboradores|empleados|directorio_colaboradores)\.csv$"
)

_AMOUNT_EVIDENCE_RE = (
    r"(?:(?:[$€£]|mxn|usd)\s*[0-9]"
    r"|[0-9]+(?:[.,][0-9]+)?\s*(?:pesos?|mxn|usd|d[oó]lares?"
    r"|diari[oa]s?|por\s+d[ií]a|l[ií]mite|tope))"
)


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 250) -> list[str]:
    """Split text into bounded chunks, repeating the active Markdown heading path.

    The public contract intentionally remains character based.  For Markdown,
    headings are metadata rather than chunkable content: every chunk of a
    section carries its complete path so a retrieved paragraph keeps its
    business meaning.  Plain text follows the same paragraph behaviour without
    a prefix.
    """
    text = (text or "").strip()
    if not text or max_chars <= 0:
        return []

    # Closing ATX hashes are optional only when separated from the title by
    # whitespace.  This preserves legitimate titles such as "Uso de C#".
    heading_re = re.compile(r"^(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
    sections: list[tuple[list[str], list[str]]] = []
    heading_path: list[str] = []
    paragraph_lines: list[str] = []

    def finish_paragraph() -> None:
        if paragraph_lines:
            paragraph = "\n".join(paragraph_lines).strip()
            if paragraph:
                if not sections or sections[-1][0] != heading_path:
                    sections.append((heading_path.copy(), []))
                sections[-1][1].append(paragraph)
            paragraph_lines.clear()

    for line in text.splitlines():
        match = heading_re.match(line.strip())
        if match:
            finish_paragraph()
            level = len(match.group(1))
            heading = f"{'#' * level} {match.group(2).strip()}"
            heading_path = heading_path[: level - 1]
            heading_path.append(heading)
            continue
        if not line.strip():
            finish_paragraph()
        else:
            paragraph_lines.append(line.strip())
    finish_paragraph()

    chunks: list[str] = []

    def bounded_prefix(path: list[str]) -> str:
        """Return the full path when possible, else a deterministic compact marker.

        A Markdown path can itself be longer than a chunk budget.  In that
        impossible case, keeping the full path would discard the evidence
        body.  The digest marker preserves a stable section identity while
        reserving at least one character for body content.
        """
        prefix = "\n".join(path)
        if not prefix or len(prefix) + 2 < max_chars:
            return prefix
        digest = sha256(prefix.encode("utf-8")).hexdigest()[:12]
        marker = f"[H:{digest}]"
        if len(marker) + 2 < max_chars:
            return marker
        # Tiny caller-provided limits cannot hold the marker and a separator;
        # reserve one body character and remain deterministic.
        return "[H]"[:max(0, max_chars - 2)]

    def render(prefix: str, body: list[str]) -> str:
        content = "\n\n".join(part for part in body if part.strip())
        return f"{prefix}\n\n{content}".strip() if prefix else content.strip()

    def split_to_budget(value: str, budget: int) -> list[str]:
        """Split a large paragraph at word boundaries; always make progress."""
        value = value.strip()
        if not value:
            return []
        if budget <= 0:
            # An impractically large heading is still emitted deterministically.
            return [value[:max_chars]]
        parts: list[str] = []
        remaining = value
        while remaining:
            if len(remaining) <= budget:
                parts.append(remaining)
                break
            boundary = remaining.rfind(" ", 0, budget + 1)
            if boundary <= max(0, budget // 2):
                boundary = budget
            part = remaining[:boundary].strip()
            if part:
                parts.append(part)
            remaining = remaining[boundary:].strip()
        return parts

    for path, paragraphs in sections:
        prefix = bounded_prefix(path)
        prefix_len = len(prefix)
        separator_len = 2 if path else 0
        body_budget = max_chars - prefix_len - separator_len
        current: list[str] = []

        def flush() -> None:
            if current:
                rendered = render(prefix, current)
                if rendered:
                    chunks.append(rendered[:max_chars])
                current.clear()

        for paragraph in paragraphs:
            pending = split_to_budget(paragraph, body_budget)
            while pending:
                part = pending.pop(0)
                prospective = render(prefix, current + [part])
                if current and len(prospective) > max_chars:
                    previous_body = "\n\n".join(current)
                    flush()
                    if overlap > 0 and body_budget > 0:
                        # Keep space for a new word after the overlap.  This is
                        # what makes overlap effective for a single long
                        # paragraph, not only for paragraph boundaries.
                        overlap_budget = max(0, body_budget - 3)
                        overlap_body = previous_body[-min(overlap, overlap_budget):].strip()
                        if overlap_body:
                            current.append(overlap_body)
                    available = max_chars - len(render(prefix, current)) - (2 if current else 0)
                    if available <= 0:
                        current.clear()
                        available = body_budget
                    if len(part) > available:
                        split_parts = split_to_budget(part, available)
                        if split_parts:
                            pending = split_parts[1:] + pending
                            part = split_parts[0]
                current.append(part)
        flush()

    return [chunk for chunk in chunks if chunk.strip()]


async def setup_rag_tables(conn) -> None:
    """Create or migrate RAG tables with strict bot-scoped chunks."""
    has_vector = False
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        has_vector = True
        log.info("pgvector extension is available.")
    except Exception:
        log.warning("pgvector is not available; using text retrieval fallback.")

    embedding_column = f", embedding VECTOR({config.EMBEDDING_DIMENSIONS})" if has_vector else ""
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS bot_knowledge_chunks (
            id BIGSERIAL PRIMARY KEY,
            bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            knowledge_id BIGINT NOT NULL REFERENCES bot_knowledge(id) ON DELETE CASCADE,
            title TEXT,
            chunk_index INT NOT NULL DEFAULT 0,
            content TEXT NOT NULL
            {embedding_column}
        );
        """
    )
    for column, definition in (("title", "TEXT"), ("chunk_index", "INT NOT NULL DEFAULT 0")):
        await conn.execute(
            f"ALTER TABLE bot_knowledge_chunks ADD COLUMN IF NOT EXISTS {column} {definition}"
        )
    if has_vector and not await has_vector_column(conn):
        await conn.execute(
            f"ALTER TABLE bot_knowledge_chunks ADD COLUMN IF NOT EXISTS embedding VECTOR({config.EMBEDDING_DIMENSIONS})"
        )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_bot_id ON bot_knowledge_chunks(bot_id);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_knowledge_id ON bot_knowledge_chunks(knowledge_id);"
    )


async def has_vector_column(conn) -> bool:
    try:
        row = await conn.fetchrow(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'bot_knowledge_chunks' AND column_name = 'embedding'
            """
        )
        return row is not None
    except Exception:
        return False


def _content_hash(content: str) -> str:
    return sha256((content or "").encode("utf-8")).hexdigest()


async def _set_index_state(
    conn,
    bot_id: int,
    knowledge_id: int,
    status: str,
    *,
    index_error: str | None = None,
    content_hash: str | None = None,
) -> None:
    """Persist only sanitized indexing metadata for the tenant document."""
    await conn.execute(
        """
        UPDATE bot_knowledge
        SET index_status = $1,
            index_error = $2,
            indexed_at = CASE WHEN $1 IN ('indexed', 'partial', 'failed') THEN now() ELSE NULL END,
            embedding_model = $3,
            content_hash = COALESCE($4, content_hash)
        WHERE id = $5 AND bot_id = $6
        """,
        status,
        index_error,
        config.EMBEDDING_MODEL,
        content_hash,
        knowledge_id,
        bot_id,
    )


async def index_document(conn, bot_id: int, knowledge_id: int, content: str) -> dict:
    """Index one active knowledge document for a bot."""
    content_hash = _content_hash(content)
    await _set_index_state(conn, bot_id, knowledge_id, "pending", content_hash=content_hash)
    await conn.execute(
        "DELETE FROM bot_knowledge_chunks WHERE knowledge_id = $1 AND bot_id = $2",
        knowledge_id,
        bot_id,
    )

    title_row = await conn.fetchrow(
        "SELECT title FROM bot_knowledge WHERE id = $1 AND bot_id = $2",
        knowledge_id,
        bot_id,
    )
    title = title_row["title"] if title_row else None
    if not title_row:
        await _set_index_state(
            conn, bot_id, knowledge_id, "failed", index_error="Documento no disponible."
        )
        return {
            "status": "failed", "chunk_count": 0,
            "embedded_chunk_count": 0, "failed_chunk_count": 0,
        }
    if is_private_directory_title(title):
        log.info(
            "Directorio privado excluido de RAG. bot_id=%s knowledge_id=%s",
            bot_id,
            knowledge_id,
        )
        await _set_index_state(conn, bot_id, knowledge_id, "indexed")
        return {
            "status": "indexed", "chunk_count": 0,
            "embedded_chunk_count": 0, "failed_chunk_count": 0,
        }

    chunks = chunk_text(content)
    if not chunks:
        await _set_index_state(
            conn, bot_id, knowledge_id, "failed", index_error="El documento no produjo fragmentos recuperables."
        )
        return {
            "status": "failed", "chunk_count": 0,
            "embedded_chunk_count": 0, "failed_chunk_count": 0,
        }

    has_vector = await has_vector_column(conn)

    from app import openai_client

    embedded_chunk_count = 0
    failed_chunk_count = 0
    try:
        for index, chunk in enumerate(chunks):
            if has_vector:
                try:
                    embedding = await openai_client.get_embedding(chunk)
                    if len(embedding) != config.EMBEDDING_DIMENSIONS:
                        raise ValueError("Embedding dimensions do not match EMBEDDING_DIMENSIONS")
                    emb_str = "[" + ",".join(map(str, embedding)) + "]"
                    await conn.execute(
                        """
                        INSERT INTO bot_knowledge_chunks(
                            bot_id, knowledge_id, title, chunk_index, content, embedding
                        )
                        VALUES($1, $2, $3, $4, $5, $6::vector)
                        """,
                        bot_id,
                        knowledge_id,
                        title,
                        index,
                        chunk,
                        emb_str,
                    )
                    embedded_chunk_count += 1
                    continue
                except Exception:
                    # Provider errors may include prompts or provider metadata; do
                    # not persist or log their raw text.
                    failed_chunk_count += 1
                    log.warning(
                        "RAG embedding failed; storing text-only chunk. bot_id=%s knowledge_id=%s",
                        bot_id, knowledge_id,
                    )

            await conn.execute(
                """
                INSERT INTO bot_knowledge_chunks(bot_id, knowledge_id, title, chunk_index, content)
                VALUES($1, $2, $3, $4, $5)
                """,
                bot_id,
                knowledge_id,
                title,
                index,
                chunk,
            )
    except Exception:
        # A storage failure means the document cannot be relied on, even if a
        # prior chunk was written in this transaction.  Keep the status honest
        # and do not expose a provider/database exception.
        log.warning("RAG document indexing failed. bot_id=%s knowledge_id=%s", bot_id, knowledge_id)
        failed_chunk_count = max(failed_chunk_count, len(chunks) - embedded_chunk_count)
        # Never leave partial, potentially stale chunks queryable after a
        # fatal document failure.  The delete retains the tenant boundary.
        await delete_document_chunks(conn, bot_id, knowledge_id)
        await _set_index_state(
            conn, bot_id, knowledge_id, "failed", index_error="No fue posible indexar el documento."
        )
        return {
            "status": "failed",
            "chunk_count": len(chunks),
            "embedded_chunk_count": embedded_chunk_count,
            "failed_chunk_count": failed_chunk_count,
        }

    status = "partial" if failed_chunk_count else "indexed"
    error = (
        f"No fue posible generar {failed_chunk_count} embedding(s)."
        if failed_chunk_count else None
    )
    await _set_index_state(conn, bot_id, knowledge_id, status, index_error=error)
    return {
        "status": status,
        "chunk_count": len(chunks),
        "embedded_chunk_count": embedded_chunk_count,
        "failed_chunk_count": failed_chunk_count,
    }


async def delete_document_chunks(conn, bot_id: int, knowledge_id: int) -> None:
    await conn.execute(
        "DELETE FROM bot_knowledge_chunks WHERE knowledge_id = $1 AND bot_id = $2",
        knowledge_id,
        bot_id,
    )


async def reindex_bot_knowledge(conn, bot_id: int) -> dict[str, int]:

    """Re-chunks and re-indexes all active knowledge documents for a bot."""
    rows = await conn.fetch(
        "SELECT id, content FROM bot_knowledge WHERE bot_id = $1 AND status = 'active'",
        bot_id,
    )
    summary = {"total": 0, "indexed": 0, "partial": 0, "failed": 0}
    for row in rows:
        report = await index_document(conn, bot_id, int(row["id"]), row["content"] or "")
        summary["total"] += 1
        status = str(report.get("status") or "failed")
        summary[status if status in summary else "failed"] += 1
    return summary


def _row_value(row, key: str, default=None):
    if hasattr(row, "get"):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, TypeError):
        return default


def _keyword_patterns(query_text: str) -> list[str]:
    stopwords = {
        "para", "como", "esta", "este", "esto", "sobre", "donde", "cuando",
        "actual", "pregunta", "contexto", "usuario", "asistente", "tambien",
    }
    words = []
    for word in re.findall(r"[\wáéíóúüñ]+", (query_text or "").lower()):
        if len(word) < 4 or word in stopwords or word in words:
            continue
        words.append(word)
        if len(words) == 8:
            break
    return [f"%{word}%" for word in words] or [f"%{query_text.strip()}%"]


def _asks_for_amount(query_text: str) -> bool:
    normalized = unicodedata.normalize("NFKD", (query_text or "").lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    words = set(re.findall(r"[a-z0-9]+", normalized))
    return bool(words & {
        "cuanto", "cuantos", "cuanta", "cuantas", "monto", "montos",
        "limite", "limites", "tope", "topes", "gastar", "gasto",
        "cuesta", "costo", "costos", "precio", "precios", "importe",
    })


async def search_knowledge(
    conn,
    bot_id: int,
    query_text: str,
    limit: int = 8,
    lexical_query: str | None = None,
    diagnostics: list[dict] | None = None,
) -> list[str]:
    """Hybrid vector/text retrieval with bot scope and per-document diversity."""
    query_text = (query_text or "").strip()
    if not query_text:
        return []

    candidate_limit = max(config.RAG_CANDIDATE_CHUNKS, limit * 2)
    vector_rows = []
    has_vector = await has_vector_column(conn)
    if has_vector:
        from app import openai_client

        try:
            embedding = await openai_client.get_embedding(query_text)
            if len(embedding) == config.EMBEDDING_DIMENSIONS:
                emb_str = "[" + ",".join(map(str, embedding)) + "]"
                vector_rows = await conn.fetch(
                    """
                    SELECT c.knowledge_id, c.chunk_index, c.title, c.content,
                           c.embedding <=> $2::vector AS distance
                    FROM bot_knowledge_chunks c
                    JOIN bot_knowledge k ON k.id = c.knowledge_id AND k.bot_id = c.bot_id
                    WHERE c.bot_id = $1
                      AND k.status = 'active'
                      AND k.index_status IN ('indexed', 'partial')
                      AND c.embedding IS NOT NULL
                      AND lower(COALESCE(c.title, '')) !~ $3
                    ORDER BY c.embedding <=> $2::vector
                    LIMIT $4
                    """,
                    bot_id,
                    emb_str,
                    _PRIVATE_DIRECTORY_TITLE_RE,
                    candidate_limit,
                )
        except Exception:
            log.warning("Vector search failed; using text fallback. bot_id=%s", bot_id)

    lexical = (lexical_query or query_text).strip()
    keyword_patterns = _keyword_patterns(lexical)
    asks_for_amount = _asks_for_amount(lexical)
    text_rows = await conn.fetch(
        """
        SELECT c.knowledge_id, c.chunk_index, c.title, c.content,
               ts_rank_cd(
                   to_tsvector('spanish', COALESCE(c.title, '') || ' ' || c.content),
                   plainto_tsquery('spanish', $2)
               ) AS rank,
               (
                   SELECT COUNT(*)::int
                   FROM unnest($3::text[]) AS keyword(pattern)
                   WHERE c.content ILIKE keyword.pattern
               ) AS content_keyword_hits,
               CASE
                   WHEN $5::boolean AND c.content ~* $6 THEN 1
                   ELSE 0
               END AS answer_shape
        FROM bot_knowledge_chunks c
        JOIN bot_knowledge k ON k.id = c.knowledge_id AND k.bot_id = c.bot_id
        WHERE c.bot_id = $1
          AND k.status = 'active'
          AND k.index_status IN ('indexed', 'partial')
          AND lower(COALESCE(c.title, '')) !~ $4
          AND (
              to_tsvector('spanish', COALESCE(c.title, '') || ' ' || c.content)
                  @@ plainto_tsquery('spanish', $2)
              OR c.content ILIKE ANY($3::text[])
              OR COALESCE(c.title, '') ILIKE ANY($3::text[])
          )
        ORDER BY answer_shape DESC, content_keyword_hits DESC, rank DESC, c.chunk_index ASC
        LIMIT $7
        """,
        bot_id,
        lexical,
        keyword_patterns,
        _PRIVATE_DIRECTORY_TITLE_RE,
        asks_for_amount,
        _AMOUNT_EVIDENCE_RE,
        candidate_limit,
    )

    candidates: dict[tuple, dict] = {}
    for source, rows, weight in (
        # Semantic evidence must survive broad title-only lexical matches.
        ("vector", vector_rows, 2.0),
        ("text", text_rows, 1.0),
    ):
        for rank_index, row in enumerate(rows, start=1):
            title = _row_value(row, "title") or "Base de conocimiento"
            if is_private_directory_title(title):
                continue
            distance = _row_value(row, "distance")
            if (
                source == "vector"
                and distance is not None
                and float(distance) > config.RAG_MAX_COSINE_DISTANCE
            ):
                continue
            knowledge_id = _row_value(row, "knowledge_id", title)
            chunk_index = int(_row_value(row, "chunk_index", 0) or 0)
            key = (knowledge_id, chunk_index)
            item = candidates.setdefault(
                key,
                {
                    "knowledge_id": knowledge_id,
                    "chunk_index": chunk_index,
                    "title": title,
                    "content": _row_value(row, "content") or "",
                    "score": 0.0,
                    "retrieval_sources": set(),
                    "vector_distance": None,
                    "text_rank": 0.0,
                    "content_keyword_hits": 0,
                    "answer_shape": 0,
                },
            )
            item["score"] += weight / (60 + rank_index)
            item["retrieval_sources"].add(source)
            if source == "vector" and distance is not None:
                item["vector_distance"] = float(distance)
                item["score"] += max(0.0, 1.0 - float(distance)) * 0.05
            elif source == "text":
                text_rank = float(_row_value(row, "rank", 0.0) or 0.0)
                keyword_hits = int(_row_value(row, "content_keyword_hits", 0) or 0)
                answer_shape = int(_row_value(row, "answer_shape", 0) or 0)
                item["text_rank"] = max(item["text_rank"], text_rank)
                item["content_keyword_hits"] = max(
                    item["content_keyword_hits"], keyword_hits
                )
                item["answer_shape"] = max(item["answer_shape"], answer_shape)
                item["score"] += min(max(text_rank, 0.0), 1.0) * 0.02
                item["score"] += min(max(keyword_hits, 0), 8) * 0.003
                item["score"] += max(answer_shape, 0) * 0.06

    selected = []
    per_document: dict[object, int] = {}
    per_document_limit = max(1, min(config.RAG_MAX_CHUNKS_PER_DOCUMENT, limit))
    for item in sorted(candidates.values(), key=lambda value: value["score"], reverse=True):
        knowledge_id = item["knowledge_id"]
        if per_document.get(knowledge_id, 0) >= per_document_limit:
            continue
        selected.append(item)
        per_document[knowledge_id] = per_document.get(knowledge_id, 0) + 1
        if len(selected) == limit:
            break
    if diagnostics is not None:
        for item in selected:
            diagnostic = {
                "knowledge_id": item["knowledge_id"],
                "chunk_index": item["chunk_index"],
                "title": item["title"],
                "score": float(item["score"]),
                "retrieval_sources": sorted(item["retrieval_sources"]),
            }
            if item["vector_distance"] is not None:
                diagnostic["vector_distance"] = item["vector_distance"]
            diagnostics.append(diagnostic)
    return [_format_result(row) for row in selected]


def _format_result(row) -> str:
    title = row.get("title") if hasattr(row, "get") else row["title"]
    content = row.get("content") if hasattr(row, "get") else row["content"]
    return f"[Fuente: {title or 'Base de conocimiento'}]\n{content or ''}"
