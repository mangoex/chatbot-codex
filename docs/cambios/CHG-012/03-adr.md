# ADR — Un modelo de conexiones y el legado apagado por default

## Contexto

Hoy conviven `attention_policy`, `routing_rules`, `grok_bot` y `external_agent`, más tres formas de payload y tres retornos. `reply_owner` cruza esas piezas para no dejar que el sistema equivocado conteste.

## Decisión

Fase 1 agrega conexiones, reglas ordenadas y el atendiente de la conversación, sin borrar nada. `bots.routing_v2_enabled` nace en false. La migración solo copia. El contrato de salida nuevo es uno, firmado como Chatwoot: `timestamp + "." + cuerpo` en `X-Asistto-Signature`. El retorno nuevo es `POST /api/v1/bots/{bot_id}/reply`.

Los retornos viejos delegan en ese camino solo cuando el flag del bot está encendido. Apagado, su código no se mueve: siguen aceptando el secreto en la query porque quitarlo rompería a Grok y a KiwiPOS que ya están conectados.

## Alternativas descartadas

- Reemplazar el pipeline en el mismo deploy. Un error de traducción dejaría sin respuesta a un restaurante o a un bot de ventas.
- Obligar ya el contrato nuevo de salida. KiwiPOS valida un payload parecido al de Meta y `X-Hub-Signature-256`. Se cambia solo al encender el flag, con aviso.
- Poner el secreto del retorno nuevo en la query “por compatibilidad”. El endpoint nuevo no lo acepta. La compatibilidad vive en los alias viejos.

## Consecuencias

- Se puede comparar, con semilla ficticia, que el camino traducido elige el mismo responsable que el legado.
- Encender el flag cambia el JSON de salida y la firma. No se enciende solo.
- El límite de la fase anterior cubre el retorno nuevo porque vive bajo `/api/v1`.
