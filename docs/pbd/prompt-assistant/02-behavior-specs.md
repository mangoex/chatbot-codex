# Especificaciones del asistente de prompt maestro

## US-001 / SPEC-001 / FLOW-001: Un solo documento (CON-001, CON-002)

En el modo «Crear o revisar el comportamiento completo», el propietario describe el comportamiento o ajuste en lenguaje natural. El asistente recibe el borrador, el contexto de su bot, extractos de conocimiento e integraciones configuradas; devuelve solo `<master_prompt_doc>` con Markdown legible. No genera Constitución, Specs ni Tests para el propietario. El panel presenta un único editor siempre visible y permite descargar su contenido como `.md`. Este flujo no ofrece la garantía de reemplazo literal del modo puntual.

Las secciones son: Identidad y contexto, Objetivos, Criterios de respuesta, Guardrails, Reglas y flujos, Fuentes autorizadas, Herramientas e integraciones, Escalado humano y fallbacks, Ejemplos de comportamiento. Cada sección contiene instrucciones concretas. Los criterios incluyen tono, WhatsApp, memoria y autoverificación; las reglas incluyen prioridades y flujos. Los ejemplos cubren consulta normal, falta de información, intento de romper reglas, fallo de herramienta y relevo.

## SPEC-002 / FLOW-002: Consolidación de PBD anterior (CON-003, CON-005)

La ruta obtiene documentos anteriores del prompt activo del mismo `bot_id`, después de verificar permisos. El asistente consolida sus prioridades, guardrails, flujos y regresiones sin exigirlos al runtime. No recorta silenciosamente reglas existentes: rechaza contexto de comportamiento que exceda el límite por documento. Las versiones anteriores se conservan archivadas al publicar la versión consolidada; esta almacena únicamente el maestro en `content`. Las rutas PBD anteriores mantienen compatibilidad. El XML existente continúa siendo editable y publicable sin sus documentos auxiliares si tiene todas las secciones ejecutables completas.

## SPEC-003 / FLOW-003: Revisión y activación (CON-004, CON-005, CON-007)

La generación nunca publica, incluso si un cliente antiguo envía `auto_publish`. El botón Guardar y activar es una acción explícita. Antes de guardar se validan estructura, contenido por sección, truncamiento y pendientes; no se completan reglas ausentes con textos genéricos. Los pendientes pueden mostrarse en el borrador y bloquean su activación. El runtime recibe el documento guardado completo, sin depender de documentos PBD.

## FB-001: Conflicto, error y edición concurrente (CON-003, CON-005)

Una petición incompatible devuelve `<blocked_change>` con explicación y alternativa. Respuestas incompletas, truncadas o errores de proveedor no sustituyen el editor ni publican. Si el propietario edita mientras espera, la respuesta no sobrescribe esos cambios. Guardar se deshabilita durante generación. Los usuarios con rol de lectura no generan ni activan; se conserva autorización por bot en las rutas.

## SPEC-004: Fuentes, herramientas y relevo (CON-004, CON-006)

No inventar datos del negocio ni integraciones. No afirmar una acción antes de confirmación de su herramienta. Escalar ante solicitud humana, quejas y casos fuera de alcance, respetando configuración operativa. No retrasar el relevo por datos obligatorios ni responder durante intervención humana. Estas instrucciones de diseño se prueban por contrato; no constituyen una evaluación semántica de resultados de un proveedor real.

## US-002 / SPEC-005 / FLOW-004: Cambio puntual (CON-003, CON-008, CON-009)

Con un prompt existente, el panel selecciona «Cambio puntual: conservar el resto». Para un bot sin prompt selecciona creación completa. El propietario describe el cambio e introduce el dato actual exacto y el dato nuevo, ambos de 3 a 240 caracteres, sin saltos de línea ni etiquetas. Así delimita explícitamente el reemplazo; no se deduce un permiso ilimitado de una solicitud libre.

El servidor carga una instantánea consistente de la versión activa, Constitución, specs, tests, todos los documentos activos completos e integraciones/skills del mismo bot. No consulta credenciales; elimina campos de secretos de la configuración visible al revisor y conserva una huella para detectar modificaciones. Si el editor tiene cambios sin guardar, se bloquea. Si el contexto supera 120000 caracteres, se bloquea sin recortarlo.

Solo se permiten valores en contexto del negocio o ejemplos; las secciones de reglas, encabezados y etiquetas quedan protegidos. Todas las coincidencias deben ser compatibles. Se bloquean coincidencias parciales, cambios de estructura, fuentes pendientes de indexación y referencias normalizadas al dato anterior en PBD, conocimiento o configuración. El mensaje identifica las dependencias; el propietario debe resolverlas en su fuente antes de volver a revisar. No se cambia automáticamente el conocimiento, sus embeddings ni las herramientas.

Un revisor de IA recibe toda la evidencia disponible y evalúa que sea un dato factual compatible con la solicitud, Constitución y reglas, incluyendo variantes semánticas del dato y dependencias como mapas, sucursales o cobertura. Solo un JSON válido con aprobación booleana y ninguna dependencia pendiente permite continuar. Incertidumbre, truncamiento, respuesta inválida, conflicto o fallo del proveedor bloquean. El revisor no puede devolver un prompt ni operaciones adicionales. La evaluación semántica es una protección adicional, no una prueba formal de equivalencia conversacional.

El servidor aplica el reemplazo literal sobre el original, conserva exactamente el resto y muestra antes/después y cantidad de apariciones. Devuelve un comprobante firmado de 30 minutos vinculado al usuario, bot, valores e instantánea revisada. Generar nunca activa. El panel invalida el comprobante si cambia la solicitud y rechaza respuestas que llegan después de editar el formulario o el prompt.

## SPEC-006 / FLOW-005 / FB-002: Activación puntual y concurrencia (CON-005, CON-008, CON-009)

Guardar en modo puntual exige el comprobante firmado. En una transacción serializable se bloquean el bot y las filas de evidencia, se vuelve a cargar el contexto y se compara su huella. Cambios de versión, conocimiento, configuración o documentos PBD invalidan la revisión. La publicación reconstruye el candidato y rechaza cualquier diferencia del texto enviado, salvo normalización CRLF/LF del transporte HTML. Se almacena el candidato original, sin normalizar ni reescribir texto ajeno al reemplazo.

Se archiva la versión anterior y se crea una nueva con el maestro modificado y copias exactas de la Constitución, specs y tests existentes. Un segundo uso del comprobante falla por cambio de versión. Conflictos transaccionales solicitan una nueva revisión. Se conservan permisos de edición y aislamiento por tenant. Las rutas de edición completa siguen siendo una operación explícita diferente, sin la garantía del modo puntual; presentar un comprobante obliga a verificarlo aunque se altere el selector de formato.
