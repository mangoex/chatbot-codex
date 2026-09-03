# Especificación funcional y técnica — Recuperación confiable de políticas extensas

**Fecha:** 2026-09-03
**Estado:** IMPLEMENTED / PENDING PRODUCTION VERIFICATION
**Alcance:** RAG multi-tenant de Asistto y comportamiento PBD de Mobibot (bot 170)

## 1. Problema

Una consulta general como “Quiero saber cuánto puedo gastar de viaje” puede recuperar los primeros fragmentos de `10_Politica_de_Gastos_de_Viaje.md` en lugar de la sección que contiene los montos. La coincidencia del término “viaje” en el título se aplica a todos los fragmentos; el ranking anterior favorece la posición de la coincidencia léxica y limita el documento a dos fragmentos. Los seguimientos “ahí viene” y “ahí dice” tampoco se clasifican como contextuales.

El resultado observado es un falso negativo: el bot afirma que la información no está documentada aunque el dato existe y aparece cuando el usuario agrega “comida diario”.

## 2. Objetivos

1. Mantener el mejor fragmento semántico frente a ruido léxico proveniente del título.
2. Priorizar evidencia con importes cuando la consulta solicita un monto, límite, costo o precio.
3. Permitir varias secciones relevantes de una misma política sin eliminar la diversidad entre documentos.
4. Conservar contexto exclusivamente escrito por el usuario ante referencias deícticas breves.
5. Diferenciar una falla de recuperación de una ausencia documental confirmada.
6. Producir diagnóstico operativo sin registrar contenido, consultas, embeddings, teléfonos o secretos.

## 3. Fuera de alcance

- Cambiar proveedor o modelo de embeddings.
- Incorporar una base vectorial externa o un reranker de terceros.
- Modificar los documentos corporativos cargados por el cliente.
- Desplegar o reindexar producción desde este cambio de repositorio.

## 4. Requisitos funcionales

### RF-RPR-001 — Consulta general de monto

Una pregunta con marcadores de monto (`cuánto`, `monto`, `límite`, `tope`, `gastar`, `costo`, `precio` o equivalentes definidos) debe priorizar fragmentos que contengan moneda, cantidades monetarias, límites o periodicidad diaria.

### RF-RPR-002 — Seguimiento contextual

Un mensaje breve que contenga referencias como `ahí`, `aquí`, `allí`, `eso dice` o `esa indica` se trata como seguimiento. La consulta incluye como máximo los dos mensajes recientes del usuario dentro de la ventana configurada. Mensajes `assistant`, `system` y `tool` quedan excluidos.

### RF-RPR-003 — Políticas con varias secciones

La búsqueda puede devolver hasta `RAG_MAX_CHUNKS_PER_DOCUMENT` fragmentos por documento, sin superar `RAG_FINAL_CHUNKS`. El valor predeterminado es cuatro.

### RF-RPR-004 — Fallback honesto

Una recuperación vacía no puede generar la afirmación “no está documentado”. El asistente debe indicar que no pudo localizar el apartado exacto, solicitar precisión y ofrecer canalización.

### RF-RPR-005 — Grounding

La respuesta sigue limitada al contenido recuperado. La mejora de ranking no autoriza inferencias ni la inyección completa de bases grandes.

## 5. Diseño técnico

### 5.1 Construcción de consulta

`bot_content.build_retrieval_query` conserva el camino autosuficiente existente y amplía el detector conservador de seguimiento. La normalización elimina acentos sólo para clasificar; la consulta conserva el texto original. Sólo se incorporan mensajes con rol `user`.

### 5.2 Recuperación textual

La consulta SQL calcula por fragmento:

- `rank`: relevancia de búsqueda de texto completo en español;
- `content_keyword_hits`: cantidad de patrones de la consulta que coinciden con el contenido, separada de la coincidencia por título;
- `answer_shape`: indicador binario de evidencia monetaria cuando la consulta pide un monto.

Los candidatos textuales se ordenan por `answer_shape`, coincidencias en contenido, `rank` e índice físico. La coincidencia por título sigue sirviendo para enrutar hacia una política, pero deja de ser el único criterio de orden.

### 5.3 Fusión híbrida

La puntuación es determinista y sólo comparable dentro de la consulta:

- RRF vectorial con peso `2.0`;
- RRF textual con peso `1.0`;
- bonificación acotada por distancia vectorial;
- bonificación acotada por `rank`, coincidencias de contenido y forma de respuesta monetaria.

El mayor peso vectorial evita que dos coincidencias genéricas del título excluyan al primer candidato semántico.

### 5.4 Selección y límites

