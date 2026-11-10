# language: es
Característica: Ruteo unificado fase 1

  Escenario: El flag apagado no cambia al responsable
    Dado un bot ficticio con agente externo y Grok, y ROUTING_V2 apagado
    Cuando escribe un cliente
    Entonces el camino legado elige al agente externo
    Y el camino nuevo, traducido de esa misma configuración, elige al agente externo

  Escenario: Un administrador gana sobre el default y sobre el relevo
    Dado una política con administradores hacia Grok y default KiwiPOS
    Y una conversación tomada por KiwiPOS
    Cuando escribe un administrador de ese bot
    Entonces lo atiende Grok

  Escenario: El externo devuelve la conversación
    Dado una conversación tomada por una conexión
    Cuando esa conexión la devuelve
    Entonces el atendiente vuelve a ser Asistto

  Escenario: El retorno nuevo no acepta el secreto en la URL
    Dado un bot con ROUTING_V2 encendido
    Cuando llaman a "/api/v1/bots/1/reply" con el secreto en la query
    Entonces la respuesta es 400
