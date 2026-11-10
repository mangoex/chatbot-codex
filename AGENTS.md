# AGENTS.md — Cómo se trabaja en Asistto

Asistto es el backend multi-bot de WhatsApp Cloud API (FastAPI y Postgres) desplegado en Easypanel. Hay bots de clientes en producción. Un cambio que “se ve pequeño” puede desviar mensajes, silenciar a un asesor o mezclar datos de dos negocios. Este archivo es la guía para quien modifique el repositorio.

## Organización del código

- `app/main.py` — aplicación FastAPI, webhook de Meta (`/webhook` y `/webhooks/whatsapp`), retornos de Grok y de agente externo, y el pipeline de cada mensaje entrante.
- `app/api.py` — API externa versión 1 (`/api/v1`), campañas y contactos. La autenticación es por bot.
- `app/attention_routing.py` — política explícita de atención (administradores, reglas por teléfono, responsable predeterminado).
- `app/db.py` — pool, esquema idempotente y migraciones. Toda fila de negocio lleva `bot_id`.
- `app/signature.py` — firma `X-Hub-Signature-256` de Meta.
- `app/grok_client.py`, `app/external_agent_client.py`, `app/chatwoot_client.py` — contratos de salida hacia sistemas externos. Hoy conviven con `routing_rules`.
- `app/bots.py` — resuelve el bot por `phone_number_id` o por id. No hay un bot global que conteste por otro.
- `prompts/` y `*/docs/pbd/` — prompt y especificaciones por cliente. No mezclar conocimiento de un negocio en el código compartido.
- `tests/` — pruebas. `tests/bdd/` son escenarios Gherkin. `tests/integration/` habla con Postgres.
- `docs/cambios/` — paquetes de cambio (CHG) antes de tocar comportamiento.
- `docs/seguridad/` — hallazgos conocidos de secretos y dependencias que el CI no bloquea.

El pipeline legado de `handle_inbound` y `forward_all` sigue vivo a propósito. No se borra hasta que el dueño lo autorice, con el flag del bot apagado por omisión en cualquier ruteo nuevo.

## Flujo obligatorio

Ningún cambio de comportamiento se implementa directo sobre `main`. El orden es:

1. **Historia.** Quién la necesita y qué pasa si sale mal en un bot que ya está en producción.
2. **Requisito.** Qué debe seguir igual para los bots actuales.
3. **Contrato OpenAPI y ADR.** El contrato público y la decisión de diseño, con la alternativa que se descartó.
4. **Gherkin.** Escenarios legibles, incluidos los casos que no deben cambiar.
5. **Casos de TDD y plan.** Lista de pruebas que van a fallar primero, y el plan por fases si el cambio no cabe en un solo despliegue.
6. **Pruebas que fallan primero.** Se corren y se ve el fallo esperado antes de la implementación.
7. **Implementación.** El mínimo para poner esas pruebas en verde, sin reescribir el pipeline legado.
8. **CI.** Lint ligero, suite, BDD, cobertura, gitleaks y pip-audit.
9. **PR con revisión de código y de seguridad.** Borrador, apilado si depende de otro PR.
10. **Merge y deploy solo con OK del dueño (Miguel).** El agente no hace merge, no empuja a `main`, no despliega, no hace force-push ni reescribe historia.

El paquete vive en `docs/cambios/CHG-00N/`. La numeración sigue al último cambio publicado. Hoy el último es `docs/CHG-011_ORDER_PAYMENTS.md`, así que el siguiente es CHG-012. La plantilla está en `docs/cambios/PLANTILLA/`.

## Comandos

Suite de unidad (sin BDD ni Postgres):

```bash
pytest tests --ignore=tests/bdd --ignore=tests/integration -q
```

BDD del webhook:

```bash
pytest tests/bdd -q
```

Integración contra Postgres. La base tiene que llamarse `asistto_test`. Localmente se levanta con el compose de prueba:

```bash
docker compose -f docker-compose.test.yml up -d
export TEST_DATABASE_URL=postgresql://asistto:asistto_test_only@127.0.0.1:5432/asistto_test
export REQUIRE_TEST_DATABASE=1
pytest tests/integration -q
```

Cobertura. El piso está en `.coveragerc` (`fail_under = 58`), un poco abajo del 64% medido el 2026-11-10. Se mide sobre la suite, sin BDD ni integración: algunas pruebas antiguas reemplazan `fastapi` y `asyncpg` en `sys.modules` al importarse, y fallan si otro módulo ya cargó la librería real. Por eso BDD e integración corren en su propio proceso.

```bash
pytest tests --ignore=tests/bdd --ignore=tests/integration -q --cov=app --cov-report=term-missing
```

Lint ligero. No reformatea el repositorio. Revisa sintaxis (`E9`, `F63`, `F7`). No incluye nombres indefinidos: en el árbol ya hay cuatro (`Any` en `app/client.py` y `re` en `app/db.py`) y corregirlos no es parte del arnés.

```bash
ruff check --select E9,F63,F7 app tests
python -m compileall -q app tests
```

Instalación de herramientas de desarrollo:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

## Reglas duras

- No commitear `.env`, `.mcp.json`, `META_SETUP.md` ni `execution/`.
- Antes de `git add`, revisar `git status`. No usar `git add -A` a ciegas.
- Antes de commit o push, buscar secretos. Si aparece un valor real, detenerse y pedir rotación. No “limpiarlo” en silencio.
- Semillas, números y llaves de prueba son ficticios. Prohibido apuntar pruebas a una base de un cliente.
- No cambiar rutas ni el ruteo de un bot existente en un PR de arnés o de documentación.
- `ROUTING_V2`, cuando exista, nace apagado por bot. Encenderlo es decisión del dueño, de uno en uno.
- Los retornos viejos siguen aceptando a los clientes ya conectados. Un endpoint nuevo no les quita la query de un día para otro.
- No agregar integraciones de agenda, correo o CRM al template público salvo que el dueño pida una variante privada.
- Merge, push a `main`, deploy, force-push y reescritura de historia quedan fuera de este flujo hasta el OK explícito del dueño.
