# Conexión segura de Chatwoot con Asistto

## Arquitectura

Meta conserva como webhook principal a Asistto. Chatwoot se conecta mediante una
bandeja de tipo API para mostrar el historial y permitir respuestas humanas.
No conectes el mismo número como bandeja nativa de WhatsApp en Chatwoot.

## Datos requeridos en Asistto

- URL base: dominio raíz HTTPS de Chatwoot, sin `/api/v1`.
- Account ID: ID numérico visible en la URL de la cuenta de Chatwoot.
- Inbox ID: ID de una bandeja de tipo API dedicada a Asistto.
- User API Token: token personal de un usuario con acceso a esa bandeja.
- Webhook Signing Secret: secreto generado por Chatwoot al crear el webhook.

Asistto nunca vuelve a mostrar los secretos guardados. Los asteriscos indican
que existe un valor cifrado y se conservan al volver a guardar.

## Configuración en Chatwoot

1. Abre `Configuración -> Integraciones -> Webhooks`.
2. Crea un webhook con la URL mostrada en la tarjeta de Asistto:

   ```text
   https://TU-DOMINIO/webhooks/chatwoot/BOT_ID
   ```

3. Suscribe solamente estos eventos:

   - `message_created`
   - `conversation_status_changed`

4. Copia el secreto de firma del webhook.
5. Pégalo en `Webhook Signing Secret` dentro de Asistto.
6. Guarda nuevamente hasta que el estado muestre `Conectado`.

## Comportamiento del relevo humano

- Los mensajes del cliente y las respuestas de la IA aparecen en Chatwoot.
- Los mensajes creados por Asistto están marcados para no regresar a WhatsApp
  como duplicados.
- Cuando un agente responde desde Chatwoot, Asistto envía esa respuesta a
  WhatsApp y silencia la IA solo para ese contacto.
- Al resolver la conversación en Chatwoot, Asistto reactiva la IA para el
  contacto y reinicia su historial conversacional.
- Las notas privadas no se envían a WhatsApp.

## Diagnóstico

- `Configuración incompleta`: falta token, secreto o verificación de la bandeja.
- Error de conexión: revisa URL, Account ID, Inbox ID, permisos y token.
- HTTP 401 en webhook: firma ausente, incorrecta o vencida.
- HTTP 403 en webhook: el evento pertenece a otra cuenta o bandeja.
- HTTP 502 en webhook: WhatsApp no aceptó la respuesta; el evento queda
  disponible para reintento.
