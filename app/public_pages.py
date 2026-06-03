"""Public compliance and landing pages for the Asistto by Humanio Tech Provider app."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public"])

PUBLIC_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@300;400;500;600;700&display=swap');

  :root {
    --primary: #0d9488;
    --primary-hover: #0f766e;
    --primary-light: #f0fdfa;
    --slate-50: #f8fafc;
    --slate-100: #f1f5f9;
    --slate-200: #e2e8f0;
    --slate-700: #334155;
    --slate-800: #1e293b;
    --slate-900: #0f172a;
    --ink: #0f172a;
    --muted: #475569;
    --border: #e2e8f0;
    --shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -4px rgba(0, 0, 0, 0.05);
    --font-display: 'Outfit', sans-serif;
    --font-sans: 'Inter', sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background-color: var(--slate-50);
    color: var(--slate-900);
    font-family: var(--font-sans);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }

  /* Header / Brand */
  header {
    padding: 18px 0;
    border-bottom: 1px solid var(--slate-200);
    background: white;
    position: sticky;
    top: 0;
    z-index: 100;
  }

  .header-container {
    max-width: 1100px;
    margin: 0 auto;
    padding: 0 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .logo {
    font-family: var(--font-display);
    font-weight: 800;
    font-size: 24px;
    color: var(--slate-900);
    display: flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
  }

  .logo span {
    color: var(--primary);
  }

  .nav-links {
    display: flex;
    gap: 20px;
    align-items: center;
  }

  .nav-links a {
    text-decoration: none;
    color: var(--slate-700);
    font-weight: 500;
    font-size: 15px;
    transition: color 0.2s;
  }

  .nav-links a:hover {
    color: var(--primary);
  }

  .btn-admin {
    background: var(--primary);
    color: white !important;
    padding: 8px 18px;
    border-radius: 8px;
    font-weight: 600;
    box-shadow: 0 4px 6px -1px rgba(13, 148, 136, 0.2);
    transition: all 0.2s;
  }

  .btn-admin:hover {
    background: var(--primary-hover);
    transform: translateY(-1px);
  }

  /* Main Layout */
  main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 60px 20px 80px;
  }

  .hero-grid {
    display: grid;
    grid-template-columns: 1.2fr 1fr;
    gap: 60px;
    align-items: center;
  }

  @media (max-width: 900px) {
    .hero-grid {
      grid-template-columns: 1fr;
      gap: 40px;
    }
    .hero-text {
      text-align: center;
    }
    .hero-actions {
      justify-content: center;
    }
  }

  /* Hero Content */
  .badge {
    display: inline-block;
    background: var(--primary-light);
    color: var(--primary);
    padding: 6px 14px;
    border-radius: 9999px;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 20px;
    border: 1px solid rgba(13, 148, 136, 0.1);
  }

  .hero-title {
    font-family: var(--font-display);
    font-size: 44px;
    font-weight: 800;
    line-height: 1.15;
    color: var(--slate-900);
    margin-bottom: 20px;
    letter-spacing: -0.02em;
  }

  @media (max-width: 600px) {
    .hero-title {
      font-size: 34px;
    }
  }

  .hero-description {
    font-size: 17px;
    color: var(--muted);
    line-height: 1.6;
    margin-bottom: 30px;
  }

  .hero-actions {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
  }

  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 12px 24px;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 600;
    text-decoration: none;
    transition: all 0.2s;
    cursor: pointer;
    border: none;
  }

  .btn-primary {
    background: var(--primary);
    color: white;
    box-shadow: 0 10px 15px -3px rgba(13, 148, 136, 0.2);
  }

  .btn-primary:hover {
    background: var(--primary-hover);
    transform: translateY(-1px);
  }

  .btn-secondary {
    background: white;
    color: var(--slate-700);
    border: 1px solid var(--slate-200);
  }

  .btn-secondary:hover {
    background: var(--slate-50);
    color: var(--slate-900);
  }

  /* Phone Mockup & Chat Simulator */
  .phone-container {
    display: flex;
    justify-content: center;
  }

  .phone-mockup {
    background: var(--slate-900);
    border: 10px solid #1e293b;
    border-radius: 36px;
    aspect-ratio: 9 / 18.5;
    width: 100%;
    max-width: 320px;
    box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
  }

  /* Notch */
  .phone-mockup::before {
    content: '';
    position: absolute;
    top: 0;
    left: 50%;
    transform: translateX(-50%);
    width: 130px;
    height: 18px;
    background: #1e293b;
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
    z-index: 10;
  }

  .chat-header {
    background: #075e54;
    color: white;
    padding: 26px 14px 10px;
    display: flex;
    align-items: center;
    gap: 10px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  }

  .chat-avatar {
    width: 28px;
    height: 28px;
    background: var(--primary-light);
    color: var(--primary);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 13px;
  }

  .chat-status-name {
    font-size: 13px;
    font-weight: 600;
  }

  .chat-status-sub {
    font-size: 9px;
    opacity: 0.8;
  }

  .chat-body {
    flex: 1;
    background: #ece5dd;
    background-image: url('https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png');
    background-size: cover;
    padding: 12px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 6px;
    scrollbar-width: none;
  }
  .chat-body::-webkit-scrollbar { display: none; }

  .chat-bubble {
    max-width: 85%;
    padding: 7px 10px;
    border-radius: 8px;
    font-size: 12px;
    line-height: 1.4;
    position: relative;
    animation: popIn 0.25s ease-out;
    word-break: break-word;
  }

  @keyframes popIn {
    from { transform: scale(0.95); opacity: 0; }
    to { transform: scale(1); opacity: 1; }
  }

  .bubble-user {
    background: #d9fdd3;
    align-self: flex-end;
    border-top-right-radius: 0;
  }

  .bubble-bot {
    background: white;
    align-self: flex-start;
    border-top-left-radius: 0;
  }

  .chat-time {
    font-size: 8px;
    color: #667781;
    text-align: right;
    margin-top: 3px;
  }

  /* Typing Indicator */
  .typing-indicator {
    align-self: flex-start;
    background: white;
    padding: 8px 12px;
    border-radius: 8px;
    border-top-left-radius: 0;
    display: none;
    align-items: center;
    gap: 3px;
  }

  .typing-dot {
    width: 5px;
    height: 5px;
    background: #a0aec0;
    border-radius: 50%;
    animation: bounce 1.4s infinite ease-in-out;
  }

  .typing-dot:nth-child(1) { animation-delay: -0.32s; }
  .typing-dot:nth-child(2) { animation-delay: -0.16s; }

  @keyframes bounce {
    0%, 80%, 100% { transform: scale(0); }
    40% { transform: scale(1); }
  }

  .chat-footer {
    background: #f0f2f5;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    border-top: 1px solid var(--slate-200);
  }

  .chat-options {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .chat-option-btn {
    background: white;
    border: 1px solid var(--slate-200);
    border-radius: 16px;
    padding: 6px 12px;
    font-size: 11px;
    font-weight: 500;
    text-align: left;
    cursor: pointer;
    color: var(--slate-700);
    transition: all 0.2s;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    width: 100%;
    outline: none;
  }

  .chat-option-btn:hover:not(:disabled) {
    background: var(--primary-light);
    border-color: var(--primary);
    color: var(--primary);
  }

  .chat-option-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* Features Grid */
  .features-section {
    padding: 80px 0 20px;
  }

  .section-title {
    font-family: var(--font-display);
    font-size: 28px;
    font-weight: 800;
    text-align: center;
    margin-bottom: 40px;
    letter-spacing: -0.01em;
  }

  .features-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 20px;
  }

  .feature-card {
    background: white;
    border: 1px solid var(--slate-200);
    border-radius: 12px;
    padding: 24px;
    box-shadow: var(--shadow);
    transition: all 0.3s;
  }

  .feature-card:hover {
    transform: translateY(-3px);
    border-color: var(--primary);
  }

  .feature-icon {
    width: 44px;
    height: 44px;
    background: var(--primary-light);
    color: var(--primary);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    margin-bottom: 16px;
  }

  .feature-name {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 8px;
    color: var(--slate-900);
  }

  .feature-desc {
    font-size: 13.5px;
    color: var(--muted);
    line-height: 1.6;
  }

  /* Compliance Document Detail view */
  .compliance-container {
    max-width: 820px;
    margin: 0 auto;
    background: white;
    border: 1px solid var(--slate-200);
    border-radius: 12px;
    padding: 40px;
    box-shadow: var(--shadow);
  }

  @media (max-width: 600px) {
    .compliance-container {
      padding: 24px;
    }
  }

  .compliance-container h1 {
    font-family: var(--font-display);
    font-size: 32px;
    font-weight: 800;
    margin-bottom: 12px;
    color: var(--slate-900);
  }

  .compliance-container .lead {
    font-size: 15px;
    color: var(--slate-700);
    margin-bottom: 24px;
    line-height: 1.6;
  }

  .compliance-container h2 {
    font-family: var(--font-display);
    font-size: 20px;
    font-weight: 700;
    margin-top: 30px;
    margin-bottom: 10px;
    border-bottom: 1px solid var(--slate-100);
    padding-bottom: 6px;
    color: var(--slate-900);
  }

  .compliance-container p {
    color: var(--muted);
    font-size: 14.5px;
    line-height: 1.7;
    margin-bottom: 14px;
  }

  .meta {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin: 20px 0;
  }

  .meta div {
    border: 1px solid var(--slate-200);
    border-radius: 8px;
    padding: 12px;
    background: var(--slate-50);
    font-size: 13.5px;
    color: var(--slate-700);
    line-height: 1.4;
  }

  .meta strong {
    display: block;
    color: var(--slate-900);
    margin-bottom: 2px;
  }

  /* Footer */
  footer {
    background: white;
    border-top: 1px solid var(--slate-200);
    padding: 40px 0;
    margin-top: 60px;
    text-align: center;
  }

  .footer-links {
    display: flex;
    justify-content: center;
    gap: 20px;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }

  .footer-links a {
    color: var(--muted);
    text-decoration: none;
    font-size: 13.5px;
    transition: color 0.2s;
  }

  .footer-links a:hover {
    color: var(--primary);
  }

  .footer-copy {
    font-size: 12px;
    color: #94a3b8;
  }
</style>
"""

