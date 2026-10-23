# Suite del asistente de prompt maestro

## AC-001 / TEST-001: Caso positivo de un solo documento
- Trace: US-001, SPEC-001, FLOW-001, CON-001, CON-002
- DADO un bot con fuentes propias y una solicitud de comportamiento.
- CUANDO el modelo devuelve el maestro completo con las secciones requeridas.
- ENTONCES se muestra un borrador editable sin generar documentos auxiliares.
- Y NO DEBE activar el comportamiento durante generación.
- Cobertura: `tests/test_single_prompt.py`; `tests/test_client_panel.py`.

## AC-002 / TEST-002: Casos negativos y extremos
- Trace: SPEC-003, FB-001, CON-004, CON-005
- DADO contenido incompleto, una sección vacía, truncamiento o decisiones pendientes.
- CUANDO se genera o intenta activar el documento.
- ENTONCES se rechaza estructura incompleta; los pendientes se permiten solo en borrador.
- Y NO DEBE sintetizar reglas de negocio para hacer pasar validación ni publicar errores.
- Cobertura: `tests/test_single_prompt.py`; `tests/test_client_panel.py`.

## AC-003 / TEST-003: Regresión de reglas y compatibilidad
- Trace: SPEC-002, FLOW-002, CON-003, CON-005
- DADO un bot con documentos PBD anteriores.
- CUANDO se solicita un ajuste de tono desde el editor único.
- ENTONCES el asistente recibe las reglas almacenadas del mismo bot y el borrador actual.
- Y NO DEBE usar documentos manipulados enviados por el navegador, recortar guardrails ni cambiar permisos.
- Cobertura: `tests/test_single_prompt.py`; `tests/test_client_panel.py`; suites PBD existentes.

## AC-004 / TEST-004: Regresión del editor
- Trace: FB-001, CON-005, CON-007
- DADO un editor con cambios locales o una respuesta bloqueada/fallida.
- CUANDO termina la generación.
- ENTONCES mantiene los cambios locales, restaura botones y muestra el estado correcto.
- Y NO DEBE afirmar ejecución de pruebas conversacionales ni introducir HTML ejecutable desde el prompt.
- Cobertura: `tests/test_prompt_workspace.js`; pruebas del panel y escape HTML.

## Alcance de verificación

Las pruebas usan proveedores simulados y verifican contratos, validación, permisos y flujo del editor. No evalúan semánticamente respuestas de IA real ni garantizan que una consolidación conserve cada regla; el propietario revisa antes de activar. Las suites de relevo y carga por tenant protegen los controles operativos existentes.

## AC-005 / TEST-005: Lenguaje natural sin campos adicionales
- Trace: US-002, SPEC-005, CON-008
- DADO un prompt con horarios, dirección, servicios y reglas.
- CUANDO se piden cambios con lenguaje natural, sin proporcionar el texto anterior.
- ENTONCES el asistente identifica fragmentos, añade/retira servicios y conserva los demás caracteres.
- Y NO DEBE añadir selectores ni campos de dato actual/dato nuevo al panel.
- Cobertura: `tests/test_prompt_changes.py`, `tests/test_prompt_workspace.js`.

## AC-006 / TEST-006: Constitución, fuentes y revisión independiente
- Trace: SPEC-005, SPEC-006, CON-003, CON-009
- DADO una propuesta que modifica un guardrail, añade un descuento no solicitado, omite fuentes o contradice horarios de un documento.
- CUANDO se valida y revisa la propuesta.
- ENTONCES se bloquea sin sustituir el editor ni publicar.
- Y NO DEBE aceptar una reescritura, instrucciones incrustadas como autoridad, documentos truncados, solapamientos o aprobaciones parciales.
- Cobertura: `tests/test_prompt_changes.py`, `tests/test_prompt_change_store.py`.

## AC-007 / TEST-007: Fuentes completas y ambigüedad
- Trace: SPEC-006, FB-001, CON-004, CON-009
- DADO información relevante después del documento 30 o del carácter 2500, o falta del dato nuevo.
- CUANDO se solicita un ajuste.
- ENTONCES se revisa toda la evidencia o se bloquea por tamaño; las ambigüedades explican qué dato falta.
- Y NO DEBE pedir al usuario un fragmento de reemplazo ni inventar un dato.
- Cobertura: `tests/test_prompt_changes.py`, `tests/test_prompt_change_store.py`.

## AC-008 / TEST-008: Publicación, borradores sucesivos y permisos
- Trace: SPEC-007, FB-002, CON-005, CON-010
- DADO un borrador revisado con comprobante firmado.
- CUANDO se pide otro ajuste compatible, se conserva el borrador anterior como base autorizada.
- CUANDO se intenta guardar con texto adicional, revisión caducada, contexto cambiado, otro usuario/bot o rol de lectura.
- ENTONCES se rechaza antes de escribir y se conserva la versión activa.
- Y NO DEBE perder los documentos PBD ni sobrescribir ediciones concurrentes.
- Cobertura: `tests/test_prompt_changes.py`, `tests/test_prompt_change_store.py`, `tests/test_prompt_workspace.js`.

Estas suites simulan el proveedor y la conexión a PostgreSQL. Verifican construcción exacta de cambios, contratos de revisión y guardado; no certifican la precisión semántica de un modelo real ni un despliegue.
