"""Public compliance pages for the Asistto by Humanio Tech Provider app."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public"])

PUBLIC_CSS = """
<style>
  :root { --bg:#f7f8f4; --ink:#151716; --muted:#616b66; --line:#dbe1da; --primary:#176b5b; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font-family:Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
  main { width:min(920px, calc(100% - 32px)); margin:0 auto; padding:44px 0 64px; }
  nav { display:flex; gap:14px; flex-wrap:wrap; margin-bottom:28px; }
  nav a { color:var(--primary); text-decoration:none; font-weight:650; }
  h1 { font-size:34px; line-height:1.08; margin:0 0 10px; letter-spacing:0; }
  h2 { font-size:19px; margin:28px 0 8px; }
  p, li { color:var(--muted); line-height:1.62; font-size:15px; }
  .lead { font-size:17px; color:#37403b; }
  .panel { background:white; border:1px solid var(--line); border-radius:8px; padding:24px; }
  .brand { font-size:13px; color:var(--muted); margin-bottom:8px; }
  .meta { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin:18px 0 8px; }
  .meta div { border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfcfa; color:#37403b; font-size:14px; line-height:1.5; }
  .meta strong { display:block; color:var(--ink); margin-bottom:3px; }
  code { background:#edf0ec; padding:2px 5px; border-radius:5px; }
</style>
"""


PAGES = {
    "/privacy": {
        "title": "Politica de privacidad",
        "lead": "Esta politica de privacidad corresponde a Asistto by Humanio, la app web publicada en https://bot.humanio.digital/ y la app de Meta llamada Asistto-chatbot.",
        "meta": [
            ("Producto", "Asistto by Humanio"),
            ("App de Meta", "Asistto-chatbot"),
            ("Negocio responsable", "Humanio"),
            ("Dominios oficiales", "humanio.digital y bot.humanio.digital"),
            ("Contacto de privacidad", "contacto@humanio.digital"),
            ("Ultima actualizacion", "22 de mayo de 2026"),
        ],
        "sections": [
            (
                "Relacion entre esta politica, la app y el negocio",
                "Humanio es el negocio responsable de Asistto by Humanio y controla esta politica de privacidad. Asistto by Humanio es una plataforma de automatizacion de atencion, ventas, agenda e integraciones por WhatsApp para negocios. La app de Meta asociada a este producto se llama Asistto-chatbot y usa el dominio publico bot.humanio.digital.",
            ),
            (
                "Responsable de los datos",
                "Humanio determina los propositos y medios del tratamiento de los datos procesados por Asistto by Humanio para operar la plataforma. Cuando un negocio cliente conecta su WhatsApp Business Account, ese negocio conserva responsabilidad sobre sus conversaciones, avisos, opt-in, plantillas y cumplimiento aplicable frente a sus usuarios.",
            ),
            (
                "Datos que procesamos",
                "Procesamos mensajes de WhatsApp, identificadores tecnicos como wa_id y phone_number_id, datos de contacto que el usuario comparte, registros de conversacion, leads, citas e integraciones configuradas por cada negocio.",
            ),
            (
                "Uso de los datos",
                "Usamos estos datos solo para operar el bot del negocio, responder mensajes, registrar prospectos, generar citas, diagnosticar errores y prestar soporte autorizado.",
            ),
            (
                "IA y entrenamiento",
                "Los datos de WhatsApp no se venden ni se usan para entrenar modelos generales de IA. Si un proveedor de IA procesa mensajes, lo hace como tercero de servicio para responder al negocio configurado.",
            ),
            (
                "Seguridad",
                "Los secretos de integraciones se cifran en reposo. No mostramos tokens completos en el panel ni en documentos operativos.",
            ),
            (
                "Contacto",
                "Para solicitudes de privacidad relacionadas con Asistto by Humanio, la app de Meta Asistto-chatbot o el dominio bot.humanio.digital, escribe a contacto@humanio.digital o usa la pagina de soporte publicada por Humanio.",
            ),
        ],
    },
    "/terms": {
        "title": "Terminos de servicio",
        "lead": "Estos terminos describen el uso de Asistto by Humanio como plataforma de automatizacion de WhatsApp para negocios.",
        "sections": [
            (
                "Servicio",
                "Asistto permite configurar bots de atencion, ventas, agenda, CRM e integraciones para negocios que usan WhatsApp Business Platform.",
            ),
            (
                "Responsabilidad del negocio",
                "Cada negocio es responsable de tener permisos, avisos, opt-in, plantillas aprobadas y contenido permitido conforme a las politicas de WhatsApp y leyes aplicables.",
            ),
            (
                "Uso aceptable",
                "No debe usarse para spam, suplantacion, productos prohibidos, solicitud de datos sensibles innecesarios ni casos donde la ley exija controles especiales no configurados.",
            ),
            (
                "Escalacion humana",
                "La automatizacion debe mantener una ruta clara de contacto humano cuando el caso lo requiera.",
            ),
        ],
    },
    "/support": {
        "title": "Soporte",
        "lead": "Canal de ayuda para negocios que usan Asistto by Humanio.",
        "sections": [
            (
                "Contacto",
                "Para soporte operativo, escribe a contacto@humanio.digital con el nombre del negocio, numero de WhatsApp conectado y descripcion del problema.",
            ),
            (
                "Casos comunes",
                "Podemos apoyar con conexion de WhatsApp, webhooks, plantillas, diagnostico de IA, calendario, CRM, integraciones y acceso al panel.",
            ),
            (
                "Emergencias operativas",
                "Si el bot responde incorrectamente, pausa el bot en el panel o cambia el flujo a atencion humana mientras se revisa el caso.",
            ),
        ],
    },
    "/data-deletion": {
        "title": "Eliminacion de datos",
        "lead": "Los negocios y usuarios pueden solicitar eliminacion de datos relacionados con una conversacion o cuenta.",
        "sections": [
            (
                "Como solicitarla",
                "Envia una solicitud a contacto@humanio.digital indicando el negocio, numero de WhatsApp y datos que quieres eliminar.",
            ),
            (
                "Alcance",
                "Podemos eliminar historial de conversacion, lead, escalaciones y memoria operativa asociada, salvo informacion que deba conservarse por obligaciones legales o seguridad.",
            ),
            (
                "Tiempo de respuesta",
                "Responderemos la solicitud con confirmacion o pasos adicionales de verificacion.",
            ),
        ],
    },
    "/ai-data-policy": {
        "title": "Politica de IA y datos",
        "lead": "Asistto usa IA como funcionalidad auxiliar para flujos de negocio concretos, no como asistente general de proposito abierto.",
        "sections": [
            (
                "Uso permitido",
                "La IA se usa para responder dudas del negocio, calificar prospectos, resumir necesidades, ayudar con agenda y activar integraciones autorizadas.",
            ),
            (
                "Entrenamiento",
                "No usamos datos de WhatsApp Business Solution Data para crear, desarrollar, entrenar o mejorar modelos generales de IA.",
            ),
            (
                "Limitaciones",
                "El bot no debe dar asesoramiento legal, medico, financiero o regulado sin autorizacion y controles especificos del negocio.",
            ),
            (
                "Supervision",
                "Los negocios deben revisar conversaciones, mantener informacion actualizada y ofrecer escalacion humana.",
            ),
        ],
    },
}


def _page(path: str) -> HTMLResponse:
    data = PAGES[path]
    links = "".join(
        f'<a href="{href}">{page["title"]}</a>'
        for href, page in PAGES.items()
    )
    sections = "".join(
        f"<h2>{title}</h2><p>{body}</p>"
        for title, body in data["sections"]
    )
    meta_items = "".join(
        f"<div><strong>{title}</strong>{body}</div>"
        for title, body in data.get("meta", [])
    )
    meta_html = f'<div class="meta">{meta_items}</div>' if meta_items else ""
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{data["title"]} - Asistto by Humanio</title>
<meta name="description" content="{data["lead"]}">
<meta property="og:site_name" content="Asistto by Humanio">
<meta property="og:title" content="{data["title"]} - Asistto by Humanio">
<meta property="og:description" content="{data["lead"]}">
{PUBLIC_CSS}</head>
<body><main>
  <div class="brand">Asistto by Humanio</div>
  <nav>{links}</nav>
  <section class="panel">
    <h1>{data["title"]}</h1>
    <p class="lead">{data["lead"]}</p>
    {meta_html}
    {sections}
  </section>
</main></body></html>"""
    return HTMLResponse(html)


@router.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def privacy_page(request: Request):
    return _page("/privacy")


@router.api_route("/terms", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def terms_page(request: Request):
    return _page("/terms")


@router.api_route("/support", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def support_page(request: Request):
    return _page("/support")


@router.api_route("/data-deletion", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def data_deletion_page(request: Request):
    return _page("/data-deletion")


@router.api_route("/ai-data-policy", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def ai_data_policy_page(request: Request):
    return _page("/ai-data-policy")
