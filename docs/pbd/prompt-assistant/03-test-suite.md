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
