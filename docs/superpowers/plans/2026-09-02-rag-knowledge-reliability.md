# Plan de implementación — Confiabilidad de Base de Conocimiento y RAG

> Fecha: 2026-09-02
> Especificación: `docs/superpowers/specs/2026-09-02-rag-knowledge-reliability-design.md`
> Método: especificación y TDD por Sol, implementación por Terra, auditoría final por Sol.

## Objetivo

Hacer que las bases grandes, como los once documentos Markdown de Mobi, recuperen evidencia con contexto estructural, fallback acotado, diagnóstico seguro, estado de indexación explícito y aislamiento estricto por bot.

## Restricciones

- Preservar `CON-006`, `CON-013` y `CON-017`.
- No cambiar `docs/pbd/*` ni compilar el Master Prompt porque no existe cambio semántico conversacional.
- No revelar ni modificar secretos.
- Aplicar migraciones aditivas; no destruir documentos o chunks existentes.
- Mantener compatibilidad del retorno normal de `search_knowledge` y del contrato de `openai_client.complete`.
- No desplegar ni tocar producción en esta tarea.

## Mapa de pruebas

| Criterio | Prueba TDD |
| --- | --- |
| AC-RAG-001 | `MarkdownAwareChunkingTests` |
| AC-RAG-002 | `BoundedKnowledgeFallbackTests` |
| AC-RAG-003 | `RetrievalQueryTests` |
| AC-RAG-004 | `SafeRetrievalDiagnosticsTests.test_diagnostics_expose_source_and_score_but_not_chunk_content` |
| AC-RAG-005 | `IndexingStateTests` |
| AC-RAG-006 | prueba de SQL acotado en `SafeRetrievalDiagnosticsTests` y borrado acotado en `tests/test_rag.py` |

## Tareas

### Tarea 1 — Sol: congelar contratos y baseline TDD

Archivos:

- Crear `tests/test_rag_knowledge_reliability.py`.
- Ajustar `tests/test_rag.py` para exigir borrado por `knowledge_id` y `bot_id`.

Pasos:

- [x] Escribir pruebas de chunking por ruta de encabezados Markdown.
- [x] Escribir pruebas de fallback acotado con retrieval vacío.
- [x] Escribir pruebas de pregunta autosuficiente y seguimiento sin respuestas del asistente.
- [x] Escribir pruebas de diagnóstico con score y sin contenido sensible.
- [x] Escribir pruebas de estado `partial`, conteos e informe seguro.
- [x] Escribir pruebas de aislamiento SQL por bot.
- [ ] Ejecutar pruebas objetivo y registrar fallos esperados antes de código Terra.

### Tarea 2 — Terra: implementar chunking Markdown consciente

Archivos:

- Modificar `app/rag.py`.
- Verificar `tests/test_rag.py` y `tests/test_rag_knowledge_reliability.py`.

Pasos:

- [x] Parsear encabezados ATX y mantener una pila por nivel.
- [x] Reservar presupuesto para repetir la ruta de encabezados en cada chunk.
- [x] Cortar párrafos largos por palabra sin superar `max_chars`.
- [x] Evitar encabezados hermanos obsoletos después de un cambio de sección.
- [x] Mantener comportamiento estable para texto plano.
- [x] Ejecutar pruebas de chunking y regresiones de RAG existentes.

### Tarea 3 — Terra: cerrar fallback y limpiar la consulta semántica

Archivos:

- Modificar `app/bot_content.py`.
- Revisar `app/openai_client.py` sin cambiar su contrato público.

Pasos:

- [x] Distinguir pregunta autosuficiente de seguimiento contextual corto.
- [x] Para seguimiento, usar sólo mensajes recientes con rol `user`.
- [x] Excluir siempre roles `assistant`, `system` y `tool`.
- [x] Cuando una base grande entra a RAG y no hay resultados, usar conocimiento vacío o una instrucción breve; nunca `all_docs`.
- [x] Mantener inyección completa para bases pequeñas dentro del umbral vigente/configurable.
- [x] Ejecutar pruebas de `RetrievalQueryTests`, `BoundedKnowledgeFallbackTests` y regresiones focalizadas de `tests/test_bot_content.py`.

### Tarea 4 — Terra: agregar diagnóstico seguro y scores

Archivos:

- Modificar `app/rag.py`.
- Modificar `app/bot_content.py` sólo si se requiere propagar un colector interno.

Pasos:

- [x] Añadir parámetro opcional `diagnostics` sin cambiar el retorno normal `list[str]`.
- [x] Conservar por candidato los métodos `vector`/`text`, score combinado y distancia disponible.
- [x] Poblar diagnóstico únicamente para seleccionados.
- [x] Excluir contenido, consulta, embeddings, directorio privado y errores crudos.
- [x] No registrar diagnóstico a nivel `INFO` con datos no sanitizados.
- [x] Ejecutar `SafeRetrievalDiagnosticsTests` y pruebas híbridas existentes.