Los candidatos se ordenan por la puntuación combinada. El límite por documento es `max(1, min(RAG_MAX_CHUNKS_PER_DOCUMENT, limit))`. Se mantienen el límite total, el aislamiento por `bot_id`, la exclusión del directorio privado y los estados recuperables `indexed`/`partial`.

### 5.5 Observabilidad

El runtime entrega un colector de diagnósticos a `search_knowledge` y registra únicamente:

- `bot_id` y cantidad seleccionada;
- `knowledge_id`, `chunk_index` y título;
- puntuación, fuentes de recuperación y distancia vectorial disponible.

No se registra contenido del fragmento, consulta, embedding, teléfono, respuesta del modelo ni error crudo del proveedor.

## 6. Criterios de aceptación

### AC-RPR-001 — Preservación semántica

**DADO** un candidato vectorial con el límite diario de alimentos y dos candidatos léxicos genéricos del mismo documento
**CUANDO** el límite final sea dos
**ENTONCES** el candidato con el monto debe estar seleccionado y ocupar la primera posición.

### AC-RPR-002 — Fallback textual de monto

**DADO** que no hay búsqueda vectorial
**Y** existe un fragmento con `$300 por día` después de fragmentos introductorios
**CUANDO** la pregunta solicite cuánto se puede gastar
**ENTONCES** el fragmento monetario debe quedar seleccionado.

### AC-RPR-003 — Varias secciones de la misma política

**DADO** seis secciones relevantes del mismo documento
**Y** `RAG_MAX_CHUNKS_PER_DOCUMENT=4`
**CUANDO** el límite total sea ocho
**ENTONCES** se devuelven cuatro fragmentos de ese documento.

### AC-RPR-004 — Referencia “ahí” no inicial

**DADO** el mensaje previo del usuario “Quiero saber cuánto puedo gastar de viaje”
**CUANDO** escriba “Tenemos una política de viaje, ahí viene”
**ENTONCES** la consulta semántica incluye ambos mensajes del usuario.

### AC-RPR-005 — Seguimiento de monto

**DADO** la conversación anterior
**CUANDO** escriba “Ahí dice cuánto puedo gastar de comida diario”
**ENTONCES** la consulta incluye el tema de viaje y la precisión de alimentos.

### AC-RPR-006 — Anticontaminación

**DADO** que existen respuestas anteriores incorrectas del asistente
**CUANDO** se construya un seguimiento
**ENTONCES** ninguna respuesta del asistente forma parte de la consulta RAG.

### AC-RPR-007 — Falso negativo prohibido

**DADO** que una base grande no devuelve fragmentos
**CUANDO** se construya el prompt
**ENTONCES** se prohíbe afirmar que el dato no existe o no está documentado y se activa el fallback de recuperación insuficiente.

### AC-RPR-008 — Seguridad multi-tenant

**DADO** cualquier indexación o búsqueda
**CUANDO** se acceda a documentos o fragmentos
**ENTONCES** toda operación conserva `bot_id`, excluye directorios privados y no amplía el contenido registrado en logs.

## 7. Pruebas

| Criterio | Prueba automatizada |
|---|---|
| AC-RPR-001 | `PolicyRetrievalRankingTests.test_best_semantic_amount_chunk_survives_title_only_lexical_noise` |
| AC-RPR-002 | `PolicyRetrievalRankingTests.test_amount_shaped_text_chunk_beats_earlier_generic_chunks_without_vectors` |
| AC-RPR-003 | `PolicyRetrievalRankingTests.test_policy_query_can_return_more_than_two_relevant_sections` |
| AC-RPR-004 | `RetrievalQueryTests.test_deictic_policy_correction_keeps_the_original_user_question` |
| AC-RPR-005/006 | `RetrievalQueryTests.test_deictic_amount_followup_keeps_recent_user_context_only` |
| AC-RPR-007 | `BoundedKnowledgeFallbackTests.test_empty_retrieval_never_injects_every_large_document` |
| AC-RPR-008 | Regresiones existentes de aislamiento, privacidad y diagnóstico seguro |

## 8. Despliegue y rollback

1. Desplegar el código desde la revisión aprobada.
2. Confirmar en el panel que todos los documentos del bot 170 estén `Indexado` o `Parcial`.
3. Ejecutar la reindexación completa del bot 170 para aplicar el chunking y metadatos vigentes.
4. Repetir TEST-014 y TEST-015 en un contacto de prueba.
5. Revisar logs de diagnóstico sin contenido y confirmar que el fragmento con el monto fue seleccionado.

Rollback: revertir el cambio de ranking y configuración; no se requiere eliminar documentos. Si se revierte la estrategia de fragmentación, marcar los índices afectados como `pending` y reindexar el bot después de restaurar la versión estable.
