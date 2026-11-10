# Cambios (CHG)

Cada cambio de comportamiento lleva un paquete en `docs/cambios/CHG-00N/` antes de modificar el código. La plantilla está en [`PLANTILLA/`](PLANTILLA/).

## Numeración

El último cambio publicado fuera de esta carpeta es [CHG-011](../CHG-011_ORDER_PAYMENTS.md) (cotizaciones y comprobantes). El siguiente paquete es **CHG-012**. No reutilices un número ya publicado.

Copia `PLANTILLA/` a `CHG-012/` (o el número que siga) y sustituye los corchetes. No dejes la plantilla como si fuera un cambio real.

## Contenido de un paquete

| Archivo | Para qué |
| --- | --- |
| `00-historia.md` | Historia, alcance y qué bots no deben cambiar |
| `01-criterios.feature` | Criterios en Gherkin |
| `02-openapi.yaml` | Fragmento del contrato HTTP |
| `03-adr.md` | Decisión y alternativas descartadas |
| `04-plan.md` | Fases, pruebas que fallan primero y rollback |

El flujo completo está en `AGENTS.md`. Merge y deploy solo con OK del dueño.
