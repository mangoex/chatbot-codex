# WhatsApp Bot Handoff

Este documento resume el estado del proyecto para continuar desde otra
computadora usando GitHub como fuente de verdad. No contiene secretos.

## Estado Actual

- Repo remoto: `https://github.com/mangoex/chatbot-codex.git`.
- Rama de trabajo: `codex/easypanel-fastapi`.
- App desplegada en Easypanel con FastAPI + Postgres.
- Dominio publico usado para el bot: `https://bot.humanio.digital`.
- Healthcheck esperado: `GET https://bot.humanio.digital/health`.
- Webhook principal: `https://bot.humanio.digital/webhooks/whatsapp`.
- El bot acepta tambien `/webhook` por compatibilidad.
- OpenRouter esta soportado usando `OPENAI_BASE_URL` y `OPENAI_API_KEY`.

## Variables De Entorno

Configurar en el servicio `app` de Easypanel, no solo a nivel de proyecto:

```env
PORT=8000
PUBLIC_BASE_URL=https://bot.humanio.digital
WHATSAPP_API_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
VERIFY_TOKEN=
META_APP_SECRET=
OPENAI_API_KEY=
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=
OPENROUTER_SITE_URL=https://bot.humanio.digital
OPENROUTER_APP_NAME=WhatsApp Bot
DATABASE_URL=
ADMIN_USER=
ADMIN_PASSWORD=
SESSION_SECRET=
QUALIFIED_CTA_URL=
ENABLE_FOLLOW_UPS=false
```

Notas:

- `WHATSAPP_API_TOKEN` debe ser el token permanente de WhatsApp Cloud API.
- `META_APP_SECRET` puede quedar vacio durante pruebas; en produccion conviene
  configurarlo.
- `QUALIFIED_CTA_URL` es opcional y reemplaza `[[ACTION_LINK]]`.

## Meta / WhatsApp

Problema resuelto durante la configuracion:

- Los mensajes reales no llegaban al bot aunque la prueba de Meta si funcionaba.
- La causa fue un `override_callback_uri` heredado apuntando a un webhook viejo
  de n8n/Chatwoot.
- Se corrigio desde Graph API Explorer actualizando `subscribed_apps` del WABA
  para usar el webhook del bot.

Validacion recomendada:

```text
GET /v25.0/{WABA_ID}/subscribed_apps
```

La respuesta debe mostrar la app correcta y el `override_callback_uri` debe
apuntar a:

```text
https://bot.humanio.digital/webhooks/whatsapp
```

Si al actualizar `subscribed_apps` aparece `Callback verification failed` con
HTTP 403, el `verify_token` enviado a Meta no coincide con `VERIFY_TOKEN` en
Easypanel.

## Configuracion Del Agente

El agente se configura por archivos versionados:

- `prompts/system.md`: identidad, objetivo, estilo, reglas y criterio comercial.
- `prompts/knowledge/*.md` o `*.txt`: base de conocimiento por temas.

El sistema carga `prompts/system.md` y despues concatena los archivos de
`prompts/knowledge/` en orden alfabetico.

Marcadores soportados:

- `[[ACTION_LINK]]`: marca el lead como calificado y se reemplaza por
  `QUALIFIED_CTA_URL` si existe.
- `[[DESCALIFICADO: motivo]]`: marca el lead como descalificado en CRM.

## Siguiente Etapa Recomendada

1. Personalizar `prompts/system.md` para el negocio real.
2. Crear archivos en `prompts/knowledge/` con servicios, FAQs, precios,
   politicas y objeciones.
3. Reimplementar en Easypanel.
4. Probar desde WhatsApp real y revisar el panel `/admin/conversations`.
5. Luego construir un panel creador de agentes multi-cliente:
   - bots
   - bot prompts
   - bot knowledge
   - bot skills
   - bot WhatsApp numbers
   - conversations
   - leads

## Prompt Para Continuar En Otra Computadora

Copia este prompt en una nueva sesion de Codex:

```text
Estoy continuando el proyecto `mangoex/chatbot-codex`, un bot de WhatsApp Cloud
API desplegado en Easypanel con FastAPI, Postgres, OpenRouter/OpenAI y panel
admin.

Contexto importante:
- Repo: https://github.com/mangoex/chatbot-codex.git
- Rama relevante: codex/easypanel-fastapi
- Dominio publico: https://bot.humanio.digital
- Webhook: https://bot.humanio.digital/webhooks/whatsapp
- El problema anterior era que los mensajes reales no llegaban porque el WABA
  tenia un override_callback_uri viejo de n8n/Chatwoot. Ya se corrigio con
  Graph API Explorer y los mensajes reales ya llegan.
- No imprimir ni commitear secretos. Las variables reales estan en Easypanel y
  Meta, no en GitHub.

Quiero continuar con la configuracion del agente:
1. Revisar `prompts/system.md`.
2. Crear una base de conocimiento en `prompts/knowledge/`.
3. Definir habilidades del chatbot: calificar leads, responder FAQ, escalar a
   humano y enviar CTA.
4. Preparar el camino para un futuro panel creador de agentes multi-cliente.

Primero lee `AGENTS.md`, `README.md`, `.env.example` y `docs/HANDOFF.md`.
Despues revisa la estructura del proyecto y propon o implementa los siguientes
pasos sin tocar secretos.
```
