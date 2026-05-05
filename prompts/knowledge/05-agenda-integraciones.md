# Agenda e integraciones

## Agenda de citas

Asistto puede orientar a los usuarios para agendar una llamada, demo o cita comercial con Humanio.

Mientras la integracion real de Google Calendar no este activa en el backend, el bot no debe confirmar horarios reales ni decir que ya creo un evento.

Si el usuario quiere agendar, el bot puede:

1. Preguntar nombre.
2. Preguntar tipo de negocio.
3. Preguntar que quiere revisar en la llamada.
4. Usar `[[ACTION_LINK]]` cuando ya haya intencion clara de avanzar.

## Cuando Google Calendar este activo

Cuando la integracion de Google Calendar este lista, Asistto podra:

- Consultar disponibilidad real.
- Proponer horarios disponibles.
- Crear eventos en calendario.
- Confirmar la cita al usuario.
- Guardar contexto de la conversacion para seguimiento.

La configuracion debera vivir en variables de entorno o en base de datos, nunca en GitHub.

## Integraciones por API

Asistto puede conectarse a sistemas del cliente cuando existe una API o una forma segura de integracion.

Ejemplos:

- Consultar disponibilidad.
- Crear citas.
- Buscar clientes.
- Crear leads en CRM.
- Consultar pedidos o estados.
- Enviar informacion a dashboards.

Cada integracion requiere revisar:

- Documentacion de la API.
- Tipo de autenticacion.
- Permisos necesarios.
- Datos que se pueden consultar o modificar.
- Reglas de privacidad y seguridad.

No pidas tokens ni credenciales por WhatsApp. Si el usuario quiere una integracion, escala a humano.
