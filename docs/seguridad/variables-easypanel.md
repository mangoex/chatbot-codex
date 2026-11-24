# Variables que Miguel pone en Easypanel

Estos valores no rompen a los bots si se aplican en este orden. Los defaults ya son los seguros para un deploy: la firma estricta nace apagada, la documentación nace apagada y el límite es holgado.

## Orden

1. Despliega el cambio **sin** encender `WHATSAPP_SIGNATURE_STRICT`. Si la variable no existe, cuenta como `false`: el webhook sigue aceptando eventos cuando falta `META_APP_SECRET`, y el log deja un WARNING.
2. Deja `ENABLE_API_DOCS` sin definir o en `false`. `/docs`, `/redoc` y `/openapi.json` dejan de ser públicos. Si alguien del equipo todavía los necesita, pon `ENABLE_API_DOCS=true` solo en ese momento, no antes de decidirlo.
3. Confirma que `/health` responde y que Meta sigue entregando mensajes. Los límites de abajo ya vienen en 1200 por IP y 600 por llave, por minuto y por proceso. No hace falta tocarlos para salir.
4. Si `META_APP_SECRET` está vacío, cópialo desde la app de Meta y reinicia. Revisa que un evento firmado entre. El WARNING de arranque debe desaparecer.
5. **Después** de ver ese evento firmado, pon `WHATSAPP_SIGNATURE_STRICT=true` y reinicia. Hacerlo antes deja el webhook en 403 y los bots dejan de recibir.
6. Si un retorno o la API v1 empiezan a responder 429, sube `RATE_LIMIT_IP_PER_MINUTE` o `RATE_LIMIT_KEY_PER_MINUTE`. `RATE_LIMIT_ENABLED=false` es la salida de emergencia, no el estado normal.

## Qué no cambia con los defaults

- El webhook de Meta (`/webhook` y `/webhooks/whatsapp`) no entra al límite.
- Los retornos `/webhooks/grok`, `/webhooks/external-agent` y `/webhooks/agent` sí entran, con el mismo tope holgado.
- La API `/api/v1` entra al límite por IP y, si mandan `Authorization: Bearer`, `X-API-Key`, `X-Grok-Secret` o `X-Webhook-Secret`, también por esa llave. La query no se usa como llave.
- Campañas, prompts y el ruteo actual no se tocan en este cambio.
