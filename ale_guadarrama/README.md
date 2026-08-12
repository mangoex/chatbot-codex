# Ale Guadarrama — Alee VitalHealth

Respaldo manual, versionado en Git, de los artefactos PBD y del prompt maestro del bot **Alee VitalHealth**.

## Estructura

```text
ale_guadarrama/
├── README.md
├── docs/
│   └── pbd/
│       ├── constitution.md
│       ├── behavior-specs.md
│       └── test-suite.md
├── knowledge/
│   └── vitalhealth-productos-enlaces.md
└── prompts/
    └── master.md
```

## Trazabilidad PBD

1. `docs/pbd/constitution.md`: identidad, misión, principios, límites duros y precedencia.
2. `docs/pbd/behavior-specs.md`: historias de usuario, estado, recursos, flujos y criterios de terminación.
3. `docs/pbd/test-suite.md`: matriz de aceptación y reglas que bloquean publicación.
4. `prompts/master.md`: prompt operativo compilado desde los tres documentos anteriores.
5. `knowledge/vitalhealth-productos-enlaces.md`: catálogo cerrado de nombres, resúmenes prudentes y enlaces exactos de productos.

La dirección contractual es:

```text
Constitución → Especificaciones → Pruebas → Prompt maestro
```

Ante una contradicción, prevalece la Constitución. Toda modificación de comportamiento debe actualizar primero las especificaciones, añadir o ajustar pruebas y finalmente recompilar el prompt maestro.

## Configuración prevista en Asistto

- Carpeta base del cliente: `ale_guadarrama`
- Ruta Prompt maestro: `prompts/master.md`
- Ruta Constitution / PBD principal: `docs/pbd/constitution.md`
- Carpeta de documentos PBD: `docs/pbd`
- Dirección de sincronización inicial: panel de Asistto a GitHub

## Estado del baseline

- Constitución: `1.1.2` (`2026-08-11`)
- Especificaciones, pruebas y prompt maestro: `1.2.2` (`2026-08-11`)
- Catálogo de productos: `1.0.2` (`2026-08-11`)
- Estado: 13 enlaces activos; preparado para ejecución de la suite y validación en el bot
- Método actual: actualización manual; sin sincronización automática con el panel

## Configuración manual requerida para la escalación

Además de publicar `prompts/master.md`, en el panel de Asistto se debe abrir **Reglas de Escalado**, activar la escalación humana y agregar estas palabras clave:

```text
evento, eventos, convención, convenciones, reunion, reunión, reuniones
```

Las palabras clave permiten que la plataforma registre el caso como pendiente para seguimiento humano. El prompt controla la respuesta visible; la configuración del panel activa el registro operativo de la escalación.

## Flujo manual de actualización

1. Registrar la historia o cambio de comportamiento solicitado.
2. Revisar su impacto contra la Constitución.
3. Actualizar `behavior-specs.md`.
4. Actualizar `test-suite.md` con los casos de aceptación y regresión.
5. Actualizar `master.md` sin debilitar límites superiores.
6. Actualizar los documentos de `knowledge/` cuando cambien recursos autorizados.
7. Ejecutar la suite PBD completa.
   - No continuar a publicación mientras exista un enlace requerido marcado como bloqueado.
8. Revisar el diff y versionar el cambio en Git.
9. Copiar los cuatro documentos PBD al panel de Asistto.
10. Subir `knowledge/vitalhealth-productos-enlaces.md` como documento activo en **Base de Conocimiento**; guardarlo solo en Git o en disco no lo incorpora al contexto productivo.
11. Verificar con conversaciones reales los casos de enlace único, ambigüedad, precio dinámico, producto desconocido y guardrail médico.

No deben guardarse tokens, credenciales, datos personales de conversaciones ni secretos operativos dentro de esta carpeta.
