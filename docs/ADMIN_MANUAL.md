# Manual del Administrador

Este manual explica como operar el panel de administracion del chatbot de
WhatsApp: alta de clientes, usuarios, bots, prompt, base de conocimiento,
conversaciones, CRM y diagnosticos.

Dominio de produccion actual:

```text
https://bot.humanio.digital
```

Panel:

```text
https://bot.humanio.digital/admin
```

## 1. Roles de acceso

### Agencia

La agencia administra toda la instalacion. Entra con las variables de entorno:

```text
ADMIN_USER
ADMIN_PASSWORD
```

Puede:

- Ver todos los clientes.
- Crear clientes.
- Crear bots.
- Crear usuarios para clientes.
- Editar prompt y base de conocimiento de cualquier bot.
- Ver conversaciones, CRM, escalaciones y diagnosticos.

### Cliente admin

Es un usuario creado desde el panel para un cliente especifico.

Puede:

- Entrar al panel.
- Ver solo los bots de su cliente.
- Ver conversaciones y CRM de sus bots.
- Editar prompt y base de conocimiento de sus bots.

### Cliente viewer

Es un usuario de solo lectura para un cliente.

Puede:

- Ver dashboard, conversaciones y CRM de su cliente.
- Ver configuracion del bot.

No puede:

- Crear clientes.
- Crear bots.
- Editar prompt.
- Editar base de conocimiento.

## 2. Mapa de navegacion

```text
/admin
  -> /admin/login
  -> /admin/dashboard
  -> /admin/clients
      -> /admin/clients/{client_id}
          -> crear bot
          -> crear usuario cliente
  -> /admin/bots
      -> /admin/bots/{bot_id}
          -> /admin/bots/{bot_id}/prompt
          -> /admin/bots/{bot_id}/knowledge
              -> /admin/bots/{bot_id}/knowledge/{knowledge_id}
  -> /admin/conversations
  -> /admin/crm
  -> /admin/escalations
  -> /admin/ai-status
  -> /admin/calendar-status
  -> /admin/reset-contact
```

## 3. Entrar al panel

Abre:

```text
https://bot.humanio.digital/admin/login
```

Si eres agencia, usa `ADMIN_USER` y `ADMIN_PASSWORD`.

Si eres cliente, usa el email y contrasena creados desde:

```text
/admin/clients/{client_id}
```

## 4. Crear un cliente

Solo la agencia puede crear clientes.

1. Entra a:

```text
/admin/clients
```

2. En el formulario **Crear cliente**, llena:

```text
Nombre: Clinica Demo
Slug: clinica-demo
```

3. Guarda.

El cliente queda disponible en:

```text
/admin/clients/{client_id}
```

Recomendacion:

- Usa slugs cortos, sin espacios, en minusculas.
- Ejemplo: `clinica-sonrisa`, `hotel-centro`, `asistto-demo`.

## 5. Crear usuarios para un cliente

Entra al detalle del cliente:

```text
/admin/clients/{client_id}
```

En **Crear usuario cliente**, llena:

```text
Email: admin@cliente.com
Nombre: Admin Cliente
Contrasena temporal: una-contrasena-segura
Rol: Admin cliente
```

Roles disponibles:

- `client_admin`: puede editar prompt y conocimiento.
- `client_viewer`: solo lectura.

Importante:

- La contrasena temporal debe compartirse por un canal seguro.
- En esta version no hay pantalla de cambio de contrasena para el cliente.

## 6. Crear un bot

Entra al cliente:

```text
/admin/clients/{client_id}
```

En **Crear bot**, llena:

```text
Nombre del bot: Bot Clinica Demo
Slug: bot-clinica-demo
Phone Number ID: ID del numero en Meta WhatsApp
Numero visible: +52...
```

El `Phone Number ID` debe venir de Meta WhatsApp Cloud API. No es el numero de
telefono visible, sino el identificador tecnico del numero.

Cuando guardas, el bot queda disponible en:

```text
/admin/bots/{bot_id}
```

Nota operativa:

- En esta version el bot puede registrar su `phone_number_id` desde el panel.
- El token global de WhatsApp sigue viniendo de variables de entorno.
- La configuracion de tokens/API por cliente sera parte de la siguiente fase de
  integraciones.

