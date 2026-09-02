# Diseño de confiabilidad para Base de Conocimiento y RAG

## Metadata

- Fecha: 2026-09-02
- Estado: `SPECIFIED`
- Alcance: plataforma multi-tenant Asistto; todos los bots, incluido Mobi (`bot_id=170`)
- Evidencia: `CONFIRMED` salvo donde se marque lo contrario
- Autoridad PBD: `CON-006`, `CON-013`, `CON-017`

## Contexto y problema

Asistto ya dispone de recuperación híbrida vectorial/textual, pero una base grande puede comportarse como si la información no existiera. El comportamiento confirmado que origina el riesgo es:

1. `app/rag.py` corta texto por párrafos y caracteres sin conservar la ruta de encabezados Markdown.
2. `app/bot_content.py` activa RAG al superar 15,000 caracteres.
3. Si la recuperación no devuelve fragmentos, `system_prompt_for_bot` vuelve a inyectar todos los documentos activos.
4. La consulta semántica incluye mensajes del asistente, por lo que una respuesta anterior errónea puede contaminar la búsqueda siguiente.
5. El panel muestra conteos de fragmentos y embeddings, pero no diferencia de forma persistente `pending`, `partial` o `failed`.
6. La selección no expone metadatos operativos suficientes para explicar qué fuente ganó y con qué puntaje.

En Mobi, once documentos compiten por un máximo de ocho fragmentos. El formato `.md` facilita la lectura humana, pero actualmente no garantiza que un fragmento conserve el encabezado que le da significado.

## Decisión PBD

Este cambio es infraestructura de recuperación de fuentes autorizadas. No agrega políticas, no cambia el tono, no altera guardrails ni modifica el significado de las respuestas. Por ello:

- `docs/pbd/01-constitution.md` se leyó primero y no requiere modificación.
- `docs/pbd/02-behavior-specs.md`, `03-test-suite.md` y `04-master-prompt.md` permanecen sin cambios.
- No se recompila el Master Prompt: la semántica conversacional no cambió.
- Se preserva `CON-006`: nunca inventar información.
- Se preserva `CON-013`: la base local sigue siendo una fuente autorizada.
- Se refuerza `CON-017`: prompt, conocimiento, índices y consultas quedan acotados al `bot_id` resuelto.

## Objetivos

1. Conservar el significado estructural de Markdown en cada fragmento.
2. Garantizar que una recuperación vacía tenga un fallback pequeño y cerrado.
3. Evitar que texto generado por el asistente se convierta en evidencia de recuperación.
4. Hacer observable el retrieval con metadatos seguros, sin registrar contenido, consultas, embeddings ni secretos.
5. Representar de manera explícita y persistente la salud de indexación por documento.
6. Mantener aislamiento estricto por bot en toda lectura, escritura, borrado, diagnóstico y reindexación.

## No objetivos

- Cambiar prompts conversacionales o reglas de negocio de Mobi.
- Mover documentos entre Base de Conocimiento y Master Prompt automáticamente.
- Incorporar un proveedor nuevo de embeddings o una base vectorial externa.
- Exponer texto completo de documentos en logs o diagnósticos.
- Resolver en esta entrega un reranker basado en otro LLM.

## Diseño funcional

### 1. Fragmentación consciente de Markdown

`rag.chunk_text(text, max_chars=1200, overlap=250)` conserva su contrato público y pasa a interpretar encabezados ATX `#` a `######`.

Reglas:

- Cada fragmento de una sección incluye la ruta completa de encabezados activa, por ejemplo `# Manual`, `## Viáticos`, `### Alimentos`.
- Al entrar a una sección hermana, se reemplaza el encabezado del mismo nivel; no se arrastra `## Alimentos` hacia `## Hospedaje`.
- El presupuesto `max_chars` incluye los encabezados repetidos.
- Los párrafos se mantienen completos cuando caben; un párrafo mayor al presupuesto se divide por límite de palabra.
- El solapamiento se aplica al cuerpo, después de reservar espacio para la ruta de encabezados.
- Ningún fragmento vacío se indexa.
- Texto plano y documentos sin encabezados conservan compatibilidad con el comportamiento anterior.
- Si la ruta completa por sí sola no cabe junto con evidencia, se usa el marcador determinista `[H:<hash>]` y se reserva cuerpo; nunca se recorta el cuerpo sólo para conservar un encabezado imposible de alojar dentro de `max_chars`. Es una excepción explícita a la repetición literal de ruta: el hash es estable para la misma ruta y no pretende ser legible como título.

Las tablas y bloques cercados deben tratarse como unidades indivisibles cuando quepan. Si por sí solos exceden el límite, pueden dividirse de forma determinista repitiendo encabezado de tabla o marcador de bloque. Este requisito es recomendado, no bloquea la primera entrega.

