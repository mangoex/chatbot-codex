# CHG-011: cotizaciones y comprobantes opt-in

## Alcance y aislamiento

La capacidad se activa exclusivamente cuando el prompt activo del bot contiene
`<order_payments_config>` con JSON y `"enabled": true`. No existen cuentas,
catálogos ni configuraciones bancarias por defecto en código. Los bots sin esa
configuración conservan su respuesta de texto y `MEDIA_REPLY` históricos; un
marcador accidental se pasa sin transformar para no alterar la identidad de otro
tenant.

Las instrucciones se derivan del prompt que `openai_client` ya cargó. La ruta
normal no realiza una consulta adicional de `order_payments`.

## Datos y comprobantes

Las expectativas se guardan por el par exacto `bot_id` y `wa_id`, se eliminan
con el TTL global y con la eliminación de datos del contacto. Importes y totales
se calculan como unidades menores enteras y se recalculan antes de persistir.

Una cotización canónica pasa primero a `awaiting_confirmation`. Sólo un
`MARONA_PAYMENT` que recalcula exactamente el mismo día, catálogo, cantidades,
unitarios, subtotales, moneda y total puede promover esa misma fila a
`awaiting_receipt`. La promoción usa bloqueo de fila y un índice parcial único
por `bot_id, wa_id`, por lo que los reintentos idénticos son idempotentes y dos
confirmaciones concurrentes no crean dos expectativas activas. Una nueva
cotización supersede únicamente el estado activo de ese mismo bot/contacto.

Un comprobante sólo se descarga de Meta/WhatsApp por HTTPS usando el token del
bot resuelto. El MIME y límite de bytes deben estar en la configuración del bot;
la descarga se corta mientras se transmite. El límite global en código es 10
MiB: el prompt puede reducirlo, nunca ampliarlo. La imagen y el texto OCR no se
persisten ni se envían a OpenAI, OpenRouter u otro proveedor. Tesseract se
ejecuta localmente fuera del event loop y se limita a dos procesos simultáneos.

`matching_fields` significa únicamente que importe, MXN, fecha no futura y
referencia coinciden. Nunca equivale a pago acreditado: la acreditación requiere
conciliación bancaria o revisión humana.

Riesgo residual conocido: importe y referencia `MARONA SABADO`/`DOMINGO` no
identifican de forma única un pedido. El sistema conserva por ello
`matching_fields` como evidencia insuficiente para acreditar y no altera esa
regla de negocio sin una decisión aprobada.

## Migración y rollback

`SCHEMA_SQL` crea de forma aditiva e idempotente
`order_payment_expectations`. La migración instala el índice parcial único de
estado activo; si existen datos heredados inconsistentes, conserva la fila activa
más reciente por bot/contacto y marca las anteriores como `superseded` antes de
instalar la restricción.

Para rollback: primero publique o restaure un prompt sin
`order_payments_config` (desactiva el flujo sin borrar datos), despliegue la
versión anterior y conserve la tabla durante el TTL vigente. Cuando ya no haya
expectativas que deban retenerse, una migración manual posterior puede eliminar
el índice y la tabla. No borrar la tabla como parte de un rollback urgente.