PAGES = {
    "/privacy": {
        "title": "Política de privacidad",
        "lead": "Esta política de privacidad corresponde a Asistto by Humanio, la app web publicada en https://bot.humanio.digital/ y la app de Meta llamada Asistto-chatbot.",
        "meta": [
            ("Producto", "Asistto by Humanio"),
            ("App de Meta", "Asistto-chatbot"),
            ("Negocio responsable", "Humanio"),
            ("Dominios oficiales", "humanio.digital y bot.humanio.digital"),
            ("Contacto de privacidad", "contacto@humanio.digital"),
            ("Última actualización", "22 de mayo de 2026"),
        ],
        "sections": [
            (
                "Relación entre esta política, la app y el negocio",
                "Humanio es el negocio responsable de Asistto by Humanio y controla esta política de privacidad. Asistto by Humanio es una plataforma de automatización de atención, ventas, agenda e integraciones por WhatsApp para negocios. La app de Meta asociada a este producto se llama Asistto-chatbot y usa el dominio público bot.humanio.digital.",
            ),
            (
                "Responsable de los datos",
                "Humanio determina los propósitos y medios del tratamiento de los datos procesados por Asistto by Humanio para operar la plataforma. Cuando un negocio cliente conecta su WhatsApp Business Account, ese negocio conserva responsabilidad sobre sus conversaciones, avisos, opt-in, plantillas y cumplimiento aplicable frente a sus usuarios.",
            ),
            (
                "Datos que procesamos",
                "Procesamos mensajes de WhatsApp, identificadores técnicos como wa_id y phone_number_id, datos de contacto que el usuario comparte, registros de conversación, leads, citas e integraciones configuradas por cada negocio.",
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
                "Para solicitudes de privacidad relacionadas con Asistto by Humanio, la app de Meta Asistto-chatbot o el dominio bot.humanio.digital, escribe a contacto@humanio.digital o usa la página de soporte publicada por Humanio.",
            ),
        ],
    },
    "/terms": {
        "title": "Términos de servicio",
        "lead": "Estos términos describen el uso de Asistto by Humanio como plataforma de automatización de WhatsApp para negocios.",
        "sections": [
            (
                "Servicio",
                "Asistto permite configurar bots de atención, ventas, agenda, CRM e integraciones para negocios que usan WhatsApp Business Platform.",
            ),
            (
                "Responsabilidad del negocio",
                "Cada negocio es responsable de tener permisos, avisos, opt-in, plantillas aprobadas y contenido permitido conforme a las políticas de WhatsApp y leyes aplicables.",
            ),
            (
                "Uso aceptable",
                "No debe usarse para spam, suplantación, productos prohibidos, solicitud de datos sensibles innecesarios ni casos donde la ley exija controles especiales no configurados.",
            ),
            (
                "Escalación humana",
                "La automatización debe mantener una ruta clara de contacto humano cuando el caso lo requiera.",
            ),
        ],
    },
    "/support": {
        "title": "Soporte",
        "lead": "Canal de ayuda para negocios que usan Asistto by Humanio.",
        "sections": [
            (
                "Contacto",
                "Para soporte operativo, escribe a contacto@humanio.digital con el nombre del negocio, número de WhatsApp conectado y descripción del problema.",
            ),
            (
                "Casos comunes",
                "Podemos apoyar con conexión de WhatsApp, webhooks, plantillas, diagnóstico de IA, calendario, CRM, integraciones y acceso al panel.",
            ),
            (
                "Emergencias operativas",
                "Si el bot responde incorrectamente, pausa el bot en el panel o cambia el flujo a atención humana mientras se revisa el caso.",
            ),
        ],
    },
    "/data-deletion": {
        "title": "Eliminación de datos",
        "lead": "Los negocios y usuarios pueden solicitar eliminación de datos relacionados con una conversación o cuenta.",
        "sections": [
            (
                "Cómo solicitarla",
                "Envía una solicitud a contacto@humanio.digital indicando el negocio, número de WhatsApp y datos que quieres eliminar.",
            ),
            (
                "Alcance",
                "Podemos eliminar historial de conversación, lead, escalaciones y memoria operativa asociada, salvo información que deba conservarse por obligaciones legales o seguridad.",
            ),
            (
                "Tiempo de respuesta",
                "Responderemos la solicitud con confirmación o pasos adicionales de verificación.",
            ),
        ],
    },
    "/ai-data-policy": {
        "title": "Política de IA y datos",
        "lead": "Asistto usa IA como funcionalidad auxiliar para flujos de negocio concretos, no como asistente general de propósito abierto.",
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
                "El bot no debe dar asesoramiento legal, médico, financiero o regulado sin autorización y controles específicos del negocio.",
            ),
            (
                "Supervisión",
                "Los negocios deben revisar conversaciones, mantener información actualizada y ofrecer escalación humana.",
            ),
        ],
    },
}


