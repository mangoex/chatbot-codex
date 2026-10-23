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

## AC-005 / TEST-005: Reemplazo exacto (CON-008, SPEC-005)
- DADO un domicilio en contexto o ejemplos y reglas en el mismo prompt.
- CUANDO el revisor aprueba un reemplazo compatible.
- ENTONCES solo cambian sus coincidencias exactas y se muestran valores y cantidad.
- Y NO DEBE reescribir, reordenar ni eliminar reglas; se conserva XML o Markdown.
- Cobertura: `tests/test_prompt_patch.py`, `tests/test_prompt_workspace.js`.

## AC-006 / TEST-006: Dependencias y límites (CON-009, SPEC-005)
- DADO el dato anterior en Constitución, specs, tests, configuración o un documento posterior al número 30 o al carácter 2500.
- CUANDO se solicita el reemplazo.
- ENTONCES se bloquea y se identifica la dependencia sin invocar al modelo.
- Y NO DEBE omitir documentos, recortar evidencia, activar fuentes pendientes de indexación ni modificar conocimiento automáticamente.
- Cobertura: `tests/test_prompt_patch.py`, `tests/test_prompt_patch_routes.py`.

## AC-007 / TEST-007: Respuesta adversa o incierta (CON-003, CON-008, CON-009)
- DADO un intento de editar una regla, una coincidencia parcial, una respuesta truncada, un JSON inválido o un conflicto semántico indicado por el revisor.
- CUANDO se procesa la revisión.
- ENTONCES se bloquea sin sustituir el prompt.
- Y NO DEBE aceptar una reescritura enviada por el modelo aunque incluya una aprobación.
- Cobertura: `tests/test_prompt_patch.py`.

## AC-008 / TEST-008: Publicación protegida (CON-005, CON-008, CON-009, SPEC-006)
- DADO un comprobante firmado para un usuario, bot y contexto.
- CUANDO se cambia una regla adicional, vence el comprobante, cambia el contexto o se intenta usar otro usuario/bot.
- ENTONCES se rechaza antes de escribir y se mantiene la versión activa.
- Y NO DEBE permitir auto-publicación, sobrescritura obsoleta ni pérdida de documentos PBD.
- Cobertura: `tests/test_prompt_patch.py`, `tests/test_prompt_patch_routes.py`, `tests/test_prompt_workspace.js`.

Las pruebas puntuales garantizan el alcance textual del reemplazo y el contrato de publicación. Los proveedores y la conexión a PostgreSQL se simulan en estas pruebas; no certifican decisiones semánticas de un modelo real ni una instalación desplegada.
