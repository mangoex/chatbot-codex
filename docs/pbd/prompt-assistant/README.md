# Prompt maestro en el panel de Asistto

El usuario final describe lo que necesita, revisa un solo documento y pulsa **Guardar y activar prompt maestro**. El asistente genera Markdown con reglas completas y ejemplos. También puede editar y descargar el prompt directamente. No necesita administrar archivos técnicos de PBD.

La ingeniería del asistente conserva aquí Constitución, especificaciones y pruebas según `AGENTS.md`. Estos archivos describen el generador; no se crean como artefactos adicionales para cada bot desde el nuevo flujo. `04-master-prompt.md` contiene las instrucciones compiladas del generador y debe coincidir con `SINGLE_PROMPT_SYSTEM_INSTRUCTIONS` en `app/prompt_assistant.py`.

El panel permite pedir cambios específicos en lenguaje natural desde el cuadro original, sin campos de reemplazo ni selector. Para prompts existentes se proponen ediciones mínimas y se revisan en una segunda llamada contra las reglas y dependencias completas. Para bots nuevos se crea un maestro y también se revisa. Generar nunca activa: el usuario revisa el resultado y guarda.

`05-change-planner.md` y `06-change-reviewer.md` son las instrucciones compiladas de `app/prompt_changes.py`; `04-master-prompt.md` sigue describiendo la creación de un maestro completo. Se verifican por pruebas de igualdad. La nueva ruta interna del panel usa `guarded_prompt`; las rutas técnicas anteriores mantienen compatibilidad.

El guardado revisado conserva Constitución, specs y tests en la nueva versión, además de archivar la anterior. No modifica conocimiento ni configuración automáticamente; ante contradicciones identifica qué fuente resolver. Un comprobante firmado evita activar cambios adicionales o usar una revisión obsoleta. Requiere SESSION_SECRET y el proveedor de IA ya configurado, sin migración de esquema. El runtime sigue usando `bot_prompts.content`.

La validación comprueba estructura, contenido por sección y ausencia de pendientes/truncamiento al activar. La revisión humana verifica sentido, fidelidad y cobertura de reglas; no se afirma haber ejecutado pruebas conversacionales del prompt generado.
