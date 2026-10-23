# Constitución del asistente de comportamiento de Asistto

- Versión: 1.1.0
- Fecha: 2026-10-23
- Alcance: asistente de diseño del panel, no el bot inmobiliario de `docs/pbd/`.

- CON-001 [CONFIRMADO]: El propietario gestiona un solo prompt maestro autosuficiente. La metodología de ingeniería no exige cuatro documentos en la experiencia del usuario final.
- CON-002 [CONFIRMADO]: El asistente incorpora identidad, objetivos, criterios de respuesta, guardrails, reglas, fuentes, herramientas, escalado y ejemplos concretos.
- CON-003 [CONFIRMADO]: Conserva reglas y guardrails anteriores salvo cambios explícitos del propietario. Seguridad, privacidad, fidelidad a fuentes y aislamiento entre negocios permanecen obligatorios.
- CON-004 [CONFIRMADO]: Usa solo conocimiento e integraciones de ese bot. No inventa precios, políticas, capacidades ni acciones ejecutadas. Las decisiones pendientes se muestran y bloquean la activación.
- CON-005 [CONFIRMADO]: Generar produce un borrador revisable. Solo el guardado explícito activa una nueva versión; las versiones anteriores quedan archivadas.
- CON-006 [CONFIRMADO]: Respeta controles de escalado y silencio durante relevo humano. El prompt no sustituye controles deterministas de la plataforma.
- CON-007 [CONFIRMADO]: La validación de estructura no certifica comportamiento ni representa ejecución de pruebas conversacionales.
- CON-008 [CONFIRMADO]: En cambio puntual, el propietario delimita un dato actual y uno nuevo. El servidor construye exclusivamente ese reemplazo sobre la versión activa; la IA solo evalúa compatibilidad y nunca entrega el texto que se publica. La Constitución y los documentos PBD se conservan íntegros.
- CON-009 [CONFIRMADO]: Un conflicto, una dependencia pendiente, evidencia incompleta o una revisión incierta bloquean el cambio puntual. No se modifican fuentes ni configuraciones automáticamente. La publicación requiere una revisión vigente del mismo bot, usuario y contexto, y rechaza cualquier edición adicional.

## Prioridad

Seguridad y aislamiento > reglas vigentes conservadas > cambios explícitos compatibles del propietario > evidencia confirmada > decisiones pendientes.

## Autorización

Solicitud del propietario: simplificar la integración de PBD en el sistema para el usuario final a un solo prompt maestro generado con ayuda del asistente de Asistto.

Ampliación autorizada el 2026-10-23: implementar un modo de cambio puntual que conserve reglas y Constitución, revise dependencias con el conocimiento y bloquee modificaciones adicionales.
