# Especificación funcional y técnica — Recuperación confiable de políticas extensas

**Fecha:** 2026-09-03
**Estado:** IMPLEMENTED / PENDING PRODUCTION VERIFICATION
**Alcance:** RAG multi-tenant de Asistto y comportamiento PBD de Mobibot (bot 170)

## 1. Problema

Una consulta general como “Quiero saber cuánto puedo gastar de viaje” puede recuperar los primeros fragmentos de `10_Politica_de_Gastos_de_Viaje.md` en lugar de la sección que contiene los montos. La coincidencia del término “viaje” en el título se aplica a todos los fragmentos; el ranking anterior favorece la posición de la coincidencia léxica y limita el documento a dos fragmentos. Los seguimientos “ahí viene” y “ahí dice” tampoco se clasifican como contextuales.

El primer resultado observado fue un falso negativo: el bot afirmó que la información no estaba documentada aunque el dato existía. Después del primer ajuste, una respuesta anterior incorrecta del asistente (`$300`) contaminó la generación y el bot la repitió aunque la política oficial mostrada por el usuario establece alimentos hasta `$1,000`. La recuperación por sí sola no garantiza que la salida final esté respaldada.

## 2. Objetivos

1. Mantener el mejor fragmento semántico frente a ruido léxico proveniente del título.
2. Priorizar evidencia con importes cuando la consulta solicita un monto, límite, costo o precio.
3. Permitir varias secciones relevantes de una misma política sin eliminar la diversidad entre documentos.
4. Conservar contexto exclusivamente escrito por el usuario ante referencias deícticas breves.
5. Diferenciar una falla de recuperación de una ausencia documental confirmada.
6. Producir diagnóstico operativo sin registrar contenido, consultas, embeddings, teléfonos o secretos.
7. Impedir determinísticamente que una cifra monetaria ausente de la evidencia oficial llegue al usuario.
8. Evitar que montos inventados por respuestas anteriores del asistente contaminen turnos posteriores.

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

### RF-RPR-006 — Tolerancia a ambigüedad ortográfica

La expresión `cuando puedo gastar` se trata como probable consulta de monto cuando no contiene marcadores temporales explícitos. El texto original se conserva y la consulta semántica recibe una expansión controlada. Una pregunta con `antes`, `después`, `fecha`, `momento`, `hora` o `autorización` conserva la interpretación temporal.

### RF-RPR-007 — Validación monetaria determinista

Cuando el runtime marca una consulta como RAG estricta y contiene una sección `knowledge_base`, toda cifra monetaria visible en la respuesta debe existir en esa sección después de normalizar separadores de miles y decimales. El historial del asistente y el contexto operativo quedan fuera de la evidencia. Si una cifra no coincide, la respuesta generada se reemplaza por un fallback sin montos. Los flujos transaccionales con cálculo determinista quedan fuera de esta barrera.

### RF-RPR-008 — Descontaminación del historial

Antes de generar una respuesta con evidencia delimitada, se eliminan del contexto las respuestas anteriores del asistente que contengan montos no respaldados por la evidencia vigente. Los mensajes del usuario no se eliminan.

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

### 5.6 Grounding monetario de salida

`reply_safety` extrae únicamente la parte de la respuesta visible para el cliente, reconoce expresiones monetarias explícitas (`$`, `pesos`, `MXN`, `USD`) y formas contextuales como `hasta`, `tope`, `límite` o `por día`. Los importes se normalizan sin usar números de respuestas anteriores como fuente.

El flujo de `openai_client.complete` filtra primero el historial contaminado, genera la respuesta y finalmente aplica el validador. Un incumplimiento produce un único fallback seguro y un log con `bot_id` y cantidad de montos bloqueados, nunca con contenido ni cifras.

## 6. Criterios de aceptación

### AC-RPR-001 — Preservación semántica

**DADO** un candidato vectorial con el límite diario de alimentos y dos candidatos léxicos genéricos del mismo documento
**CUANDO** el límite final sea dos
**ENTONCES** el candidato con el monto debe estar seleccionado y ocupar la primera posición.

### AC-RPR-002 — Fallback textual de monto

**DADO** que no hay búsqueda vectorial
**Y** existe un fragmento con `$1,000 por día` después de fragmentos introductorios
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

### AC-RPR-009 — “Cuando” como probable error de “cuánto”

**DADO** el mensaje “Cuando puedo gastar de viaje” sin marcadores temporales
**CUANDO** se construya la consulta RAG
**ENTONCES** se conserva el texto original y se agrega una intención probable de monto o límite.

### AC-RPR-010 — Candidatos insuficientes

**DADO** que la recuperación devuelve fragmentos pero no contienen la respuesta exacta
**CUANDO** se construya el prompt del bot
**ENTONCES** se prohíbe concluir que el dato no existe o no está documentado.

### AC-RPR-011 — Monto inventado bloqueado

**DADO** que la evidencia oficial contiene `$1,000` para alimentos
**Y** el modelo genera `$300`
**CUANDO** se valida la salida
**ENTONCES** la respuesta con `$300` no se envía y se sustituye por un fallback sin cifras.

### AC-RPR-012 — Formatos equivalentes permitidos

**DADO** que la evidencia oficial contiene `$1,000`
**CUANDO** la respuesta expresa `$1000.00` o `1000 pesos`
**ENTONCES** el monto se reconoce como respaldado.

### AC-RPR-013 — Historial del bot no es evidencia

**DADO** que una respuesta anterior del asistente contiene `$300`
**Y** la evidencia vigente sólo contiene `$1,000`
**CUANDO** se prepara el siguiente turno
**ENTONCES** la respuesta anterior se excluye del contexto, conservando los mensajes del usuario.

### AC-RPR-014 — Recuperación vacía falla cerrada

**DADO** un turno RAG sin fragmentos recuperados
**CUANDO** el modelo intenta emitir cualquier monto
**ENTONCES** el delimitador explícito de evidencia vacía permite bloquearlo antes del envío.

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
| AC-RPR-009 | `RetrievalQueryTests.test_likely_cuando_cuanto_typo_adds_amount_intent_without_rewriting_user_text` y caso temporal complementario |
| AC-RPR-010 | `BoundedKnowledgeFallbackTests.test_nonempty_candidate_retrieval_still_forbids_false_absence_claims` |
| AC-RPR-011/012/014 | Pruebas unitarias de `reply_safety.enforce_grounded_monetary_claims` |
| AC-RPR-013 | `ReplySafetyTests.test_removes_stale_assistant_amount_but_keeps_user_context` y prueba integral de `openai_client.complete` |

## 8. Despliegue y rollback

1. Desplegar el código desde la revisión aprobada.
2. Confirmar en el panel que todos los documentos del bot 170 estén `Indexado` o `Parcial`.
3. Ejecutar la reindexación completa del bot 170 para aplicar el chunking y metadatos vigentes.
4. Repetir TEST-014 y TEST-015 en un contacto de prueba.
5. Revisar logs de diagnóstico sin contenido y confirmar que el fragmento con el monto fue seleccionado.

Rollback: revertir el cambio de ranking y configuración; no se requiere eliminar documentos. Si se revierte la estrategia de fragmentación, marcar los índices afectados como `pending` y reindexar el bot después de restaurar la versión estable.
