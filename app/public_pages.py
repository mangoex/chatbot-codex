"""Public compliance and landing pages for the Asistto by Humanio Tech Provider app.
Designed with Pear.no scrollytelling luxury aesthetics, WebCodecs background video scrubber,
interactive 3D WhatsApp simulator, and bottom-left legal & system access menu.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public"])

PUBLIC_DARK_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,400&family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;600&display=swap');

  :root {
    --bg-color: #080c10;
    --text-primary: #f8fafc;
    --text-muted: #8e9dae;
    --accent-teal: #0d9488;
    --accent-cyan: #14b8a6;
    --accent-gold: #dfb758;
    --surface-glass: rgba(17, 24, 34, 0.75);
    --border-subtle: rgba(255, 255, 255, 0.08);
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  
  body {
    background-color: var(--bg-color);
    color: var(--text-primary);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
    overflow-x: hidden;
  }

  .font-serif-luxury { font-family: 'Cormorant Garamond', Georgia, serif; }
  .font-display-modern { font-family: 'Outfit', sans-serif; }
  .font-mono-tech { font-family: 'JetBrains Mono', monospace; }

  .glass-panel {
    background: var(--surface-glass);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid var(--border-subtle);
    box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }

  .glow-teal { text-shadow: 0 0 24px rgba(20, 184, 166, 0.4); }
  .glow-gold { text-shadow: 0 0 20px rgba(223, 183, 88, 0.35); }

  .perspective-stage {
    perspective: 1600px;
    transform-style: preserve-3d;
  }

  /* Compliance Page Specifics */
  .compliance-wrapper {
    max-width: 860px;
    margin: 40px auto 80px;
    padding: 0 24px;
    position: relative;
    z-index: 10;
  }

  .compliance-card {
    background: rgba(17, 24, 34, 0.85);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 24px;
    padding: 48px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
  }

  @media (max-width: 640px) {
    .compliance-card { padding: 24px; }
  }

  .compliance-card h1 {
    font-family: 'Outfit', sans-serif;
    font-size: 36px;
    font-weight: 800;
    color: #f8fafc;
    margin-bottom: 12px;
    letter-spacing: -0.02em;
  }

  .compliance-card .lead {
    font-size: 16px;
    color: #8e9dae;
    margin-bottom: 28px;
    line-height: 1.6;
  }

  .compliance-card h2 {
    font-family: 'Outfit', sans-serif;
    font-size: 20px;
    font-weight: 700;
    margin-top: 32px;
    margin-bottom: 10px;
    color: #2dd4bf;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding-bottom: 8px;
  }

  .compliance-card p {
    color: #8e9dae;
    font-size: 14.5px;
    line-height: 1.7;
    margin-bottom: 14px;
  }

  .meta-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 12px;
    margin: 24px 0;
  }

  .meta-item {
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 14px;
    background: rgba(255, 255, 255, 0.02);
    font-size: 13px;
    color: #8e9dae;
  }

  .meta-item strong {
    display: block;
    color: #f8fafc;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
  }

  /* Animations */
  @keyframes popIn {
    from { transform: scale(0.96); opacity: 0; }
    to { transform: scale(1); opacity: 1; }
  }
  .animate-pop-in { animation: popIn 0.22s cubic-bezier(0.16, 1, 0.3, 1) forwards; }

  @keyframes bounceDot {
    0%, 80%, 100% { transform: scale(0); }
    40% { transform: scale(1); }
  }
  .animate-bounce-1 { animation: bounceDot 1.4s infinite ease-in-out -0.32s; }
  .animate-bounce-2 { animation: bounceDot 1.4s infinite ease-in-out -0.16s; }
  .animate-bounce-3 { animation: bounceDot 1.4s infinite ease-in-out 0s; }
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
            ("Última actualización", "2026"),
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
<header class="fixed top-0 left-0 w-full z-30 px-6 py-6 md:px-12 md:py-8 flex justify-between items-center pointer-events-auto bg-[#080c10]/80 backdrop-blur-md border-b border-white/[0.06]">
  <a href="/" class="group flex items-center space-x-3 text-inherit no-underline">
    <div class="w-8 h-8 rounded-lg border border-[#0d9488]/40 bg-[#0d9488]/15 flex items-center justify-center transition-transform group-hover:scale-105 shadow-[0_0_15px_rgba(13,148,136,0.3)]">
      <span class="font-display-modern font-bold text-sm text-[#2dd4bf]">A</span>
    </div>
    <div class="flex flex-col">
      <span class="font-display-modern text-xl md:text-2xl font-bold tracking-tight text-[#f8fafc] leading-none">
        Asistto<span class="text-[#14b8a6]">.</span>
      </span>
      <span class="text-[9px] font-mono text-[#8e9dae] tracking-widest uppercase mt-0.5">
        By Humanio · AI WhatsApp Engine
      </span>
    </div>
  </a>

  <div class="flex items-center space-x-3 md:space-x-4">
    <div class="hidden md:flex items-center space-x-2 px-3 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.08] text-[11px] font-mono text-[#8e9dae]">
      <i data-lucide="shield-check" class="w-3.5 h-3.5 text-[#14b8a6]"></i>
      <span>META TECH PROVIDER</span>
    </div>
    <a
      href="/admin/login"
      class="group relative inline-flex items-center space-x-2 px-4 py-2 md:px-5 md:py-2.5 rounded-full bg-[#0d9488] hover:bg-[#0f766e] text-white font-semibold text-xs md:text-sm tracking-wide transition-all shadow-[0_0_20px_rgba(13,148,136,0.35)] hover:shadow-[0_0_30px_rgba(13,148,136,0.55)] active:scale-95 no-underline"
    >
      <span>Panel Admin</span>
      <i data-lucide="external-link" class="w-3.5 h-3.5 opacity-80"></i>
    </a>
  </div>
</header>
"""


def _shared_footer() -> str:
    return """
<footer class="border-t border-white/[0.08] bg-[#080c10] py-12 px-6 text-center relative z-20">
  <div class="max-w-4xl mx-auto flex flex-col items-center space-y-4">
    <div class="flex flex-wrap justify-center gap-4 sm:gap-6 text-xs text-[#8e9dae]">
      <a href="/privacy" class="hover:text-[#2dd4bf] transition-colors no-underline">Política de Privacidad</a>
      <a href="/terms" class="hover:text-[#2dd4bf] transition-colors no-underline">Términos de Servicio</a>
      <a href="/support" class="hover:text-[#2dd4bf] transition-colors no-underline">Centro de Soporte</a>
      <a href="/data-deletion" class="hover:text-[#2dd4bf] transition-colors no-underline">Eliminación de Datos</a>
      <a href="/ai-data-policy" class="hover:text-[#2dd4bf] transition-colors no-underline">Política de Datos de IA</a>
      <a href="/admin/login" class="hover:text-[#2dd4bf] transition-colors no-underline text-[#2dd4bf] font-medium">Acceso Clientes</a>
    </div>
    <div class="text-[11px] font-mono text-[#8e9dae]/60">
      &copy; 2026 Asistto by Humanio. Meta Tech Provider Autorizado. Todos los derechos reservados.
    </div>
  </div>
</footer>
"""


