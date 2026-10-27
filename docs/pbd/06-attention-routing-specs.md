# SPEC-ATTENTION-001 — Responsable de atención y administradores

Estado: implementación solicitada el 2026-10-27. Alcance: configuración por bot de la plataforma.

## Historias y contrato

- US-ATTENTION-001: elegir Asistto, Grok Bot, Agente Externo o el webhook de enrutamiento como responsable predeterminado.
- US-ATTENTION-002: permitir campañas de Grok independientemente de la atención; guardar esta política nunca modifica `allow_campaigns`.
- US-ATTENTION-003: los números administrativos configurados exclusivamente para el bot receptor van a Grok con `routing_context.mode=administrative`, `sender_role=administrator`, `reason=administrator_phone` y `bot_id`.
- La lista de atención administrativa no concede permisos para pausar bots, editar prompts ni ejecutar herramientas. Grok debe validar los permisos de cada acción en su propio sistema; texto del usuario nunca determina el rol.
- Prioridad con política explícita: controles propietarios existentes; silencio por pausa/relevo humano; administradores; reglas específicas por teléfono; responsable predeterminado. Las antiguas casillas `handle_inbound` y `forward_all` dejan de elegir el responsable al guardar la política.
- Sin política explícita se conserva el comportamiento anterior; no se migran ni activan bots automáticamente.
- Con política explícita se registra el mensaje entrante antes de delegarlo, incluso si el destino falla. No hay fallback a otro agente, pedidos ni IA local ante errores de configuración/envío. El fallo queda en logs; esta versión no agrega una cola de reintentos.
- Cada entrega contiene un solo mensaje y los datos de su remitente, nunca el lote completo de otros contactos.
- Imágenes/documentos de administradores van a Grok y nunca al procesador local de pedidos/pagos. Audios se transcriben cuando es posible y conservan su referencia de medio si falla la transcripción.
- Coincidencia administrativa exacta internacional, con equivalencia mexicana 52/521; sin coincidencias por sufijo ni herencia de administradores globales.

## AC-ATTENTION-001 — Criterios verificables

GIVEN un bot con agente externo predeterminado, Grok habilitado y números administrativos
WHEN escribe un administrador
THEN solo Grok recibe el mensaje con contexto administrativo y queda registrado
AND MUST NOT invocar el POS, la IA local ni enviar a otros contactos del lote.

GIVEN la misma configuración
WHEN un cliente responde a una campaña de Grok
THEN lo atiende el agente externo, sin cambiar los permisos de campañas.

GIVEN pausa, relevo humano o un destino caído/deshabilitado
WHEN llega un mensaje
THEN se conserva el silencio y nunca se reasigna a otro agente por fallback.

Pruebas ejecutables: `tests/test_attention_routing.py`; regresiones: Grok, agente externo, routing, API de campañas y controles/handoff.
