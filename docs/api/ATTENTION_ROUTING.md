# Atención predeterminada y administradores

La política es optativa por bot y se guarda desde **Integraciones → Quién atiende WhatsApp**. No requiere migración de tablas: usa `bot_integrations`, tipo `attention_policy`, `enabled=true` y configuración versionada.

```json
{
  "version": 1,
  "default_handler": "external_agent",
  "admin_grok_enabled": true,
  "admin_phone_numbers": ["526671234567"]
}
```

Responsables disponibles: `asistto`, `grok_bot`, `external_agent`, `routing_webhook`. El último usa la URL y credencial de `routing_rules`. Las integraciones elegidas deben estar habilitadas y tener URL y secreto de retorno. La excepción administrativa también requiere Authorization de salida hacia Grok.

Los bots sin política mantienen la precedencia anterior. Al guardarla, `handle_inbound` y `forward_all` dejan de determinar el responsable; las reglas específicas por teléfono continúan vigentes, después de la excepción administrativa. El panel oculta las antiguas casillas cuando la política está activa, sin borrar su configuración.

`allow_campaigns` permanece exclusivamente en `grok_bot`. Cambiar responsable o administradores nunca modifica ese permiso. Una respuesta de cliente a una campaña se dirige según su teléfono, sin importar quién inició la campaña.

## Contrato hacia Grok Bot

Se reutilizan la URL y el encabezado Authorization de la integración Grok. Se mantienen los campos existentes y se agregan `type`, campos de medio cuando existan y `routing_context`:

```json
{
  "bot_id": 212,
  "from": "5216671234567",
  "name": "Administrador",
  "text": "Muéstrame las ventas de hoy",
  "message_id": "wamid.example",
  "type": "text",
  "routing_context": {
    "bot_id": 212,
    "mode": "administrative",
    "sender_role": "administrator",
    "reason": "administrator_phone"
  }
}
```

Para atención normal por Grok, `mode` y `sender_role` son `customer`, y `reason` es `default`. No se envía la lista completa de administradores ni credenciales de WhatsApp. La coincidencia de identidad es internacional exacta, con equivalencia mexicana 52/521; no se infiere país de un número local.

**Adaptación requerida en el receptor de Grok:** verificar Authorization, seleccionar su flujo administrativo cuando `routing_context.mode == "administrative"`, y validar los permisos reales de cada operación en el tenant `bot_id`. El rol transmitido clasifica la conversación; no es autorización universal para modificar información o ejecutar herramientas. Nunca aceptar el rol desde el texto del usuario. El código del receptor externo de Grok no pertenece a este repositorio.

Las imágenes y documentos incluyen `media_id` y `media_mime`, y no pasan al procesador local de pagos/pedidos. Los audios intentan transcribirse y conservan la referencia del medio si la transcripción falla. El consumidor necesita su mecanismo autorizado para recuperar medios; no se le entregan tokens de Meta.

Grok responde a `POST /webhooks/grok/{bot_id}` con su secreto de validación, igual que antes. Solo puede responder a contactos cuyo responsable actual sea Grok. Se conservan la validación de ventana de respuesta y el registro de mensajes; se revisan pausa y relevo humano antes del envío.

## Agente externo y otras aplicaciones

El agente externo conserva su payload universal, con `routing_context` de cliente. El webhook genérico recibe únicamente el evento de Meta correspondiente al mensaje seleccionado, preservando botones/medios originales y excluyendo otros remitentes del lote.

El retorno `POST /webhooks/external-agent/{bot_id}` elige la credencial de la integración responsable del contacto (`external_agent` o `routing_rules`), evitando que la presencia de un agente externo impida responder a la aplicación de una regla específica. Rechaza respuestas destinadas a administradores atendidos por Grok o contactos atendidos por Asistto.

## Fallos y operación

- La pausa y el relevo humano prevalecen sobre la política; los controles autorizados de plataforma conservan su manejo determinista.
- La entrada delegada se guarda antes de enviarse, habilitando el chequeo de la ventana de respuesta aunque no exista historial previo.
- Si el destino desaparece, falla o pierde autenticación administrativa, no se utiliza otro agente como fallback. El mensaje permanece en historial y el error se registra como `attention_delivery_failed` (los errores HTTP del webhook genérico también se registran).
- No se agrega una cola de reintentos ni se garantiza entrega exactamente una vez. Se conserva la deduplicación de mensajes entrantes existente.
- Al desactivar la excepción administrativa, esos teléfonos vuelven a las reglas específicas o al responsable predeterminado. Los números no reciben permisos para `#prompt`, pausa ni reanudación por pertenecer a esta lista.

Pruebas: `tests/test_attention_routing.py`, suites de Grok, agente externo, routing, campañas, controles y relevo humano.