### 2. Recuperación y fallback acotado

- Las bases pequeñas pueden seguir inyectándose completas según un umbral configurable.
- Una base que entra al flujo RAG nunca vuelve a `all_docs` por una consulta vacía o sin resultados.
- Esto también aplica cuando la consulta es `None` o está vacía (por ejemplo, generación de follow-ups): una base grande nunca se inyecta completa.
- Si la búsqueda híbrida no selecciona evidencia, el prompt contiene sólo el prompt base y, opcionalmente, una instrucción corta de evidencia no encontrada; no contiene los documentos grandes completos.
- El límite final continúa controlado por `RAG_FINAL_CHUNKS`.
- La búsqueda textual es parte de la recuperación híbrida normal, no una autorización para inyectar documentos completos.
- Los fragmentos privados de directorio continúan excluidos del RAG general.

### 3. Consulta semántica resistente a autocontaminación

`bot_content.build_retrieval_query(user_message, history)` aplica dos caminos:

- Pregunta autosuficiente: usa únicamente la pregunta actual normalizada.
- Seguimiento contextual corto: incorpora los mensajes recientes del usuario necesarios para resolver referencias como “¿y para alimentos?”, “¿cuál de esos?” o “¿y en ese caso?”.

En ambos caminos se excluyen siempre los mensajes con rol `assistant`, `system` o `tool`. Una respuesta anterior del bot no es una fuente autorizada y nunca se embebe como parte de la consulta.

La detección de seguimiento debe ser determinista y conservadora. Si existe duda, se prefiere la pregunta actual sola antes que incorporar una respuesta del asistente.

### 4. Diagnóstico seguro de recuperación

`rag.search_knowledge` mantiene como retorno normal `list[str]`. Acepta un colector opcional `diagnostics: list[dict] | None`; cuando existe, agrega una entrada por fragmento seleccionado con:

- `knowledge_id`
- `chunk_index`
- `title`
- `score` combinado
- `retrieval_sources`: subconjunto de `vector` y `text`
- `vector_distance`, únicamente si ya está disponible y no contiene información de usuario

El diagnóstico no incluye:

- `content` o extractos del fragmento
- consulta original o consulta reescrita
- embeddings
- credenciales, errores crudos del proveedor o datos del directorio privado

Los puntajes sirven para comparación operativa dentro de la misma consulta; no se presentan como probabilidad. Los títulos se escapan al renderizarse en HTML.

### 5. Estado y estadísticas de indexación

Cada documento activo tiene estado persistente:

- `pending`: creado o modificado, todavía sin intento completo.
- `indexed`: todos los fragmentos esperados están disponibles; si pgvector no existe, el modo puede ser sólo textual sin considerarse fallo.
- `partial`: existen fragmentos recuperables, pero uno o más embeddings fallaron.
- `failed`: el documento no produjo fragmentos recuperables o ocurrió un fallo fatal.

Los documentos `pending` o `failed` no son candidatos de recuperación. Un fallo fatal limpia los chunks del documento y bot afectados antes de persistir `failed`.

Campos aditivos propuestos en `bot_knowledge`:

- `index_status TEXT NOT NULL DEFAULT 'pending'`
- `index_error TEXT`
- `indexed_at TIMESTAMPTZ`
- `embedding_model TEXT`
- `content_hash TEXT`

Restricciones:

- `index_error` es un resumen sanitizado y acotado; nunca contiene contenido del documento, tokens o respuesta cruda del proveedor.
- `index_document` devuelve un reporte con `status`, `chunk_count`, `embedded_chunk_count` y `failed_chunk_count`.
- `get_bot_knowledge_index_stats(bot_id)` expone esos conteos y estado, sin contenido.
- El panel distingue visualmente `Pendiente`, `Indexado`, `Parcial` y `Fallido`.
- Reindexar recalcula hash, modelo, conteos y estado sólo para el bot solicitado.

### 6. Aislamiento multi-tenant

Todo SQL sobre `bot_knowledge_chunks` incluye `bot_id` además de `knowledge_id`, incluso cuando el identificador sea globalmente único.

Esto aplica a:

- indexación y borrado previo de fragmentos
- archivado y borrado de fragmentos
- recuperación vectorial y textual
- estadísticas y diagnósticos
- reindexación completa

No se aceptan filas `bot_id IS NULL`, fallbacks hacia bot 1 ni búsquedas globales para compatibilidad heredada.

## Contratos de código