def _shared_header() -> str:
    return """
<header>
  <div class="header-container">
    <a href="/" class="logo">Asistto<span>.</span></a>
    <nav class="nav-links">
      <a href="/privacy">Privacidad</a>
      <a href="/terms">Términos</a>
      <a href="/support">Soporte</a>
      <a href="/admin/login" class="btn-admin">Panel Admin</a>
    </nav>
  </div>
</header>
"""


def _shared_footer() -> str:
    return """
<footer>
  <div class="footer-links">
    <a href="/privacy">Política de Privacidad</a>
    <a href="/terms">Términos de Servicio</a>
    <a href="/support">Centro de Soporte</a>
    <a href="/data-deletion">Eliminación de Datos</a>
    <a href="/ai-data-policy">Política de Datos de IA</a>
    <a href="/admin/login">Acceso Clientes</a>
  </div>
  <div class="footer-copy">&copy; 2026 Asistto by Humanio. Todos los derechos reservados.</div>
</footer>
"""


def _page(path: str) -> HTMLResponse:
    data = PAGES[path]
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
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{data["title"]} - Asistto by Humanio</title>
  <meta name="description" content="{data["lead"]}">
  <meta property="og:site_name" content="Asistto by Humanio">
  <meta property="og:title" content="{data["title"]} - Asistto by Humanio">
  <meta property="og:description" content="{data["lead"]}">
  {PUBLIC_CSS}
