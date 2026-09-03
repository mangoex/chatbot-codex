# Plan de implementación — Recuperación confiable de políticas extensas

**Especificación:** `docs/superpowers/specs/2026-09-03-rag-policy-retrieval-ranking.md`
**Fecha:** 2026-09-03
**Estado:** IMPLEMENTED / PENDING PRODUCTION DEPLOYMENT

## Tarea 1 — Capturar la regresión observada

- [x] Agregar prueba para “Tenemos una política de viaje, ahí viene”.
- [x] Agregar prueba para “Ahí dice cuánto puedo gastar de comida diario”.
- [x] Verificar que las respuestas anteriores del asistente no entren a la consulta.
- [x] Ejecutar las pruebas antes del cambio y confirmar fallas.

## Tarea 2 — Corregir continuidad contextual

- [x] Normalizar marcadores deícticos con y sin acento.
- [x] Detectar referencias aunque no estén al inicio del mensaje.
- [x] Mantener el límite de longitud y máximo de mensajes recientes.
- [x] Preservar exclusión de roles no autorizados.

## Tarea 3 — Corregir ranking híbrido

- [x] Añadir señal de coincidencias dentro del contenido.
- [x] Añadir señal monetaria condicionada a consultas de monto.
- [x] Priorizar la señal antes del índice físico en SQL.
- [x] Rebalancear RRF para preservar el mejor candidato vectorial.
- [x] Incorporar señales acotadas a la puntuación combinada.

## Tarea 4 — Ajustar diversidad por documento

- [x] Crear `RAG_MAX_CHUNKS_PER_DOCUMENT` con valor predeterminado cuatro.
- [x] Respetar el límite total de resultados.
- [x] Documentar la variable en `.env.example`.

## Tarea 5 — Evitar falsos negativos categóricos

- [x] Cambiar la instrucción de recuperación vacía.
- [x] Separar en PBD “dato no documentado” de “evidencia no recuperada”.
- [x] Agregar prueba automatizada del fallback.

## Tarea 6 — Observabilidad segura

- [x] Conectar el colector existente de diagnósticos al runtime.
- [x] Registrar únicamente metadatos seguros de selección.
- [x] Conservar pruebas que prohíben contenido, consulta y embeddings.

## Tarea 7 — Actualizar comportamiento PBD y compilar prompt

- [x] Añadir CON-010.
- [x] Añadir US-008 y SPEC-007.
- [x] Añadir TEST-014 a TEST-017.
- [x] Compilar los cambios en `mobi_muebles/prompts/master.md` versión 1.2.0.

## Tarea 8 — Verificación de repositorio

- [x] Ejecutar regresiones herméticas de RAG.
- [x] Ejecutar la suite completa con todas las dependencias del proyecto: `362 passed`.
- [ ] Validar el SQL contra PostgreSQL/pgvector real.
- [ ] Desplegar en producción.
- [ ] Reindexar exclusivamente el bot 170.
- [ ] Ejecutar prueba conversacional end-to-end y revisar diagnóstico seguro.

Las tareas pendientes requieren el entorno de despliegue y acceso operativo; no se ejecutan como parte del cambio local.
