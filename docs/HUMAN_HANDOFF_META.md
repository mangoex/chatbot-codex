# Relevo humano estricto por WhatsApp Business

La regla `escalate_when_agent_initiates` solo se activa mediante el webhook de
Meta con `field: smb_message_echoes` y `value.message_echoes[]`. Es el evento
de coexistencia que representa mensajes enviados desde WhatsApp Business o un
dispositivo vinculado; los eventos `statuses` (`sent`, `delivered`, `read`) no
identifican al autor y nunca activan el relevo.

## Configuración operativa

1. En Meta App Dashboard, suscribir el campo de webhook `smb_message_echoes`
   para el producto WhatsApp, además de los campos de mensajes requeridos por
   el bot. La suscripción de la app al WABA no confirma por sí sola que el
   campo esté habilitado: verificarlo en Dashboard y con un eco real
   sanitizado en los logs.
2. En Asistto, habilitar la skill `escalation` y la opción
   `escalate_when_agent_initiates` para el bot correspondiente. El control es
   aislado por `bot_id + wa_id`.
3. Cuando llega un echo válido, Asistto registra la escalación, cancela
   follow-ups y bloquea respuestas de IA, follow-ups y automatizaciones para
   ese contacto. Los reintentos del mismo `message_id` son idempotentes.
4. Antes de activar el relevo, Asistto comprueba si el eco es un comando de
   pausa o reanudación ya soportado, enviado por un propietario autorizado al
   número visible del mismo bot. Solo ese caso controla el estado global; una
   frase equivalente enviada a un cliente sigue siendo intervención humana.
5. La reanudación del relevo de una conversación es explícita: resolver la escalación o limpiar el relevo
   desde la acción administrativa autorizada. Un nuevo mensaje del cliente no
   reactiva al bot por sí mismo.

## Control recomendado en instalaciones multi-tenant

El control global del bot no debe depender del automensaje del número de negocio.
Cada cliente registra en el panel uno o más números administradores para su bot y
envía `Pausa` o `Sigue` desde uno de esos números al WhatsApp del bot. El webhook
estándar se resuelve por `phone_number_id` y la autorización se valida únicamente
contra el `bot_id` receptor. `ADMIN_PHONE_NUMBERS` queda reservado como acceso de
emergencia de la agencia y no sustituye la configuración por tenant.

## Diagnóstico seguro

El endpoint de diagnóstico WABA muestra la suscripción de la app y la URL de
callback configurada, pero no declara que `smb_message_echoes` esté activo si
Meta no entrega ese dato. Para confirmar la integración, usar una conversación
de prueba controlada y revisar el evento recibido sin registrar contenido ni
números completos en logs.
