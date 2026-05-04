# Asistto WhatsApp Agent

API propia para un chatbot de WhatsApp con agentes, pensada para desplegarse en Easypanel. Usa Meta WhatsApp Cloud API como canal, OpenRouter como proveedor de modelo y Postgres para conversaciones, mensajes, tenants y citas.

## Endpoints

- `GET /health`: estado del servicio para Easypanel.
- `GET /webhooks/whatsapp`: verificacion de webhook de Meta.
- `POST /webhooks/whatsapp`: recepcion de mensajes entrantes de WhatsApp.

## Variables

Copia `.env.example` como referencia y configura estas variables en Easypanel:

- `WHATSAPP_VERIFY_TOKEN`: token que tambien pondras en Meta al registrar el webhook.
- `WHATSAPP_ACCESS_TOKEN`: token de Meta WhatsApp Cloud API.
- `WHATSAPP_PHONE_NUMBER_ID`: id del numero de WhatsApp del primer cliente.
- `OPENROUTER_API_KEY`: llave de OpenRouter.
- `OPENROUTER_MODEL`: modelo que usara el agente.
- `DATABASE_URL`: conexion al Postgres del proyecto en Easypanel.

## Despliegue En Easypanel

1. Crea el proyecto `asistto-whatsapp-agent`.
2. Crea un servicio Postgres.
3. Crea un servicio App usando este repositorio o el Dockerfile.
4. Configura el dominio del servicio, por ejemplo `bot.tudominio.com`.
5. Agrega las variables de entorno.
6. En Meta Developers, registra el webhook:

```text
https://bot.tudominio.com/webhooks/whatsapp
```

7. Usa el mismo `WHATSAPP_VERIFY_TOKEN` en Meta y en Easypanel.
8. Suscribe el webhook al campo `messages` de WhatsApp Business Account.

## Desarrollo Local

```bash
npm install
npm run dev
```

Para compilar:

```bash
npm run build
```

Para pruebas:

```bash
npm test
```

## Comportamiento

- El webhook identifica el tenant por `phone_number_id`.
- Cada mensaje entrante se guarda con `wa_message_id` unico para evitar respuestas duplicadas.
- El agente responde en JSON estructurado.
- Las herramientas actuales soportan listar servicios, crear solicitud de cita y cancelar la cita activa mas reciente.
- La capa de citas ya esta aislada para conectar Google Calendar u otro calendario real despues.
