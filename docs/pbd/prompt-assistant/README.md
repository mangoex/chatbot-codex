# Prompt maestro en el panel de Asistto

El usuario final describe lo que necesita, revisa un solo documento y pulsa **Guardar y activar prompt maestro**. El asistente genera Markdown con reglas completas y ejemplos. También puede editar y descargar el prompt directamente. No necesita administrar archivos técnicos de PBD.

La ingeniería del asistente conserva aquí Constitución, especificaciones y pruebas según `AGENTS.md`. Estos archivos describen el generador; no se crean como artefactos adicionales para cada bot desde el nuevo flujo. `04-master-prompt.md` contiene las instrucciones compiladas del generador y debe coincidir con `SINGLE_PROMPT_SYSTEM_INSTRUCTIONS` en `app/prompt_assistant.py`.

La consolidación se aplica por bot cuando el propietario pide generar y luego guarda el resultado. No existe una migración masiva de prompts activos. Al guardar se archiva la versión previa con sus documentos PBD. El runtime usa `bot_prompts.content` como siempre. Las rutas técnicas anteriores conservan compatibilidad para integraciones existentes.

El modo puntual es el predeterminado para prompts existentes. Pide dato actual y nuevo, revisa dependencias y construye el reemplazo en el servidor. Su revisión usa `05-patch-review-prompt.md`, compilado desde `PATCH_REVIEW_INSTRUCTIONS` en `app/prompt_patch.py`. A diferencia de la consolidación completa, la nueva versión puntual conserva también los documentos PBD exactos. Requiere `SESSION_SECRET` y el proveedor de IA ya configurado; no requiere migración de esquema.

Para cambiar un domicilio: selecciona cambio puntual, copia el domicilio actual, introduce el nuevo, describe a qué sede corresponde y genera la revisión. Si aparece una dependencia, resuélvela en la fuente indicada y vuelve a revisar. Verifica antes/después y guarda para activar. Si necesitas modificar una regla o una sección protegida, utiliza una revisión completa del comportamiento; el modo puntual lo bloqueará.

La validación comprueba estructura, contenido por sección y ausencia de pendientes/truncamiento al activar. La revisión humana verifica sentido, fidelidad y cobertura de reglas; no se afirma haber ejecutado pruebas conversacionales del prompt generado.
