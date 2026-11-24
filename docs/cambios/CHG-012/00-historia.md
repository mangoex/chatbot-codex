# CHG-012 — Ruteo unificado, fase 1

Estado: fase 1 en borrador. Dueño del producto: Miguel.

## Historia

Como operador de Asistto, quiero una sola forma de conectar un sistema externo y de saber quién atiende cada conversación, para dejar de mantener cuatro configuraciones que se pisan y tres retornos distintos.

## Qué no puede romperse

- Con `ROUTING_V2` apagado, que es el default de cada bot, el pipeline de `app/main.py` (`handle_inbound`, `forward_all`, política de atención, Grok y agente externo) sigue decidiendo igual que hoy.
- Los retornos `/webhooks/grok` y `/webhooks/external-agent` siguen aceptando el secreto como hoy, incluida la query, mientras el flag del bot esté apagado.
- Las campañas siguen en `POST /api/v1/bots/{bot_id}/campaigns`.
- No se borra configuración legada ni se enciende el flag al migrar.

## Alcance de esta fase

- Conexiones externas con presets `grok_bot`, `kiwipos` y `webhook_custom`.
- Reglas en orden: teléfonos de administradores, luego número o etiqueta del contacto, luego default Asistto.
- La conversación guarda quién la atiende. Un externo puede tomarla o devolverla, con regreso a Asistto al vencer el plazo.
- Un solo contrato de salida, con la misma forma y con firma HMAC al estilo de Chatwoot (`timestamp + "." + cuerpo`).
- Un solo retorno nuevo: `POST /api/v1/bots/{bot_id}/reply`, con llave por conexión en `Authorization: Bearer` o `X-API-Key`. Sin secreto en la query.
- Con el flag encendido, los retornos viejos delegan en ese camino. Apagado, no se tocan.
- Migración idempotente y reversible que traduce la configuración actual a reglas equivalentes.

## Fuera de alcance

- Borrar el pipeline legado.
- Encender `ROUTING_V2` en un bot real. Eso lo hace Miguel, de uno en uno, después de ver la equivalencia.
- Cambiar el contrato que ya consume KiwiPOS mientras el flag siga apagado. Al encenderlo, la salida pasa al contrato único; hay que avisar al externo antes.
