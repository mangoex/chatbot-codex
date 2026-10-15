# Especificación SBD: Integración Universal con Agentes Externos (POS / Bots de Terceros)

**ID:** SPEC-EXT-AGENT-001  
**Estado:** Aprobado  
**Nivel de Riesgo:** R2 (Producción Estándar)  
**Autor:** Director Técnico (Metodología Humanio CEO & SBD)  

---

## 1. Contexto & Propósito de Negocio

### 1.1 Problema
Los negocios (ej. restaurantes con sistemas POS como KiwiPOS / RestaurantOS, plataformas de e-commerce o agentes conversacionales en n8n/Flowise) cuentan con sus propios bots especializados capaces de procesar lógica transaccional compleja (ej. levantar pedidos y enviarlos directamente a la comanda o terminal punto de venta). 

Actualmente, si un bot de este tipo se conecta a WhatsApp a través de Asistto, se requiere triangular o usar la integración específica de "Grok Bot", lo cual resulta conceptualmente confuso, limita a un solo proveedor y no ofrece una abstracción estandarizada para cualquier backend o POS.

### 1.2 Objetivo
Proveer una integración nativa y universal denominada **"Agente Externo (POS / Bot Personalizado)"** (`external_agent`), que permita:
1. Reenviar de forma transparente los mensajes entrantes de WhatsApp desde Asistto hacia el Webhook del sistema externo.
2. Silenciar la IA interna de Asistto cuando el agente externo tiene delegada la conversación (`handle_inbound=True`), evitando respuestas duplicadas o inconsistencias transaccionales.
3. Exponer un endpoint de retorno seguro (`/webhooks/external-agent/{bot_id}`) en Asistto donde el sistema externo despache las respuestas y confirmaciones de pedidos hacia Meta WhatsApp Cloud API.
4. Soporte para múltiples esquemas de payload (JSON plano y formato Meta WhatsApp Cloud API).
5. Mantener la estricta política de seguridad: secretos cifrados con `secure_store`, validación `hmac.compare_digest` en tiempo constante y verificación de la ventana de 24 horas antes de cada despacho saliente.

---

## 2. Contratos de Interfaz (API & Webhooks)

### 2.1 Reenvío Entrante (Asistto -> Sistema Externo / POS)
- **Método:** `POST`
- **URL Destino:** Configurada en el campo `webhook_url` de la integración.
- **Encabezados Criptográficos y de Autorización:**
  - `Content-Type: application/json`
  - `Accept: application/json`
  - `X-Hub-Signature-256: sha256=<hmac_sha256_hex>` (Firma criptográfica HMAC-SHA256 del cuerpo exacto de la petición usando el Webhook Secret de Entrada. Requerido por KiwiPOS / RestaurantOS).
  - `X-Hub-Signature: sha1=<hmac_sha1_hex>`
  - `Authorization: Bearer <secret>`
  - `X-Webhook-Secret: <secret>`
  - `X-Asistto-Secret-Token: <secret>`
- **Payload Universal Dual (Estructura Meta Cloud API + Campos Planos):**
  ```json
  {
    "object": "whatsapp_business_account",
    "entry": [
      {
        "id": "147",
        "changes": [
          {
            "field": "messages",
            "value": {
              "messaging_product": "whatsapp",
              "metadata": {
                "display_phone_number": "5215500000000",
                "phone_number_id": "phone-147"
              },
              "contacts": [
                {
                  "profile": {
                    "name": "Cliente Nombre"
                  },
                  "wa_id": "523312345678"
                }
              ],
              "messages": [
                {
                  "from": "523312345678",
                  "id": "wamid.HBgNNTIzMzEyMzQ1Njc4FQIAEhgg...",
                  "timestamp": "1710000000",
                  "type": "text",
                  "text": {
                    "body": "Quiero ordenar una hamburguesa con papas"
                  }
                }
              ]
            }
          }
        ]
      }
    ],
    "bot_id": 147,
    "from": "523312345678",
    "wa_id": "523312345678",
    "name": "Cliente Nombre",
    "text": "Quiero ordenar una hamburguesa con papas",
    "message_id": "wamid.HBgNNTIzMzEyMzQ1Njc4FQIAEhgg...",
    "timestamp": "1710000000",
    "type": "text"
  }
  ```
  *Nota: Si el cliente envía una nota de voz / audio, Asistto la transcribe automáticamente con Whisper antes de delegar el payload al Agente Externo, permitiendo procesar pedidos por voz sin fricción.*

