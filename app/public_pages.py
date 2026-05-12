"""Public compliance pages for the Asistto by Humanio Tech Provider app."""
from fastapi import APIRouter
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
  code { background:#edf0ec; padding:2px 5px; border-radius:5px; }
</style>
"""


PAGES = {
    "/privacy": {
        "title": "Politica de privacidad",
        "lead": "Asistto by Humanio ayuda a negocios a atender clientes por WhatsApp con automatizacion, agenda e integraciones.",
        "sections": [
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
                "Para solicitudes de privacidad, escribe a soporte@humanio.digital o usa la pagina de soporte publicada por Humanio.",
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
                "Para soporte operativo, escribe a soporte@humanio.digital con el nombre del negocio, numero de WhatsApp conectado y descripcion del problema.",
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
                "Envia una solicitud a soporte@humanio.digital indicando el negocio, numero de WhatsApp y datos que quieres eliminar.",
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
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{data["title"]} - Asistto by Humanio</title>{PUBLIC_CSS}</head>
<body><main>
  <div class="brand">Asistto by Humanio</div>
  <nav>{links}</nav>
  <section class="panel">
    <h1>{data["title"]}</h1>
    <p class="lead">{data["lead"]}</p>
    {sections}
  </section>
</main></body></html>"""
    return HTMLResponse(html)


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page():
    return _page("/privacy")


@router.get("/terms", response_class=HTMLResponse)
async def terms_page():
    return _page("/terms")


@router.get("/support", response_class=HTMLResponse)
async def support_page():
    return _page("/support")


@router.get("/data-deletion", response_class=HTMLResponse)
async def data_deletion_page():
    return _page("/data-deletion")


@router.get("/ai-data-policy", response_class=HTMLResponse)
async def ai_data_policy_page():
    return _page("/ai-data-policy")