## 7. Ver el detalle del bot

Entra a:

```text
/admin/bots/{bot_id}
```

Aqui ves:

- Cliente propietario.
- `phone_number_id`.
- Estado del bot.
- Total de conversaciones.
- Total de mensajes.
- Leads.
- Leads calificados.
- Accesos a prompt y base de conocimiento.

Desde aqui puedes abrir:

```text
/admin/bots/{bot_id}/prompt
/admin/bots/{bot_id}/knowledge
```

## 8. Configurar el prompt del bot

Entra a:

```text
/admin/bots/{bot_id}/prompt
```

El prompt define:

- Identidad del agente.
- Tono de voz.
- Reglas comerciales.
- Que debe preguntar.
- Que debe evitar.
- Como debe agendar.
- Cuando debe escalar.

Ejemplo base:

```text
Eres el asistente de WhatsApp de Clinica Demo.
Tu objetivo es resolver dudas, calificar interesados y agendar citas.

Reglas:
- Responde breve, claro y amable.
- No inventes precios.
- Si el usuario quiere una cita, pide nombre, motivo, dia y hora.
- Si pregunta por servicios, responde solo con la informacion de la base de conocimiento.
- Si no sabes algo, ofrece pasar el caso a una persona.
```

Al guardar, el prompt se publica en Postgres y se usa de inmediato en nuevas
respuestas de WhatsApp. No requiere redeploy.

Si un bot no tiene prompt propio, usa el fallback versionado en:

```text
prompts/system.md
```

## 9. Configurar base de conocimiento

Entra a:

```text
/admin/bots/{bot_id}/knowledge
```

La base de conocimiento son documentos que el agente usa junto con el prompt.

Puedes crear documentos como:

- Servicios
- Precios
- Preguntas frecuentes
- Politicas
- Horarios
- Sucursales
- Reglas de agenda
- Objeciones frecuentes

Ejemplo:

```text
Titulo: Servicios

Contenido:
La clinica ofrece limpieza dental, blanqueamiento, ortodoncia e implantes.
El horario de atencion es lunes a viernes de 9:00 a 18:00.
Para precios exactos, el agente debe ofrecer una llamada o cita de valoracion.
```

Cada documento puede editarse desde:

```text
/admin/bots/{bot_id}/knowledge/{knowledge_id}
```

Tambien puede archivarse. Los documentos archivados no se usan en el runtime del
bot.

## 10. Probar que el prompt y conocimiento funcionan

Despues de editar prompt o knowledge:

1. Envia un mensaje real por WhatsApp al numero conectado.
2. Revisa la conversacion en:

```text
/admin/conversations?bot_id={bot_id}
```

3. Haz preguntas que dependan del documento creado.

Ejemplo:

```text
Que servicios ofrecen?
```

Luego:

```text
Quiero agendar una cita para limpieza dental
```

Si la respuesta usa la informacion nueva, la configuracion quedo activa.

## 11. Conversaciones

Ruta:

```text
/admin/conversations
```

Con bot especifico:

```text
/admin/conversations?bot_id={bot_id}
```

Sirve para:

- Ver historial real de WhatsApp.
- Confirmar si llegaron mensajes.
- Revisar respuestas del bot.
- Abrir el contacto en WhatsApp.

Si una prueba de Meta funciona pero WhatsApp real no aparece aqui, revisar:

- Webhook suscrito a `messages`.
- `subscribed_apps` del WABA.
- `override_callback_uri` heredado de n8n/Chatwoot.
- `WHATSAPP_PHONE_NUMBER_ID`.
- Logs de Easypanel.

## 12. CRM

Ruta:

```text
/admin/crm
```

Permite ver leads por estado:

- `en_progreso`
- `calificado`
- `descalificado`
- `todos`

Tambien permite cambiar estado manualmente.

## 13. Escalaciones

Ruta:

```text
/admin/escalations
```

Sirve para revisar casos que deben pasar a humano, por ejemplo:

- Solicitudes urgentes.
- Quejas.
- Problemas con pedido o servicio.
- Casos con media o informacion incompleta.

Detalle:

```text
/admin/escalations/{eid}
```