</head>
<body>
  {_shared_header()}
  <main>
    <section class="compliance-container">
      <h1>{data["title"]}</h1>
      <p class="lead">{data["lead"]}</p>
      {meta_html}
      {sections}
    </section>
  </main>
  {_shared_footer()}
</body>
</html>"""
    return HTMLResponse(html)


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def landing_page(request: Request):
    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Asistto - Automatiza tu WhatsApp con Inteligencia Artificial</title>
  <meta name="description" content="Conecta tu WhatsApp Business Account a un asistente inteligente que califica prospectos, responde dudas y agenda citas en tiempo real.">
  <meta property="og:site_name" content="Asistto by Humanio">
  <meta property="og:title" content="Asistto - Automatiza tu WhatsApp con Inteligencia Artificial">
  <meta property="og:description" content="Chatbots inteligentes integrados con Google Calendar y CRM para llevar la atención al cliente de tu negocio al siguiente nivel.">
  {PUBLIC_CSS}
</head>
<body>
  {_shared_header()}
  <main>
    <div class="hero-grid">
      <div class="hero-text">
        <span class="badge">Meta Tech Provider Autorizado</span>
        <h1 class="hero-title">Automatiza tu atención en WhatsApp con IA</h1>
        <p class="hero-description">
          Asistto conecta el canal de WhatsApp de tu negocio con agentes virtuales inteligentes. Responde consultas frecuentes, califica leads en tu CRM y agenda citas reales en tu Google Calendar sin esfuerzo.
        </p>
        <div class="hero-actions">
          <a href="/admin/login" class="btn btn-primary">Acceder al Panel Admin</a>
          <button onclick="document.getElementById('features').scrollIntoView({{behavior: 'smooth'}})" class="btn btn-secondary">Ver Características</button>
        </div>
      </div>
      <div class="phone-container">
        <div class="phone-mockup">
          <div class="chat-header">
            <div class="chat-avatar">A</div>
            <div>
              <div class="chat-status-name">Asistto Bot</div>
              <div class="chat-status-sub">en línea</div>
            </div>
          </div>
          <div class="chat-body" id="chatBody">
            <div class="chat-bubble bubble-bot">
              ¡Hola! Soy Asistto, tu asistente inteligente para WhatsApp. ¿En qué te puedo ayudar hoy?
              <div class="chat-time">10:00 AM</div>
            </div>
          </div>
          <div class="typing-indicator" id="typingIndicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
          </div>
          <div class="chat-footer">
            <div class="chat-options" id="chatOptions">
              <button class="chat-option-btn" onclick="startDemo('funcionamiento')">💡 ¿Cómo funciona Asistto?</button>
              <button class="chat-option-btn" onclick="startDemo('agenda')">📅 Simular Agendar una Cita</button>
              <button class="chat-option-btn" onclick="startDemo('precios')">💵 Ver Paquetes y Precios</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="features-section" id="features">
      <h2 class="section-title">Habilidades integradas para tu negocio</h2>
      <div class="features-grid">
        <div class="feature-card">
          <div class="feature-icon">💬</div>
          <h3 class="feature-name">Atención 24/7</h3>
          <p class="feature-desc">Responde consultas frecuentes al instante utilizando la base de conocimiento cargada para tu negocio.</p>
        </div>
        <div class="feature-card">
          <div class="feature-icon">📅</div>
          <h3 class="feature-name">Agenda de Citas</h3>
          <p class="feature-desc">Conexión nativa y segura con Google Calendar para verificar horarios libres, agendar y cancelar citas de forma autónoma.</p>
        </div>
        <div class="feature-card">
          <div class="feature-icon">📊</div>
          <h3 class="feature-name">Calificación y CRM</h3>
          <p class="feature-desc">Detecta la intención del usuario, captura sus datos clave y guárdalos automáticamente en el CRM o webhook de tu elección.</p>
        </div>
        <div class="feature-card">
          <div class="feature-icon">👥</div>
          <h3 class="feature-name">Handoff Humano</h3>
          <p class="feature-desc">Cuando la IA detecta soporte técnico o necesidades especiales, deriva la conversación inmediatamente a tu equipo humano.</p>
        </div>
      </div>
    </div>
  </main>
  {_shared_footer()}

  <script>
    const chatBody = document.getElementById('chatBody');
    const typingIndicator = document.getElementById('typingIndicator');
    const chatOptions = document.getElementById('chatOptions');

    const PATHS = {{
      funcionamiento: [
        {{ type: 'user', text: '¿Cómo funciona Asistto?' }},
        {{ type: 'bot', text: 'Es muy sencillo. Vinculamos tu número de WhatsApp a un asistente de IA entrenado específicamente con la información de tu negocio.' }},
        {{ type: 'bot', text: 'El asistente responde dudas frecuentes, captura prospectos y agenda citas reales en tu calendario. Si hay algún caso complejo, lo deriva a una persona en tu panel admin.' }}
      ],
      agenda: [
        {{ type: 'user', text: 'Quiero agendar una llamada con ustedes' }},
        {{ type: 'bot', text: '¡Excelente! Estaré encantado de ayudarte. ¿A nombre de quién registro la llamada?' }},
        {{ type: 'user', text: 'Miguel González' }},
        {{ type: 'bot', text: 'Muchas gracias, Miguel. ¿Qué día y hora te queda mejor?' }},
        {{ type: 'user', text: 'Mañana a las 10:00 AM' }},
        {{ type: 'bot', text: 'He verificado la disponibilidad en mi agenda y ese horario está libre.' }},
        {{ type: 'bot', text: 'Listo, Miguel. Quedó agendada tu llamada para el día de mañana a las 10:00 AM. ¡Nos vemos pronto!' }}
      ],
      precios: [
        {{ type: 'user', text: '¿Cuáles son los paquetes y precios?' }},
        {{ type: 'bot', text: 'Ofrecemos tres paquetes mensuales adaptados a tu escala:\\n\\n• Inicio ($47 USD/mes): FAQs y captura de leads.\\n• PRO ($97 USD/mes): Inicio + Agenda y Google Calendar.\\n• Premium ($149 USD/mes): Multi-sucursal y dashboards.' }},
        {{ type: 'bot', text: '¿Cuál de estos paquetes consideras que se adapta mejor a tu negocio?' }}
      ]
    }};

    let isRunning = false;

    async function sleep(ms) {{
      return new Promise(resolve => setTimeout(resolve, ms));
    }}

    function getCurrentTime() {{
      const now = new Date();
      let hours = now.getHours();
      let minutes = now.getMinutes();
      const ampm = hours >= 12 ? 'PM' : 'AM';
      hours = hours % 12;
      hours = hours ? hours : 12;
      minutes = minutes < 10 ? '0' + minutes : minutes;
      return `${{hours}}:${{minutes}} ${{ampm}}`;
    }}

    async function startDemo(key) {{
      if (isRunning) return;
      isRunning = true;

      // Disable buttons
      const buttons = chatOptions.querySelectorAll('button');
      buttons.forEach(btn => btn.disabled = true);

      // Clear previous interactive messages (keep the first bot welcome message)
      const messages = chatBody.querySelectorAll('.chat-bubble');
      for (let i = 1; i < messages.length; i++) {{
        messages[i].remove();
      }}

      const steps = PATHS[key];
      for (const step of steps) {{
        if (step.type === 'user') {{
          // User bubble
          const userBubble = document.createElement('div');
          userBubble.className = 'chat-bubble bubble-user';
          userBubble.innerHTML = `${{step.text}}<div class="chat-time">${{getCurrentTime()}}</div>`;
          chatBody.appendChild(userBubble);
          chatBody.scrollTop = chatBody.scrollHeight;
          await sleep(800);
        }} else {{
          // Bot typing
          typingIndicator.style.display = 'flex';
          chatBody.scrollTop = chatBody.scrollHeight;
          
          const textLength = step.text.length;
          const typingTime = Math.max(1000, Math.min(2200, textLength * 15));
          await sleep(typingTime);

          typingIndicator.style.display = 'none';

          // Bot bubble
          const botBubble = document.createElement('div');
          botBubble.className = 'chat-bubble bubble-bot';
          botBubble.innerHTML = `${{step.text.replace(/\\n/g, '<br>')}}<div class="chat-time">${{getCurrentTime()}}</div>`;
          chatBody.appendChild(botBubble);
          chatBody.scrollTop = chatBody.scrollHeight;
          await sleep(500);
        }}
      }}

      // Enable buttons
      buttons.forEach(btn => btn.disabled = false);
      isRunning = false;
    }}
  </script>
</body>
</html>"""
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
