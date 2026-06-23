from __future__ import annotations

import logging

from app import config

log = logging.getLogger("whatsapp-bot")


def chunk_text(text: str, max_chars: int = 600, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks while preserving paragraphs."""
    text = (text or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0

            start = 0
            while start < len(paragraph):
                end = start + max_chars
                if end < len(paragraph):
                    last_space = paragraph.rfind(" ", start, end)
                    if last_space != -1 and last_space > start + max_chars // 2:
                        end = last_space
                chunks.append(paragraph[start:end].strip())
                start = end - overlap if end - overlap > start else end
            continue

        extra = len(paragraph) + (1 if current_chunk else 0)
        if current_len + extra <= max_chars:
            current_chunk.append(paragraph)
            current_len += extra
        else:
            chunks.append("\n".join(current_chunk))
            overlap_chunk: list[str] = []
            overlap_len = 0
            for previous in reversed(current_chunk):
                previous_extra = len(previous) + (1 if overlap_chunk else 0)
                if overlap_len + previous_extra <= overlap:
                    overlap_chunk.insert(0, previous)
                    overlap_len += previous_extra
                else:
                    break
            current_chunk = overlap_chunk + [paragraph]
            current_len = sum(len(item) for item in current_chunk) + len(current_chunk) - 1

    if current_chunk:
        chunks.append("\n".join(current_chunk))
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


async def index_document(conn, bot_id: int, knowledge_id: int, content: str) -> None:
    """Index one active knowledge document for a bot."""
    await conn.execute("DELETE FROM bot_knowledge_chunks WHERE knowledge_id = $1", knowledge_id)

    chunks = chunk_text(content)
    if not chunks:
        return

    title_row = await conn.fetchrow(
        "SELECT title FROM bot_knowledge WHERE id = $1 AND bot_id = $2",
        knowledge_id,
        bot_id,
    )
    title = title_row["title"] if title_row else None
    has_vector = await has_vector_column(conn)

    from app import openai_client

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
                continue
            except Exception as exc:
                log.warning("RAG embedding failed; storing plain text chunk: %s", exc)

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


async def delete_document_chunks(conn, knowledge_id: int) -> None:
    await conn.execute("DELETE FROM bot_knowledge_chunks WHERE knowledge_id = $1", knowledge_id)


async def search_knowledge(conn, bot_id: int, query_text: str, limit: int = 3) -> list[str]:
    """Return active bot-scoped knowledge snippets. Knowledge is data, not instructions."""
    query_text = (query_text or "").strip()
    if not query_text:
        return []

    has_vector = await has_vector_column(conn)
    if has_vector:
        from app import openai_client

        try:
            embedding = await openai_client.get_embedding(query_text)
            if len(embedding) == config.EMBEDDING_DIMENSIONS:
                emb_str = "[" + ",".join(map(str, embedding)) + "]"
                rows = await conn.fetch(
                    """
                    SELECT c.title, c.content
                    FROM bot_knowledge_chunks c
                    JOIN bot_knowledge k ON k.id = c.knowledge_id
                    WHERE c.bot_id = $1
                      AND k.status = 'active'
                      AND c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> $2::vector
                    LIMIT $3
                    """,
                    bot_id,
                    emb_str,
                    limit,
                )
                if rows:
                    return [_format_result(row) for row in rows]
        except Exception as exc:
            log.warning("Vector search failed; using text fallback: %s", exc)

    rows = await conn.fetch(
        """
        SELECT c.title, c.content,
               ts_rank_cd(to_tsvector('spanish', c.content), plainto_tsquery('spanish', $2)) AS rank
        FROM bot_knowledge_chunks c
        JOIN bot_knowledge k ON k.id = c.knowledge_id
        WHERE c.bot_id = $1
          AND k.status = 'active'
          AND to_tsvector('spanish', c.content) @@ plainto_tsquery('spanish', $2)
        ORDER BY rank DESC, c.chunk_index ASC
        LIMIT $3
        """,
        bot_id,
        query_text,
        limit,
    )
    if not rows:
        words = [f"%{word}%" for word in query_text.split() if len(word) > 2]
        if not words:
            words = [f"%{query_text}%"]
        rows = await conn.fetch(
            """
            SELECT c.title, c.content
            FROM bot_knowledge_chunks c
            JOIN bot_knowledge k ON k.id = c.knowledge_id
            WHERE c.bot_id = $1
              AND k.status = 'active'
              AND c.content ILIKE $2
            ORDER BY c.chunk_index ASC
            LIMIT $3
            """,
            bot_id,
            words[0],
            limit,
        )
    return [_format_result(row) for row in rows]


def _format_result(row) -> str:
    title = row.get("title") if hasattr(row, "get") else row["title"]
    content = row.get("content") if hasattr(row, "get") else row["content"]
    return f"[Fuente: {title or 'Base de conocimiento'}]\n{content or ''}"
