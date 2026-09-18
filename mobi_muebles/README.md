# Mobibot — Asistente Interno de Colaboradores (Mobi Muebles / Industrias Recio)

Respaldo versionado en Git de los artefactos de diseño conversacional (PBD - Prompt Behavior Design) y del prompt maestro para **Mobibot** (Bot ID: 170).

## Identidad y Propósito
Mobibot es el asistente virtual interno vía WhatsApp para más de 500 colaboradores de **Mobi Muebles / Industrias Recio, S.A. de C.V.** en Culiacán, Sinaloa. Su objetivo es brindar orientación cálida, amable y certera sobre políticas, procedimientos, horarios, citas con psicología y directorio de colaboradores, basándose estrictamente en su Base de Conocimiento activa.

## Estructura de Archivos PBD

```text
mobi_muebles/
├── README.md
├── docs/
│   └── pbd/
│       ├── 01-constitution.md       # Constitución, principios innegociables y guardrails
│       ├── 02-behavior-specs.md     # Historias de usuario, especificaciones y flujos
│       ├── 03-test-suite.md         # Matriz de pruebas y criterios de aceptación (Gherkin)
│       └── 04-master-prompt.md      # Master canónico del paquete PBD
└── prompts/
    └── master.md                    # Copia idéntica del Master canónico para compatibilidad
```

## Fuentes Institucionales Declaradas (Asistto Bot ID 170)

Catálogo de referencia proporcionado por el propietario, no certificación de actividad actual en producción.
1. `Colaboradores.csv` (Directorio de colaboradores con Nombre, Área y Teléfono normalizable a 10 dígitos).
2. `03_Politica_de_Ciberseguridad.md`
3. `08_Politica_de_Aplicaciones_y_Software.md`
4. `07_Politica_de_Uso_Responsable_de_Inteligencia_Artificial.md`
5. `05_Politica_de_Uso_de_Correo_Electronico.md`
6. `11_Politica_de_lineas_Celulares.md`
7. `Politica_de_Ergonomia_y_Derecho_al_Descanso_Ley_Silla.md`
8. `12_Politica_de_Liderazgo_Mobi.md`
9. `10_Politica_de_Gastos_de_Viaje.md`
10. `POLI-ADMI-01_Manual_de_politicas_generales.md`
11. `04_Reglamento_Interior_Trabajo_ADPEF-16-15.md`

## Actualización Manual del Paquete 1.4.0

Marco utilizado: [PBD WhatsApp Skill Starter](https://github.com/mangoex/pbd-whatsapp-skill-starter), revisión `241e4eeee4ceff4b8c2ef9f2da64beebe7e8e6c9`, verificada el 2026-09-03. Modo AUTO: actualización de los tres documentos existentes y reconstrucción del cuarto canónico desde el Master previo.

En **Comportamiento (IA)** del bot **170 — Mobi Muebles**, respalda primero los cuatro contenidos actuales para poder revertir. Reemplaza cada campo completo, sin concatenar versiones:

| Campo del panel | Documento a copiar |
| --- | --- |
| Constitución PBD | `docs/pbd/01-constitution.md` completo |
| Especificaciones PBD | `docs/pbd/02-behavior-specs.md` completo |
| Suite de pruebas PBD | `docs/pbd/03-test-suite.md` completo |
| Prompt del Sistema / Master Prompt | Solo el bloque XML de `docs/pbd/04-master-prompt.md`, desde `<sistema version="1.4.0">` hasta `</sistema>` |

Guarda/publica con el control existente del panel y vuelve a abrirlo para comprobar que los cuatro campos quedaron actualizados. El número de versión de publicación de Asistto puede diferir de la versión documental 1.4.0.

**No cargar estos documentos PBD como artículos de la Base de Conocimiento.** Las políticas empresariales y el directorio permanecen separados. En especial, los importes de prueba de la suite no deben convertirse en evidencia RAG.

El código lee el prompt activo del bot en la base de datos (`get_active_bot_prompt`). Un commit, push o redeploy no reemplaza por sí solo los campos del panel. Esta entrega no cambió código, base de datos ni configuración de producción.

## Plan y Tareas de Verificación

1. Completado: contrastar documentos 1.1.0 proporcionados, respaldo 1.3.0, capturas e instrucciones PBD; resolver contradicciones sin quitar guardrails.
2. Completado: preparar Constitución, especificaciones y pruebas 1.4.0; compilar el Master al final y conservar IDs previos.
3. Validación local: comprobar contrato PBD, XML, continuidad de IDs y equivalencia de las dos copias del Master; ver `docs/pbd/VALIDACION-1.4.0.md`.
4. Por ejecutar por el propietario: copiar/publicar los cuatro campos como se indica arriba y verificar el bot y la versión activa.
5. Verificar que la política de gastos de viaje vigente está cargada y que el apartado de topes forma parte del contenido recuperado. La captura compartida acredita su texto visible, no el índice ni la versión activa.
6. Probar "Hola", "Cuánto puedo gastar si salgo de viaje", "Cuánto de comida diario" y "Perdón, cuánto", tanto en conversación nueva como en la que tuvo respuestas incorrectas. No borrar conversaciones para ocultar regresiones.
7. Probar ausencia de evidencia, montos de otro concepto, empleo, catálogo parcial y solicitud humana/psicología sin integración. Evaluar los criterios y bloques de `03-test-suite.md`.
8. Si falla, registrar de forma segura la versión del prompt, los identificadores de fragmentos recuperados y la respuesta. Evitar publicar datos personales o secretos. No atribuir automáticamente el fallo al prompt: revisar recuperación y ruta de salida.

## Límites de la Entrega

- DEPLOYMENT STATUS: NOT VERIFIED. No se accedió al panel, WhatsApp ni a la base de datos de producción.
- La suite conversacional fue revisada estáticamente, no ejecutada con un modelo ni aprobada en WhatsApp.
- Cambiar instrucciones no repara un índice RAG ni garantiza cero alucinaciones. El control monetario de código tampoco verifica por sí solo la relación entre concepto e importe.
- No se inventaron contactos ni disponibilidad de agenda. Sin resultado de integración, el comportamiento definido es orientar, no confirmar una acción.
