# Asistto WhatsApp Bot Handoff

Este documento resume el estado operativo para continuar el proyecto desde otra
computadora usando GitHub como fuente de verdad. No contiene secretos.

## Estado Actual

- Repo remoto: `https://github.com/mangoex/chatbot-codex.git`.
- Rama fuente de verdad: `main`.
- App desplegada en Easypanel con FastAPI + Postgres.
- Dominio publico: `https://bot.humanio.digital`.
- Healthcheck esperado: `GET https://bot.humanio.digital/health`.
- Webhook principal: `https://bot.humanio.digital/webhooks/whatsapp`.
- Webhook compatible: `https://bot.humanio.digital/webhook`.
- Panel admin: `https://bot.humanio.digital/admin`.
- Producto configurado: Asistto, iniciativa de Humanio para chatbots de
  WhatsApp con IA.
- Proveedor IA actual: OpenRouter usando API compatible con OpenAI.
- Agenda real con Google Calendar: activa y probada.

## Cambios Importantes Ya Subidos

Los ultimos commits funcionales en `main` antes de este handoff fueron:

- `057c407`: agrega flujo de cancelacion real de citas en Google Calendar y
  tabla `calendar_appointments`.
- `25af39e`: corrige casos de agenda como `pasadomañana`, `Gracias` despues
  de confirmar cita y cambios de hora como `a las 10`.
- `e825bcb`: mantiene modo cancelacion cuando el bot pide identificar la cita;
  soporta frases como `esta de pasadomañana a las 9`, `la quiero cancelar` y
  abreviaturas como `jue 7 a las 8`.

## Variables De Entorno

Configurar en el servicio `app` de Easypanel, no solo a nivel de proyecto:

```env
PORT=8000
PUBLIC_BASE_URL=https://bot.humanio.digital
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=
META_APP_SECRET=
OPENAI_API_KEY=
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openrouter/free
OPENROUTER_SITE_URL=https://bot.humanio.digital
OPENROUTER_APP_NAME=Asistto
OPENAI_TIMEOUT_SECONDS=45
OPENAI_MAX_TOKENS=450
DATABASE_URL=
ADMIN_USER=
ADMIN_PASSWORD=
SESSION_SECRET=
QUALIFIED_CTA_URL=https://asistto.humanio.digital/
ENABLE_FOLLOW_UPS=false
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=America/Chihuahua
GOOGLE_APPOINTMENT_DURATION_MINUTES=30
GOOGLE_APPOINTMENT_BUFFER_MINUTES=0
GOOGLE_APPOINTMENT_SUMMARY_PREFIX=Llamada Asistto
GOOGLE_APPOINTMENT_LOCATION=
```

Aliases soportados:

- `WHATSAPP_API_TOKEN` en lugar de `WHATSAPP_ACCESS_TOKEN`.
- `VERIFY_TOKEN` en lugar de `WHATSAPP_VERIFY_TOKEN`.
- `WEBHOOK_DOMAIN` en lugar de `PUBLIC_BASE_URL`.

## Meta / WhatsApp

Problema ya resuelto:

- Los mensajes reales no llegaban al bot aunque la prueba de Meta si
  funcionaba.
- La causa era un `override_callback_uri` heredado apuntando a un webhook viejo
  de n8n/Chatwoot.
- Se corrigio desde Graph API Explorer actualizando `subscribed_apps` del WABA.

Validacion recomendada:

```text
GET /v25.0/{WABA_ID}/subscribed_apps
```

El webhook debe apuntar a:

```text
https://bot.humanio.digital/webhooks/whatsapp
```

## Configuracion Del Agente

El agente se configura por archivos versionados:

- `prompts/system.md`: identidad, objetivo, estilo, reglas y criterio comercial.
- `prompts/knowledge/*.md` o `*.txt`: base de conocimiento por temas.

El bot actual esta configurado para Asistto:

