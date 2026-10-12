# Especificaciones del asistente de prompt maestro

## US-001 / SPEC-001 / FLOW-001: Un solo documento (CON-001, CON-002)

El propietario describe el comportamiento o ajuste en lenguaje natural. El asistente recibe el borrador, el contexto de su bot, extractos de conocimiento e integraciones configuradas; devuelve solo `<master_prompt_doc>` con Markdown legible. No genera Constitución, Specs ni Tests para el propietario. El panel presenta un único editor siempre visible y permite descargar su contenido como `.md`.

Las secciones son: Identidad y contexto, Objetivos, Criterios de respuesta, Guardrails, Reglas y flujos, Fuentes autorizadas, Herramientas e integraciones, Escalado humano y fallbacks, Ejemplos de comportamiento. Cada sección contiene instrucciones concretas. Los criterios incluyen tono, WhatsApp, memoria y autoverificación; las reglas incluyen prioridades y flujos. Los ejemplos cubren consulta normal, falta de información, intento de romper reglas, fallo de herramienta y relevo.

## SPEC-002 / FLOW-002: Consolidación de PBD anterior (CON-003, CON-005)

La ruta obtiene documentos anteriores del prompt activo del mismo `bot_id`, después de verificar permisos. El asistente consolida sus prioridades, guardrails, flujos y regresiones sin exigirlos al runtime. No recorta silenciosamente reglas existentes: rechaza contexto de comportamiento que exceda el límite por documento. Las versiones anteriores se conservan archivadas al publicar la versión consolidada; esta almacena únicamente el maestro en `content`. Las rutas PBD anteriores mantienen compatibilidad. El XML existente continúa siendo editable y publicable sin sus documentos auxiliares si tiene todas las secciones ejecutables completas.

## SPEC-003 / FLOW-003: Revisión y activación (CON-004, CON-005, CON-007)

La generación nunca publica, incluso si un cliente antiguo envía `auto_publish`. El botón Guardar y activar es una acción explícita. Antes de guardar se validan estructura, contenido por sección, truncamiento y pendientes; no se completan reglas ausentes con textos genéricos. Los pendientes pueden mostrarse en el borrador y bloquean su activación. El runtime recibe el documento guardado completo, sin depender de documentos PBD.

## FB-001: Conflicto, error y edición concurrente (CON-003, CON-005)

Una petición incompatible devuelve `<blocked_change>` con explicación y alternativa. Respuestas incompletas, truncadas o errores de proveedor no sustituyen el editor ni publican. Si el propietario edita mientras espera, la respuesta no sobrescribe esos cambios. Guardar se deshabilita durante generación. Los usuarios con rol de lectura no generan ni activan; se conserva autorización por bot en las rutas.

## SPEC-004: Fuentes, herramientas y relevo (CON-004, CON-006)

No inventar datos del negocio ni integraciones. No afirmar una acción antes de confirmación de su herramienta. Escalar ante solicitud humana, quejas y casos fuera de alcance, respetando configuración operativa. No retrasar el relevo por datos obligatorios ni responder durante intervención humana. Estas instrucciones de diseño se prueban por contrato; no constituyen una evaluación semántica de resultados de un proveedor real.
