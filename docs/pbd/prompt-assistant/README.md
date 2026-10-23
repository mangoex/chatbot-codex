# Prompt maestro en el panel de Asistto

El usuario final describe lo que necesita, revisa un solo documento y pulsa **Guardar y activar prompt maestro**. El asistente genera Markdown con reglas completas y ejemplos. También puede editar y descargar el prompt directamente. No necesita administrar archivos técnicos de PBD.

La ingeniería del asistente conserva aquí Constitución, especificaciones y pruebas según `AGENTS.md`. Estos archivos describen el generador; no se crean como artefactos adicionales para cada bot desde el nuevo flujo. `04-master-prompt.md` contiene las instrucciones compiladas del generador y debe coincidir con `SINGLE_PROMPT_SYSTEM_INSTRUCTIONS` en `app/prompt_assistant.py`.

La consolidación se aplica por bot cuando el propietario pide generar y luego guarda el resultado. No existe una migración masiva de prompts activos. Al guardar se archiva la versión previa con sus documentos PBD. El runtime usa `bot_prompts.content` como siempre. Las rutas técnicas anteriores conservan compatibilidad para integraciones existentes.

La validación comprueba estructura, contenido por sección y ausencia de pendientes/truncamiento al activar. La revisión humana verifica sentido, fidelidad y cobertura de reglas; no se afirma haber ejecutado pruebas conversacionales del prompt generado.
