# Agent Instructions

Estas instrucciones ayudan a continuar el proyecto con Codex u otro agente sin
depender de archivos locales.

## Rol

Eres un agente trabajando en `mangoex/chatbot-codex`, motor de bots de
WhatsApp desplegable en Easypanel. El bot actual esta configurado para Asistto,
iniciativa de Humanio para asistentes virtuales con IA.

Manten el proyecto seguro para publicar: el codigo y prompts viven en GitHub;
los secretos viven en Easypanel, Meta, Google y OpenRouter.

## Antes De Desplegar

- Lee `.env.example` y valida que el usuario tenga valores reales en Easypanel o
  en un `.env` local.
- No imprimas secretos completos en la conversacion.
- Revisa `prompts/system.md`; si conserva placeholders, ayuda a personalizarlo.
- Revisa `docs/HANDOFF.md` para entender el estado operativo.
- Si el usuario pide continuar desde otro equipo, trata `main` como fuente de
  verdad y actualiza `docs/HANDOFF.md`.

## Deploy En Easypanel

- Usa las herramientas disponibles para GitHub, Hostinger o Easypanel cuando
  esten configuradas.
- Crea o usa un repositorio privado de GitHub.
- Crea un servicio Postgres en Easypanel y configura `DATABASE_URL` con la URL
  interna.
- Publica la app con `PUBLIC_BASE_URL` o su alias `WEBHOOK_DOMAIN`.
- Verifica `GET /health`.
- Verifica handshake de Meta con `GET /webhooks/whatsapp`.
- En Meta, configura el Callback URL, Verify Token y suscribe el campo
  `messages`.
- Si los mensajes reales no llegan pero la prueba de Meta si, revisa
  `subscribed_apps` del WABA y cualquier `override_callback_uri` heredado.

## Asistto

- El proveedor IA actual es OpenRouter con API compatible con OpenAI.
- El agente explica el servicio de chatbots de WhatsApp con IA, recomienda
  paquetes y agenda llamadas.
- Para Meta Tech Provider, posiciona el producto como Asistto by Humanio:
  automatizacion de atencion, ventas, agenda e integraciones por WhatsApp para
  negocios. No lo describas como asistente general de IA.
- El flujo Tech Provider vive en `/admin/tech-provider/review`,
  `/admin/bots/{bot_id}/whatsapp`,
  `/admin/bots/{bot_id}/whatsapp/diagnostics` y
  `/admin/bots/{bot_id}/whatsapp/send-test` para el video messaging, y
  `/admin/bots/{bot_id}/whatsapp/templates`.
- Nuevos tokens de WhatsApp deben guardarse cifrados como secreto
  `access_token` en la integracion `whatsapp_cloud`, no en prompts ni docs.
- La agenda con Google Calendar ya crea eventos reales y guarda el
  `google_event_id` en `calendar_appointments`.
- La cancelacion debe borrar el evento real de Google Calendar, no solo
  contestar de forma conversacional.
- Mantener prioridad de cancelacion sobre agenda. Si el bot pidio identificar
  una cita para cancelar, frases como `la del viernes a las 10`, `esta de
  pasadomañana a las 9` o `jue 7 a las 8` siguen siendo cancelacion.
- No tomar profesiones o giros como nombre personal: `soy consultor de IA`,
  `soy dentista`, `tengo una clinica` no son nombres.

## Diagnostico Rapido

- `/admin/ai-status`: valida OpenRouter/OpenAI sin mostrar API key.
- `/admin/calendar-status`: valida Google Calendar sin mostrar secretos.
- `/admin/reset-contact`: limpia memoria de un contacto para empezar una prueba.
- `/reload`: solo recarga prompts; cambios Python requieren redeploy completo.

## Seguridad

- Nunca commitees `.env`, `.mcp.json`, `META_SETUP.md` ni `execution/`.
- Antes de `git add`, `git commit` o `git push`, ejecuta una busqueda de
  secretos.
- No imprimas tokens completos, refresh tokens, client secrets, API keys,
  passwords ni URLs de base de datos con credenciales.
