# Manual de Operación para el Cliente Final: Asistto by Humanio

Bienvenido a tu panel de **Asistto**. Este manual te guiará paso a paso para operar, personalizar y monitorear el asistente virtual de WhatsApp de tu negocio. 

El panel está diseñado para que gestiones tu chatbot de forma sencilla, sin necesidad de conocimientos técnicos o de programación.

---

## 1. Conceptos Clave

Antes de comenzar, es importante entender cómo trabaja Asistto para tu negocio:

* **El Asistente (Bot):** Es el agente de inteligencia artificial entrenado específicamente con los datos de tu empresa. Responde a tus clientes a través de WhatsApp.
* **El Prompt (Instrucciones):** Es el documento que define la "personalidad" del bot, cómo debe saludar, qué preguntas debe hacer y cómo comportarse.
* **La Base de Conocimiento:** Es el archivo de información de tu negocio (servicios, precios, políticas, horarios) que el bot consulta para responder preguntas específicas.
* **Cita Calificada (Lead):** Un cliente potencial que ha proporcionado sus datos y ha mostrado un interés real en tu servicio.
* **Escalación Humana:** Ocurre cuando el bot detecta que una persona necesita ayuda personalizada y detiene sus respuestas para que tú o tu equipo tomen el control.

---

## 2. Acceso al Panel de Control

Para ingresar a tu panel operativo:
1. Ve al dominio provisto por tu administrador (por ejemplo, `https://bot.humanio.digital/admin`).
2. Escribe tu correo electrónico y la contraseña temporal proporcionada por tu agencia.
3. Haz clic en **Ingresar**.

> [!TIP]
> Te recomendamos guardar esta página en tus marcadores de favoritos del navegador para acceder de forma rápida diariamente.

---

## 3. Explorando el Panel de Control

Una vez dentro, verás las siguientes secciones principales en el menú lateral:

### A. Dashboard (Métricas de Control)
Te da un resumen rápido del desempeño de tu asistente en tiempo real:
* **Conversaciones:** Número de chats únicos iniciados por clientes.
* **Mensajes:** Cantidad total de mensajes procesados por el bot.
* **Leads:** Prospectos que han interactuado.
* **Leads Calificados:** Clientes potenciales con intención de compra o cita agendada.
* **Escalaciones Pendientes:** Chats que requieren atención humana urgente.

### B. Conversaciones (`/conversations`)
Aquí puedes auditar y leer en tiempo real las conversaciones entre el bot y tus clientes:
* Los mensajes del cliente aparecen alineados a la izquierda y los del bot a la derecha.
* Si el bot está tardando en procesar una respuesta, verás el mensaje del cliente reflejado de inmediato en el panel para mantenerte al tanto.
* Puedes hacer clic en el botón de **"Seguimiento por WhatsApp"** para abrir directamente el chat en tu aplicación de WhatsApp Web y responder manualmente.

### C. CRM de Prospectos (Leads)
Toda la información de valor que recopila el bot se organiza en una tabla estructurada:
* **Nombre:** El nombre del cliente que el bot capturó de la conversación.
* **Negocio / Motivo:** Breve resumen de lo que el cliente necesita.
* **Estado:**
  * `En Progreso`: El cliente sigue chateando o respondiendo preguntas.
  * `Calificado`: El cliente ha completado el filtro, ha agendado una cita o ha solicitado formalmente ser contactado por un asesor.
  * `Descalificado`: Contacto que no encaja con tus servicios (con el motivo especificado).

### D. Bandeja de Escalaciones
Muestra a los clientes que han sido transferidos a atención humana. El bot clasifica la razón del traspaso automáticamente:
* *Por ejemplo:* Si el cliente dice que un producto le llegó roto, el bot detectará un "daño físico", creará un caso de escalación y dejará de responder para que tú resuelvas el caso directamente.

---

## 4. Cómo Entrenar y Personalizar tu Bot

No necesitas editar código para cambiar lo que el bot responde. Puedes moldear su comportamiento en dos apartados:

### A. Personalidad y Reglas (El Prompt)
Ruta: `Configuración > Prompt`

