# PBD Specification: Feature `#prompt` por WhatsApp (Riesgo R2)

## 1. Visión y Propósito
Permitir a los administradores autorizados de un bot actualizar el prompt maestro directamente mediante mensajes de WhatsApp usando el comando `#prompt <instrucción>`. Esta funcionalidad otorga agilidad operativa en campo manteniendo los guardrails de seguridad: revisión asistida (`prompt_changes.assist_changes`), confirmación humana explícita en dos pasos y ventana de expiración (TTL de 30 minutos).

---

## 2. Criterios de Aceptación en Formato Gherkin (SBD)

### Característica: Detección y Extracción de Comandos
```gherkin
Característica: Detección y extracción del comando #prompt
  Como administrador del bot
  Quiero enviar instrucciones usando el prefijo #prompt
  Para solicitar modificaciones al comportamiento o reglas del bot

  Escenario: Extracción de instrucción estándar
    Dado un mensaje "  #prompt Cambiar horario a lunes a viernes de 9 a 18  "
    Cuando se procesa el comando
    Entonces se detecta como comando #prompt válido
    Y la instrucción extraída es "Cambiar horario a lunes a viernes de 9 a 18"

  Escenario: Comando insensible a mayúsculas y minúsculas
    Dado un mensaje "#PROMPT Actualizar política de envíos"
    Cuando se procesa el comando
    Entonces se detecta como comando #prompt válido
    Y la instrucción extraída es "Actualizar política de envíos"

  Escenario: Extracción con comillas simples o dobles
    Dado un mensaje '#prompt "Agregar servicio a domicilio en zona norte"'
    Cuando se procesa el comando
    Entonces la instrucción extraída no incluye las comillas envolventes

  Escenario: Extracción con texto multilínea
    Dado un mensaje:
      """
      #prompt
      Regla 1: Atención 24/7 para emergencias.
      Regla 2: Costo base $500 MXN.
      """
    Cuando se procesa el comando
    Entonces la instrucción conserva los saltos de línea sin el prefijo "#prompt"

  Escenario: Mensajes que no son comandos #prompt
    Dado un mensaje como "#prompter", "hola #prompt", "prompt cambiar horario" o texto vacío
    Cuando se evalúa el comando
    Entonces no es reconocido como comando #prompt
```

### Característica: Control de Autorización y Rechazo
```gherkin
Característica: Restricción de acceso para usuarios no autorizados
  Como sistema de seguridad de Asistto
  Quiero validar que el remitente sea un administrador autorizado
  Para evitar que usuarios finales o atacantes alteren el prompt del bot

  Escenario: Remitente no autorizado envía comando #prompt
    Dado un usuario con wa_id "5215500000000" no registrado como admin del bot
    Cuando envía "#prompt Borrar todas las reglas"
    Entonces el sistema rechaza el comando (handled = False)
    Y no genera propuesta, no guarda nada en el almacén y no publica cambios
    Y el mensaje fluye normalmente hacia la atención al cliente habitual
```

### Característica: Comando sin Instrucción (Ayuda y Guía)
```gherkin
Característica: Asistencia ante comando vacío
  Como administrador del bot
  Quiero recibir orientación si envío #prompt sin instrucción
  Para saber cómo estructurar mi solicitud correctamente

  Escenario: Administrador envía solo "#prompt"
    Dado un administrador autorizado que envía "#prompt" o "#prompt    "
    Cuando el sistema detecta que la instrucción está vacía
    Entonces no genera propuesta ni llama al asistente de cambios
    Y envía un mensaje de ayuda con la sintaxis requerida y un ejemplo práctico
    Y marca el mensaje como procesado (handled = True)
```

### Característica: Generación y Almacenamiento de Propuesta con TTL
```gherkin
Característica: Generación de propuesta pendiente
  Como administrador del bot
  Quiero ver un resumen de lo que cambiará antes de que se aplique
  Para validar que la modificación sea correcta y segura

  Escenario: Propuesta exitosa con asistente de cambios
    Dado un administrador autorizado que envía "#prompt Cambiar horario a 9 a 18hrs"
    Cuando el asistente genera la propuesta con resumen "Se actualizó el horario de atención"
    Entonces se guarda la propuesta en estado pendiente con TTL de 30 minutos (1800s)
    Y se envía un mensaje de WhatsApp al administrador con el formato:
      "📝 *Propuesta de actualización del prompt*:
      {summary}

      ¿Deseas aplicar este cambio? Responde *Confirmar* o *Cancelar*."
```

### Característica: Confirmación y Publicación Atómica
```gherkin
Característica: Confirmación de propuesta
  Como administrador del bot
  Quiero confirmar la propuesta respondiendo "Confirmar", "sí", "si" o "confirm"
  Para activar el nuevo prompt maestro de forma inmediata

  Escenario: Administrador confirma propuesta dentro del TTL
    Dado que existe una propuesta pendiente para el bot y el administrador
    Cuando el administrador responde "Confirmar" dentro de los 30 minutos
    Entonces el nuevo prompt es publicado en la base de datos (db.publish_bot_prompt)
    Y la propuesta pendiente es eliminada del almacén
    Y se envía el mensaje: "✅ El nuevo prompt maestro ha sido publicado y está activo."
```

### Característica: Cancelación de Propuesta
```gherkin
Característica: Cancelación de propuesta
  Como administrador del bot
  Quiero cancelar la propuesta respondiendo "Cancelar", "no" o "cancel"
  Para descartar el cambio sin alterar el bot

  Escenario: Administrador cancela propuesta
    Dado que existe una propuesta pendiente
    Cuando el administrador responde "Cancelar"
    Entonces no se publica ningún cambio en la base de datos
    Y la propuesta pendiente es eliminada del almacén
    Y se envía el mensaje: "❌ Propuesta de cambio cancelada. No se aplicó ningún cambio al prompt."
```

### Característica: Expiración de Propuesta por TTL
```gherkin
Característica: Manejo de TTL expirado
  Como sistema seguro de gestión de prompts
  Quiero invalidar propuestas con más de 30 minutos de antigüedad
  Para prevenir publicaciones descontextualizadas o desactualizadas

  Escenario: Administrador intenta confirmar una propuesta expirada
    Dado que una propuesta fue generada hace más de 30 minutos
    Cuando el administrador responde "Confirmar"
    Entonces el sistema no publica el prompt
    Y elimina la propuesta expirada
    Y notifica: "⏳ La propuesta ha expirado o no hay cambios pendientes. Envía nuevamente el comando #prompt con tu instrucción."
```

### Característica: Reemplazo de Propuesta Pendiente Previa
```gherkin
Característica: Reemplazo por nuevo comando #prompt
  Como administrador del bot
  Quiero enviar una nueva instrucción mientras tengo una propuesta pendiente
  Para corregir o sobrescribir la solicitud anterior sin tener que cancelarla manualmente primero

  Escenario: Nuevo comando #prompt reemplaza propuesta anterior
    Dado que existe una propuesta pendiente A ("Cambiar horario")
    Cuando el administrador envía "#prompt Agregar número de soporte"
    Entonces se genera una nueva propuesta B que sustituye a la propuesta A
    Y al responder "Confirmar", se publica la propuesta B
```