- Explica como funcionan chatbots de WhatsApp con IA.
- Responde casos de uso y beneficios.
- Recomienda paquetes:
  - Inicio: 47 USD/mes.
  - PRO: 97 USD/mes.
  - Premium: 149 USD/mes.
- Distingue entre `quiero automatizar agendar citas` y `quiero agendar una
  llamada con Asistto`.
- Evita tomar profesiones como nombres, por ejemplo `soy consultor de IA`.

Marcadores soportados:

- `[[ACTION_LINK]]`: marca el lead como calificado y se reemplaza por
  `QUALIFIED_CTA_URL` si existe.
- `[[DESCALIFICADO: motivo]]`: marca el lead como descalificado.
- `[[CALENDAR_EVENT: {...}]]`: marcador interno para crear citas en Google
  Calendar. No debe mostrarse al usuario.

## Agenda Y Cancelacion

Agenda:

- El backend crea eventos reales en Google Calendar cuando tiene nombre,
  objetivo y fecha/hora.
- Antes de crear, revisa si el horario esta ocupado.
- Las citas nuevas se guardan en Postgres en `calendar_appointments` con
  `google_event_id`.
- Ejemplos soportados:
  - `mañana a las 5`
  - `pasadomañana a las 9`
  - `el 11 a las 11`
  - `jueves 7 de mayo a las 10`
  - si un horario esta ocupado, `a las 10` reutiliza el dia anterior.
- Las confirmaciones de cita usan formato natural, por ejemplo
  `lunes 11 de mayo de 2026 a las 10:00`.

Cancelacion:

- El bot detecta frases como `no podré asistir`, `no puedo ir`, `cancela mi
  cita`, `la quiero cancelar`.
- Si hay una sola cita activa, borra el evento real de Google Calendar.
- Si hay varias citas activas, pide solo dia y hora.
- Debe mantener modo cancelacion en seguimientos como:
  - `esta de pasadomañana a las 9`
  - `la del jueves a las 9`
  - `jue 7 a las 8`
  - `la quiero cancelar`
- Para citas creadas antes de `calendar_appointments`, intenta buscar en Google
  Calendar por el WhatsApp guardado en la descripcion del evento.

## Endpoints Utiles

- `GET /health`: valida que la app este viva.
- `POST /reload`: recarga prompts sin redeploy; requiere `RELOAD_TOKEN`.
- `POST /maintenance/reset-contact`: limpia memoria de un contacto; requiere
  `RELOAD_TOKEN`.
- `GET /admin`: panel principal.
- `GET /admin/conversations`: conversaciones.
- `GET /admin/reset-contact`: UI para limpiar un contacto.
- `GET /admin/calendar-status`: diagnostico seguro de Google Calendar.
- `GET /admin/ai-status`: diagnostico seguro de IA/OpenRouter/OpenAI.

Importante: cambios de Python requieren redeploy completo desde GitHub/main.
`/reload` solo sirve para recargar prompts/conocimiento dentro del contenedor.

## Pruebas Recomendadas

Despues de cada redeploy:

```text
GET https://bot.humanio.digital/health
GET https://bot.humanio.digital/admin/ai-status
GET https://bot.humanio.digital/admin/calendar-status
```

Prueba de informacion:

```text
Hola
Quiero entender como funciona un chatbot de WhatsApp
Soy consultor de IA
Agendar citas
```

Prueba de agenda:

```text
Hola, quiero agendar una cita
Miguel Gonzalez
pasadomañana a las 9
gracias
```

Prueba de horario ocupado:

```text
quiero otra cita
Miguel Gonzalez
pasadomañana a las 9
a las 10
```

Prueba de cancelacion:

```text
quiero cancelar mi cita
esta de pasadomañana a las 9
```

## Siguiente Etapa Recomendada

