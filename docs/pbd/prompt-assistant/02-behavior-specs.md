# Especificaciones del asistente de prompt maestro

## US-001 / SPEC-001 / FLOW-001: Un solo documento (CON-001, CON-002)

El propietario describe el comportamiento o ajuste en lenguaje natural. El panel conserva el cuadro de solicitud, el botón de generación, el editor y el guardado; no añade selectores ni campos de reemplazo. Para crear un prompt se genera un documento completo. Para modificar uno existente se identifican fragmentos mínimos, se aplican en el servidor y se revisa el resultado de forma independiente (SPEC-005). No genera Constitución, Specs ni Tests para el propietario. El editor sigue permitiendo descargar el contenido como `.md`.

Las secciones son: Identidad y contexto, Objetivos, Criterios de respuesta, Guardrails, Reglas y flujos, Fuentes autorizadas, Herramientas e integraciones, Escalado humano y fallbacks, Ejemplos de comportamiento. Cada sección contiene instrucciones concretas. Los criterios incluyen tono, WhatsApp, memoria y autoverificación; las reglas incluyen prioridades y flujos. Los ejemplos cubren consulta normal, falta de información, intento de romper reglas, fallo de herramienta y relevo.

## SPEC-002 / FLOW-002: Consolidación de PBD anterior (CON-003, CON-005)

La ruta obtiene documentos anteriores del prompt activo del mismo `bot_id`, después de verificar permisos. El flujo del panel conserva esos documentos en la versión publicada, además del maestro en `content`. No modifica la Constitución ni descarta specs/tests. Si hay dependencias incompatibles con el ajuste, indica qué fuente debe resolverse. El runtime sigue ejecutando `content`; las rutas anteriores conservan compatibilidad y el guardado manual/legado mantiene su contrato anterior. La revisión protegida corresponde a la generación desde el cuadro y a su guardado firmado.

## SPEC-003 / FLOW-003: Revisión y activación (CON-004, CON-005, CON-007)

La generación nunca publica, incluso si un cliente antiguo envía `auto_publish`. El botón Guardar y activar es una acción explícita. Antes de guardar se validan estructura, contenido por sección, truncamiento y pendientes; no se completan reglas ausentes con textos genéricos. Los pendientes pueden mostrarse en el borrador y bloquean su activación. El runtime recibe el documento guardado completo, sin depender de documentos PBD.

## FB-001: Conflicto, error y edición concurrente (CON-003, CON-005)

Una petición incompatible devuelve `<blocked_change>` con explicación y alternativa. Respuestas incompletas, truncadas o errores de proveedor no sustituyen el editor ni publican. Si el propietario edita mientras espera, la respuesta no sobrescribe esos cambios. Guardar se deshabilita durante generación. Los usuarios con rol de lectura no generan ni activan; se conserva autorización por bot en las rutas.

## SPEC-004: Fuentes, herramientas y relevo (CON-004, CON-006)

No inventar datos del negocio ni integraciones. No afirmar una acción antes de confirmación de su herramienta. Escalar ante solicitud humana, quejas y casos fuera de alcance, respetando configuración operativa. No retrasar el relevo por datos obligatorios ni responder durante intervención humana. Estas instrucciones de diseño se prueban por contrato; no constituyen una evaluación semántica de resultados de un proveedor real.

## US-002 / SPEC-005 / FLOW-004: Ajustes naturales y alcance mínimo (CON-003, CON-008, CON-009)

Ejemplos: «Los sábados también atendemos de 9 a 14», «Nuestra dirección ahora es Avenida Central 20», «Agrega el servicio de instalación» o «Retira el servicio de entrega». El usuario no necesita conocer ni copiar el texto actual. Si faltan datos o la sede es ambigua, el cuadro muestra una explicación/pregunta y conserva el borrador.