def _page(path: str) -> HTMLResponse:
    data = PAGES[path]
    sections = "".join(
        f"<h2>{title}</h2><p>{body}</p>"
        for title, body in data["sections"]
    )
    meta_items = "".join(
        f'<div class="meta-item"><strong>{title}</strong>{body}</div>'
        for title, body in data.get("meta", [])
    )
    meta_html = f'<div class="meta-grid">{meta_items}</div>' if meta_items else ""
    html = f"""<!doctype html>
<html lang="es" class="bg-[#080c10] text-[#f8fafc]">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{data["title"]} - Asistto by Humanio</title>
  <meta name="description" content="{data["lead"]}">
  <meta property="og:site_name" content="Asistto by Humanio">
  <meta property="og:title" content="{data["title"]} - Asistto by Humanio">
  <meta property="og:description" content="{data["lead"]}">
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  {PUBLIC_DARK_CSS}
</head>
<body class="bg-[#080c10] text-[#f8fafc] min-h-screen flex flex-col justify-between pt-24">
  {_shared_header()}
  <main class="compliance-wrapper flex-1">
    <section class="compliance-card">
      <h1>{data["title"]}</h1>
      <p class="lead">{data["lead"]}</p>
      {meta_html}
      {sections}
    </section>
  </main>
  {_shared_footer()}
  <script>
    lucide.createIcons();
  </script>
</body>
</html>"""
    return HTMLResponse(html)


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def landing_page(request: Request):
    html = """<!DOCTYPE html>
<html lang="es" class="scroll-smooth bg-[#080c10] text-[#f8fafc] antialiased">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta name="theme-color" content="#080c10">
  <title>Asistto — Automatiza tu WhatsApp con Inteligencia Artificial | Meta Tech Provider</title>
  <meta name="description" content="Conecta tu WhatsApp Business Account a un asistente inteligente que califica prospectos, responde dudas y agenda citas en tiempo real. By Humanio.">

  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            humanio: {
              dark: '#080c10',
              obsidian: '#0b1016',
              surface: '#111822',
              glass: 'rgba(17, 24, 34, 0.75)',
              border: 'rgba(255, 255, 255, 0.08)',
              teal: '#0d9488',
              cyan: '#14b8a6',
              accent: '#2dd4bf',
              gold: '#dfb758',
              cream: '#f8fafc',
              muted: '#8e9dae'
            }
          },
          fontFamily: {
            serif: ['"Cormorant Garamond"', 'Georgia', 'serif'],
            display: ['"Outfit"', 'sans-serif'],
            sans: ['"Inter"', '"Plus Jakarta Sans"', 'sans-serif'],
            mono: ['"JetBrains Mono"', 'monospace']
          }
        }
      }
    }
  </script>

  <!-- Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,400&family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">

  <!-- Lucide Icons -->
  <script src="https://unpkg.com/lucide@latest"></script>

  <style>
    :root {
      --bg-color: #080c10;
      --text-primary: #f8fafc;
      --text-muted: #8e9dae;
      --accent-teal: #0d9488;
      --accent-cyan: #14b8a6;
      --accent-gold: #dfb758;
      --surface-glass: rgba(17, 24, 34, 0.75);
      --border-subtle: rgba(255, 255, 255, 0.08);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      background-color: var(--bg-color);
      color: var(--text-primary);
      font-family: 'Inter', sans-serif;
      overflow-x: hidden;
      overscroll-behavior-y: none;
    }
    .font-serif-luxury { font-family: 'Cormorant Garamond', Georgia, serif; }
    .font-display-modern { font-family: 'Outfit', sans-serif; }
    .font-mono-tech { font-family: 'JetBrains Mono', monospace; }

    .glass-panel {
      background: var(--surface-glass);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border-subtle);
      box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }

    .glow-teal { text-shadow: 0 0 24px rgba(20, 184, 166, 0.4); }
    .glow-gold { text-shadow: 0 0 20px rgba(223, 183, 88, 0.35); }

    .perspective-stage {
      perspective: 1600px;
      transform-style: preserve-3d;
    }

    @keyframes popIn {
      from { transform: scale(0.96); opacity: 0; }
      to { transform: scale(1); opacity: 1; }
    }
    .animate-pop-in { animation: popIn 0.22s cubic-bezier(0.16, 1, 0.3, 1) forwards; }

    @keyframes bounceDot {
      0%, 80%, 100% { transform: scale(0); }
      40% { transform: scale(1); }
    }
    .animate-bounce-1 { animation: bounceDot 1.4s infinite ease-in-out -0.32s; }
    .animate-bounce-2 { animation: bounceDot 1.4s infinite ease-in-out -0.16s; }
    .animate-bounce-3 { animation: bounceDot 1.4s infinite ease-in-out 0s; }
  </style>
</head>
<body class="bg-[#080c10] text-[#f8fafc] selection:bg-[#0d9488] selection:text-[#ffffff] overflow-x-hidden">

  <!-- VIRTUAL SCROLL TRACK: 500vh for smooth continuous frame playback with generous reading dwell time -->
  <div id="scroll-track" class="h-[500vh] w-full pointer-events-none"></div>

  <!-- SINGLE PINNED STAGE -->
  <main class="fixed inset-0 w-full h-full overflow-hidden select-none">
    
    <!-- 1. Background Visual & Canvas Frame Scrubber -->
    <div class="fixed inset-0 w-full h-full pointer-events-none z-0 overflow-hidden">
      <img
        id="bg-video-image"
        src="https://res.cloudinary.com/dfvnyhur4/image/upload/v1788130387/ezgif.com-video-to-webp-converter_3_asohiq.webp"
        alt="Asistto AI Background"
        class="absolute inset-0 w-full h-full object-cover opacity-20 filter blur-sm transform scale-105"
      />
      <canvas id="bg-canvas" class="absolute inset-0 w-full h-full block"></canvas>
      <div class="absolute inset-0 bg-gradient-to-t from-[#080c10] via-transparent to-[#080c10]/80 pointer-events-none opacity-85"></div>
    </div>

    <!-- 2. Analog Grain Texture Overlay -->
    <div 
      class="fixed inset-0 w-full h-full pointer-events-none z-10 opacity-[0.035] mix-blend-overlay"
      style="background-image: url('data:image/svg+xml,%3Csvg viewBox=\\'0 0 200 200\\' xmlns=\\'http://www.w3.org/2000/svg\\'%3E%3Cfilter id=\\'noiseFilter\\'%3E%3CfeTurbulence type=\\'fractalNoise\\' baseFrequency=\\'0.85\\' numOctaves=\\'3\\' stitchTiles=\\'stitch\\'/%3E%3C/filter%3E%3Crect width=\\'100%25\\' height=\\'100%25\\' filter=\\'url(%23noiseFilter)\\'/%3E%3C/svg%3E'); background-repeat: repeat;"
    ></div>

    <!-- 3. Technical Blueprint & Precision HUD -->
    <div class="fixed inset-0 pointer-events-none z-20 select-none">
      <div class="absolute inset-4 md:inset-8 border border-white/[0.04] rounded-lg"></div>

      <!-- Top Left: Meta Tech Provider Accreditation -->
      <div class="absolute top-6 left-6 md:top-10 md:left-12 flex items-center space-x-3 text-[10px] font-mono tracking-widest text-[#8e9dae]/60 uppercase">
        <span class="w-1.5 h-1.5 rounded-full bg-[#14b8a6] animate-pulse"></span>
        <span>META TECH PROVIDER · BOT.HUMANIO.DIGITAL</span>
      </div>

      <!-- Top Right: Live Stage Counter -->
      <div class="absolute top-6 right-6 md:top-10 md:right-12 flex items-center space-x-4 text-[10px] font-mono text-[#8e9dae]/60">
        <div class="hidden sm:flex items-center space-x-1.5">
          <span>CHAPTER</span>
          <span id="hud-stage-num" class="text-[#f8fafc] font-semibold">01</span>
          <span>/</span>
          <span>04</span>
        </div>
        <div class="px-2 py-0.5 rounded bg-white/[0.03] border border-white/[0.06] text-[#2dd4bf]">
          <span id="hud-percent">INDEX 00%</span>
        </div>
      </div>

      <!-- Bottom Right: Scroll Navigation Hint -->
      <div class="absolute bottom-6 right-6 md:bottom-10 md:right-12 flex items-center space-x-3 text-[10px] font-mono text-[#8e9dae]/60">
        <span class="hidden sm:inline">SCROLL TO ADVANCE</span>
        <div class="w-4 h-7 rounded-full border border-white/20 flex items-start justify-center p-1">
          <div id="scroll-pill" class="w-1 h-1.5 rounded-full bg-[#14b8a6] transition-transform duration-75"></div>
        </div>
      </div>

      <!-- 4 Corner Precision Crosshairs -->
      <div class="absolute top-4 left-4 md:top-8 md:left-8 text-white/20 font-mono text-xs">+</div>
      <div class="absolute top-4 right-4 md:top-8 md:right-8 text-white/20 font-mono text-xs">+</div>
      <div class="absolute bottom-4 left-4 md:bottom-8 md:left-8 text-white/20 font-mono text-xs">+</div>
      <div class="absolute bottom-4 right-4 md:bottom-8 md:right-8 text-white/20 font-mono text-xs">+</div>
    </div>

    <!-- 4. Luxury Header -->
    <header class="fixed top-0 left-0 w-full z-30 px-6 py-6 md:px-12 md:py-8 flex justify-between items-center pointer-events-auto">
      <a href="#top" onclick="event.preventDefault(); window.scrollTo({top: 0, behavior: 'smooth'});" class="group flex items-center space-x-3 text-inherit no-underline">
        <div class="w-8 h-8 rounded-lg border border-[#0d9488]/40 bg-[#0d9488]/15 flex items-center justify-center transition-transform group-hover:scale-105 shadow-[0_0_15px_rgba(13,148,136,0.3)]">
          <span class="font-display-modern font-bold text-sm text-[#2dd4bf]">A</span>
        </div>
        <div class="flex flex-col">
          <span class="font-display-modern text-xl md:text-2xl font-bold tracking-tight text-[#f8fafc] leading-none">
            Asistto<span class="text-[#14b8a6]">.</span>
          </span>
          <span class="text-[9px] font-mono text-[#8e9dae] tracking-widest uppercase mt-0.5">
            By Humanio · AI WhatsApp Engine
          </span>
        </div>
      </a>

      <div class="flex items-center space-x-3 md:space-x-4">
        <div class="hidden md:flex items-center space-x-2 px-3 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.08] text-[11px] font-mono text-[#8e9dae]">
          <i data-lucide="shield-check" class="w-3.5 h-3.5 text-[#14b8a6]"></i>
          <span>META TECH PROVIDER</span>
        </div>
        <a
          href="/admin/login"
          class="group relative inline-flex items-center space-x-2 px-4 py-2 md:px-5 md:py-2.5 rounded-full bg-[#0d9488] hover:bg-[#0f766e] text-white font-semibold text-xs md:text-sm tracking-wide transition-all shadow-[0_0_20px_rgba(13,148,136,0.35)] hover:shadow-[0_0_30px_rgba(13,148,136,0.55)] active:scale-95 no-underline"
        >
          <span>Panel Admin</span>
          <i data-lucide="external-link" class="w-3.5 h-3.5 opacity-80"></i>
        </a>
      </div>
    </header>

    <!-- 5. Bottom-Left Menu (Panel Admin, Privacidad, Términos, Soporte) -->
    <div class="fixed bottom-6 left-6 md:bottom-10 md:left-12 z-40 pointer-events-auto select-none">
      <div id="bottom-menu-drawer" class="hidden mb-3 p-3 w-64 rounded-2xl glass-panel border border-white/[0.12] shadow-2xl animate-pop-in flex flex-col space-y-1">
        <div class="px-3 py-2 border-b border-white/[0.06] mb-1 flex items-center justify-between">
          <div class="text-[10px] font-mono text-[#8e9dae] uppercase tracking-wider">Asistto · Humanio Engine</div>
          <span class="w-1.5 h-1.5 rounded-full bg-[#14b8a6]"></span>
        </div>

        <a href="/admin/login" class="flex items-center justify-between px-3 py-2 rounded-xl bg-[#0d9488]/15 hover:bg-[#0d9488]/25 text-[#2dd4bf] text-xs font-medium transition-all no-underline">
          <div class="flex items-center space-x-2.5">
            <i data-lucide="lock" class="w-3.5 h-3.5 text-[#2dd4bf]"></i>
            <span>Panel de Administración</span>
          </div>
          <i data-lucide="external-link" class="w-3 h-3 opacity-60"></i>
        </a>

        <button onclick="openModal('privacy')" class="w-full flex items-center justify-between px-3 py-2 rounded-xl hover:bg-white/[0.05] text-[#f8fafc] text-xs transition-colors text-left">
          <div class="flex items-center space-x-2.5">
            <i data-lucide="shield" class="w-3.5 h-3.5 text-[#8e9dae]"></i>
            <span>Política de Privacidad</span>
          </div>
          <span class="text-[10px] font-mono text-[#8e9dae]/50">DOC</span>
        </button>

        <button onclick="openModal('terms')" class="w-full flex items-center justify-between px-3 py-2 rounded-xl hover:bg-white/[0.05] text-[#f8fafc] text-xs transition-colors text-left">
          <div class="flex items-center space-x-2.5">
            <i data-lucide="file-text" class="w-3.5 h-3.5 text-[#8e9dae]"></i>
            <span>Términos de Servicio</span>
          </div>
          <span class="text-[10px] font-mono text-[#8e9dae]/50">DOC</span>
        </button>

        <button onclick="openModal('support')" class="w-full flex items-center justify-between px-3 py-2 rounded-xl hover:bg-white/[0.05] text-[#f8fafc] text-xs transition-colors text-left">
          <div class="flex items-center space-x-2.5">
            <i data-lucide="help-circle" class="w-3.5 h-3.5 text-[#8e9dae]"></i>
            <span>Centro de Soporte</span>
          </div>
          <span class="text-[10px] font-mono text-[#8e9dae]/50">HELP</span>
        </button>

        <div class="pt-2 mt-1 border-t border-white/[0.06] px-3 py-1 flex items-center justify-between text-[9px] font-mono text-[#8e9dae]/60">
          <span>META TECH PROVIDER</span>
          <span class="text-[#14b8a6]">APP: ASISTTO-CHATBOT</span>
        </div>
      </div>

      <button onclick="toggleBottomMenu()" class="group flex items-center space-x-2.5 px-3.5 py-2 rounded-full glass-panel border border-white/[0.1] hover:border-[#14b8a6]/40 text-[#f8fafc] text-xs font-mono tracking-wider transition-all duration-200 hover:shadow-[0_0_20px_rgba(20,184,166,0.25)] active:scale-95">
        <span class="w-2 h-2 rounded-full bg-[#14b8a6] shadow-[0_0_8px_#14b8a6]"></span>
        <span class="text-[11px] uppercase text-[#8e9dae] group-hover:text-[#f8fafc] transition-colors">Sistema & Legal</span>
        <i id="bottom-menu-chevron" data-lucide="chevron-up" class="w-3.5 h-3.5 text-[#8e9dae] transition-transform duration-300"></i>
      </button>
    </div>

    <!-- 6. Side Chapter Rail -->
    <nav class="fixed right-6 md:right-12 top-1/2 -translate-y-1/2 z-30 hidden md:flex flex-col space-y-5 pointer-events-auto">
      <button onclick="jumpToChapter(0)" class="chapter-btn group flex items-center justify-end space-x-3 text-right focus:outline-none" data-idx="0">
        <span class="chapter-label text-xs font-mono tracking-wider text-[#8e9dae]/50 opacity-0 group-hover:opacity-100 transition-all">El Manifiesto</span>
        <span class="chapter-num text-[11px] font-mono text-[#8e9dae]/60 group-hover:text-[#f8fafc]">01</span>
        <div class="relative flex items-center justify-center w-3 h-3">
          <div class="chapter-dot rounded-full w-1 h-1 bg-white/20 group-hover:bg-white/60 transition-all duration-300"></div>
        </div>
      </button>
      <button onclick="jumpToChapter(1)" class="chapter-btn group flex items-center justify-end space-x-3 text-right focus:outline-none" data-idx="1">
        <span class="chapter-label text-xs font-mono tracking-wider text-[#8e9dae]/50 opacity-0 group-hover:opacity-100 transition-all">Simulador 3D</span>
        <span class="chapter-num text-[11px] font-mono text-[#8e9dae]/60 group-hover:text-[#f8fafc]">02</span>
        <div class="relative flex items-center justify-center w-3 h-3">
          <div class="chapter-dot rounded-full w-1 h-1 bg-white/20 group-hover:bg-white/60 transition-all duration-300"></div>
        </div>
      </button>
      <button onclick="jumpToChapter(2)" class="chapter-btn group flex items-center justify-end space-x-3 text-right focus:outline-none" data-idx="2">
        <span class="chapter-label text-xs font-mono tracking-wider text-[#8e9dae]/50 opacity-0 group-hover:opacity-100 transition-all">Habilidades Core</span>
        <span class="chapter-num text-[11px] font-mono text-[#8e9dae]/60 group-hover:text-[#f8fafc]">03</span>
        <div class="relative flex items-center justify-center w-3 h-3">
          <div class="chapter-dot rounded-full w-1 h-1 bg-white/20 group-hover:bg-white/60 transition-all duration-300"></div>
        </div>
      </button>
      <button onclick="jumpToChapter(3)" class="chapter-btn group flex items-center justify-end space-x-3 text-right focus:outline-none" data-idx="3">
        <span class="chapter-label text-xs font-mono tracking-wider text-[#8e9dae]/50 opacity-0 group-hover:opacity-100 transition-all">Activación</span>
        <span class="chapter-num text-[11px] font-mono text-[#8e9dae]/60 group-hover:text-[#f8fafc]">04</span>
        <div class="relative flex items-center justify-center w-3 h-3">
          <div class="chapter-dot rounded-full w-1 h-1 bg-white/20 group-hover:bg-white/60 transition-all duration-300"></div>
        </div>
      </button>
    </nav>

    <!-- 7. Pinned Sections Container -->
    <div class="relative w-full h-full z-10">

      <!-- SECTION 01: EL MANIFIESTO -->
      <section id="section-0" class="absolute inset-0 w-full h-full flex flex-col justify-center items-center px-6 md:px-16 pointer-events-none transition-opacity duration-300">
        <div class="max-w-4xl mx-auto text-center flex flex-col items-center">
          <div class="inline-flex items-center space-x-2 px-4 py-1.5 rounded-full bg-[#0d9488]/15 border border-[#14b8a6]/30 text-xs font-mono text-[#2dd4bf] mb-6 md:mb-8 backdrop-blur-md shadow-[0_0_20px_rgba(13,148,136,0.2)]">
            <span class="w-2 h-2 rounded-full bg-[#14b8a6] animate-ping"></span>
            <span>META TECH PROVIDER AUTORIZADO</span>
          </div>

          <h1 class="font-display-modern text-4xl sm:text-6xl md:text-7xl lg:text-8xl font-extrabold tracking-tight text-[#f8fafc] leading-[1.05] mb-6 md:mb-8">
            Automatiza tu WhatsApp <span class="text-transparent bg-clip-text bg-gradient-to-r from-[#2dd4bf] via-[#14b8a6] to-[#0d9488] glow-teal font-serif-luxury italic font-normal">con Inteligencia Artificial.</span>
          </h1>

          <p class="max-w-2xl text-sm sm:text-base md:text-lg text-[#8e9dae] font-normal leading-relaxed mb-8 md:mb-12">
            Asistto conecta el canal de WhatsApp de tu negocio con agentes virtuales autónomos. Responde dudas frecuentes 24/7, califica prospectos en tu CRM y agenda citas reales en tu Google Calendar sin esfuerzo humano.
          </p>

          <div class="flex flex-col sm:flex-row items-center gap-4 mb-12">
            <button onclick="jumpToChapter(1)" class="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-8 py-3.5 rounded-full bg-[#0d9488] hover:bg-[#0f766e] text-white font-semibold text-sm tracking-wide transition-all duration-300 shadow-[0_0_30px_rgba(13,148,136,0.4)] hover:scale-105">
              <span>Ver Simulador en Vivo</span>
              <i data-lucide="arrow-down" class="w-4 h-4"></i>
            </button>
            <a href="/admin/login" class="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-8 py-3.5 rounded-full bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.12] text-[#f8fafc] font-semibold text-sm tracking-wide transition-all duration-300 no-underline">
              <span>Acceder al Panel Admin</span>
            </a>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-6 w-full max-w-3xl text-left">
            <div class="p-4 rounded-xl glass-panel flex items-start space-x-3">
              <div class="p-2 rounded-lg bg-[#0d9488]/20 text-[#2dd4bf] shrink-0">
                <i data-lucide="bot" class="w-4 h-4"></i>
              </div>
              <div>
                <h4 class="text-xs font-mono font-semibold text-[#f8fafc] uppercase">Respuestas 24/7</h4>
                <p class="text-[11px] text-[#8e9dae] leading-snug mt-0.5">Atención instantánea basada en tu catálogo y FAQs.</p>
              </div>
            </div>
            <div class="p-4 rounded-xl glass-panel flex items-start space-x-3">
              <div class="p-2 rounded-lg bg-[#dfb758]/20 text-[#dfb758] shrink-0">
                <i data-lucide="calendar" class="w-4 h-4"></i>
              </div>
              <div>
                <h4 class="text-xs font-mono font-semibold text-[#f8fafc] uppercase">Google Calendar</h4>
                <p class="text-[11px] text-[#8e9dae] leading-snug mt-0.5">Verificación de disponibilidad y agendamiento real.</p>
              </div>
            </div>
            <div class="p-4 rounded-xl glass-panel flex items-start space-x-3">
              <div class="p-2 rounded-lg bg-[#14b8a6]/20 text-[#14b8a6] shrink-0">
                <i data-lucide="shield-check" class="w-4 h-4"></i>
              </div>
              <div>
                <h4 class="text-xs font-mono font-semibold text-[#f8fafc] uppercase">Oficial Meta API</h4>
                <p class="text-[11px] text-[#8e9dae] leading-snug mt-0.5">Seguridad empresarial y cifrado de datos en reposo.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- SECTION 02: SIMULADOR 3D -->
      <section id="section-1" class="absolute inset-0 w-full h-full flex flex-col justify-center items-center px-6 md:px-16 pointer-events-none opacity-0 transition-opacity duration-300">
        <div class="max-w-6xl w-full mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          <div class="lg:col-span-6 flex flex-col">
            <div class="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.1] text-xs font-mono text-[#2dd4bf] mb-4 w-fit">
              <span class="w-1.5 h-1.5 rounded-full bg-[#14b8a6]"></span>
              <span>CAPÍTULO 02 — SIMULADOR EN TIEMPO REAL</span>
            </div>
            <h2 class="font-display-modern text-3xl sm:text-5xl font-bold text-[#f8fafc] leading-tight mb-4">
              Conversaciones naturales. <span class="font-serif-luxury italic font-normal text-[#14b8a6]">Resultados reales.</span>
            </h2>
            <p class="text-xs sm:text-sm text-[#8e9dae] leading-relaxed mb-6 font-sans">
              Prueba cómo interactúa Asistto directamente desde el teléfono interactivo a la derecha. La IA comprende lenguaje coloquial, resuelve dudas y agenda reuniones sin intermediarios.
            </p>

            <div class="flex flex-col space-y-3 mb-6">
              <div class="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                <div class="p-2 rounded-lg bg-[#0d9488]/15 text-[#2dd4bf] shrink-0 mt-0.5">
                  <i data-lucide="sparkles" class="w-3.5 h-3.5"></i>
                </div>
                <div>
                  <h4 class="text-xs font-semibold text-[#f8fafc]">IA Entrenada para tu Negocio</h4>
                  <p class="text-[11px] text-[#8e9dae] mt-0.5">Aprende tus precios, servicios, horarios y políticas sin alucinaciones.</p>
                </div>
              </div>
              <div class="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                <div class="p-2 rounded-lg bg-[#dfb758]/15 text-[#dfb758] shrink-0 mt-0.5">
                  <i data-lucide="calendar" class="w-3.5 h-3.5"></i>
                </div>
                <div>
                  <h4 class="text-xs font-semibold text-[#f8fafc]">Sincronización Bidireccional</h4>
                  <p class="text-[11px] text-[#8e9dae] mt-0.5">Consulta espacios en Google Calendar y añade la cita automáticamente.</p>
                </div>
              </div>
              <div class="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                <div class="p-2 rounded-lg bg-[#14b8a6]/15 text-[#14b8a6] shrink-0 mt-0.5">
                  <i data-lucide="shield-check" class="w-3.5 h-3.5"></i>
                </div>
                <div>
                  <h4 class="text-xs font-semibold text-[#f8fafc]">Control y Supervisión Humana</h4>
                  <p class="text-[11px] text-[#8e9dae] mt-0.5">Toma el control de cualquier chat desde el panel web cuando lo desees.</p>
                </div>
              </div>
            </div>

            <button onclick="jumpToChapter(2)" class="w-fit inline-flex items-center space-x-2 text-xs font-mono font-semibold text-[#2dd4bf] hover:text-[#f8fafc] transition-colors">
              <span>Conocer Habilidades Técnicas</span>
              <i data-lucide="arrow-right" class="w-3.5 h-3.5"></i>
            </button>
          </div>

          <!-- 3D Phone Mockup -->
          <div class="lg:col-span-6 flex justify-center perspective-stage">
            <div class="relative w-full max-w-[340px] sm:max-w-[360px] rounded-[40px] bg-[#0b1016] border-[8px] sm:border-[10px] border-[#1e293b] shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9),0_0_30px_rgba(13,148,136,0.2)] overflow-hidden flex flex-col h-[520px] sm:h-[560px]">
              <div class="absolute top-0 left-1/2 -translate-x-1/2 w-32 h-4 bg-[#1e293b] rounded-b-xl z-30"></div>
              
              <div class="bg-[#075e54] text-white px-4 pt-6 pb-2.5 flex items-center justify-between shadow-md z-20 shrink-0">
                <div class="flex items-center space-x-2.5">
                  <div class="w-8 h-8 rounded-full bg-[#14b8a6]/20 border border-[#2dd4bf]/40 flex items-center justify-center font-bold text-xs text-[#2dd4bf]">A</div>
                  <div>
                    <div class="text-xs font-semibold leading-none flex items-center space-x-1">
                      <span>Asistto Bot</span>
                      <span class="w-1.5 h-1.5 rounded-full bg-[#2dd4bf]"></span>
                    </div>
                    <div class="text-[10px] text-white/75 mt-0.5">en línea · IA activa</div>
                  </div>
                </div>
                <button onclick="runStandaloneDemo('funcionamiento')" class="p-1 rounded-full hover:bg-white/10 text-white/80 transition-colors">
                  <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
                </button>
              </div>

              <div id="standalone-chat-body" class="flex-1 p-3 overflow-y-auto flex flex-col space-y-2.5 bg-[#0d141c] no-scrollbar relative" style="background-image: radial-gradient(#1e293b 1px, transparent 1px); background-size: 16px 16px;">
                <div class="chat-msg self-start bg-[#1f2c34] text-[#e9edef] p-2.5 rounded-xl rounded-tl-none border border-white/[0.04] text-xs leading-relaxed max-w-[85%]">
                  ¡Hola! Soy Asistto, tu asistente inteligente para WhatsApp. ¿En qué te puedo ayudar hoy?
                  <div class="text-[9px] text-white/50 text-right mt-1 font-mono">10:00 AM</div>
                </div>
                <div id="standalone-typing" class="hidden self-start bg-[#1f2c34] px-3.5 py-2.5 rounded-xl rounded-tl-none flex items-center space-x-1 text-white/60 border border-white/[0.04]">
                  <span class="w-1.5 h-1.5 rounded-full bg-[#2dd4bf] animate-bounce-1"></span>
                  <span class="w-1.5 h-1.5 rounded-full bg-[#2dd4bf] animate-bounce-2"></span>
                  <span class="w-1.5 h-1.5 rounded-full bg-[#2dd4bf] animate-bounce-3"></span>
                </div>
              </div>

              <div class="p-2.5 bg-[#111b21] border-t border-white/[0.08] flex flex-col space-y-1.5 shrink-0">
                <div class="text-[9px] font-mono text-[#8e9dae]/70 uppercase tracking-wider px-1">Simulaciones Interactivas</div>
                <button onclick="runStandaloneDemo('funcionamiento')" class="demo-btn w-full text-left px-2.5 py-1.5 rounded-lg bg-white/[0.04] hover:bg-[#0d9488]/20 border border-white/[0.06] hover:border-[#14b8a6]/40 text-[11px] text-[#f8fafc] font-medium flex items-center justify-between transition-colors">
                  <span class="flex items-center space-x-1.5">
                    <i data-lucide="sparkles" class="w-3 h-3 text-[#2dd4bf]"></i>
                    <span>¿Cómo funciona Asistto?</span>
                  </span>
                  <span class="text-[9px] font-mono text-[#2dd4bf]">PROBAR</span>
                </button>
                <button onclick="runStandaloneDemo('agenda')" class="demo-btn w-full text-left px-2.5 py-1.5 rounded-lg bg-white/[0.04] hover:bg-[#0d9488]/20 border border-white/[0.06] hover:border-[#14b8a6]/40 text-[11px] text-[#f8fafc] font-medium flex items-center justify-between transition-colors">
                  <span class="flex items-center space-x-1.5">
                    <i data-lucide="calendar" class="w-3 h-3 text-[#dfb758]"></i>
                    <span>Agendar Cita en Google Calendar</span>
                  </span>
                  <span class="text-[9px] font-mono text-[#dfb758]">DEMO</span>
                </button>
                <button onclick="runStandaloneDemo('capacidades')" class="demo-btn w-full text-left px-2.5 py-1.5 rounded-lg bg-white/[0.04] hover:bg-[#0d9488]/20 border border-white/[0.06] hover:border-[#14b8a6]/40 text-[11px] text-[#f8fafc] font-medium flex items-center justify-between transition-colors">
                  <span class="flex items-center space-x-1.5">
                    <i data-lucide="zap" class="w-3 h-3 text-[#14b8a6]"></i>
                    <span>Integraciones & Canales</span>
                  </span>
                  <span class="text-[9px] font-mono text-[#14b8a6]">VER</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- SECTION 03: HABILIDADES CORE -->
      <section id="section-2" class="absolute inset-0 w-full h-full flex flex-col justify-center items-center px-6 md:px-16 pointer-events-none opacity-0 transition-opacity duration-300">
        <div class="max-w-6xl w-full mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          <div class="lg:col-span-5 flex flex-col">
            <div class="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.1] text-xs font-mono text-[#14b8a6] mb-4 w-fit">
              <span class="w-1.5 h-1.5 rounded-full bg-[#14b8a6]"></span>
              <span>CAPÍTULO 03 — CAPACIDADES CORE</span>
            </div>
            <h2 class="font-display-modern text-3xl sm:text-5xl font-bold text-[#f8fafc] leading-tight mb-4">
              Infraestructura inteligente. <span class="font-serif-luxury italic font-normal text-[#2dd4bf]">Control total.</span>
            </h2>
            <p class="text-xs sm:text-sm text-[#8e9dae] leading-relaxed mb-6 font-sans">
              Cada módulo ha sido diseñado para operar de forma autónoma con estándares de seguridad bancaria y conexión directa a la API oficial de WhatsApp Cloud.
            </p>

            <div id="standalone-feature-list" class="flex flex-col space-y-2">
              <!-- Injected by JS -->
            </div>
          </div>

          <div class="lg:col-span-7 flex justify-center perspective-stage">
            <div id="standalone-feature-card" class="w-full max-w-lg p-6 sm:p-8 rounded-2xl glass-panel relative overflow-hidden transition-all duration-500 border border-white/[0.1] shadow-2xl">
              <div class="absolute -top-12 -right-12 w-48 h-48 bg-[#0d9488]/15 rounded-full filter blur-3xl pointer-events-none"></div>
              
              <div class="flex justify-between items-center mb-6">
                <span id="feat-card-cat" class="text-[10px] font-mono uppercase tracking-widest text-[#2dd4bf] px-3 py-1 rounded bg-[#0d9488]/15 border border-[#14b8a6]/30">Inteligencia Conversacional</span>
                <span id="feat-card-badge" class="text-xs font-mono text-[#dfb758] px-2.5 py-1 rounded bg-[#dfb758]/10 border border-[#dfb758]/20">Latencia &lt; 1.2s</span>
              </div>

              <h3 id="feat-card-title" class="font-display-modern text-2xl sm:text-3xl font-bold text-[#f8fafc] mb-3">Atención 24/7 Autónoma</h3>
              <p id="feat-card-desc" class="text-xs sm:text-sm text-[#8e9dae] leading-relaxed mb-6 font-sans">
                Responde consultas frecuentes al instante utilizando la base de conocimiento y catálogos cargados específicamente para tu negocio.
              </p>

              <div class="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] mb-6">
                <div class="text-[10px] font-mono text-[#8e9dae] uppercase tracking-wider mb-3">Especificaciones & Garantías Técnicas</div>
                <div id="feat-card-specs" class="flex flex-col space-y-2 text-xs text-[#f8fafc]/90">
                  <!-- Injected by JS -->
                </div>
              </div>

              <div class="flex items-center justify-between text-[10px] font-mono text-[#8e9dae]/70 border-t border-white/[0.06] pt-4">
                <span>META TECH PROVIDER AUTORIZADO</span>
                <span class="text-[#2dd4bf]">DOMINIO: BOT.HUMANIO.DIGITAL</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- SECTION 04: ACTIVACIÓN -->
      <section id="section-3" class="absolute inset-0 w-full h-full flex flex-col justify-center items-center px-6 md:px-16 pointer-events-none opacity-0 transition-opacity duration-300">
        <div class="max-w-6xl w-full mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          <div class="lg:col-span-6 flex flex-col">
            <div class="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.1] text-xs font-mono text-[#dfb758] mb-4 w-fit">
              <span class="w-1.5 h-1.5 rounded-full bg-[#dfb758]"></span>
              <span>CAPÍTULO 04 — ACTIVACIÓN & ONBOARDING</span>
            </div>
            <h2 class="font-display-modern text-3xl sm:text-5xl font-bold text-[#f8fafc] leading-tight mb-4">
              Despliega tu Asistente <span class="font-serif-luxury italic font-normal text-[#14b8a6]">en minutos.</span>
            </h2>
            <p class="text-xs sm:text-sm text-[#8e9dae] leading-relaxed mb-6 font-sans">
              Conecta tu cuenta de WhatsApp Business oficial y comienza a atender prospectos y agendar citas en Google Calendar hoy mismo.
            </p>

            <div class="flex flex-col space-y-3 mb-6">
              <div class="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                <div class="w-5 h-5 rounded-full bg-[#0d9488]/20 border border-[#14b8a6]/40 flex items-center justify-center font-mono text-[10px] text-[#2dd4bf] shrink-0 mt-0.5">1</div>
                <div>
                  <h4 class="text-xs font-semibold text-[#f8fafc]">Vinculación WhatsApp Cloud API</h4>
                  <p class="text-[11px] text-[#8e9dae] mt-0.5">Autorización rápida y segura a través de Meta Tech Provider.</p>
                </div>
              </div>
              <div class="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                <div class="w-5 h-5 rounded-full bg-[#dfb758]/20 border border-[#dfb758]/40 flex items-center justify-center font-mono text-[10px] text-[#dfb758] shrink-0 mt-0.5">2</div>
                <div>
                  <h4 class="text-xs font-semibold text-[#f8fafc]">Carga de Catálogo & Google Calendar</h4>
                  <p class="text-[11px] text-[#8e9dae] mt-0.5">Configuración de respuestas inteligentes y horarios de atención.</p>
                </div>
              </div>
              <div class="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-start space-x-3">
                <div class="w-5 h-5 rounded-full bg-[#14b8a6]/20 border border-[#14b8a6]/40 flex items-center justify-center font-mono text-[10px] text-[#14b8a6] shrink-0 mt-0.5">3</div>
                <div>
                  <h4 class="text-xs font-semibold text-[#f8fafc]">Acceso al Panel de Administración</h4>
                  <p class="text-[11px] text-[#8e9dae] mt-0.5">Monitoreo en tiempo real, gestión de leads y métricas de conversión.</p>
                </div>
              </div>
            </div>

            <a href="/admin/login" class="w-fit inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.1] text-xs font-mono text-[#f8fafc] transition-all no-underline">
              <i data-lucide="lock" class="w-3.5 h-3.5 text-[#2dd4bf]"></i>
              <span>Acceder directamente al Panel Clientes</span>
              <i data-lucide="external-link" class="w-3 h-3 opacity-60"></i>
            </a>
          </div>

          <div class="lg:col-span-6 flex justify-center perspective-stage">
            <form onsubmit="handleActivationSubmit(event)" class="w-full max-w-md p-6 sm:p-8 rounded-2xl glass-panel relative border border-white/[0.12] shadow-2xl">
              <div class="flex items-center justify-between mb-6">
                <div class="flex items-center space-x-2">
                  <i data-lucide="message-circle" class="w-5 h-5 text-[#2dd4bf]"></i>
                  <h3 class="font-display-modern text-xl text-[#f8fafc] font-bold">Solicitar Activación</h3>
                </div>
                <span class="text-[10px] font-mono text-[#2dd4bf] px-2 py-0.5 rounded bg-[#0d9488]/15 border border-[#14b8a6]/30">Setup Rápido</span>
              </div>

              <div class="mb-4">
                <label class="block text-[11px] font-mono text-[#8e9dae] mb-1.5 uppercase">Nombre de tu Empresa / Negocio</label>
                <input id="act-name" type="text" required placeholder="Ej. Clínica Dental / Estudio Digital" class="w-full px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/[0.1] text-xs text-[#f8fafc] placeholder-[#8e9dae]/50 focus:outline-none focus:border-[#14b8a6] transition-colors" />
              </div>

              <div class="mb-4">
                <label class="block text-[11px] font-mono text-[#8e9dae] mb-1.5 uppercase">Número de WhatsApp para Conectar</label>
                <input id="act-phone" type="tel" required placeholder="+52 (667) 000-0000" class="w-full px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/[0.1] text-xs text-[#f8fafc] placeholder-[#8e9dae]/50 focus:outline-none focus:border-[#14b8a6] transition-colors" />
              </div>

              <div class="mb-6">
                <label class="block text-[11px] font-mono text-[#8e9dae] mb-1.5 uppercase">¿Qué procesos deseas automatizar?</label>
                <textarea id="act-notes" rows="3" placeholder="Ej. Respuestas de catálogo, cotizaciones y agendamiento de citas en Google Calendar." class="w-full px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/[0.1] text-xs text-[#f8fafc] placeholder-[#8e9dae]/50 focus:outline-none focus:border-[#14b8a6] transition-colors resize-none"></textarea>
              </div>

              <button type="submit" class="w-full py-3.5 rounded-xl bg-[#0d9488] hover:bg-[#0f766e] text-white font-bold text-xs uppercase tracking-wider flex items-center justify-center space-x-2 transition-all shadow-[0_0_25px_rgba(13,148,136,0.4)] active:scale-98">
                <i data-lucide="send" class="w-4 h-4"></i>
                <span>Contactar con Equipo Técnico</span>
              </button>
            </form>
          </div>
        </div>
      </section>

    </div>
  </main>

  <!-- MODAL COMPLIANCE -->
  <div id="compliance-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 md:p-10 pointer-events-auto">
    <div class="absolute inset-0 bg-[#080c10]/80 backdrop-blur-md" onclick="closeModal()"></div>
    <div class="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto glass-panel rounded-2xl p-6 sm:p-8 border border-white/[0.12] shadow-2xl z-10 no-scrollbar">
      <div class="flex items-center justify-between border-b border-white/[0.08] pb-4 mb-6 sticky top-0 bg-[#111822]/90 backdrop-blur-md pt-1 -mt-1 z-20">
        <div class="flex items-center space-x-2.5">
          <i data-lucide="shield-check" class="w-5 h-5 text-[#14b8a6]"></i>
          <h2 id="modal-title" class="font-display-modern text-xl sm:text-2xl font-bold text-[#f8fafc]">Documento</h2>
        </div>
        <button onclick="closeModal()" class="p-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-[#8e9dae] hover:text-white transition-colors">
          <i data-lucide="x" class="w-4 h-4"></i>
        </button>
      </div>
      <p id="modal-lead" class="text-xs sm:text-sm text-[#8e9dae] leading-relaxed mb-6 font-sans"></p>
      <div id="modal-meta" class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mb-6"></div>
      <div id="modal-sections" class="flex flex-col space-y-6"></div>
      <div class="mt-8 pt-6 border-t border-white/[0.08] flex flex-col sm:flex-row items-center justify-between gap-4">
        <div class="flex items-center space-x-2 text-xs text-[#8e9dae]">
          <i data-lucide="mail" class="w-4 h-4 text-[#14b8a6]"></i>
          <span>contacto@humanio.digital</span>
        </div>
        <button onclick="closeModal()" class="px-5 py-2 rounded-xl bg-white/[0.06] hover:bg-white/[0.1] text-xs font-semibold text-white transition-colors">Entendido</button>
      </div>
    </div>
  </div>

  <!-- SCRIPT -->
  <script>
    const FEATURES_DATA = [
      {
        id: 'atencion-247',
        title: 'Atención 24/7 Autónoma',
        category: 'Inteligencia Conversacional',
        desc: 'Responde consultas frecuentes al instante utilizando la base de conocimiento y catálogos cargados específicamente para tu negocio.',
        badge: 'Latencia < 1.2s',
        specs: ['Entrenamiento con PDFs y webs', 'Respuestas contextuales sin alucinaciones', 'Soporte multilingüe natural']
      },
      {
        id: 'agenda-citas',
        title: 'Agenda en Google Calendar',
        category: 'Sincronización Nativa',
        desc: 'Conexión nativa y segura con Google Calendar para verificar horarios libres, agendar, reprogramar y cancelar citas de forma autónoma.',
        badge: 'API Oficial Google',
        specs: ['Lectura de disponibilidad en tiempo real', 'Envío de confirmación automática', 'Prevención de empalmes']
      },
      {
        id: 'calificacion-crm',
        title: 'Calificación de Leads & CRM',
        category: 'Ventas & Captura',
        desc: 'Detecta la intención de compra del usuario, captura sus datos clave y guárdalos automáticamente en tu CRM o webhook preferido.',
        badge: 'Webhooks & Zapier',
        specs: ['Captura de nombre, email y teléfono', 'Etiquetado automático de interés', 'Disparo de eventos en tiempo real']
      },
      {
        id: 'handoff-humano',
        title: 'Handoff a Equipo Humano',
        category: 'Escalamiento Inteligente',
        desc: 'Cuando la IA detecta solicitudes de soporte técnico o situaciones complejas, deriva la conversación inmediatamente a tu equipo humano.',
        badge: 'Control Total',
        specs: ['Pausa del bot en 1 clic', 'Notificaciones a agentes por WhatsApp', 'Historial unificado de conversación']
      }
    ];

    let currentFeatIdx = 0;

    function initFeatures() {
      const list = document.getElementById('standalone-feature-list');
      list.innerHTML = FEATURES_DATA.map((f, i) => `
        <button onclick="selectFeature(${i})" class="feat-btn group flex items-center justify-between p-3.5 rounded-xl border text-left transition-all duration-200 ${i === currentFeatIdx ? 'bg-[#0d9488]/15 border-[#14b8a6]/40 text-[#f8fafc]' : 'bg-white/[0.02] border-white/[0.06] text-[#8e9dae] hover:bg-white/[0.04] hover:text-[#f8fafc]'}" data-i="${i}">
          <div class="flex items-center space-x-3">
            <div class="p-2 rounded-lg ${i === currentFeatIdx ? 'bg-[#0d9488]/30 text-[#2dd4bf]' : 'bg-white/[0.04] text-[#8e9dae]'}">
              <i data-lucide="${i === 0 ? 'message-square' : i === 1 ? 'calendar' : i === 2 ? 'database' : 'users-2'}" class="w-4 h-4"></i>
            </div>
            <div>
              <div class="text-xs font-semibold">${f.title}</div>
              <div class="text-[10px] text-[#8e9dae] font-mono">${f.category}</div>
            </div>
          </div>
          <i data-lucide="chevron-right" class="w-4 h-4 transition-transform ${i === currentFeatIdx ? 'text-[#2dd4bf] translate-x-1' : 'opacity-30'}"></i>
        </button>
      `).join('');

      renderSelectedFeature();
    }

    function selectFeature(idx) {
      currentFeatIdx = idx;
      initFeatures();
      lucide.createIcons();
    }

    function renderSelectedFeature() {
      const f = FEATURES_DATA[currentFeatIdx];
      document.getElementById('feat-card-cat').innerText = f.category;
      document.getElementById('feat-card-badge').innerText = f.badge;
      document.getElementById('feat-card-title').innerText = f.title;
      document.getElementById('feat-card-desc').innerText = f.desc;
      document.getElementById('feat-card-specs').innerHTML = f.specs.map(s => `
        <div class="flex items-center space-x-2">
          <i data-lucide="check-circle-2" class="w-3.5 h-3.5 text-[#14b8a6] shrink-0"></i>
          <span>${s}</span>
        </div>
      `).join('');
    }

    // Interactive Demo Scripts
    const PATHS = {
      funcionamiento: [
        { type: 'user', text: '¿Cómo funciona Asistto?' },
        { type: 'bot', text: 'Es muy sencillo. Vinculamos tu número de WhatsApp a un asistente de IA entrenado específicamente con la información de tu negocio.' },
        { type: 'bot', text: 'El asistente responde dudas frecuentes, captura prospectos y agenda citas reales en tu calendario. Si hay algún caso complejo, lo deriva a una persona en tu panel admin.' }
      ],
      agenda: [
        { type: 'user', text: 'Quiero agendar una llamada con ustedes' },
        { type: 'bot', text: '¡Excelente! Estaré encantado de ayudarte. ¿A nombre de quién registro la llamada?' },
        { type: 'user', text: 'Miguel González' },
        { type: 'bot', text: 'Muchas gracias, Miguel. ¿Qué día y hora te queda mejor?' },
        { type: 'user', text: 'Mañana a las 10:00 AM' },
        { type: 'bot', text: 'He verificado la disponibilidad en mi agenda de Google Calendar y ese horario está libre.' },
        { type: 'bot', text: 'Listo, Miguel. Quedó agendada tu llamada para el día de mañana a las 10:00 AM. ¡Nos vemos pronto!' }
      ],
      capacidades: [
        { type: 'user', text: '¿Qué integraciones y canales soportan?' },
        { type: 'bot', text: 'Asistto opera como Meta Tech Provider sobre la API Oficial de WhatsApp Cloud.' },
        { type: 'bot', text: 'Nos integramos con Google Calendar, Webhooks REST, CRMs (HubSpot, Salesforce, Zoho) y contamos con Panel de Control multi-agente.' }
      ]
    };

    let isDemoRunning = false;

    async function runStandaloneDemo(key) {
      if (isDemoRunning) return;
      isDemoRunning = true;

      const chatBody = document.getElementById('standalone-chat-body');
      const typingEl = document.getElementById('standalone-typing');
      const buttons = document.querySelectorAll('.demo-btn');
      buttons.forEach(b => b.disabled = true);

      chatBody.innerHTML = `
        <div class="chat-msg self-start bg-[#1f2c34] text-[#e9edef] p-2.5 rounded-xl rounded-tl-none border border-white/[0.04] text-xs leading-relaxed max-w-[85%]">
          ¡Hola! Soy Asistto, tu asistente inteligente para WhatsApp. ¿En qué te puedo ayudar hoy?
          <div class="text-[9px] text-white/50 text-right mt-1 font-mono">10:00 AM</div>
        </div>
      `;

      const steps = PATHS[key];
      for (const step of steps) {
        if (step.type === 'user') {
          await new Promise(r => setTimeout(r, 600));
          const el = document.createElement('div');
          el.className = 'chat-msg self-end bg-[#005c4b] text-white p-2.5 rounded-xl rounded-tr-none text-xs leading-relaxed max-w-[85%] animate-pop-in shadow-sm';
          el.innerHTML = `<div>${step.text}</div><div class="text-[9px] text-white/50 text-right mt-1 font-mono">${getCurrTime()}</div>`;
          chatBody.appendChild(el);
          chatBody.scrollTop = chatBody.scrollHeight;
        } else {
          typingEl.classList.remove('hidden');
          chatBody.appendChild(typingEl);
          chatBody.scrollTop = chatBody.scrollHeight;

          const typingTime = Math.max(900, Math.min(1800, step.text.length * 12));
          await new Promise(r => setTimeout(r, typingTime));

          typingEl.classList.add('hidden');
          const el = document.createElement('div');
          el.className = 'chat-msg self-start bg-[#1f2c34] text-[#e9edef] p-2.5 rounded-xl rounded-tl-none border border-white/[0.04] text-xs leading-relaxed max-w-[85%] animate-pop-in shadow-sm';
          el.innerHTML = `<div class="whitespace-pre-line">${step.text}</div><div class="text-[9px] text-white/50 text-right mt-1 font-mono">${getCurrTime()}</div>`;
          chatBody.appendChild(el);
          chatBody.scrollTop = chatBody.scrollHeight;
          await new Promise(r => setTimeout(r, 400));
        }
      }

      buttons.forEach(b => b.disabled = false);
      isDemoRunning = false;
    }

    function getCurrTime() {
      const now = new Date();
      let hours = now.getHours();
      let minutes = now.getMinutes();
      const ampm = hours >= 12 ? 'PM' : 'AM';
      hours = hours % 12 || 12;
      return `${hours}:${minutes < 10 ? '0' + minutes : minutes} ${ampm}`;
    }

    // Modals
    const COMPLIANCE = {
      privacy: {
        title: 'Política de Privacidad',
        lead: 'Esta política de privacidad corresponde a Asistto by Humanio, la app web publicada en https://bot.humanio.digital/ y la app de Meta llamada Asistto-chatbot.',
        meta: [
          { label: 'Producto', value: 'Asistto by Humanio' },
          { label: 'App de Meta', value: 'Asistto-chatbot' },
          { label: 'Negocio responsable', value: 'Humanio' },
          { label: 'Dominios oficiales', value: 'humanio.digital y bot.humanio.digital' },
          { label: 'Contacto de privacidad', value: 'contacto@humanio.digital' },
          { label: 'Última actualización', value: '2026' }
        ],
        sections: [
          { heading: 'Relación entre esta política, la app y el negocio', body: 'Humanio es el negocio responsable de Asistto by Humanio y controla esta política de privacidad. Asistto by Humanio es una plataforma de automatización de atención, ventas, agenda e integraciones por WhatsApp para negocios. La app de Meta asociada a este producto se llama Asistto-chatbot y usa el dominio público bot.humanio.digital.' },
          { heading: 'Responsable de los datos', body: 'Humanio determina los propósitos y medios del tratamiento de los datos procesados por Asistto by Humanio para operar la plataforma. Cuando un negocio cliente conecta su WhatsApp Business Account, ese negocio conserva responsabilidad sobre sus conversaciones, avisos, opt-in, plantillas y cumplimiento aplicable frente a sus usuarios.' },
          { heading: 'Datos que procesamos', body: 'Procesamos mensajes de WhatsApp, identificadores técnicos como wa_id y phone_number_id, datos de contacto que el usuario comparte, registros de conversación, leads, citas e integraciones configuradas por cada negocio.' },
          { heading: 'Uso de los datos', body: 'Usamos estos datos solo para operar el bot del negocio, responder mensajes, registrar prospectos, generar citas, diagnosticar errores y prestar soporte autorizado.' },
          { heading: 'IA y entrenamiento', body: 'Los datos de WhatsApp no se venden ni se usan para entrenar modelos generales de IA. Si un proveedor de IA procesa mensajes, lo hace como tercero de servicio para responder al negocio configurado.' },
          { heading: 'Seguridad', body: 'Los secretos de integraciones se cifran en reposo. No mostramos tokens completos en el panel ni en documentos operativos.' }
        ]
      },
      terms: {
        title: 'Términos de Servicio',
        lead: 'Estos términos describen el uso de Asistto by Humanio como plataforma de automatización de WhatsApp para negocios.',
        sections: [
          { heading: 'Servicio', body: 'Asistto permite configurar bots de atención, ventas, agenda, CRM e integraciones para negocios que usan WhatsApp Business Platform.' },
          { heading: 'Responsabilidad del negocio', body: 'Cada negocio es responsable de tener permisos, avisos, opt-in, plantillas aprobadas y contenido permitido conforme a las políticas de WhatsApp y leyes aplicables.' },
          { heading: 'Uso aceptable', body: 'No debe usarse para spam, suplantación, productos prohibidos, solicitud de datos sensibles innecesarios ni casos donde la ley exija controles especiales no configurados.' },
          { heading: 'Escalación humana', body: 'La automatización debe mantener una ruta clara de contacto humano cuando el caso lo requiera.' }
        ]
      },
      support: {
        title: 'Centro de Soporte & Ayuda',
        lead: 'Canal de asistencia operativa para negocios que usan Asistto by Humanio.',
        sections: [
          { heading: 'Contacto Técnico', body: 'Para soporte operativo, escribe a contacto@humanio.digital con el nombre del negocio, número de WhatsApp conectado y descripción del caso.' },
          { heading: 'Casos Comunes', body: 'Brindamos soporte para la conexión de WhatsApp Business Platform, webhooks, plantillas de Meta, diagnóstico de IA, sincronización de Google Calendar y CRM.' },
          { heading: 'Emergencias Operativas', body: 'Si el bot requiere intervención inmediata, puedes pausarlo directamente desde el Panel de Administración o cambiar el flujo a atención humana en cualquier momento.' }
        ]
      }
    };

    function openModal(type) {
      const doc = COMPLIANCE[type];
      if (!doc) return;
      document.getElementById('modal-title').innerText = doc.title;
      document.getElementById('modal-lead').innerText = doc.lead;
      
      const metaEl = document.getElementById('modal-meta');
      if (doc.meta) {
        metaEl.innerHTML = doc.meta.map(m => `
          <div class="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] text-xs">
            <div class="text-[10px] font-mono text-[#8e9dae] uppercase tracking-wider">${m.label}</div>
            <div class="text-[#f8fafc] font-medium mt-0.5">${m.value}</div>
          </div>
        `).join('');
        metaEl.classList.remove('hidden');
      } else {
        metaEl.innerHTML = '';
        metaEl.classList.add('hidden');
      }

      document.getElementById('modal-sections').innerHTML = doc.sections.map(s => `
        <div class="space-y-1.5">
          <h3 class="font-display-modern text-sm font-semibold text-[#2dd4bf]">${s.heading}</h3>
          <p class="text-xs sm:text-sm text-[#8e9dae] leading-relaxed">${s.body}</p>
        </div>
      `).join('');

      document.getElementById('compliance-modal').classList.remove('hidden');
      lucide.createIcons();
    }

    function closeModal() {
      document.getElementById('compliance-modal').classList.add('hidden');
    }

    function toggleBottomMenu() {
      const drawer = document.getElementById('bottom-menu-drawer');
      const chev = document.getElementById('bottom-menu-chevron');
      if (drawer.classList.contains('hidden')) {
        drawer.classList.remove('hidden');
        chev.classList.add('rotate-180', 'text-[#2dd4bf]');
      } else {
        drawer.classList.add('hidden');
        chev.classList.remove('rotate-180', 'text-[#2dd4bf]');
      }
    }

    function handleActivationSubmit(e) {
      e.preventDefault();
      const name = document.getElementById('act-name').value;
      const phone = document.getElementById('act-phone').value;
      const notes = document.getElementById('act-notes').value;
      const text = `¡Hola equipo de Humanio! 👋%0A%0AQuiero activar *Asistto* para mi negocio:%0A*Negocio:* ${encodeURIComponent(name)}%0A*WhatsApp:* ${encodeURIComponent(phone)}%0A*Detalles:* ${encodeURIComponent(notes || 'Automatizar WhatsApp')}%0A%0A_Enviado desde bot.humanio.digital_`;
      window.open(`https://wa.me/526671234567?text=${text}`, '_blank');
    }

    // Scroll Engine
    let currentProgress = 0;
    let targetProgress = 0;
    const TOTAL_SECTIONS = 4;

    function handleScroll() {
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      targetProgress = maxScroll > 0 ? Math.min(Math.max(window.scrollY / maxScroll, 0), 1) : 0;
    }

    window.addEventListener('scroll', handleScroll, { passive: true });

    function jumpToChapter(index) {
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      const targetY = (index / (TOTAL_SECTIONS - 1)) * maxScroll;
      window.scrollTo({ top: targetY, behavior: 'smooth' });
    }

    // Canvas Background Engine
    const canvas = document.getElementById('bg-canvas');
    const ctx = canvas.getContext('2d', { alpha: false });
    const bgImage = document.getElementById('bg-video-image');
    let decodedFrames = [];

    async function loadWebPFrames() {
      try {
        if ('ImageDecoder' in window) {
          const res = await fetch('https://res.cloudinary.com/dfvnyhur4/image/upload/v1788130387/ezgif.com-video-to-webp-converter_3_asohiq.webp');
          const buf = await res.arrayBuffer();
          const decoder = new ImageDecoder({ data: buf, type: 'image/webp' });
          await decoder.tracks.ready;
          const count = decoder.tracks.selectedTrack.frameCount;
          if (count > 0) {
            const list = [];
            for (let i = 0; i < count; i++) {
              const { image } = await decoder.decode({ frameIndex: i });
              const bmp = await createImageBitmap(image);
              list.push(bmp);
              image.close();
            }
            decodedFrames = list;
          }
        }
      } catch (e) {
        console.log('Using fallback renderer', e);
      }
    }

    function renderBackground(progress) {
      const width = (canvas.width = window.innerWidth * window.devicePixelRatio);
      const height = (canvas.height = window.innerHeight * window.devicePixelRatio);

      ctx.clearRect(0, 0, width, height);

      // Base
      ctx.fillStyle = '#080c10';
      ctx.fillRect(0, 0, width, height);

      // Draw decoded frame
      if (decodedFrames.length > 0) {
        const frameIdx = Math.min(Math.floor(progress * decodedFrames.length), decodedFrames.length - 1);
        const frame = decodedFrames[frameIdx];
        if (frame) {
          const hRatio = width / frame.width;
          const vRatio = height / frame.height;
          const ratio = Math.max(hRatio, vRatio);

          const dynamicScale = 1.02 + progress * 0.08;
          const renderW = frame.width * ratio * dynamicScale;
          const renderH = frame.height * ratio * dynamicScale;

          const shiftX = (width - renderW) / 2;
          const shiftY = (height - renderH) / 2 - progress * 40;

          ctx.save();
          ctx.globalAlpha = 0.68;
          ctx.drawImage(frame, shiftX, shiftY, renderW, renderH);
          ctx.restore();
        }
      } else if (bgImage && bgImage.complete) {
        const hRatio = width / (bgImage.naturalWidth || width);
        const vRatio = height / (bgImage.naturalHeight || height);
        const ratio = Math.max(hRatio, vRatio);

        const dynamicScale = 1.05 + progress * 0.15;
        const renderW = (bgImage.naturalWidth || width) * ratio * dynamicScale;
        const renderH = (bgImage.naturalHeight || height) * ratio * dynamicScale;

        const shiftX = (width - renderW) / 2;
        const shiftY = (height - renderH) / 2 - progress * 60;

        ctx.save();
        ctx.globalAlpha = 0.55 + Math.sin(progress * Math.PI) * 0.15;
        ctx.drawImage(bgImage, shiftX, shiftY, renderW, renderH);
        ctx.restore();
      }

      // Vignette
      const gradient = ctx.createRadialGradient(
        width / 2, height / 2, width * 0.15,
        width / 2, height / 2, width * 0.75
      );
      gradient.addColorStop(0, 'rgba(8, 12, 16, 0.2)');
      gradient.addColorStop(0.5, 'rgba(8, 12, 16, 0.65)');
      gradient.addColorStop(1, 'rgba(8, 12, 16, 0.95)');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, height);

      // Tint
      const tintGrad = ctx.createLinearGradient(0, 0, width, height);
      tintGrad.addColorStop(0, 'rgba(13, 148, 136, 0.12)');
      tintGrad.addColorStop(0.5, 'rgba(20, 184, 166, 0.04)');
      tintGrad.addColorStop(1, 'rgba(11, 16, 22, 0.3)');
      ctx.fillStyle = tintGrad;
      ctx.fillRect(0, 0, width, height);
    }

    function updateLoop() {
      const diff = targetProgress - currentProgress;
      currentProgress += diff * 0.14;

      if (Math.abs(diff) < 0.0001) {
        currentProgress = targetProgress;
      }

      const p = currentProgress;
      const rawSection = p * TOTAL_SECTIONS;
      const activeIdx = Math.min(Math.floor(rawSection), TOTAL_SECTIONS - 1);

      // HUD
      const percentStr = Math.round(p * 100).toString().padStart(2, '0');
      document.getElementById('hud-percent').innerText = `INDEX ${percentStr}%`;
      document.getElementById('hud-stage-num').innerText = `0${activeIdx + 1}`;
      document.getElementById('scroll-pill').style.transform = `translateY(${p * 12}px)`;

      // Render Video
      renderBackground(p);

      // Section 0 (0.00 to 0.25)
      let op0 = 0, ty0 = 0;
      if (p <= 0.17) { op0 = 1; ty0 = -p * 20; }
      else if (p <= 0.25) { const t = (p - 0.17) / 0.08; op0 = Math.max(0, 1 - t); ty0 = -20 - t * 40; }
      const s0 = document.getElementById('section-0');
      if (s0) {
        s0.style.opacity = op0;
        s0.style.transform = `translateY(${ty0}px)`;
        s0.style.pointerEvents = op0 > 0.05 ? 'auto' : 'none';
        s0.style.visibility = op0 > 0.05 ? 'visible' : 'hidden';
      }

      // Section 1 (0.20 to 0.50)
      let op1 = 0, ty1 = 0;
      if (p < 0.20) { op1 = 0; ty1 = 40; }
      else if (p < 0.27) { const t = (p - 0.20) / 0.07; op1 = t; ty1 = 40 * (1 - t); }
      else if (p <= 0.43) { op1 = 1; ty1 = 0; }
      else if (p <= 0.50) { const t = (p - 0.43) / 0.07; op1 = Math.max(0, 1 - t); ty1 = -40 * t; }
      const s1 = document.getElementById('section-1');
      if (s1) {
        s1.style.opacity = op1;
        s1.style.transform = `translateY(${ty1}px)`;
        s1.style.pointerEvents = op1 > 0.05 ? 'auto' : 'none';
        s1.style.visibility = op1 > 0.05 ? 'visible' : 'hidden';
      }

      // Section 2 (0.45 to 0.75)
      let op2 = 0, ty2 = 0;
      if (p < 0.45) { op2 = 0; ty2 = 40; }
      else if (p < 0.52) { const t = (p - 0.45) / 0.07; op2 = t; ty2 = 40 * (1 - t); }
      else if (p <= 0.68) { op2 = 1; ty2 = 0; }
      else if (p <= 0.75) { const t = (p - 0.68) / 0.07; op2 = Math.max(0, 1 - t); ty2 = -40 * t; }
      const s2 = document.getElementById('section-2');
      if (s2) {
        s2.style.opacity = op2;
        s2.style.transform = `translateY(${ty2}px)`;
        s2.style.pointerEvents = op2 > 0.05 ? 'auto' : 'none';
        s2.style.visibility = op2 > 0.05 ? 'visible' : 'hidden';
      }

      // Section 3 (0.70 to 1.00)
      let op3 = 0, ty3 = 0;
      if (p < 0.70) { op3 = 0; ty3 = 40; }
      else if (p < 0.77) { const t = (p - 0.70) / 0.07; op3 = t; ty3 = 40 * (1 - t); }
      else { op3 = 1; ty3 = 0; }
      const s3 = document.getElementById('section-3');
      if (s3) {
        s3.style.opacity = op3;
        s3.style.transform = `translateY(${ty3}px)`;
        s3.style.pointerEvents = op3 > 0.05 ? 'auto' : 'none';
        s3.style.visibility = op3 > 0.05 ? 'visible' : 'hidden';
      }

      // Chapter Rail
      document.querySelectorAll('.chapter-btn').forEach((btn, i) => {
        const isAct = activeIdx === i;
        const num = btn.querySelector('.chapter-num');
        const dot = btn.querySelector('.chapter-dot');
        const label = btn.querySelector('.chapter-label');

        if (isAct) {
          num.className = 'chapter-num text-[11px] font-mono text-[#2dd4bf] font-bold';
          dot.className = 'chapter-dot rounded-full w-2 h-2 bg-[#14b8a6] ring-4 ring-[#14b8a6]/20 shadow-[0_0_10px_#14b8a6] transition-all duration-300';
          label.className = 'chapter-label text-xs font-mono tracking-wider text-[#f8fafc] opacity-100 translate-x-0 transition-all';
        } else {
          num.className = 'chapter-num text-[11px] font-mono text-[#8e9dae]/60 group-hover:text-[#f8fafc]';
          dot.className = 'chapter-dot rounded-full w-1 h-1 bg-white/20 group-hover:bg-white/60 group-hover:scale-150 transition-all duration-300';
          label.className = 'chapter-label text-xs font-mono tracking-wider text-[#8e9dae]/50 opacity-0 group-hover:opacity-100 translate-x-2 group-hover:translate-x-0 transition-all';
        }
      });

      requestAnimationFrame(updateLoop);
    }

    // Init
    window.addEventListener('DOMContentLoaded', () => {
      initFeatures();
      lucide.createIcons();
      loadWebPFrames();
      requestAnimationFrame(updateLoop);
    });
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
