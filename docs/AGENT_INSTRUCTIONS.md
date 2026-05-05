# Agent Instructions

Estas instrucciones ayudan a continuar el proyecto con Codex u otro agente sin
depender de archivos locales.

## Rol

Eres un agente trabajando dentro de una plantilla publica para bots de WhatsApp
desplegables en Easypanel. Manten el proyecto generico y seguro para publicar.

## Antes De Desplegar

- Lee `.env.example` y valida que el usuario tenga valores reales en Easypanel o
  en un `.env` local.
- No imprimas secretos completos en la conversacion.
- Revisa `prompts/system.md`; si conserva placeholders, ayuda a personalizarlo.
- Revisa `docs/HANDOFF.md` para entender el estado operativo.

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

## Seguridad

- Nunca commitees `.env`, `.mcp.json`, `META_SETUP.md` ni `execution/`.
- Antes de `git add`, `git commit` o `git push`, ejecuta una busqueda de
  secretos.
- Manten este template libre de integraciones privadas de agenda, correo o
  filtros de prueba salvo que el usuario pida crear una variante privada.
