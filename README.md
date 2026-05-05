# WhatsApp Bot Template

Plantilla para crear y desplegar un chatbot de WhatsApp sin n8n:

- FastAPI
- WhatsApp Cloud API de Meta
- OpenAI u OpenRouter por API compatible
- Postgres
- Panel admin con login, conversaciones, CRM, dashboard y escalaciones
- Google Calendar opcional para agendar citas
- Dockerfile listo para Easypanel
- Prompt editable por negocio

## 1. Configuracion local

```bash
cp .env.example .env
```

Rellena `.env` con tus valores reales. No subas `.env` a GitHub.

Variables principales:

- `PUBLIC_BASE_URL`: dominio publico del bot, por ejemplo `https://bot.humanio.digital`.
- `WHATSAPP_ACCESS_TOKEN`: token de Meta WhatsApp Cloud API.
- `WHATSAPP_PHONE_NUMBER_ID`: Phone Number ID de tu numero de WhatsApp.
- `WHATSAPP_VERIFY_TOKEN`: texto secreto inventado por ti para validar el webhook en Meta.
- `META_APP_SECRET`: App Secret de Meta para validar firmas. Recomendado en produccion.
- `OPENAI_API_KEY`: API key de OpenAI o de OpenRouter.
- `OPENAI_BASE_URL`: usa `https://openrouter.ai/api/v1` cuando trabajes con OpenRouter.
- `OPENAI_MODEL`: modelo del agente. Para modelos gratis de OpenRouter puedes usar `openrouter/free`.
- `OPENAI_MAX_TOKENS`: limite de salida para respuestas mas cortas y rapidas.
- `DATABASE_URL`: conexion interna al Postgres de Easypanel.
- `ADMIN_USER`, `ADMIN_PASSWORD`, `SESSION_SECRET`: acceso al panel `/admin`.
- `QUALIFIED_CTA_URL`: link opcional para leads calificados.

Tambien se soportan los aliases anteriores:

- `WHATSAPP_API_TOKEN` en lugar de `WHATSAPP_ACCESS_TOKEN`.
- `VERIFY_TOKEN` en lugar de `WHATSAPP_VERIFY_TOKEN`.
- `WEBHOOK_DOMAIN` en lugar de `PUBLIC_BASE_URL`.

## OpenRouter gratis

Para usar modelos gratis de OpenRouter, configura:

```text
OPENAI_API_KEY=tu_openrouter_api_key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openrouter/free
OPENROUTER_SITE_URL=https://bot.humanio.digital
OPENROUTER_APP_NAME=Humanio WhatsApp Bot
```

`openrouter/free` elige automaticamente un modelo gratuito disponible. Si prefieres un
modelo especifico, usa un ID con sufijo `:free`, por ejemplo
`meta-llama/llama-3.2-3b-instruct:free`, siempre revisando que siga disponible en
OpenRouter.

## 2. Personaliza el bot

Edita [prompts/system.md](prompts/system.md). Reemplaza los placeholders con la identidad,
tono, reglas y criterios del negocio.

Si necesitas cargar FAQs, catalogo, politicas o respuestas frecuentes, crea archivos `.md` o
`.txt` dentro de:

```text
prompts/knowledge/
```

El sistema guarda el mensaje entrante en el admin antes de llamar al modelo. Si la IA tarda,
la conversacion aparece de inmediato y la respuesta se agrega cuando esta lista.

## 3. Agenda con Google Calendar

La agenda es opcional. Para activarla configura en Easypanel:

```text
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=America/Chihuahua
GOOGLE_APPOINTMENT_DURATION_MINUTES=30
GOOGLE_APPOINTMENT_BUFFER_MINUTES=0
GOOGLE_APPOINTMENT_SUMMARY_PREFIX=Llamada Asistto
```

El `GOOGLE_REFRESH_TOKEN` debe venir de OAuth con permiso de Google Calendar. No lo guardes
en GitHub. Cuando el modelo detecta nombre, objetivo y fecha/hora, el backend revisa
`freeBusy` y crea el evento con Google Calendar API si el horario esta libre.

## 4. Ejecutar localmente

Necesitas Postgres y las variables de `.env` listas.

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Endpoints:

- `GET /health`
- `GET /webhook`
- `POST /webhook`
- `GET /webhooks/whatsapp`
- `POST /webhooks/whatsapp`
- `POST /reload`
- `POST /maintenance/reset-contact`
- `GET /admin`

## 5. DNS para Easypanel

Para `bot.humanio.digital`, crea en tu DNS:

```text
Tipo: A
Host/Nombre: bot
Valor: IP publica de tu VPS de Hostinger
TTL: automatico o 300
```

El registro A apunta al servidor. Luego Easypanel decide que app responde a ese dominio.

## 6. Deploy en Easypanel

1. Crea un proyecto en Easypanel, por ejemplo `whatsapp-bot`.
2. Crea un servicio Postgres.
3. Crea un servicio App desde este repositorio de GitHub.
4. Usa el Dockerfile del repo.
5. Configura puerto interno `8000`.
6. Agrega el dominio `bot.humanio.digital` al servicio App y activa HTTPS.
7. Agrega las variables de entorno desde `.env.example`.
8. Usa la URL interna de Postgres en `DATABASE_URL`.
9. Deploy.
10. Verifica:

```text
https://bot.humanio.digital/health
```

## 7. Conectar Meta

Cuando el despliegue este listo, configura el webhook en Meta:

- Callback URL: `https://bot.humanio.digital/webhooks/whatsapp`
- Verify token: el valor de `WHATSAPP_VERIFY_TOKEN`
- Webhook field: `messages`

La app tambien acepta `https://bot.humanio.digital/webhook` por compatibilidad.

## 8. Panel admin

Abre:

```text
https://bot.humanio.digital/admin
```

Usa `ADMIN_USER` y `ADMIN_PASSWORD`.

## Seguridad

Antes de publicar este template:

```bash
rg -n "sk-|ghp_|github_pat_|EAA|token_real|password_real|secret_real|api_key_real" .
```

No deben existir secretos reales. Los archivos `.env`, `.mcp.json`, `META_SETUP.md` y
`execution/` estan ignorados porque pueden contener credenciales.
