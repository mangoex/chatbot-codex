# VipGo — Asistente Virtual en WhatsApp para Campañas de Meta Ads (Vital Health)

Respaldo versionado en Git de los artefactos de diseño conversacional (PBD - Prompt Behavior Design) y del prompt maestro para el bot de **VipGo** (v1.1.0).

## Identidad y Propósito

VipGo es el servicio especializado de campañas de Meta Ads (Facebook e Instagram) para asociados independientes de Vital Health que desean promover sus eventos de escaneo con el Escáner Biocuántico, sus productos y la búsqueda de nuevos asociados en México, Estados Unidos y Panamá.

Su misión en WhatsApp es orientar a los asociados, resolver dudas sobre el servicio con total transparencia, calificar qué objetivos desean promover y facilitar el acceso a la plataforma oficial (`www.vipgo.lat/portal`) únicamente cuando el usuario exprese interés explícito en contratar.

## Estructura de Archivos PBD

```text
vipgo/
├── README.md
├── docs/
│   └── pbd/
│       ├── 01-constitution.md       # Constitución, principios innegociables y guardrails (v1.1.0)
│       ├── 02-behavior-specs.md     # Historias de usuario, especificaciones y flujos (v1.1.0)
│       ├── 03-test-suite.md         # Matriz de pruebas y criterios de aceptación Gherkin (v1.1.0)
│       └── 04-master-prompt.md      # Master canónico del paquete PBD (v1.1.0)
└── prompts/
    └── master.md                    # Copia idéntica del Master canónico para despliegue
```

## Aislamiento Multi-Tenant y Guardrails Clave

De acuerdo con la gobernanza de Asistto (`AGENTS.md`) y las reglas constitucionales `CON-001` a `CON-025`, cada bot de tenant opera de forma estrictamente aislada:
- No comparte ni hereda contexto de otros bots (como el bot inmobiliario base o el bot de colaboradores).
- Promueve eventos de escaneo, productos y búsqueda de asociados mediante campañas, pero **no** proporciona información, precios, ingredientes ni beneficios de productos, ni detalles del plan de compensación de Vital Health.
- No realiza afirmaciones médicas sobre el escáner ni sobre los suplementos de Vital Health, ni promete ingresos, ganancias o crecimiento de red (`CON-025`).
- Mantiene a **VipGo** como la única marca pública (sin mencionar "Estudio 1414", "Creativo Siete", "Luis Garduño" ni personal del equipo).
- Protege la liga del portal (`www.vipgo.lat/portal`) hasta que el asociado exprese interés explícito.

## Despliegue en Panel Asistto

Para actualizar o activar este bot en el panel administrativo de Asistto:

| Campo del panel | Documento a copiar |
| --- | --- |
| Constitución PBD | `vipgo/docs/pbd/01-constitution.md` completo |
| Especificaciones PBD | `vipgo/docs/pbd/02-behavior-specs.md` completo |
| Suite de pruebas PBD | `vipgo/docs/pbd/03-test-suite.md` completo |
| Prompt del Sistema / Master Prompt | Bloque XML de `vipgo/docs/pbd/04-master-prompt.md` (o `vipgo/prompts/master.md`) |
