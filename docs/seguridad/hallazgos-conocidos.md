# Hallazgos conocidos

Estos hallazgos existen en el pin actual de `requirements.txt`. El CI los registra y **no bloquea** el PR. Una vulnerabilidad que no esté en la línea base sí rompe el workflow.

No se actualizan estas librerías en el arnés: un bump de `cryptography`, `starlette` o `pypdf` puede cambiar el runtime de bots que ya están en producción. Subirlas es un cambio aparte, con pruebas y OK del dueño.

Medición: 2026-11-10, `pip-audit -r requirements.txt`.

| Paquete | Versión pin | Ids en la línea base | Notas |
| --- | --- | --- | --- |
| pypdf | 6.12.1 | 42 | Solo entra al leer PDF de conocimiento. |
| python-multipart | 0.0.17 | 7 | Formularios del panel. |
| starlette | 0.38.6 (viene con FastAPI 0.115.0) | 7 | Capa HTTP. |
| cryptography | 42.0.8 | 7 | Cifrado de secretos de integración. |
| python-dotenv | 1.0.1 | 1 | Lectura de entorno local. |

La lista exacta está en [`pip-audit-baseline.json`](pip-audit-baseline.json), con el id principal y sus alias (GHSA, CVE o PYSEC). Dos versiones de pip-audit pueden nombrar el mismo hallazgo distinto; si cualquiera de esos ids ya está, no bloquea. Un id que no esté en la lista sí rompe el workflow. Gitleaks corre con `.gitleaks.toml` y sí bloquea un secreto nuevo.

Gitleaks también marca placeholders que ya estaban en pruebas y en el manual de la API (`tests/test_external_agent_integration.py`, `tests/test_routing_rules.py`, `docs/api/GROK_EXTERNAL_API.md`). Son cadenas de ejemplo, no llaves de producción, y están permitidas por regex. Un secreto distinto sí falla el workflow.

## Brecha de contrato ya vista

`GET /webhook` y `GET /webhooks/whatsapp` responden `text/plain` con el reto de Meta. El OpenAPI generado por FastAPI anuncia `application/json` con esquema vacío. La prueba de contrato deja pasar solo esa pareja de ruta y estado. No se cambia la ruta en el arnés: Meta depende del cuerpo de texto.