1. Hacer mas pruebas reales de conversacion, agenda y cancelacion.
2. Afinar prompt y base de conocimiento de Asistto.
3. Agregar registros visibles en admin para citas creadas/canceladas.
4. Mejorar cancelacion cuando existan dos citas exactas a la misma hora.
5. Preparar panel creador de agentes multi-cliente:
   - `bots`
   - `bot_prompts`
   - `bot_knowledge`
   - `bot_skills`
   - `bot_integrations`
   - `bot_whatsapp_numbers`
   - `calendar_appointments`

La arquitectura futura debe enrutar por `phone_number_id` de Meta para que un
solo backend maneje muchos bots/clientes.

## Multi-Bot Studio

Design spec:
`docs/superpowers/specs/2026-05-05-multi-bot-studio-design.md`.

Phase 1 implementation plan:
`docs/superpowers/plans/2026-05-05-multi-bot-foundation.md`.

La primera fase de implementacion agrega clientes, bots, tablas base y
enrutamiento por `phone_number_id` sin cambiar el comportamiento publico de
Asistto. El bot actual queda como fallback usando las variables globales de
Easypanel.

Phase 2 agrega el primer Dashboard Multi-Bot:

- Login de agencia con `ADMIN_USER` / `ADMIN_PASSWORD`.
- Login de usuarios cliente desde Postgres.
- `/admin/clients` para crear clientes, bots y usuarios cliente.
- `/admin/bots` y `/admin/bots/{bot_id}` para operar bots.
- Usuarios cliente solo ven bots de su `client_id`.
- Las paginas actuales de conversaciones, dashboard y CRM se filtran por bot
  cuando entra un usuario cliente.

Phase 3A agrega configuracion editable del agente por bot:

- `/admin/bots/{bot_id}/prompt` publica el prompt activo en Postgres.
- `/admin/bots/{bot_id}/knowledge` crea y lista documentos de conocimiento.
- `/admin/bots/{bot_id}/knowledge/{knowledge_id}` edita o archiva documentos.
- El runtime usa prompt/conocimiento activo por `bot_id`; si un bot no tiene
  contenido propio, conserva el fallback de archivos versionados.
- La agencia y los usuarios `client_admin` pueden editar. `client_viewer` tiene
  acceso de solo lectura.

Phase 3D agrega runtime para APIs externas, webhooks y CRM:

- Nuevo modulo `app/external_actions.py`.
- El panel de habilidades ahora incluye:
  - `webhook`
  - `external_api`
  - `crm`
- Estas habilidades nacen apagadas por seguridad. Se deben activar en
  `/admin/bots/{bot_id}/skills`.
- Las llamadas se ejecutan solo si tambien existe una integracion activa del
  mismo tipo en `/admin/bots/{bot_id}/integrations`.
- Los secretos siguen cifrados en `integration_secrets`; nombres sugeridos:
  `access_token`, `api_key`, `bearer_token` o `token`.
- El modelo puede producir marcadores internos que se limpian antes de enviar
  la respuesta por WhatsApp:

```text
[[WEBHOOK_POST: {"payload": {"name": "Miguel", "phone": "521..."}}]]
[[EXTERNAL_API_REQUEST: {"method": "GET", "path": "/clientes", "params": {"phone": "521..."}}]]
[[EXTERNAL_API_REQUEST: {"method": "POST", "path": "/leads", "json": {"name": "Miguel"}}]]
[[CRM_LEAD: {"name": "Miguel", "phone": "521...", "status": "new", "notes": "Quiere una cita"}}]]
```

Configuracion sugerida para `external_api`:

```json
{
  "base_url": "https://api.example.com",
  "allowed_methods": ["GET", "POST"],
  "auth_header": "Authorization",
  "auth_scheme": "Bearer",
  "timeout_seconds": 20
}
```

Phase 3B agrega configuracion de integraciones por bot:

- `/admin/bots/{bot_id}/integrations` lista y crea integraciones.
- `/admin/bots/{bot_id}/integrations/{integration_id}` edita nombre, tipo,
  estado y config JSON no secreta.
