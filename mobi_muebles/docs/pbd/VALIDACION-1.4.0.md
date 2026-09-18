# Validación documental — Mobibot 1.4.0

Fecha: 2026-09-03. Alcance: archivos de configuración conversacional; sin cambios de aplicación ni publicación.

## Método y Evidencia

- Marco PBD solicitado: revisión `241e4eeee4ceff4b8c2ef9f2da64beebe7e8e6c9` de `mangoex/pbd-whatsapp-skill-starter`. Se comprobó por SHA-256 que el skill, contrato documental y referencia normativa locales coinciden con esa revisión remota.
- CONFIRMED: documentos adjuntos 1.1.0, respaldo Git 1.3.0, incidente de saludo/fallback, captura de topes y contratos del constructor de contexto y publicador PBD.
- CONTRADICTORY, corregido: estado OUT_OF_SCOPE por búsqueda vacía contra CON-010; ejemplo de exclusión sin evidencia contra CON-001; promesas incondicionales de agenda/canalización contra veracidad.
- NOT FOUND: trazas de producción que permitan atribuir causalidad exacta; contenido completo y vigencia de la política de viaje activa; integración de agenda/transferencia disponible. No se inventaron esos datos.

## Comprobaciones Ejecutadas

| Comprobación | Resultado |
| --- | --- |
| `python -m unittest tests.test_pbd_validation -v` | 8 pruebas, todas correctas |
| `validate_pbd_bundle(..., for_publish=True)` sobre el paquete real | Válido, sin errores ni advertencias |
| Preservación de IDs frente a Git 1.3.0 y adjuntos 1.1.0 | Correcta en ambas comparaciones |
| Referencias CON/US/SPEC/FLOW/FB/TEST | Resuelven a declaraciones existentes |
| XML y 16 secciones obligatorias | Correctos |
| Versión 1.4.0 en los cuatro documentos | Correcta |
| Master canónico frente a `mobi_muebles/prompts/master.md` | Contenido idéntico |
| Importes de viaje no incrustados en el Master | Correcto |
| Bloques de pruebas con GIVEN/WHEN/THEN/AND MUST NOT | 35 escenarios en 32 casos |
| `git diff --check` | Sin errores de espacios; advertencias de conversión LF/CRLF del entorno |

La comprobación adicional de referencias se ajustó para reconocer declaraciones FLOW en viñetas, además de encabezados; posteriormente pasó completa. No fue una ejecución conversacional.

## Revisión de Regresiones

- Preservados CON-001 a CON-011, US-001 a US-009, SPEC-001 a SPEC-008 y TEST-001 a TEST-019; también AC-001, AC-011 y AC-012 presentes en los adjuntos.
- Añadidos US-010/011, SPEC-009/010, FLOW-002/003, FB-002/003 y TEST-020 a TEST-032. Criterios de aceptación concretos, incluyendo AC-010 y AC-013 a AC-015.
- Se mantiene reclutamiento: sin afirmar/negar vacantes, solicitud presencial, espera de entrevista, horario y domicilio autorizados.
- Se mantienen privacidad, no diagnóstico, identidad no bloqueante y veracidad. La reserva no se sustituye por una garantía técnica absoluta; una solicitud registrada no se confunde con una cita confirmada.
- Se retiran ejemplos con identidad personal y ejemplos que afirmaban contenido de políticas sin un fragmento de respaldo. No se incorporan reglas empresariales nuevas.

## Pendiente de Verificación Operativa

Los 35 escenarios están STATICALLY REVIEWED; no se ejecutaron contra un modelo ni en WhatsApp. El validador comprueba estructura y conservación, no veracidad de respuestas generadas.

DEPLOYMENT STATUS: NOT VERIFIED. El propietario debe copiar/publicar los cuatro campos y verificar la versión activa, las fuentes recuperadas y los escenarios críticos. No se requiere inventar nuevos datos para usar la configuración: la falta de fuentes, contactos o integraciones tiene un comportamiento seguro definido.

Los documentos por sí solos no certifican recuperación correcta ni cero alucinaciones. No se realizó commit, merge, push ni redeploy en esta entrega.
