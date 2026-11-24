# language: es
Característica: Webhook de WhatsApp Cloud API
  El handshake y la recepción de eventos son el contrato que Meta ya tiene
  configurado en los bots en producción. Estos escenarios fijan ese
  comportamiento. Los tokens y los eventos son ficticios.

  Escenario: Meta verifica el webhook con el token correcto
    Dado el token de verificación "token-ficticio-webhook"
    Cuando Meta consulta el webhook con el reto "reto-ficticio-123"
    Entonces el estado HTTP es 200
    Y el cuerpo de texto es "reto-ficticio-123"

  Escenario: Meta rechaza un token de verificación distinto
    Dado el token de verificación "token-ficticio-webhook"
    Cuando Meta consulta el webhook con el token "otro-token" y el reto "reto-ficticio-123"
    Entonces el estado HTTP es 403

  Escenario: Un POST sin secreto de aplicación se acepta
    Dado que META_APP_SECRET no está configurado
    Cuando Meta entrega un evento de mensajes vacío
    Entonces el estado HTTP es 200
    Y el JSON incluye status "received"

  Escenario: Un POST con firma válida se acepta
    Dado el secreto de aplicación "secreto-ficticio-meta"
    Cuando Meta entrega un evento de mensajes vacío con firma válida
    Entonces el estado HTTP es 200
    Y el JSON incluye status "received"

  Escenario: Un POST con firma inválida se rechaza
    Dado el secreto de aplicación "secreto-ficticio-meta"
    Cuando Meta entrega un evento de mensajes vacío con la firma "sha256=0000000000000000000000000000000000000000000000000000000000000000"
    Entonces el estado HTTP es 403
