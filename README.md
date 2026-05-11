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
- `INTEGRATION_SECRET_KEY`: clave estable para cifrar secretos de integraciones por bot.
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

## Asistente de prompts del panel

El editor `/admin/bots/{bot_id}/prompt` incluye un cuadro de IA para generar,
corregir o reescribir el prompt del bot antes de publicarlo. Por defecto usa la
misma configuracion `OPENAI_*` del bot, asi que con OpenRouter basta con tener:

```text
OPENAI_API_KEY=tu_openrouter_api_key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openrouter/free
```

Si quieres separar el modelo del asistente de prompts del modelo que contesta
WhatsApp, configura:

```text
PROMPT_ASSISTANT_PROVIDER=openrouter
PROMPT_ASSISTANT_API_KEY=
PROMPT_ASSISTANT_BASE_URL=https://openrouter.ai/api/v1
PROMPT_ASSISTANT_MODEL=openrouter/free
PROMPT_ASSISTANT_MAX_TOKENS=2500
```

Tambien puedes usar Claude en ese cuadro:

```text
PROMPT_ASSISTANT_PROVIDER=anthropic
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

Las claves pueden vivir en Easypanel o pegarse temporalmente en el formulario;
no se guardan en GitHub.

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

Para operar bots por cliente desde el panel, usa el manual paso a paso:
[docs/MANUAL_AGENTES_WHATSAPP.md](docs/MANUAL_AGENTES_WHATSAPP.md).

## Multi-bot foundation

La app esta avanzando hacia una arquitectura multi-cliente. El bot actual de
Asistto sigue siendo el bot por defecto y usa las variables globales de entorno.
Los nuevos bots viviran en Postgres y los mensajes entrantes de WhatsApp se
enrutaran por el `phone_number_id` de Meta.

La primera version del panel multi-bot agrega:

- `GET /admin/clients`: clientes y usuarios cliente.
- `GET /admin/bots`: bots disponibles por agencia o cliente.
- `GET /admin/bots/{bot_id}`: detalle del bot con conversaciones y leads.
- `GET /admin/bots/{bot_id}/prompt`: editor del prompt activo del bot con
  asistente de IA opcional.
- `GET /admin/bots/{bot_id}/knowledge`: base de conocimiento del bot.
- `GET /admin/bots/{bot_id}/integrations`: integraciones del bot con APIs,
  calendarios, CRMs o webhooks.
- `GET /admin/bots/{bot_id}/skills`: habilidades runtime activas para el bot.
- Login de clientes con usuarios guardados en Postgres.

Si un bot tiene prompt o conocimiento activo en Postgres, el runtime lo usa en
las respuestas de WhatsApp. Si no tiene contenido propio, conserva el fallback
de `prompts/system.md` y `prompts/knowledge/`.

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
en GitHub. Cuando el modelo detecta nombre, objetivo y fecha/hora, el backend consulta los
eventos existentes en esa ventana y crea el evento con Google Calendar API si el horario esta libre.

Las citas creadas se guardan en Postgres en `calendar_appointments` junto con el
`google_event_id`. Esto permite cancelar y borrar el evento real de Google Calendar cuando
el usuario escribe algo como `no podre asistir`, `cancela mi cita` o `la quiero cancelar`.
Si hay varias citas activas, el bot pide dia y hora para identificar la correcta.

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
- `GET /admin/ai-status`
- `GET /admin/calendar-status`
- `GET /admin/reset-contact`

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

Desde el detalle de cada bot puedes editar su prompt, base de conocimiento e
integraciones. Los secretos de integraciones se guardan cifrados en Postgres con
`INTEGRATION_SECRET_KEY` y no se muestran de vuelta en el panel.

La primera habilidad runtime es `google_calendar`. Si existe una integracion
activa de tipo `google_calendar`, el bot usa sus credenciales y config:

```json
{
  "client_id": "google-oauth-client-id",
  "calendar_id": "primary",
  "timezone": "America/Chihuahua",
  "duration_minutes": 30,
  "buffer_minutes": 0,
  "summary_prefix": "Llamada cliente"
}
```

Guarda como secretos de esa integracion:

```text
client_secret
refresh_token
```

Tambien puedes activar habilidades por cliente para conectar APIs externas,
webhooks o CRMs. El flujo es:

1. Crea una integracion en `/admin/bots/{bot_id}/integrations`.
2. Guarda la configuracion publica en JSON.
3. Guarda tokens o API keys en `Guardar secreto`.
4. Activa la habilidad correspondiente en `/admin/bots/{bot_id}/skills`.
5. Ajusta el prompt del bot para que use la habilidad solo cuando el caso lo
   requiera.

Ejemplo de integracion `webhook`:

```json
{
  "url": "https://hooks.example.com/whatsapp-lead",
  "headers": {
    "X-Source": "asistto"
  },
  "timeout_seconds": 20
}
```

Secretos sugeridos:

```text
access_token
api_key
```

Ejemplo de integracion `external_api`:

```json
{
  "base_url": "https://api.example.com",
  "allowed_methods": ["GET", "POST"],
  "auth_header": "Authorization",
  "auth_scheme": "Bearer",
  "timeout_seconds": 20
}
```

El runtime soporta marcadores internos que el modelo agrega al final de su
respuesta y que nunca se muestran al usuario:

```text
[[WEBHOOK_POST: {"payload": {"name": "Miguel", "phone": "521..."}}]]
[[EXTERNAL_API_REQUEST: {"method": "GET", "path": "/clientes", "params": {"phone": "521..."}}]]
[[EXTERNAL_API_REQUEST: {"method": "POST", "path": "/leads", "json": {"name": "Miguel"}}]]
[[CRM_LEAD: {"name": "Miguel", "phone": "521...", "status": "new", "notes": "Quiere una cita"}}]]
```

Por seguridad, las habilidades `webhook`, `external_api` y `crm` nacen apagadas
en cada bot. Solo ejecutan llamadas si la habilidad esta activa y existe una
integracion activa del mismo tipo.

Si no existe integracion `google_calendar` para el bot, se conserva el fallback
global de variables `GOOGLE_*`.

## Seguridad

Antes de publicar este template:

```bash
rg -n "sk-|ghp_|github_pat_|EAA|token_real|password_real|secret_real|api_key_real" .
```

No deben existir secretos reales. Los archivos `.env`, `.mcp.json`, `META_SETUP.md` y
`execution/` estan ignorados porque pueden contener credenciales.