### 2.2 Despacho Saliente (Sistema Externo / POS -> Asistto)
- **Método:** `POST`
- **Endpoint:** `/webhooks/external-agent/{bot_id}` (o `/webhooks/external-agent`)
- **Autenticación Soportada:**
  - Encabezado `X-Hub-Signature-256: sha256=<hmac>` (Firma criptográfica HMAC)
  - `Authorization: Bearer <webhook_secret>`
  - Encabezados `X-Webhook-Secret: <webhook_secret>` / `X-API-Key: <webhook_secret>`
  - Resolución dual: Se valida contra `webhook_secret` o `auth_header`.
- **Payloads Soportados:**
  
  *Opción A (JSON Plano):*
  ```json
  {
    "to": "523312345678",
    "text": "¡Tu pedido #1042 ha sido recibido y está en preparación!"
  }
  ```
  *(Alias aceptados para destinatario: `to`, `from`, `wa_id`, `recipient_id`, `phone_number`)*  
  *(Alias aceptados para mensaje: `text`, `message`, `response`, `content`, `body`)*

  *Opción B (Formato Meta Cloud API):*
  ```json
  {
    "messaging_product": "whatsapp",
    "to": "523312345678",
    "type": "text",
    "text": {
      "body": "¡Tu pedido #1042 ha sido recibido y está en preparación!"
    }
  }
  ```
  *(También soporta formatos interactivos con botones y plantillas).*

---

## 3. Criterios de Aceptación Gherkin

### Escenario 1: Reenvío de mensaje entrante y silencio de IA local
```gherkin
Given un bot con la integración "external_agent" activa
  And con "handle_inbound" en True
  And con la URL de webhook "https://pos.ejemplo.com/webhook"
When llega un mensaje de WhatsApp del cliente "523312345678" con texto "Pedir pizza"
Then Asistto reenvía el payload JSON al webhook del sistema externo
  And incluye el encabezado de autorización configurado
  And Asistto NO invoca su modelo local de IA ni envía respuestas directas
  And el mensaje del usuario se almacena en el historial de conversaciones
```

### Escenario 2: Despacho saliente dentro de la ventana de 24 horas
```gherkin
Given un bot con la integración "external_agent" activa
  And con un "webhook_secret" configurado
  And el cliente "523312345678" envió un mensaje hace menos de 24 horas
When el sistema externo realiza un POST a "/webhooks/external-agent/{bot_id}"
  And envía el token correcto en "Authorization: Bearer <secret>"
  And envía el destinatario "523312345678" y el texto de respuesta
Then Asistto valida la autenticación exitosamente
  And Asistto envía el mensaje a WhatsApp vía Meta Cloud API
  And guarda la respuesta en el historial con rol "assistant"
  And responde con HTTP 200 {"status": "sent"}
```

### Escenario 3: Rechazo por secreto inválido o ausente
```gherkin
Given un bot con la integración "external_agent" activa
When se recibe un POST en "/webhooks/external-agent/{bot_id}" con un secreto incorrecto o nulo
Then Asistto rechaza la petición con HTTP 401 Unauthorized
  And ningún mensaje es enviado a WhatsApp
```

### Escenario 4: Rechazo por expiración de ventana de 24 horas
```gherkin
Given un bot con la integración "external_agent" activa
  And el cliente no ha interactuado en más de 24 horas
When el sistema externo intenta responder con texto libre
Then Asistto bloquea el envío para evitar penalizaciones de Meta
  And devuelve {"status": "window_expired", "detail": "..."}
  And no se despacha el mensaje a Meta
```

### Escenario 5: Preservación de credenciales enmascaradas en UI
```gherkin
Given una integración "external_agent" existente con secretos guardados
When el usuario guarda el formulario en el panel enviando "********" en los secretos
Then Asistto NO sobrescribe los secretos con asteriscos
  And mantiene cifrados los valores originales previamente configurados
```