El planificador recibe solicitud, borrador autorizado y contexto completo; propone hasta 16 cambios con fragmento anterior exacto, fragmento nuevo, número de aparición y cita de la solicitud. Estos campos son internos y nunca se piden al propietario. Se permiten inserciones ancladas, sustituciones y retiros de información de negocio. El servidor rechaza operaciones inválidas, coincidencias inexistentes, solapamientos, encabezados o etiquetas modificadas y secciones protegidas (guardrails, Constitución, prioridades, fuentes, herramientas, relevo, etc.). Conserva el resto del documento, normalizando únicamente CRLF/LF por transporte HTML.

Se puede ajustar información en contexto, flujos o ejemplos, incluyendo referencias repetidas seleccionadas individualmente. Una cita de la solicitud no constituye autorización por sí sola: un auditor en una segunda llamada recibe la solicitud original, base, candidato, cambios y fuentes, sin confiar en el razonamiento/resumen del planificador. Debe comprobar que cada cambio responde al pedido, que ninguna otra regla se compromete y que las referencias afectadas quedan coherentes. Su JSON debe aprobar todos los índices y declarar revisión de todas las fuentes. Cualquier conflicto, incertidumbre, cobertura incompleta, respuesta inválida o truncamiento bloquea; no hay un fallback que publique una reescritura completa.

Si no existe prompt, se genera uno completo con las instrucciones de `04-master-prompt.md`, pasando también por revisión independiente. Si la solicitud ya está satisfecha, se puede revisar el mismo contenido sin reescribirlo. Los ajustes sucesivos reutilizan el borrador firmado vigente; las ediciones manuales no revisadas requieren guardar manualmente o recargar la versión activa antes de solicitar ajustes naturales.

## SPEC-006 / FLOW-005: Dependencias y fuentes completas (CON-004, CON-009)

Una transacción de lectura obtiene versión activa, Constitución, specs, tests, todos los documentos activos y configuraciones de integraciones/skills del bot. Las credenciales se omiten del contexto del modelo. No hay límite silencioso de 30 documentos ni extractos de 2500 caracteres. Si el contexto de una llamada supera 120000 caracteres, o hay fuentes sin indexar completamente, se bloquea en vez de recortar evidencia.

La revisión considera horarios operativos, calendarios, mapas, sedes, cobertura, catálogo, precios y variantes del mismo dato. Una afirmación explícita del propietario aporta el dato nuevo, pero no resuelve automáticamente contradicciones con documentos o configuración. Se informa la fuente y la dependencia pendiente. Este flujo no escribe conocimiento, embeddings ni herramientas. La coherencia semántica usa IA y no es una prueba formal de equivalencia conversacional; las protecciones de alcance textual y publicación se implementan en código.

## SPEC-007 / FLOW-006 / FB-002: Guardado verificado y concurrencia (CON-005, CON-010)

El resultado muestra explicación y fragmentos antes/después como información, sin nuevos campos. Sigue siendo un borrador hasta Guardar y activar. Un comprobante firmado con SESSION_SECRET vincula usuario, bot, huella del resultado y contexto durante 30 minutos. No incluye credenciales ni documentos completos. Se transmite en campos ocultos.

El guardado de resultados revisados exige el comprobante incluso si se altera el formato enviado. Dentro de una transacción serializable se bloquean bot y filas de evidencia, se vuelven a cargar fuentes/versiones y se verifican sus huellas y el contenido enviado antes de escribir. Una diferencia adicional, revisión vencida o fuente modificada bloquea. Se archiva la versión anterior y se publica el maestro junto a copias exactas de sus documentos PBD. Un segundo guardado con el mismo comprobante falla al cambiar la versión.

Un borrador firmado que caducó puede volver a revisarse si su contenido y contexto siguen coincidiendo; no puede activarse con la revisión caducada. Cambiar la solicitud o el editor mientras se genera impide sobrescribir el estado del usuario. Se mantienen permisos por tenant y rol. Fallos de proveedor o conflictos transaccionales nunca activan un resultado parcial.