Desde el detalle puedes cambiar estado y agregar notas.

## 14. Diagnosticos

### Estado de IA

```text
/admin/ai-status
```

Verifica:

- API key configurada.
- Proveedor IA.
- Modelo.
- Respuesta de prueba del modelo.

### Estado de Google Calendar

```text
/admin/calendar-status
```

Verifica si la agenda esta configurada y si el backend puede consultar Calendar.

### Reset de contacto

```text
/admin/reset-contact
```

Sirve para borrar historial/estado de uno o varios contactos de prueba.

Usalo cuando quieras repetir una prueba desde cero.

## 15. Checklist para alta de un cliente

```text
[ ] Crear cliente
[ ] Crear usuario client_admin
[ ] Crear bot
[ ] Registrar Phone Number ID
[ ] Configurar webhook de Meta si es un numero nuevo
[ ] Configurar prompt del bot
[ ] Cargar base de conocimiento
[ ] Probar mensaje real de WhatsApp
[ ] Confirmar conversacion en admin
[ ] Probar una pregunta de conocimiento
[ ] Probar una agenda o accion principal
[ ] Revisar AI status y Calendar status
```

## 16. Checklist de configuracion del bot

```text
[ ] Nombre claro
[ ] Slug unico
[ ] Phone Number ID correcto
[ ] Prompt publicado
[ ] Knowledge activo
[ ] Tono validado por el cliente
[ ] Reglas de agenda claras
[ ] Frases de escalacion claras
[ ] Prueba real completada
```

## 17. Prompts visuales para gpt-image-2

Usa estos prompts para crear laminas visuales del manual con `gpt-image-2`.

### Lamina 1: Mapa general del admin

```text
Create a clean SaaS admin manual infographic in Spanish for a WhatsApp chatbot
platform. Show a navigation map with these nodes: Login, Dashboard, Clientes,
Bots, Prompt, Base de conocimiento, Conversaciones, CRM, Escalaciones,
Diagnosticos. Use a calm professional interface style, white background,
dark text, green accent, flat UI cards, no fictional screenshots, no logos.
Readable Spanish labels, 16:9.
```

### Lamina 2: Alta de cliente

```text
Create a Spanish step-by-step admin guide illustration for creating a client in
a WhatsApp chatbot platform. Steps: Entrar como agencia, Crear cliente, Crear
usuario client_admin, Crear bot, Configurar prompt, Cargar conocimiento,
Probar en WhatsApp. Professional SaaS style, simple numbered flow, green accent,
white background, 16:9, readable labels.
```

### Lamina 3: Configuracion del bot

```text
Create a Spanish visual checklist for configuring a WhatsApp AI bot. Include:
Nombre del bot, Phone Number ID, Prompt, Base de conocimiento, Prueba de
WhatsApp, Conversaciones, CRM. Use clean UI components, subtle icons, green and
black accent, no brand logos, 16:9.
```

### Lamina 4: Roles y permisos

```text
Create a Spanish permissions matrix infographic for a WhatsApp chatbot admin
panel. Columns: Agencia, Cliente admin, Cliente viewer. Rows: Crear clientes,
Crear bots, Editar prompt, Editar conocimiento, Ver conversaciones, Ver CRM.
Use checkmarks and lock icons, professional SaaS dashboard style, white
background, green accent, 16:9.
```

### Lamina 5: Operacion diaria

```text
Create a Spanish daily operations infographic for a WhatsApp AI chatbot admin.
Show: revisar conversaciones, revisar CRM, atender escalaciones, probar IA,
probar calendario, ajustar prompt/conocimiento. Clean workflow diagram, modern
admin UI style, readable labels, green accent, 16:9.
```

## 18. Que falta para produccion multi-cliente avanzada

La base actual ya permite clientes, usuarios, bots, prompt y conocimiento por
bot.

Siguientes fases recomendadas:

- Configurar tokens/API por bot o cliente.
- Panel de integraciones por bot.
- Google Calendar por cliente.
- Webhooks/API externa por cliente.
- Plantillas de bots por industria.
- Auditoria de cambios en prompt y knowledge.
- Cambio de contrasena para usuarios cliente.
- Exportacion de conversaciones/leads.

