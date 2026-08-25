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
│       └── 03-test-suite.md         # Matriz de pruebas y criterios de aceptación (Gherkin)
└── prompts/
    └── master.md                    # Prompt Maestro compilado en XML listo para Asistto
```

## Base de Conocimiento Activa (Asistto Bot ID 170)
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

## Reglas de Integración en Asistto
- Copiar el contenido de `mobi_muebles/prompts/master.md` en la sección **Comportamiento (IA) -> Prompt del Sistema**.
- Asegurar que los documentos de la Base de Conocimiento estén cargados y activos.