- Cada integracion puede guardar secretos de escritura unica como `api_key`,
  `access_token` o `refresh_token`.
- Los secretos se cifran antes de guardarse en `integration_secrets` con
  `INTEGRATION_SECRET_KEY`; si no existe, se usa `SESSION_SECRET`.
- Esta fase deja configuradas las conexiones por cliente. La siguiente fase debe
  hacer que las habilidades consuman esas integraciones en runtime.

Phase 3C agrega runtime inicial de habilidades:

- `/admin/bots/{bot_id}/skills` permite activar/desactivar habilidades.
- La habilidad `google_calendar` controla agenda y cancelacion.
- Si el bot tiene una integracion activa `google_calendar`, Calendar usa esa
  configuracion y sus secretos cifrados.
- Secretos esperados para Google Calendar: `client_secret` y `refresh_token`.
  `client_id` puede ir en config JSON o como secreto `client_id`.
- Config JSON util: `calendar_id`, `timezone`, `duration_minutes`,
  `buffer_minutes`, `summary_prefix`, `location`.
- Si un bot no tiene integracion `google_calendar`, se conserva el fallback
  global de variables `GOOGLE_*` para Asistto.

## Prompt Para Continuar En Otra Computadora

Copia este prompt en una nueva sesion de Codex:

```text
Estoy continuando el proyecto `mangoex/chatbot-codex`, un bot de WhatsApp Cloud
API desplegado en Easypanel con FastAPI, Postgres, OpenRouter/OpenAI, Google
Calendar y panel admin.

Contexto importante:
- Repo: https://github.com/mangoex/chatbot-codex.git
- Rama fuente de verdad: main
- Dominio publico: https://bot.humanio.digital
- Webhook: https://bot.humanio.digital/webhooks/whatsapp
- Panel admin: https://bot.humanio.digital/admin
- Producto actual: Asistto, iniciativa de Humanio para chatbots de WhatsApp con
  IA que explican el servicio, capturan leads, recomiendan paquetes, agendan
  citas y cancelan citas en Google Calendar.
- Proveedor IA actual: OpenRouter con `OPENAI_BASE_URL=https://openrouter.ai/api/v1`.
- No imprimir ni commitear secretos. Las variables reales estan en Easypanel,
  Meta, OpenRouter y Google, no en GitHub.
- El problema anterior de Meta era un `override_callback_uri` viejo de
  n8n/Chatwoot. Ya fue corregido y WhatsApp real funciona.

Estado funcional:
- `prompts/system.md` y `prompts/knowledge/` ya estan personalizados para
  Asistto.
- Google Calendar ya crea citas reales.
- Las citas nuevas se guardan en Postgres en `calendar_appointments`.
- El bot ya maneja casos como `pasadomañana a las 9`, `gracias` despues de
  confirmar cita, cambios de hora como `a las 10`, y continuidad de cancelacion
  con frases como `esta de pasadomañana a las 9`, `la quiero cancelar` o
  `jue 7 a las 8`.

Primero lee:
- `README.md`
- `.env.example`
- `docs/HANDOFF.md`
- `docs/AGENT_INSTRUCTIONS.md`
- `prompts/system.md`
- `app/agenda_guard.py`
- `app/calendar_client.py`
- `app/db.py`

Tareas siguientes:
1. Verificar que GitHub/main este desplegado en Easypanel.
2. Probar en WhatsApp real: informacion, agenda, horario ocupado y cancelacion.
3. Si algo falla, revisar primero `/admin/ai-status`, `/admin/calendar-status`
   y las conversaciones en `/admin/conversations`.
4. Afinar prompt y base de conocimiento sin tocar secretos.
5. Preparar el futuro panel creador de agentes multi-cliente con bots,
   knowledge, skills, integraciones y enrutamiento por `phone_number_id`.
```
