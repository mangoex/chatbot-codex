# language: es
Característica: Equivalencia del ruteo unificado

  Escenario: KiwiPOS gana sobre Grok cuando ambos atienden inbound
    Dado un bot ficticio con KiwiPOS y Grok atendiendo inbound
    Cuando el cliente "5216672000002" escribe
    Entonces el legado y el camino nuevo eligen "external_agent"

  Escenario: Un administrador de la política va a Grok
    Dado una política ficticia con administrador "5216671000001" y default KiwiPOS
    Cuando el cliente "526671000001" escribe
    Entonces el legado y el camino nuevo eligen "grok_bot"
