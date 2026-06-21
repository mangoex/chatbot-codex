from __future__ import annotations
import logging

log = logging.getLogger("whatsapp-bot")


def chunk_text(text: str, max_chars: int = 600, overlap: int = 150) -> list[str]:
    """Divide un texto en fragmentos (chunks) respetando párrafos y límites de caracteres."""
    text = (text or "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current_chunk = []
    current_len = 0

    for p in paragraphs:
        if len(p) > max_chars:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0

            start = 0
            while start < len(p):
                end = start + max_chars
                if end < len(p):
                    last_space = p.rfind(" ", start, end)
                    if last_space != -1 and last_space > start + max_chars // 2:
                        end = last_space
                chunks.append(p[start:end].strip())
                start = end - overlap if end - overlap > start else end
            continue

        if current_len + len(p) + (1 if current_chunk else 0) <= max_chars:
            current_chunk.append(p)
            current_len += len(p) + (1 if current_chunk else 0)
        else:
            chunks.append("\n".join(current_chunk))
            overlap_chunk = []
            overlap_len = 0
            for prev in reversed(current_chunk):
                if overlap_len + len(prev) + (1 if overlap_chunk else 0) <= overlap:
                    overlap_chunk.insert(0, prev)
                    overlap_len += len(prev) + (1 if overlap_chunk else 0)
                else:
                    break
            current_chunk = overlap_chunk + [p]
            current_len = sum(len(x) for x in current_chunk) + len(current_chunk) - 1

    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return [c for c in chunks if c.strip()]


async def setup_rag_tables(conn) -> None:
    """Configura las tablas para RAG y habilita pgvector si está disponible."""
    has_vector = False
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        has_vector = True
        log.info("Extensión pgvector habilitada con éxito.")
    except Exception:
        log.warning("pgvector no disponible. Fallbackando a búsqueda textual.")

    if has_vector:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_knowledge_chunks (
                id BIGSERIAL PRIMARY KEY,
                bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
                knowledge_id BIGINT NOT NULL REFERENCES bot_knowledge(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                embedding VECTOR(1536)
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_bot_id ON bot_knowledge_chunks(bot_id);
        """)
    else:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_knowledge_chunks (
                id BIGSERIAL PRIMARY KEY,
                bot_id BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
                knowledge_id BIGINT NOT NULL REFERENCES bot_knowledge(id) ON DELETE CASCADE,
                content TEXT NOT NULL
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_bot_id ON bot_knowledge_chunks(bot_id);
        """)


async def has_vector_column(conn) -> bool:
    """Verifica si la columna embedding existe en la tabla de chunks."""
    try:
        row = await conn.fetchrow("""
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'bot_knowledge_chunks' AND column_name = 'embedding'
        """)
        return row is not None
    except Exception:
        return False


async def index_document(conn, bot_id: int, knowledge_id: int, content: str) -> None:
    """Genera chunks y guarda embeddings para un documento de conocimiento."""
    # Eliminar chunks viejos
    await conn.execute("DELETE FROM bot_knowledge_chunks WHERE knowledge_id = $1", knowledge_id)

    chunks = chunk_text(content)
    if not chunks:
        return

    from app import openai_client
    has_vector = await has_vector_column(conn)

    for chunk in chunks:
        if has_vector:
            try:
                emb = await openai_client.get_embedding(chunk)
                emb_str = "[" + ",".join(map(str, emb)) + "]"
                await conn.execute(
                    """
                    INSERT INTO bot_knowledge_chunks (bot_id, knowledge_id, content, embedding)
                    VALUES ($1, $2, $3, $4::vector)
                    """,
                    bot_id, knowledge_id, chunk, emb_str
                )
            except Exception as e:
                log.warning("Fallo al generar embedding para RAG, fallback a texto plano: %s", e)
                await conn.execute(
                    """
                    INSERT INTO bot_knowledge_chunks (bot_id, knowledge_id, content)
                    VALUES ($1, $2, $3)
                    """,
                    bot_id, knowledge_id, chunk
                )
        else:
            await conn.execute(
                """
                INSERT INTO bot_knowledge_chunks (bot_id, knowledge_id, content)
                VALUES ($1, $2, $3)
                """,
                bot_id, knowledge_id, chunk
            )


async def delete_document_chunks(conn, knowledge_id: int) -> None:
    """Elimina chunks de un documento de conocimiento."""
    await conn.execute("DELETE FROM bot_knowledge_chunks WHERE knowledge_id = $1", knowledge_id)


async def search_knowledge(conn, bot_id: int, query_text: str, limit: int = 3) -> list[str]:
    """Busca los fragmentos de conocimiento más relevantes para la consulta del usuario."""
    query_text = (query_text or "").strip()
    if not query_text:
        return []

    has_vector = await has_vector_column(conn)
    if has_vector:
        from app import openai_client
        try:
            emb = await openai_client.get_embedding(query_text)
            emb_str = "[" + ",".join(map(str, emb)) + "]"
            rows = await conn.fetch(
                """
                SELECT content FROM bot_knowledge_chunks
                WHERE bot_id = $1 AND embedding IS NOT NULL
                ORDER BY embedding <=> $2::vector
                LIMIT $3
                """,
                bot_id, emb_str, limit
            )
            if rows:
                return [r["content"] for r in rows]
        except Exception as e:
            log.warning("Búsqueda vectorial falló, recurriendo a búsqueda de texto: %s", e)

    # Fallback: Búsqueda simple de texto ILIKE
    words = [f"%{w}%" for w in query_text.split() if len(w) > 2]
    if not words:
        words = [f"%{query_text}%"]

    rows = await conn.fetch(
        """
        SELECT content FROM bot_knowledge_chunks
        WHERE bot_id = $1 AND (content ILIKE $2)
        LIMIT $3
        """,
        bot_id, words[0], limit
    )
    return [r["content"] for r in rows]