### Tarea 5 — Terra: persistir y presentar salud de indexación

Archivos:

- Modificar `app/db.py`.
- Modificar `app/rag.py`.
- Modificar `app/client.py`.
- Ampliar `tests/test_db_multibot_schema.py` y/o `tests/test_client_panel.py` si la implementación añade migración/renderizado.

Pasos:

- [x] Añadir columnas aditivas de estado, error sanitizado, fecha, modelo y hash.
- [x] Marcar `pending` antes del trabajo y `indexed`, `partial` o `failed` al terminar.
- [x] Devolver reporte de conteos desde `index_document`.
- [x] Calcular `failed_chunk_count` sin leer contenido en el helper de estadísticas.
- [x] Renderizar badges diferenciados y un mensaje operativo seguro en el panel.
- [x] Marcar índices existentes como `pending` si no se puede demostrar su vigencia y permitir reindexación explícita.
- [x] Ejecutar `IndexingStateTests` y esquema multi-bot; panel compilado, prueba pytest bloqueada por dependencia ausente.

### Tarea 6 — Terra: endurecer aislamiento multi-tenant

Archivos:

- Modificar `app/rag.py`.
- Modificar llamadas en `app/db.py`.

Pasos:

- [x] Agregar `bot_id` al borrado previo de `index_document`.
- [x] Cambiar `delete_document_chunks` para recibir y filtrar por `bot_id`.
- [x] Propagar el `bot_id` desde actualizar/archivar.
- [x] Confirmar que vector, texto, estadísticas y reindexación filtran por `bot_id`.
- [x] Confirmar que ninguna ruta reclama filas `bot_id IS NULL`.
- [x] Ejecutar pruebas de aislamiento nuevas y existentes.

### Tarea 7 — Terra: verificación integral

- [ ] Ejecutar pruebas unittest completas: bloqueado en este runtime porque faltan `httpx` y `cryptography`; se ejecutó la batería hermética con stubs y regresiones focalizadas.
- [ ] Ejecutar pruebas pytest para el panel: bloqueado porque este runtime no incluye `pytest`.
- [ ] Ejecutar la regresión integral según el runner disponible: pendiente de un entorno con dependencias del proyecto.
- [x] Ejecutar `python -m compileall app tests`.
- [x] Revisar `git diff --check`.
- [x] Revisar `git status --short` y no incluir cambios ajenos.
- [x] Buscar patrones de secretos sólo en archivos modificados; sólo se encontraron identificadores de configuración y sentinelas de prueba, no valores reales.
- [x] No marcar despliegue como verificado.

### Tarea 8 — Sol: auditoría de cierre

Checklist:

- [ ] Comparar código con AC-RAG-001..006, no sólo con pruebas verdes.
- [ ] Verificar que el fallback de RAG vacío no tenga ruta indirecta a `all_docs`.
- [ ] Verificar que ningún texto de rol `assistant` llegue al embedding de consulta.
- [ ] Verificar que diagnóstico y `index_error` no incluyan contenido o excepción cruda sensible.
- [ ] Revisar SQL de lectura, escritura y borrado por `bot_id`.
- [ ] Revisar que `partial` siga permitiendo recuperación textual.
- [ ] Confirmar que todos los guardrails previos y el directorio privado siguen intactos.
- [ ] Ejecutar suites objetivo e integral y registrar resultados exactos.
- [ ] Declarar `DEPLOYMENT STATUS: NOT VERIFIED` mientras no exista despliegue autorizado.

## Secuencia de entrega

1. Sol entrega especificación, plan y pruebas rojas.
2. Terra implementa tareas 2 a 7 y entrega diff más resultados.
3. Sol audita, solicita correcciones si hay desviaciones y repite pruebas.
4. Sólo después de auditoría aprobada puede planearse reindexación controlada de Mobi en producción.

## Condición de terminado

La mejora está terminada cuando:

- AC-RAG-001..006 están implementados.
- Las pruebas nuevas y regresiones existentes relevantes pasan.
- La suite integral no presenta regresiones atribuibles al cambio.
- El diff no contiene secretos ni cambios conversacionales/PBD no autorizados.
- El auditor Sol documenta hallazgos, pruebas ejecutadas y estado de despliegue.

## Rollback

El código puede revertirse sin borrar documentos. Las columnas nuevas son aditivas y pueden permanecer. Si la nueva fragmentación presenta una regresión, se revierte el algoritmo, se marcan documentos afectados como `pending` y se reindexa únicamente el bot correspondiente después de corregirla.
