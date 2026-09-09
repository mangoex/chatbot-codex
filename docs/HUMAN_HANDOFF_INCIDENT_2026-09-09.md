# Silencio por intervención desde WhatsApp Business

## Evidencia en producción

- Bot revisado: Mobi Muebles, `bot_id=170`.
- Configuración persistida: escalado habilitado, `escalate_when_agent_initiates=true`, `handoff_expiration_hours=12`.
- `GET /{app_id}/subscriptions` respondió HTTP 200. La suscripción activa de `whatsapp_business_account` tenía únicamente `messages` y callback `https://bot.humanio.digital/webhooks/whatsapp`.
- Faltaba `smb_message_echoes`: el código no podía recibir la señal del mensaje humano desde WhatsApp Business.
- Se actualizó la suscripción existente conservando callback y campos previos, añadiendo `smb_message_echoes`. Meta respondió HTTP 200, `success=true`.
- Una segunda lectura confirmó ambos campos activos en v25.0. También se consultó el WABA del bot: HTTP 200 y app suscrita.
- No se enviaron mensajes a contactos ni se modificó su historial para simular una intervención.

## Correcciones locales adicionales

- Diagnóstico de la suscripción de la app, además de la suscripción del WABA. Diferencia entre campo verificado, ausente y comprobación no disponible.
- Coincidencia de destinatarios internacionales mexicanos `52`/`521`, conservando aislamiento por bot.
- Comprobación de vencimiento sin borrar un relevo que acaba de renovarse concurrentemente.
- Plazo configurado también para comprobaciones de medios y seguimientos que no pasan horas explícitas.
- Eliminación de la inferencia de autoría humana por historial `assistant`, que podía reiniciar una ventana vencida.
- Exclusión de eventos salientes de la ruta de mensajes de clientes.

## Validación y límite

- Cuatro regresiones reprodujeron fallos antes de corregir el código; quedaron pasando.
- Suite relacionada: 130 pruebas aprobadas, incluyendo plazo configurado y resolución manual.
- Documentación PBD actualizada y Master Prompt compilado/validado sin errores.
- La corrección de suscripción ya se aplicó en Meta y no requiere redeploy. Las correcciones de código y documentación se entregan en Git para redeploy por el propietario; la activación del evento en Meta ya está aplicada.
- Pendiente: evento real de un mensaje iniciado desde el celular y de una intervención sobre una conversación existente; comprobar el relevo y ausencia de respuesta automática tras contestar el contacto. La aceptación de la suscripción por Meta no sustituye esta prueba de extremo a extremo.