Aquí defines el tono de voz y las reglas que el asistente debe seguir de manera estricta.
* **Buenas Prácticas:**
  * Escribe reglas en formato directo (ej. *"Responde siempre de manera breve, máximo 3 líneas por mensaje"*).
  * Indica qué cosas **no** debe hacer (ej. *"Nunca des precios de tratamientos complejos sin una cita previa"*).
  * Di qué información debe capturar antes de agendar (ej. *"Pide el nombre de la persona y el motivo de su cita"*).
* **Asistente con IA:**
  * Del lado derecho del editor de prompts verás un cuadro de ayuda con Inteligencia Artificial.
  * Puedes escribir una instrucción informal (ej. *"Haz que el bot hable de manera más amigable y use emojis"*).
  * Haz clic en **Generar** y la IA te propondrá un prompt mejorado que podrás aplicar con un clic.
  * Recuerda hacer clic en **Publicar** para que los cambios se guarden en el número de WhatsApp.

### B. Cargar Base de Conocimiento (Knowledge Base)
Ruta: `Configuración > Base de conocimiento`

Es la memoria de datos de tu negocio. Puedes crear varios documentos para segmentar la información:
* **Ejemplos de documentos a crear:**
  * `Horarios y Sucursales`: Direcciones exactas, ligas a Google Maps y horarios de atención al público.
  * `Precios y Paquetes`: Precios base de tus servicios o productos comunes.
  * `FAQs (Preguntas Frecuentes)`: Respuestas a dudas repetitivas (ej. *"¿Tienen estacionamiento?"*, *"¿Aceptan tarjeta de crédito?"*).

> [!IMPORTANT]
> El bot tiene prohibido inventar información que no exista en tu prompt o base de conocimiento. Si un cliente le pregunta algo que no subiste al panel, el bot dirá amablemente que no cuenta con esa información y ofrecerá pasarlo con un asesor humano. ¡Mantén tu base de conocimiento actualizada!

---

## 5. Integración con Google Calendar (Agenda Automática)

Si tu bot tiene activada la habilidad de agenda, se sincronizará de forma transparente con tu cuenta de Google Calendar:

### ¿Cómo agenda el bot una cita?
1. El cliente le indica al bot por WhatsApp que quiere agendar una cita.
2. El bot inicia el flujo de captura y le solicitará:
   * **Nombre completo.**
   * **Motivo o tema de la cita.**
   * **Día y hora deseada.**
3. El bot consulta en tiempo real tu Google Calendar. Si detecta que ese horario ya está ocupado (o está dentro de tus horas bloqueadas), le dirá al cliente: *"Ese horario está ocupado. ¿Qué te parece a las 11:00 AM o prefieres otro día?"*.
4. Si el horario está libre, **el bot creará el evento directamente en tu Google Calendar** en segundos y le enviará la confirmación al cliente por WhatsApp.

### ¿Cómo cancela o reagenda el bot una cita?
* **Cancelación:** Si el cliente escribe por WhatsApp *"Cancela mi cita"*, el bot buscará el evento correspondiente al número de teléfono en tu calendario, **borrará el evento de Google Calendar** y confirmará la cancelación.
* **Reagendar:** Si el cliente escribe *"Ya no podré asistir a las 10, mejor muévela a las 12"*, el bot borrará la cita anterior y registrará el nuevo horario automáticamente si está disponible.

---

## 6. Consejos Operativos para el Éxito de tu Bot

1. **Evita la ambigüedad:** Si cambias un precio en tu sucursal, actualízalo de inmediato en la Base de Conocimiento del panel.
2. **Revisa la bandeja diariamente:** Entra al menos una vez al día a la pestaña `/conversations` para auditar cómo está respondiendo el bot y detectar dudas de tus clientes que aún no tengas documentadas.
3. **Optimiza el Prompt periódicamente:** Si notas que el bot repite mucho una frase que no te agrada, agrega una regla negativa en su prompt (ej. *"No uses la palabra X para responder"*).
4. **Respeta las políticas de Meta:** Recuerda que WhatsApp prohíbe el envío masivo de spam o el uso de lenguajes inapropiados. Mantén tus flujos limpios y amigables.