```python
def chunk_text(text: str, max_chars: int = 1200, overlap: int = 250) -> list[str]: ...

def build_retrieval_query(user_message: str, history: list[dict]) -> str: ...

async def search_knowledge(
    conn,
    bot_id: int,
    query_text: str,
    limit: int = 8,
    lexical_query: str | None = None,
    diagnostics: list[dict] | None = None,
) -> list[str]: ...

async def index_document(
    conn,
    bot_id: int,
    knowledge_id: int,
    content: str,
) -> dict: ...

async def get_bot_knowledge_index_stats(bot_id: int) -> dict[int, dict]: ...
```

No se cambia el contrato de `openai_client.complete`; sólo consume una consulta de recuperación más segura y un system prompt acotado.

## Criterios de aceptación

### AC-RAG-001 — Estructura Markdown

```text
DADO QUE un documento Markdown tiene encabezados anidados y una sección ocupa varios fragmentos
CUANDO se ejecuta chunk_text
ENTONCES cada fragmento de esa sección contiene la ruta completa de encabezados que le da contexto
Y NO DEBE exceder max_chars ni heredar un encabezado hermano anterior.
```

### AC-RAG-002 — Recuperación vacía

```text
DADO QUE la base activa supera el umbral de RAG
CUANDO la recuperación híbrida devuelve cero fragmentos
ENTONCES el system prompt queda acotado al prompt base y una indicación breve de falta de evidencia
Y NO DEBE inyectar todos los documentos activos.
```

### AC-RAG-003 — Consulta semántica

```text
DADO QUE el historial contiene preguntas del usuario y respuestas del bot
CUANDO se construye una consulta para una pregunta autosuficiente o un seguimiento
ENTONCES se usa la pregunta actual y, sólo para el seguimiento, contexto reciente del usuario
Y NO DEBE incluir respuestas del asistente.
```

### AC-RAG-004 — Diagnóstico seguro

```text
DADO QUE un fragmento fue seleccionado por vector, texto o ambos
CUANDO se solicita diagnóstico
ENTONCES se reportan fuente, índice, score y métodos de recuperación
Y NO DEBE exponerse contenido, consulta, embedding, secreto o fila de directorio privado.
```

### AC-RAG-005 — Estado de indexación

```text
DADO QUE algunos embeddings de un documento fallan
CUANDO termina la indexación
ENTONCES los fragmentos textuales siguen recuperables y el documento queda partial con conteos coherentes
Y NO DEBE mostrarse como indexed completo ni guardar un error sensible.
```

### AC-RAG-006 — Aislamiento

```text
DADO QUE existen documentos de dos bots
CUANDO se indexa, busca, diagnostica, archiva o reindexa uno de ellos
ENTONCES cada consulta y escritura incluye el bot_id solicitado
Y NO DEBE leer, mutar o presentar metadatos del otro bot.
```

## Riesgos y mitigaciones

- Repetir encabezados reduce cuerpo útil por fragmento: el límite contabiliza encabezados y evita crecimiento no controlado.
- Una ruta de encabezados matemáticamente mayor que `max_chars` no puede repetirse literalmente sin perder la evidencia: el marcador `[H:<hash>]` conserva identidad determinista y reserva cuerpo. Si se requiere ver el título completo, debe consultarse el documento fuente, no ampliar el fragmento fuera del límite.
- Un detector de seguimiento demasiado amplio reintroduce ruido: se usan reglas deterministas y sólo mensajes de usuario.
- Persistir errores podría filtrar secretos: se almacena una categoría sanitizada, no `str(exc)` crudo.
- Reindexar dentro de una transacción larga puede aumentar latencia: esta entrega conserva el flujo actual; procesamiento en segundo plano queda como evolución posterior.
- Cambiar chunks invalida embeddings previos: la migración debe reindexar documentos activos o marcarlos `pending` hasta reindexación.

## Observabilidad y privacidad

Eventos recomendados de log, siempre como metadatos:

- `rag_index_started`: `bot_id`, `knowledge_id`, `content_hash`
- `rag_index_completed`: estado y conteos
- `rag_search_completed`: `bot_id`, número de candidatos, número seleccionado y duración

No registrar texto de documento, pregunta del usuario, número telefónico, embedding ni respuesta completa del proveedor.

## Evoluciones posteriores

- Recuperar más candidatos y aplicar reranking determinista o cross-encoder.
- Convertir el umbral de contexto completo de caracteres a tokens.
- Indexación en segundo plano por lotes con reintentos.
- Buscador de diagnóstico interactivo en el panel con acceso restringido.
- Versionar estrategia de chunks además de modelo/hash para detectar índices obsoletos.

## Estado de despliegue

`NO VERIFICADO`. Esta especificación y sus pruebas no modifican producción ni conectan a base de datos externa.
