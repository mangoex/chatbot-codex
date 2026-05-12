"""Admin frontend: login, dashboard, conversations, CRM and escalations."""
import html
import json
import re
import secrets
from contextvars import ContextVar
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import auth, config, db, meta_provider, secure_store

router = APIRouter(prefix="/admin", tags=["admin"])
_current_session: ContextVar[dict | None] = ContextVar("admin_session", default=None)


def _empty_metrics() -> dict:
    return {
        "conversations": 0,
        "messages": 0,
        "leads": 0,
        "qualified": 0,
        "pending_escalations": 0,
    }


def _require_login(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    session = {
        "user": user,
        "role": request.session.get("role", "agency_admin"),
        "client_id": request.session.get("client_id"),
        "user_id": request.session.get("user_id"),
        "name": request.session.get("name") or user,
    }
    _current_session.set(session)
    return session


def _is_agency(session: dict) -> bool:
    return session.get("role") == "agency_admin"


def _require_agency(request: Request) -> dict:
    session = _require_login(request)
    if not _is_agency(session):
        raise HTTPException(status_code=403, detail="Solo agencia")
    return session


def _require_user_manager(request: Request) -> dict:
    session = _require_login(request)
    if _is_agency(session) or session.get("role") == "client_admin":
        return session
    raise HTTPException(status_code=403, detail="Solo administradores pueden gestionar usuarios")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().strip())
    return slug.strip("-") or "cliente"


async def _first_allowed_bot(session: dict) -> dict | None:
    bots = await db.list_bots(
        client_id=None if _is_agency(session) else int(session["client_id"]),
        limit=1,
    )
    return bots[0] if bots else None


async def _data_scope_bot_id(session: dict) -> tuple[int | None, bool]:
    """Returns bot_id plus whether this session is allowed to read scoped data."""
    if _is_agency(session):
        return None, True
    bot = await _first_allowed_bot(session)
    if not bot:
        return None, False
    return int(bot["id"]), True


async def _require_bot_access(session: dict, bot_id: int) -> dict:
    bot = await db.get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")
    if not _is_agency(session) and bot.get("client_id") != session.get("client_id"):
        raise HTTPException(status_code=403, detail="Sin acceso a este bot")
    return bot


async def _require_bot_editor(session: dict, bot_id: int) -> dict:
    bot = await _require_bot_access(session, bot_id)
    if _is_agency(session) or session.get("role") == "client_admin":
        return bot
    raise HTTPException(status_code=403, detail="Solo administradores pueden editar este bot")


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else "-"


def _clip(value: str | None, size: int = 160) -> str:
    text = (value or "").strip()
    return text if len(text) <= size else text[: size - 1].rstrip() + "..."


def _parse_config_json(value: str) -> dict:
    clean = (value or "").strip()
    if not clean:
        return {}
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Config JSON invalido: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Config JSON debe ser un objeto.")
    return parsed


def _pretty_json(value: dict | None) -> str:
    return json.dumps(value or {}, ensure_ascii=True, indent=2)


def _wa_link(wa_id: str) -> str:
    return f"https://wa.me/{html.escape(wa_id)}"


def _display_name(name: str | None, wa_id: str) -> str:
    clean = (name or "").strip()
    invalid_terms = (
        "quien", "quien toma", "toma", "decision", "decisión", "dueno",
        "dueño", "negocio", "empresa", "encargado", "responsable",
    )
    if not clean or any(term in clean.lower() for term in invalid_terms):
        return wa_id
    return clean


ADMIN_APP_SECTIONS = (
    {
        "key": "administracion",
        "title": "Administracion",
        "items": (
            {
                "label": "Ver clientes",
                "description": "Alta de clientes, usuarios y primer bot.",
                "href": "/admin/clients",
                "kind": "static",
                "agency_only": True,
            },
            {
                "label": "Control de usuarios",
                "description": "Accesos, roles y usuarios por cliente.",
                "href": "/admin/users",
                "kind": "static",
                "manager_only": True,
            },
            {
                "label": "Ver bots",
                "description": "Listado operativo de bots disponibles.",
                "href": "/admin/bots",
                "kind": "static",
            },
            {
                "label": "Revisar conversaciones",
                "description": "Historial guardado por WhatsApp y bot.",
                "href": "/admin/conversations",
                "kind": "conversation",
            },
        ),
    },
    {
        "key": "configuracion",
        "title": "Configuracion del bot",
        "items": (
            {
                "label": "Prompt + asistente IA",
                "description": "Crea, corrige y publica instrucciones del agente.",
                "href": "/admin/bots/{bot_id}/prompt",
                "kind": "bot",
            },
            {
                "label": "Cargar conocimiento",
                "description": "Servicios, precios, politicas y FAQs.",
                "href": "/admin/bots/{bot_id}/knowledge",
                "kind": "bot",
            },
            {
                "label": "Configurar agenda, API, webhook o CRM",
                "description": "Integraciones por cliente sin exponer secretos.",
                "href": "/admin/bots/{bot_id}/integrations",
                "kind": "bot",
            },
            {
                "label": "Conectar WhatsApp",
                "description": "Embedded Signup, WABA y numero del cliente.",
                "href": "/admin/bots/{bot_id}/whatsapp",
                "kind": "bot",
            },
            {
                "label": "Activar habilidades",
                "description": "Calendar, webhook, API externa y CRM.",
                "href": "/admin/bots/{bot_id}/skills",
                "kind": "bot",
            },
        ),
    },
    {
        "key": "pruebas",
        "title": "Pruebas y diagnostico",
        "items": (
            {
                "label": "Probar IA",
                "description": "Proveedor, modelo y respuesta de prueba.",
                "href": "/admin/ai-status",
                "kind": "static",
            },
            {
                "label": "Probar Calendar",
                "description": "Conexion global o del bot seleccionado.",
                "href": "/admin/calendar-status?bot_id={bot_id}",
                "kind": "bot",
            },
            {
                "label": "Diagnostico Meta",
                "description": "WABA, token, subscribed_apps y numero.",
                "href": "/admin/bots/{bot_id}/whatsapp/diagnostics",
                "kind": "bot",
            },
            {
                "label": "Plantillas Meta",
                "description": "Listar y crear plantillas de WhatsApp.",
                "href": "/admin/bots/{bot_id}/whatsapp/templates",
                "kind": "bot",
            },
            {
                "label": "Modo revision Meta",
                "description": "Checklist y guion para App Review.",
                "href": "/admin/tech-provider/review",
                "kind": "static",
                "agency_only": True,
            },
        ),
    },
)


def _admin_app_href(template: str, bot_id: int | None) -> str:
    if "{bot_id}" not in template:
        return template
    return template.replace("{bot_id}", str(bot_id or 1))


def _admin_app_link_cards(
    bot_id: int | None,
    is_agency: bool,
    role: str = "agency_admin",
) -> str:
    sections = []
    can_manage_users = is_agency or role == "client_admin"
    for section in ADMIN_APP_SECTIONS:
        cards = []
        for item in section["items"]:
            if item.get("agency_only") and not is_agency:
                continue
            if item.get("manager_only") and not can_manage_users:
                continue
            href = _admin_app_href(item["href"], bot_id)
            disabled = (item["kind"] == "bot" and not bot_id) or (
                item["kind"] == "conversation" and not is_agency and not bot_id
            )
            classes = "control-link disabled" if disabled else "control-link"
            attrs = 'aria-disabled="true"' if disabled else f'href="{html.escape(href)}"'
            route = html.escape(href)
            cards.append(
                f"""
                <a class="{classes}" data-template="{html.escape(item["href"])}" data-kind="{html.escape(item["kind"])}" {attrs}>
                  <span class="link-icon" aria-hidden="true"></span>
                  <span class="link-copy">
                    <strong>{html.escape(item["label"])}</strong>
                    <small>{html.escape(item["description"])}</small>
                    <code>{route}</code>
                  </span>
                </a>
                """
            )
        if cards:
            sections.append(
                f"""
                <section class="control-section">
                  <div class="section-title">
                    <span>{html.escape(section["title"])}</span>
                    <small>{len(cards)} accesos</small>
                  </div>
                  <div class="control-grid">{''.join(cards)}</div>
                </section>
                """
            )
    return "".join(sections)


def _admin_api_bot(bot: dict) -> dict:
    phone = bot.get("display_phone_number") or bot.get("phone_number_id") or ""
    return {
        "id": int(bot["id"]),
        "name": bot.get("name") or f"Bot #{bot['id']}",
        "slug": bot.get("slug") or "",
        "client_id": bot.get("client_id"),
        "client_name": bot.get("client_name") or "",
        "phone": phone,
        "status": bot.get("status") or "active",
        "whatsapp_status": bot.get("whatsapp_status") or "",
        "links": _admin_bot_links(int(bot["id"])),
    }


def _admin_api_client(client: dict) -> dict:
    return {
        "id": int(client["id"]),
        "name": client.get("name") or "",
        "slug": client.get("slug") or "",
        "status": client.get("status") or "active",
        "bot_count": int(client.get("bot_count") or 0),
        "links": {"detail": f"/admin/clients/{int(client['id'])}"},
    }


def _admin_api_user(user: dict) -> dict:
    return {
        "id": int(user["id"]),
        "email": user.get("email") or "",
        "name": user.get("name") or "",
        "status": user.get("status") or "active",
        "role": user.get("role") or "client_viewer",
        "client_id": user.get("client_id"),
        "client_name": user.get("client_name") or "",
        "client_slug": user.get("client_slug") or "",
    }


def _admin_bot_links(bot_id: int) -> dict:
    return {
        "detail": f"/admin/bots/{bot_id}",
        "prompt": f"/admin/bots/{bot_id}/prompt",
        "knowledge": f"/admin/bots/{bot_id}/knowledge",
        "integrations": f"/admin/bots/{bot_id}/integrations",
        "skills": f"/admin/bots/{bot_id}/skills",
        "whatsapp": f"/admin/bots/{bot_id}/whatsapp",
        "whatsapp_diagnostics": f"/admin/bots/{bot_id}/whatsapp/diagnostics",
        "whatsapp_templates": f"/admin/bots/{bot_id}/whatsapp/templates",
        "conversations": f"/admin/conversations?bot_id={bot_id}",
        "calendar_status": f"/admin/calendar-status?bot_id={bot_id}",
    }


def _admin_api_metrics(metrics: dict) -> dict:
    return {
        "conversations": int(metrics.get("conversations") or 0),
        "messages": int(metrics.get("messages") or 0),
        "leads": int(metrics.get("leads") or 0),
        "qualified": int(metrics.get("qualified") or 0),
        "pending_escalations": int(metrics.get("pending_escalations") or 0),
    }


async def _admin_app_state(session: dict, bot_id: int | None = None) -> dict:
    is_agency = _is_agency(session)
    client_id = None if is_agency else int(session["client_id"])
    bots = await db.list_bots(client_id=client_id, limit=100)
    selected_bot = None
    if bot_id:
        selected_bot = await _require_bot_access(session, bot_id)
    elif bots:
        selected_bot = bots[0]
        bot_id = int(selected_bot["id"])
    has_data_scope = is_agency or bool(bot_id)
    metrics = await db.admin_metrics(bot_id=bot_id) if has_data_scope else _empty_metrics()
    clients = await db.list_clients() if is_agency else []
    users = await db.list_users(client_id=None if is_agency else int(session["client_id"]))
    return {
        "user": {
            "name": session.get("name") or session.get("user") or "",
            "role": session.get("role") or "agency_admin",
            "is_agency": is_agency,
            "client_id": session.get("client_id"),
        },
        "selected_bot_id": int(bot_id) if bot_id else None,
        "selected_bot": _admin_api_bot(selected_bot) if selected_bot else None,
        "bots": [_admin_api_bot(bot) for bot in bots],
        "clients": [_admin_api_client(client) for client in clients],
        "users": [_admin_api_user(user) for user in users],
        "metrics": _admin_api_metrics(metrics),
        "links": _admin_bot_links(int(bot_id)) if bot_id else {},
    }


BASE_CSS = """
<style>
  :root {
    --bg: #f4f5f2;
    --panel: #ffffff;
    --ink: #151716;
    --muted: #68706c;
    --line: #dde2dc;
    --line-strong: #c9d0c8;
    --primary: #176b5b;
    --primary-ink: #ffffff;
    --amber: #ad6500;
    --red: #a83b35;
    --blue: #315f9f;
    --green: #20724d;
    --shadow: 0 18px 45px rgba(24, 31, 27, .08);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  }
  a { color: inherit; text-decoration: none; }
  button, input, textarea, select { font: inherit; }
  .shell { min-height: 100vh; display: grid; grid-template-columns: 248px 1fr; }
  .side {
    border-right: 1px solid var(--line);
    background: #fbfcfa;
    padding: 22px 16px;
    position: sticky;
    top: 0;
    height: 100vh;
  }
  .brand { display: flex; gap: 10px; align-items: center; margin-bottom: 26px; }
  .mark {
    width: 36px; height: 36px; border-radius: 8px;
    background: var(--ink); color: white; display: grid; place-items: center;
    font-weight: 800; letter-spacing: 0;
  }
  .brand strong { display: block; font-size: 15px; }
  .brand span { display: block; font-size: 12px; color: var(--muted); margin-top: 2px; }
  .nav { display: grid; gap: 6px; }
  .nav a {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 12px; border-radius: 8px; color: #37403b;
    font-size: 14px;
  }
  .nav a.active, .nav a:hover { background: #e8eee9; color: var(--ink); }
  .nav svg { width: 18px; height: 18px; stroke-width: 2; }
  .nav-sep { height: 1px; background: var(--line); margin: 10px 8px; }
  .logout { position: absolute; bottom: 18px; left: 16px; right: 16px; }
  .main { padding: 26px 30px 42px; min-width: 0; }
  .topbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 22px; }
  h1 { font-size: 28px; line-height: 1.1; margin: 0 0 7px; letter-spacing: 0; }
  .sub { color: var(--muted); font-size: 14px; }
  .grid { display: grid; gap: 14px; }
  .kpis { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .card, .table-wrap, .panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: var(--shadow);
  }
  .card { padding: 16px; min-height: 112px; }
  .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
  .n { font-size: 31px; font-weight: 750; margin-top: 13px; letter-spacing: 0; }
  .trend { margin-top: 8px; font-size: 12px; color: var(--green); }
  .demo { color: var(--amber); }
  .split { grid-template-columns: minmax(0, 1.2fr) minmax(320px, .8fr); margin-top: 14px; }
  .panel { padding: 18px; }
  .panel h2 { font-size: 16px; margin: 0 0 14px; }
  .bars { display: grid; gap: 12px; }
  .bar-row { display: grid; gap: 7px; }
  .bar-label { display: flex; justify-content: space-between; color: var(--muted); font-size: 13px; }
  .bar-track { height: 9px; border-radius: 999px; background: #edf0ec; overflow: hidden; }
  .bar-fill { height: 100%; background: var(--primary); border-radius: 999px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 13px 14px; border-bottom: 1px solid #edf0ec; text-align: left; vertical-align: top; font-size: 13px; }
  th { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; background: #fafbf9; }
  tr:last-child td { border-bottom: 0; }
  .table-wrap { overflow: hidden; }
  .tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
  .tabs a {
    border: 1px solid var(--line);
    background: white;
    border-radius: 8px;
    padding: 8px 11px;
    font-size: 13px;
    color: #3f4743;
  }
  .tabs a.active { background: var(--ink); border-color: var(--ink); color: white; }
  .badge {
    display: inline-flex; align-items: center; min-height: 24px;
    padding: 3px 9px; border-radius: 999px; font-size: 12px; font-weight: 650;
    background: #edf0ec; color: #46504a; white-space: nowrap;
  }
  .b-en_progreso, .b-pendiente { background: #fff1cf; color: #845000; }
  .b-calificado, .b-resuelto { background: #dff4e8; color: #17643e; }
  .b-descalificado, .b-urgente { background: #f8dfdc; color: #95322d; }
  .b-en_proceso, .b-media { background: #dfeafd; color: #264f8c; }
  .b-hardware { background: #ffe7c2; color: #875000; }
  .btn {
    border: 1px solid var(--ink); background: var(--ink); color: white;
    border-radius: 8px; padding: 8px 11px; cursor: pointer; font-size: 13px;
    display: inline-flex; align-items: center; gap: 7px; min-height: 36px;
  }
  .btn svg { width: 16px; height: 16px; }
  .btn.secondary { background: white; color: var(--ink); }
  .btn.whatsapp { background: #1f9d61; border-color: #1f9d61; }
  .actions { display: flex; gap: 7px; flex-wrap: wrap; }
  .control-hero {
    background: #fbfcfa;
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: var(--shadow);
    padding: 22px;
    margin-bottom: 14px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
    gap: 18px;
    align-items: end;
  }
  .control-hero h1 { font-size: 30px; }
  .control-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  .sync-status { font-size: 12px; color: var(--muted); margin-top: 10px; min-height: 18px; }
  .sync-status.ok { color: var(--green); }
  .sync-status.err { color: var(--red); }
  .bot-select-card {
    background: white;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 14px;
  }
  .bot-select-card label { margin-top: 0; }
  .bot-select-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }
  .control-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
    gap: 14px;
    align-items: start;
  }
  .control-section {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: var(--shadow);
    padding: 16px;
    margin-bottom: 14px;
  }
  .section-title {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    margin-bottom: 12px;
  }
  .section-title span { font-weight: 750; }
  .section-title small { color: var(--muted); font-size: 12px; }
  .control-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .control-link {
    display: grid;
    grid-template-columns: 38px minmax(0, 1fr);
    gap: 11px;
    min-height: 118px;
    padding: 12px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #fbfcfa;
    transition: transform .16s ease, border-color .16s ease, background .16s ease;
  }
  .control-link:hover { transform: translateY(-1px); border-color: var(--line-strong); background: white; }
  .control-link.disabled { opacity: .58; pointer-events: none; }
  .link-icon {
    width: 38px;
    height: 38px;
    border-radius: 8px;
    background: #e8eee9;
    position: relative;
  }
  .link-icon::before,
  .link-icon::after {
    content: "";
    position: absolute;
    border-radius: 3px;
    background: var(--primary);
  }
  .link-icon::before { width: 16px; height: 2px; left: 11px; top: 14px; }
  .link-icon::after { width: 16px; height: 2px; left: 11px; top: 21px; }
  .link-copy { display: grid; gap: 5px; min-width: 0; }
  .link-copy strong { font-size: 14px; line-height: 1.25; }
  .link-copy small { color: var(--muted); line-height: 1.35; }
  .link-copy code {
    color: #42504a;
    background: #edf0ec;
    border-radius: 6px;
    padding: 4px 6px;
    font-size: 11px;
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .route-list { display: grid; gap: 8px; }
  .route-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
    align-items: center;
    padding: 9px 0;
    border-bottom: 1px solid #edf0ec;
  }
  .route-row:last-child { border-bottom: 0; }
  .route-row code { overflow-wrap: anywhere; }
  .mini-stack { display: grid; gap: 10px; }
  .stack-item {
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 11px;
    background: #fbfcfa;
  }
  .stack-item strong { display: block; font-size: 13px; margin-bottom: 4px; }
  .stack-item span { color: var(--muted); font-size: 12px; }
  .editor textarea { min-height: 520px; line-height: 1.45; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
  .editor textarea.short { min-height: 220px; }
  .prompt-workspace { grid-template-columns: minmax(0, 1.1fr) minmax(320px, .9fr); align-items: start; }
  .prompt-assistant textarea { min-height: 118px; line-height: 1.4; }
  .prompt-assistant textarea.result {
    min-height: 300px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }
  .prompt-status { font-size: 12px; color: var(--muted); min-height: 18px; margin-top: 10px; }
  .prompt-status.ok { color: var(--green); }
  .prompt-status.err { color: var(--red); }
  .knowledge-preview { white-space: pre-wrap; color: var(--muted); font-size: 13px; max-height: 90px; overflow: hidden; }
  .code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }
  .muted { color: var(--muted); }
  .empty { padding: 40px; text-align: center; color: var(--muted); }
  .messages { display: grid; gap: 10px; }
  .chat-widget {
    height: min(680px, calc(100vh - 210px));
    min-height: 420px;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .bubble {
    max-width: min(720px, 88%);
    padding: 11px 13px;
    border-radius: 8px;
    border: 1px solid var(--line);
    background: white;
  }
  .bubble.assistant { margin-left: auto; background: #e8f1ed; border-color: #cfe1d8; }
  .bubble .meta { font-size: 11px; color: var(--muted); margin-bottom: 6px; }
  .login {
    min-height: 100vh; display: grid; place-items: center; padding: 24px;
    background: radial-gradient(circle at 15% 0%, #dfeade, transparent 30%), var(--bg);
  }
  .login-card { width: min(420px, 100%); padding: 24px; }
  label { display: block; font-size: 13px; color: var(--muted); margin: 14px 0 6px; }
  input, textarea, select {
    width: 100%; border: 1px solid var(--line-strong); border-radius: 8px;
    padding: 10px 11px; background: white; color: var(--ink);
  }
  .err { background: #f8dfdc; color: #95322d; padding: 10px 12px; border-radius: 8px; font-size: 13px; margin: 14px 0; }
  form.inline { display: inline; }
  @media (max-width: 860px) {
    .shell { grid-template-columns: 1fr; }
    .side { position: relative; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
    .logout { position: static; margin-top: 18px; }
    .main { padding: 20px 16px 32px; }
    .kpis, .split { grid-template-columns: 1fr; }
    .control-hero, .control-layout, .control-grid, .prompt-workspace { grid-template-columns: 1fr; }
    .bot-select-actions { grid-template-columns: 1fr; }
    .topbar { flex-direction: column; }
    th:nth-child(4), td:nth-child(4) { display: none; }
  }
</style>
"""


ICONS = {
    "dashboard": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M3 13h8V3H3v10Z"/><path d="M13 21h8V11h-8v10Z"/><path d="M13 3h8v6h-8V3Z"/><path d="M3 21h8v-6H3v6Z"/></svg>',
    "chat": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z"/></svg>',
    "crm": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    "alert": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
    "building": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M3 21h18"/><path d="M5 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16"/><path d="M9 7h1"/><path d="M14 7h1"/><path d="M9 11h1"/><path d="M14 11h1"/><path d="M9 15h1"/><path d="M14 15h1"/></svg>',
    "out": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>',
    "wa": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M20 11.5a8 8 0 0 1-11.9 7L4 20l1.5-4A8 8 0 1 1 20 11.5Z"/><path d="M9 8.8c.4 2 1.9 3.5 4.2 4.3l1.3-1.1 1.8.4c.2 1.2-.6 2.3-1.8 2.3-3.5-.1-6.2-2.8-6.5-6.2C8 7.3 9.2 6.6 10.3 7l.4 1.7L9 8.8Z"/></svg>',
}


def _nav(active: str, session: dict | None = None) -> str:
    session = session or _current_session.get() or {"role": "agency_admin"}
    role = session.get("role") or "agency_admin"
    is_agency = role == "agency_admin"
    can_manage_users = is_agency or role == "client_admin"
    items = [
        ("app", "Centro de control", "/admin/app", ICONS["dashboard"], {}),
        ("dashboard", "Dashboard", "/admin/dashboard", ICONS["dashboard"], {}),
        ("clients", "Clientes", "/admin/clients", ICONS["building"], {"agency_only": True}),
        ("users", "Usuarios", "/admin/users", ICONS["crm"], {"manager_only": True}),
        ("bots", "Bots", "/admin/bots", ICONS["building"], {}),
        ("tech-provider", "Tech Provider", "/admin/tech-provider/review", ICONS["wa"], {"agency_only": True}),
        ("conversations", "Conversaciones", "/admin/conversations", ICONS["chat"], {}),
        ("crm", "CRM", "/admin/crm", ICONS["crm"], {}),
        ("escalations", "Escalaciones", "/admin/escalations", ICONS["alert"], {"agency_only": True}),
    ]
    visible = [
        (key, label, href, icon)
        for key, label, href, icon, rules in items
        if not (rules.get("agency_only") and not is_agency)
        and not (rules.get("manager_only") and not can_manage_users)
    ]
    links = "".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{icon}<span>{label}</span></a>'
        for key, label, href, icon in visible
    )
    return f"""
    <aside class="side">
      <div class="brand">
        <div class="mark">AH</div>
        <div><strong>Asistto</strong><span>by Humanio</span></div>
      </div>
      <nav class="nav">{links}</nav>
      <form method="post" action="/admin/logout" class="logout">
        <button class="btn secondary" type="submit">{ICONS["out"]} Salir</button>
      </form>
    </aside>
    """


def _layout(title: str, active: str, body: str, session: dict | None = None) -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - Asistto by Humanio</title>
{BASE_CSS}
</head><body><div class="shell">{_nav(active, session)}<main class="main">{body}</main></div></body></html>"""


def _login_layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - Asistto by Humanio</title>
{BASE_CSS}
</head><body><div class="login">{body}</div></body></html>"""


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    if request.session.get("user"):
        return RedirectResponse("/admin/dashboard", status_code=302)
    err_html = f'<div class="err">{html.escape(error)}</div>' if error else ""
    body = f"""
    <section class="card login-card">
      <div class="brand" style="margin-bottom:18px">
        <div class="mark">AH</div>
        <div><strong>Asistto</strong><span>by Humanio</span></div>
      </div>
      <h1>Entrar al panel</h1>
      <div class="sub">Conversaciones, CRM y diagnostico comercial.</div>
      {err_html}
      <form method="post" action="/admin/login">
        <label>Usuario</label>
        <input name="username" autocomplete="username" autofocus required>
        <label>Contrasena</label>
        <input type="password" name="password" autocomplete="current-password" required>
        <div style="margin-top:18px"><button class="btn" type="submit">Entrar</button></div>
      </form>
    </section>"""
    return HTMLResponse(_login_layout("Login", body))


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    ok_user = secrets.compare_digest(username, config.ADMIN_USER)
    ok_pass = secrets.compare_digest(password, config.ADMIN_PASSWORD)
    if ok_user and ok_pass and config.ADMIN_USER and config.ADMIN_PASSWORD:
        request.session["user"] = username
        request.session["role"] = "agency_admin"
        request.session["client_id"] = None
        request.session["user_id"] = None
        request.session["name"] = username
        return RedirectResponse("/admin/app", status_code=302)
    user = await db.get_user_login(username)
    if user and auth.verify_password(password, user.get("password_hash")):
        request.session["user"] = user["email"]
        request.session["role"] = user["role"]
        request.session["client_id"] = user["client_id"]
        request.session["user_id"] = user["user_id"]
        request.session["name"] = user.get("name") or user["email"]
        return RedirectResponse("/admin/app", status_code=302)
    return RedirectResponse(
        "/admin/login?error=" + "Usuario+o+contrasena+incorrectos",
        status_code=302,
    )


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)


@router.get("", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse("/admin/app", status_code=302)


@router.get("/api/panel-state", response_class=JSONResponse)
async def api_panel_state(request: Request, bot_id: int | None = None):
    session = _require_login(request)
    return JSONResponse(await _admin_app_state(session, bot_id=bot_id))


@router.get("/api/bots", response_class=JSONResponse)
async def api_bots(request: Request):
    session = _require_login(request)
    client_id = None if _is_agency(session) else int(session["client_id"])
    bots = await db.list_bots(client_id=client_id, limit=100)
    return JSONResponse({"bots": [_admin_api_bot(bot) for bot in bots]})


@router.get("/api/clients", response_class=JSONResponse)
async def api_clients(request: Request):
    session = _require_agency(request)
    clients = await db.list_clients()
    return JSONResponse({"clients": [_admin_api_client(client) for client in clients]})


@router.get("/api/users", response_class=JSONResponse)
async def api_users(request: Request):
    session = _require_user_manager(request)
    client_id = None if _is_agency(session) else int(session["client_id"])
    users = await db.list_users(client_id=client_id)
    return JSONResponse({"users": [_admin_api_user(user) for user in users]})


@router.get("/app", response_class=HTMLResponse)
async def control_app(request: Request, bot_id: int | None = None):
    session = _require_login(request)
    state = await _admin_app_state(session, bot_id=bot_id)
    is_agency = bool(state["user"]["is_agency"])
    bots = state["bots"]
    selected_bot = state["selected_bot"]
    bot_id = state["selected_bot_id"]
    metrics = state["metrics"]
    clients = state["clients"]
    users = state["users"]
    can_manage_users = is_agency or session.get("role") == "client_admin"
    conversations_href = f"/admin/conversations?bot_id={bot_id}" if bot_id else "/admin/conversations"
    bot_detail_href = f"/admin/bots/{bot_id}" if bot_id else "/admin/bots"
    prompt_href = f"/admin/bots/{bot_id}/prompt" if bot_id else "#"
    calendar_href = f"/admin/calendar-status?bot_id={bot_id}" if bot_id else "#"
    role_label = {
        "agency_admin": "Agencia",
        "client_admin": "Admin cliente",
        "client_viewer": "Solo lectura",
    }.get(session.get("role"), session.get("role", "Usuario"))
    bot_options = "".join(
        f"""
        <option value="{int(bot["id"])}" {"selected" if int(bot["id"]) == int(bot_id or 0) else ""}
          data-name="{html.escape(bot["name"])}"
          data-client="{html.escape(bot.get("client_name") or "-")}"
          data-phone="{html.escape(bot.get("phone") or "sin WhatsApp")}"
          data-status="{html.escape(bot.get("status") or "active")}">
          #{int(bot["id"])} - {html.escape(bot["name"])}
        </option>
        """
        for bot in bots
    )
    bot_name = html.escape((selected_bot or {}).get("name") or "Sin bot seleccionado")
    bot_client = html.escape((selected_bot or {}).get("client_name") or "-")
    bot_phone = html.escape((selected_bot or {}).get("phone") or "sin WhatsApp")
    bot_status = html.escape((selected_bot or {}).get("status") or "sin bot")
    helper = "Usar bot_id real, por ejemplo 1." if not bot_id else f"Bot activo: {int(bot_id)}."

    route_rows = "".join(
        f"""
        <div class="route-row">
          <code data-template="{html.escape(item["href"])}" data-kind="{html.escape(item["kind"])}">{html.escape(_admin_app_href(item["href"], bot_id))}</code>
          <a class="btn secondary" data-template="{html.escape(item["href"])}" data-kind="{html.escape(item["kind"])}" href="{html.escape(_admin_app_href(item["href"], bot_id))}">Entrar</a>
        </div>
        """
        for section in ADMIN_APP_SECTIONS
        for item in section["items"]
        if not item.get("agency_only") or is_agency
        if not item.get("manager_only") or can_manage_users
    )
    body = f"""
    <section class="control-hero">
      <div>
        <h1>Centro de control</h1>
        <div class="sub">Una sola entrada para operar clientes, bots, conversaciones, diagnosticos e integraciones.</div>
        <div class="control-meta">
          <span class="badge">{html.escape(role_label)}</span>
          <span class="badge">{html.escape(session.get("name") or session.get("user") or "Usuario")}</span>
          <span class="badge b-calificado">{html.escape(helper)}</span>
        </div>
      </div>
      <div class="bot-select-card">
        <label>Bot seleccionado</label>
        <select id="botSelector" {"disabled" if not bots else ""}>
          {bot_options or '<option value="">No hay bots disponibles</option>'}
        </select>
        <div class="mini-stack" style="margin-top:12px">
          <div class="stack-item"><strong id="botName">{bot_name}</strong><span id="botClient">{bot_client}</span></div>
          <div class="stack-item"><strong id="botPhone">{bot_phone}</strong><span id="botStatus">Estado: {bot_status}</span></div>
        </div>
        <div class="bot-select-actions">
          <a id="openBot" class="btn" href="{html.escape(bot_detail_href)}">Abrir bot</a>
          <a id="testCalendar" class="btn secondary" href="{html.escape(calendar_href)}">Probar Calendar</a>
        </div>
        <div id="syncStatus" class="sync-status">Datos listos.</div>
      </div>
    </section>
    <section class="grid kpis" style="margin-bottom:14px">
      <div class="card"><div class="k">Clientes</div><div class="n" id="kpiClients">{len(clients) if is_agency else 1}</div><div class="trend">Control de acceso activo</div></div>
      <div class="card"><div class="k">Bots</div><div class="n" id="kpiBots">{len(bots)}</div><div class="trend">Seleccionables desde este panel</div></div>
      <div class="card"><div class="k">Conversaciones</div><div class="n" id="kpiConversations">{metrics.get("conversations", 0)}</div><div class="trend">Del bot seleccionado</div></div>
      <div class="card"><div class="k">Usuarios</div><div class="n" id="kpiUsers">{len(users)}</div><div class="trend">Roles por cliente</div></div>
    </section>
    <section class="control-layout">
      <div>{_admin_app_link_cards(bot_id, is_agency, session.get("role", "agency_admin"))}</div>
      <aside class="panel">
        <h2>Rutas del manual</h2>
        <div class="sub" style="margin-bottom:12px">Los accesos reemplazan automaticamente <span class="code">{{bot_id}}</span> por el bot activo.</div>
        <div class="route-list">{route_rows}</div>
        <div class="actions" style="margin-top:14px">
          <a id="openPrompt" class="btn secondary" href="{html.escape(prompt_href)}">Prompt con IA</a>
          <a class="btn secondary" href="/admin/ai-status">Probar IA</a>
          <a id="openConversations" class="btn secondary" href="{html.escape(conversations_href)}">Conversaciones</a>
        </div>
      </aside>
    </section>
    <script>
      (() => {{
        const selector = document.getElementById("botSelector");
        const syncStatus = document.getElementById("syncStatus");
        const replaceBotId = (template, botId) => template.replace("{{bot_id}}", botId || "1");
        const setText = (id, value) => {{
          const node = document.getElementById(id);
          if (node) node.textContent = value;
        }};
        const setStatus = (message, className = "") => {{
          if (!syncStatus) return;
          syncStatus.className = `sync-status ${{className}}`;
          syncStatus.textContent = message;
        }};
        const setHref = (node, botId) => {{
          const template = node.dataset.template;
          if (!template) return;
          const href = replaceBotId(template, botId);
          if (node.dataset.kind === "bot" && !botId) {{
            node.removeAttribute("href");
            node.setAttribute("aria-disabled", "true");
            node.classList.add("disabled");
          }} else {{
            node.setAttribute("href", href);
            node.removeAttribute("aria-disabled");
            node.classList.remove("disabled");
          }}
          if (node.tagName === "CODE") node.textContent = href;
        }};
        const applyPanelState = (state) => {{
          const bot = state.selected_bot;
          if (!bot) return;
          setText("botName", bot.name || `Bot #${{bot.id}}`);
          setText("botClient", bot.client_name || "-");
          setText("botPhone", bot.phone || "sin WhatsApp");
          setText("botStatus", `Estado: ${{bot.status || "active"}}`);
          setText("kpiClients", state.user?.is_agency ? String(state.clients?.length || 0) : "1");
          setText("kpiBots", String(state.bots?.length || 0));
          setText("kpiConversations", String(state.metrics?.conversations || 0));
          setText("kpiUsers", String(state.users?.length || 0));
          document.querySelectorAll("[data-template]").forEach((node) => setHref(node, bot.id));
          document.getElementById("openBot").href = bot.links.detail;
          document.getElementById("testCalendar").href = bot.links.calendar_status;
          document.getElementById("openPrompt").href = bot.links.prompt;
          document.getElementById("openConversations").href = bot.links.conversations;
        }};
        const update = async () => {{
          const option = selector?.selectedOptions?.[0];
          const botId = option?.value || "";
          if (!botId) return;
          setStatus("Actualizando datos...");
          setText("botName", option.dataset.name || `Bot #${{botId}}`);
          setText("botClient", option.dataset.client || "-");
          setText("botPhone", option.dataset.phone || "sin WhatsApp");
          setText("botStatus", `Estado: ${{option.dataset.status || "active"}}`);
          document.querySelectorAll("[data-template]").forEach((node) => setHref(node, botId));
          document.getElementById("openBot").href = `/admin/bots/${{botId}}`;
          document.getElementById("testCalendar").href = `/admin/calendar-status?bot_id=${{botId}}`;
          document.getElementById("openPrompt").href = `/admin/bots/${{botId}}/prompt`;
          document.getElementById("openConversations").href = `/admin/conversations?bot_id=${{botId}}`;
          const url = new URL(window.location.href);
          url.searchParams.set("bot_id", botId);
          window.history.replaceState(null, "", url);
          try {{
            const response = await fetch(`/admin/api/panel-state?bot_id=${{encodeURIComponent(botId)}}`, {{
              headers: {{ "Accept": "application/json" }},
            }});
            if (!response.ok) throw new Error("No se pudo cargar el estado del panel.");
            const state = await response.json();
            applyPanelState(state);
            setStatus("Datos actualizados.", "ok");
          }} catch (error) {{
            setStatus("No se pudieron actualizar las metricas; los enlaces siguen listos.", "err");
          }}
        }};
        selector?.addEventListener("change", update);
      }})();
    </script>
    """
    return HTMLResponse(_layout("Centro de control", "app", body))


@router.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request):
    _require_agency(request)
    clients = await db.list_clients()
    rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(c["name"])}</strong><br><span class="muted">{html.escape(c["slug"])}</span></td>
          <td><span class="badge b-calificado">{int(c.get("bot_count") or 0)} bots</span></td>
          <td><span class="badge">{html.escape(c.get("status") or "active")}</span></td>
          <td><a class="btn secondary" href="/admin/clients/{c["id"]}">Ver</a></td>
        </tr>
        """
        for c in clients
    ) or '<tr><td colspan="4" class="empty">Aun no hay clientes.</td></tr>'
    body = f"""
    <div class="topbar"><div><h1>Clientes</h1><div class="sub">Cuentas de negocio con uno o mas bots de WhatsApp.</div></div></div>
    <section class="grid split">
      <div class="table-wrap"><table><thead><tr><th>Cliente</th><th>Bots</th><th>Estado</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>
      <div class="panel">
        <h2>Crear cliente</h2>
        <form method="post" action="/admin/clients">
          <label>Nombre</label><input name="name" placeholder="Clinica Demo" required>
          <label>Slug</label><input name="slug" placeholder="clinica-demo">
          <div class="actions" style="margin-top:14px"><button class="btn" type="submit">Crear cliente</button></div>
        </form>
      </div>
    </section>
    """
    return HTMLResponse(_layout("Clientes", "clients", body))


@router.post("/clients")
async def create_client_page(request: Request, name: str = Form(...), slug: str = Form("")):
    _require_agency(request)
    clean_slug = _slugify(slug or name)
    client_id = await db.create_client(name.strip(), clean_slug)
    return RedirectResponse(f"/admin/clients/{client_id}", status_code=302)


@router.get("/clients/{client_id}", response_class=HTMLResponse)
async def client_detail(request: Request, client_id: int):
    _require_agency(request)
    client = await db.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    bots = await db.list_bots(client_id=client_id)
    users = await db.list_client_users(client_id)
    bot_rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(b["name"])}</strong><br><span class="muted">{html.escape(b["slug"])}</span></td>
          <td>{html.escape(b.get("display_phone_number") or b.get("phone_number_id") or "-")}</td>
          <td><span class="badge">{html.escape(b.get("status") or "active")}</span></td>
          <td><a class="btn secondary" href="/admin/bots/{b["id"]}">Abrir</a></td>
        </tr>
        """
        for b in bots
    ) or '<tr><td colspan="4" class="empty">Este cliente aun no tiene bots.</td></tr>'
    user_rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(u.get("name") or u["email"])}</strong><br><span class="muted">{html.escape(u["email"])}</span></td>
          <td><span class="badge">{html.escape(u["role"])}</span></td>
          <td>{html.escape(u.get("status") or "active")}</td>
        </tr>
        """
        for u in users
    ) or '<tr><td colspan="3" class="empty">Sin usuarios cliente.</td></tr>'
    body = f"""
    <div class="topbar"><div><a class="sub" href="/admin/clients">Volver</a><h1>{html.escape(client["name"])}</h1><div class="sub">{html.escape(client["slug"])}</div></div></div>
    <section class="grid split">
      <div class="table-wrap"><table><thead><tr><th>Bot</th><th>WhatsApp</th><th>Estado</th><th></th></tr></thead><tbody>{bot_rows}</tbody></table></div>
      <div class="panel">
        <h2>Crear bot</h2>
        <form method="post" action="/admin/bots">
          <input type="hidden" name="client_id" value="{client_id}">
          <label>Nombre del bot</label><input name="name" placeholder="Bot Clinica Demo" required>
          <label>Slug</label><input name="slug" placeholder="bot-clinica-demo">
          <label>Phone Number ID</label><input name="phone_number_id" placeholder="1234567890">
          <label>Numero visible</label><input name="display_phone_number" placeholder="+52...">
          <div class="actions" style="margin-top:14px"><button class="btn" type="submit">Crear bot</button></div>
        </form>
      </div>
    </section>
    <section class="grid split" style="margin-top:14px">
      <div class="table-wrap"><table><thead><tr><th>Usuario</th><th>Rol</th><th>Estado</th></tr></thead><tbody>{user_rows}</tbody></table></div>
      <div class="panel">
        <h2>Crear usuario cliente</h2>
        <form method="post" action="/admin/clients/{client_id}/users">
          <label>Email</label><input name="email" type="email" required>
          <label>Nombre</label><input name="name">
          <label>Contrasena temporal</label><input name="password" type="password" required>
          <label>Rol</label><select name="role"><option value="client_admin">Admin cliente</option><option value="client_viewer">Solo lectura</option></select>
          <div class="actions" style="margin-top:14px"><button class="btn" type="submit">Crear usuario</button></div>
        </form>
      </div>
    </section>
    """
    return HTMLResponse(_layout("Cliente", "clients", body))


@router.post("/clients/{client_id}/users")
async def create_client_user_page(
    request: Request,
    client_id: int,
    email: str = Form(...),
    name: str = Form(""),
    password: str = Form(...),
    role: str = Form("client_admin"),
):
    _require_agency(request)
    if role not in ("client_admin", "client_viewer"):
        raise HTTPException(status_code=400, detail="Rol invalido")
    await db.create_client_user(
        client_id,
        email,
        name.strip() or None,
        auth.hash_password(password),
        role,
    )
    return RedirectResponse(f"/admin/clients/{client_id}", status_code=302)


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, saved: str | None = None):
    session = _require_user_manager(request)
    is_agency = _is_agency(session)
    client_id = None if is_agency else int(session["client_id"])
    users = await db.list_users(client_id=client_id)
    clients = await db.list_clients() if is_agency else []
    rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(u.get("name") or u["email"])}</strong><br><span class="muted">{html.escape(u["email"])}</span></td>
          <td>{html.escape(u.get("client_name") or "-")}<br><span class="muted">{html.escape(u.get("client_slug") or "")}</span></td>
          <td><span class="badge">{html.escape(u.get("role") or "client_viewer")}</span></td>
          <td><span class="badge {'b-calificado' if (u.get("status") or "active") == "active" else 'b-descalificado'}">{html.escape(u.get("status") or "active")}</span></td>
        </tr>
        """
        for u in users
    ) or '<tr><td colspan="4" class="empty">Sin usuarios cliente.</td></tr>'
    if is_agency:
        client_options = "".join(
            f'<option value="{int(c["id"])}">{html.escape(c["name"])} ({html.escape(c["slug"])})</option>'
            for c in clients
        )
        client_field = f"""
          <label>Cliente</label>
          <select name="client_id" required>{client_options or '<option value="">Crea un cliente primero</option>'}</select>
        """
    else:
        client_field = f'<input type="hidden" name="client_id" value="{int(session["client_id"])}">'
    notice = '<div class="trend">Usuario guardado.</div>' if saved else ""
    body = f"""
    <div class="topbar">
      <div><h1>Usuarios</h1><div class="sub">Control de acceso por cliente para admins y usuarios de solo lectura.</div>{notice}</div>
    </div>
    <section class="grid split">
      <div class="table-wrap">
        <table><thead><tr><th>Usuario</th><th>Cliente</th><th>Rol</th><th>Estado</th></tr></thead><tbody>{rows}</tbody></table>
      </div>
      <div class="panel">
        <h2>Crear o actualizar usuario</h2>
        <form method="post" action="/admin/users">
          {client_field}
          <label>Email</label><input name="email" type="email" required>
          <label>Nombre</label><input name="name">
          <label>Contrasena temporal</label><input name="password" type="password" required>
          <label>Rol</label>
          <select name="role">
            <option value="client_admin">Admin cliente</option>
            <option value="client_viewer">Solo lectura</option>
          </select>
          <div class="actions" style="margin-top:14px"><button class="btn" type="submit">Guardar usuario</button></div>
        </form>
      </div>
    </section>
    """
    return HTMLResponse(_layout("Usuarios", "users", body))


@router.post("/users")
async def create_user_page(
    request: Request,
    client_id: int = Form(...),
    email: str = Form(...),
    name: str = Form(""),
    password: str = Form(...),
    role: str = Form("client_admin"),
):
    session = _require_user_manager(request)
    target_client_id = int(client_id)
    if not _is_agency(session):
        target_client_id = int(session["client_id"])
    if role not in ("client_admin", "client_viewer"):
        raise HTTPException(status_code=400, detail="Rol invalido")
    if not await db.get_client(target_client_id):
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    await db.create_client_user(
        target_client_id,
        email,
        name.strip() or None,
        auth.hash_password(password),
        role,
    )
    return RedirectResponse("/admin/users?saved=1", status_code=302)


@router.get("/bots", response_class=HTMLResponse)
async def bots_page(request: Request):
    session = _require_login(request)
    client_id = None if _is_agency(session) else int(session["client_id"])
    bots = await db.list_bots(client_id=client_id)
    rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(b["name"])}</strong><br><span class="muted">{html.escape(b["slug"])}</span></td>
          <td>{html.escape(b.get("client_name") or "-")}</td>
          <td>{html.escape(b.get("display_phone_number") or b.get("phone_number_id") or "-")}</td>
          <td><span class="badge">{html.escape(b.get("status") or "active")}</span></td>
          <td><a class="btn secondary" href="/admin/bots/{b["id"]}">Abrir</a></td>
        </tr>
        """
        for b in bots
    ) or '<tr><td colspan="5" class="empty">No hay bots disponibles.</td></tr>'
    body = f"""
    <div class="topbar"><div><h1>Bots</h1><div class="sub">Bots de WhatsApp configurados en esta instalacion.</div></div></div>
    <section class="table-wrap"><table><thead><tr><th>Bot</th><th>Cliente</th><th>WhatsApp</th><th>Estado</th><th></th></tr></thead><tbody>{rows}</tbody></table></section>
    """
    return HTMLResponse(_layout("Bots", "bots", body))


@router.post("/bots")
async def create_bot_page(
    request: Request,
    client_id: int = Form(...),
    name: str = Form(...),
    slug: str = Form(""),
    phone_number_id: str = Form(""),
    display_phone_number: str = Form(""),
):
    _require_agency(request)
    bot_id = await db.create_bot(
        client_id=client_id,
        slug=_slugify(slug or name),
        name=name.strip(),
        phone_number_id=phone_number_id.strip() or None,
        display_phone_number=display_phone_number.strip() or None,
    )
    return RedirectResponse(f"/admin/bots/{bot_id}", status_code=302)


@router.get("/bots/{bot_id}", response_class=HTMLResponse)
async def bot_detail(request: Request, bot_id: int):
    session = _require_login(request)
    bot = await _require_bot_access(session, bot_id)
    metrics = await db.admin_metrics(bot_id=bot_id)
    threads = await db.list_conversation_threads(limit=8, bot_id=bot_id)
    lead_rows = await db.list_leads(limit=8, bot_id=bot_id)
    thread_html = "".join(
        f"<tr><td><strong>{html.escape(t['wa_id'])}</strong><br><span class='muted'>{html.escape(_clip(t.get('last_content'), 80))}</span></td><td>{_fmt_dt(t.get('last_message_at'))}</td><td><a class='btn secondary' href='/admin/conversations?bot_id={bot_id}&wa_id={html.escape(t['wa_id'])}'>Ver</a></td></tr>"
        for t in threads
    ) or '<tr><td colspan="3" class="empty">Sin conversaciones.</td></tr>'
    leads_html = "".join(
        f"<tr><td><strong>{html.escape(_display_name(l.get('nombre'), l['wa_id']))}</strong><br><span class='muted'>{html.escape(l['wa_id'])}</span></td><td><span class='badge b-{html.escape(l['qualification_status'])}'>{html.escape(l['qualification_status'].replace('_', ' '))}</span></td></tr>"
        for l in lead_rows
    ) or '<tr><td colspan="2" class="empty">Sin leads.</td></tr>'
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/bots">Volver</a><h1>{html.escape(bot["name"])}</h1><div class="sub">{html.escape(bot.get("client_name") or "-")} - {html.escape(bot.get("phone_number_id") or "sin phone_number_id")}</div></div>
      <span class="badge">{html.escape(bot.get("status") or "active")}</span>
    </div>
    <section class="panel" style="margin-bottom:14px">
      <h2>Configuracion del agente</h2>
      <div class="actions">
        <a class="btn secondary" href="/admin/bots/{bot_id}/prompt">Prompt con IA</a>
        <a class="btn secondary" href="/admin/bots/{bot_id}/knowledge">Base de conocimiento</a>
        <a class="btn secondary" href="/admin/bots/{bot_id}/integrations">Integraciones</a>
        <a class="btn secondary" href="/admin/bots/{bot_id}/whatsapp">Conectar WhatsApp</a>
        <a class="btn secondary" href="/admin/bots/{bot_id}/whatsapp/diagnostics">Diagnostico Meta</a>
        <a class="btn secondary" href="/admin/bots/{bot_id}/whatsapp/templates">Plantillas Meta</a>
        <a class="btn secondary" href="/admin/bots/{bot_id}/skills">Habilidades</a>
        <a class="btn secondary" href="/admin/calendar-status?bot_id={bot_id}">Probar calendario</a>
      </div>
    </section>
    <section class="grid kpis">
      <div class="card"><div class="k">Conversaciones</div><div class="n">{metrics.get("conversations", 0)}</div></div>
      <div class="card"><div class="k">Mensajes</div><div class="n">{metrics.get("messages", 0)}</div></div>
      <div class="card"><div class="k">Leads</div><div class="n">{metrics.get("leads", 0)}</div></div>
      <div class="card"><div class="k">Calificados</div><div class="n">{metrics.get("qualified", 0)}</div></div>
    </section>
    <section class="grid split" style="margin-top:14px">
      <div class="table-wrap"><table><thead><tr><th>Conversacion</th><th>Ultimo</th><th></th></tr></thead><tbody>{thread_html}</tbody></table></div>
      <div class="table-wrap"><table><thead><tr><th>Lead</th><th>Estado</th></tr></thead><tbody>{leads_html}</tbody></table></div>
    </section>
    """
    return HTMLResponse(_layout("Bot", "bots", body))


@router.get("/meta/oauth/callback", response_class=HTMLResponse)
async def meta_oauth_callback(request: Request, code: str = "", error: str = ""):
    _require_login(request)
    message = (
        "Meta devolvio un codigo. Vuelve a la pantalla Conectar WhatsApp del bot y confirma el guardado."
        if code else
        "Meta no devolvio codigo. Revisa la configuracion de Embedded Signup."
    )
    if error:
        message = f"Meta devolvio un error: {html.escape(error)}"
    body = f"""
    <div class="topbar"><div><h1>Callback de Meta</h1><div class="sub">{message}</div></div></div>
    <section class="panel">
      <label>Codigo recibido</label>
      <input value="{html.escape(code)}" readonly>
      <div class="actions" style="margin-top:14px">
        <a class="btn secondary" href="/admin/app">Volver al centro de control</a>
      </div>
    </section>
    """
    return HTMLResponse(_layout("Callback Meta", "tech-provider", body))


@router.get("/tech-provider/review", response_class=HTMLResponse)
async def tech_provider_review_page(request: Request):
    _require_agency(request)
    settings = meta_provider.embedded_signup_settings()
    missing = ", ".join(settings["missing"]) if settings["missing"] else "Configuracion base completa"
    checklist = (
        ("Business Portfolio", "2FA activo, negocio verificable y documentos listos."),
        ("App Meta nueva", "Nombre visible Humanio/Asistto, sin marcas Meta ni WhatsApp en el nombre."),
        ("Permisos", "Solicitar whatsapp_business_messaging y whatsapp_business_management."),
        ("Video messaging", "Mostrar el panel enviando un mensaje y el telefono recibiendolo."),
        ("Video management", "Mostrar creacion/listado de una plantilla desde la pantalla Plantillas Meta."),
        ("Datos", "Declarar que WhatsApp Business Solution Data no entrena modelos generales de IA."),
        ("Produccion", "Probar health, webhook, bot demo, plantilla, conversacion y escalacion humana."),
    )
    rows = "".join(
        f"<tr><td><strong>{html.escape(name)}</strong></td><td>{html.escape(desc)}</td></tr>"
        for name, desc in checklist
    )
    body = f"""
    <div class="topbar"><div><h1>Modo revision Meta</h1><div class="sub">Guion interno para preparar App Review y Access Verification.</div></div></div>
    <section class="grid split">
      <div class="table-wrap"><table><thead><tr><th>Pieza</th><th>Evidencia</th></tr></thead><tbody>{rows}</tbody></table></div>
      <div class="panel">
        <h2>Estado Embedded Signup</h2>
        <p class="sub">App ID: {html.escape(settings["app_id"] or "-")}</p>
        <p class="sub">Config ID: {html.escape(settings["config_id"] or "-")}</p>
        <p class="sub">Redirect URI: {html.escape(settings["redirect_uri"] or "-")}</p>
        <p class="sub">Graph: {html.escape(settings["graph_version"])}</p>
        <p><span class="badge {'b-calificado' if settings["ready"] else 'b-pendiente'}">{html.escape(missing)}</span></p>
        <div class="actions" style="margin-top:14px">
          <a class="btn secondary" href="/privacy">Privacidad</a>
          <a class="btn secondary" href="/terms">Terminos</a>
          <a class="btn secondary" href="/ai-data-policy">IA y datos</a>
          <a class="btn secondary" href="/data-deletion">Eliminar datos</a>
        </div>
      </div>
    </section>
    """
    return HTMLResponse(_layout("Revision Meta", "tech-provider", body))


@router.get("/bots/{bot_id}/whatsapp", response_class=HTMLResponse)
async def bot_whatsapp_connect_page(request: Request, bot_id: int, saved: str | None = None):
    session = _require_login(request)
    bot = await _require_bot_editor(session, bot_id)
    settings = meta_provider.embedded_signup_settings()
    missing = ", ".join(settings["missing"]) if settings["missing"] else "Listo para abrir Embedded Signup"
    notice = '<div class="trend">Conexion guardada y token cifrado.</div>' if saved else ""
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/bots/{bot_id}">Volver</a><h1>Conectar WhatsApp</h1><div class="sub">{html.escape(bot["name"])} - Embedded Signup oficial de Meta.</div>{notice}</div>
      <span class="badge {'b-calificado' if settings["ready"] else 'b-pendiente'}">{html.escape(missing)}</span>
    </div>
    <section class="grid split">
      <div class="panel">
        <h2>Embedded Signup</h2>
        <p class="sub">Usa este flujo cuando el cliente conecta su propio WABA/numero. El token se guarda cifrado como integracion <span class="code">whatsapp_cloud</span>.</p>
        <div class="actions" style="margin-top:14px">
          <button class="btn whatsapp" type="button" id="launchSignup" {"disabled" if not settings["ready"] else ""}>Abrir Embedded Signup</button>
          <a class="btn secondary" href="/admin/bots/{bot_id}/whatsapp/diagnostics">Diagnostico</a>
          <a class="btn secondary" href="/admin/bots/{bot_id}/whatsapp/templates">Plantillas</a>
        </div>
        <div id="signupStatus" class="sync-status">Esperando conexion.</div>
      </div>
      <div class="panel">
        <h2>Guardar conexion</h2>
        <form method="post" action="/admin/bots/{bot_id}/whatsapp/connect">
          <label>Authorization code de Meta</label><input id="authCode" name="authorization_code" autocomplete="off">
          <label>Access token temporal/manual</label><input name="access_token" type="password" autocomplete="off">
          <label>Business ID</label><input id="businessId" name="business_id" value="{html.escape(bot.get("business_id") or "")}">
          <label>WABA ID</label><input id="wabaId" name="waba_id" value="{html.escape(bot.get("waba_id") or "")}">
          <label>Phone Number ID</label><input id="phoneNumberId" name="phone_number_id" value="{html.escape(bot.get("phone_number_id") or "")}" required>
          <label>Numero visible</label><input id="displayPhoneNumber" name="display_phone_number" value="{html.escape(bot.get("display_phone_number") or "")}">
          <div class="actions" style="margin-top:14px"><button class="btn" type="submit">Guardar conexion cifrada</button></div>
        </form>
      </div>
    </section>
    <script async defer crossorigin="anonymous" src="https://connect.facebook.net/en_US/sdk.js"></script>
    <script>
      (() => {{
        const settings = {json.dumps(settings)};
        const status = document.getElementById("signupStatus");
        const setStatus = (text, cls = "") => {{
          status.className = `sync-status ${{cls}}`;
          status.textContent = text;
        }};
        window.fbAsyncInit = function() {{
          if (!settings.app_id) return;
          FB.init({{ appId: settings.app_id, cookie: true, xfbml: true, version: settings.graph_version }});
        }};
        window.addEventListener("message", (event) => {{
          if (!event.origin.endsWith("facebook.com")) return;
          let data = event.data;
          try {{ if (typeof data === "string") data = JSON.parse(data); }} catch (_) {{ return; }}
          const payload = data?.data || data;
          if (payload?.phone_number_id) document.getElementById("phoneNumberId").value = payload.phone_number_id;
          if (payload?.waba_id) document.getElementById("wabaId").value = payload.waba_id;
          if (payload?.business_id) document.getElementById("businessId").value = payload.business_id;
          if (payload?.display_phone_number) document.getElementById("displayPhoneNumber").value = payload.display_phone_number;
          if (payload?.phone_number_id || payload?.waba_id) setStatus("Datos recibidos de Embedded Signup. Revisa y guarda.", "ok");
        }});
        document.getElementById("launchSignup")?.addEventListener("click", () => {{
          if (!window.FB) return setStatus("Facebook SDK no esta listo todavia.", "err");
          FB.login((response) => {{
            const code = response?.authResponse?.code;
            if (code) {{
              document.getElementById("authCode").value = code;
              setStatus("Codigo recibido. Revisa los IDs y guarda.", "ok");
            }} else {{
              setStatus("Meta no devolvio codigo. Revisa permisos o configuracion.", "err");
            }}
          }}, {{
            config_id: settings.config_id,
            response_type: "code",
            override_default_response_type: true,
            extras: {{ feature: "whatsapp_embedded_signup" }}
          }});
        }});
      }})();
    </script>
    """
    return HTMLResponse(_layout("Conectar WhatsApp", "bots", body, session=session))


@router.post("/bots/{bot_id}/whatsapp/connect")
async def bot_whatsapp_connect_submit(
    request: Request,
    bot_id: int,
    authorization_code: str = Form(""),
    access_token: str = Form(""),
    business_id: str = Form(""),
    waba_id: str = Form(""),
    phone_number_id: str = Form(...),
    display_phone_number: str = Form(""),
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    try:
        await meta_provider.connect_bot_from_embedded_signup(
            meta_provider.MetaConnectionInput(
                bot_id=bot_id,
                phone_number_id=phone_number_id,
                display_phone_number=display_phone_number,
                waba_id=waba_id,
                business_id=business_id,
                authorization_code=authorization_code,
                access_token=access_token,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/admin/bots/{bot_id}/whatsapp?saved=1", status_code=302)


@router.get("/bots/{bot_id}/whatsapp/diagnostics", response_class=HTMLResponse)
async def bot_whatsapp_diagnostics_page(request: Request, bot_id: int):
    session = _require_login(request)
    bot = await _require_bot_access(session, bot_id)
    diag = await meta_provider.diagnose_bot_connection(bot_id)
    checks = diag.get("checks", {})
    rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(key.replace("_", " "))}</strong></td>
          <td><span class="badge {'b-calificado' if value else 'b-pendiente'}">{'OK' if value else 'Pendiente'}</span></td>
        </tr>
        """
        for key, value in checks.items()
    )
    override = diag.get("override_callback_uri") or ""
    override_html = (
        f'<div class="err">Hay override_callback_uri heredado: {html.escape(override)}</div>'
        if override else
        '<div class="trend">No se detecto override_callback_uri en subscribed_apps.</div>'
    )
    error_html = f'<div class="err">{html.escape(diag.get("error") or "")}</div>' if diag.get("error") else ""
    payload = html.escape(_pretty_json({
        "subscribed_apps": diag.get("subscribed_apps"),
        "phone_number": diag.get("phone_number"),
    }))
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/bots/{bot_id}/whatsapp">Volver</a><h1>Diagnostico Meta</h1><div class="sub">{html.escape(bot["name"])} - WABA, token, webhook y numero.</div></div>
      <span class="badge {'b-calificado' if diag.get("ok") else 'b-pendiente'}">{'OK' if diag.get("ok") else 'Pendiente'}</span>
    </div>
    {error_html}
    <section class="grid split">
      <div class="table-wrap"><table><thead><tr><th>Revision</th><th>Estado</th></tr></thead><tbody>{rows}</tbody></table></div>
      <div class="panel">
        <h2>Conexion</h2>
        <p class="sub">WABA: {html.escape(diag.get("waba_id") or "-")}</p>
        <p class="sub">Phone Number ID: {html.escape(diag.get("phone_number_id") or "-")}</p>
        <p class="sub">Numero: {html.escape(diag.get("display_phone_number") or "-")}</p>
        {override_html}
      </div>
    </section>
    <section class="panel" style="margin-top:14px">
      <h2>Respuesta Meta resumida</h2>
      <textarea readonly class="short code">{payload}</textarea>
    </section>
    """
    return HTMLResponse(_layout("Diagnostico Meta", "bots", body, session=session))


@router.get("/bots/{bot_id}/whatsapp/templates", response_class=HTMLResponse)
async def bot_whatsapp_templates_page(request: Request, bot_id: int, saved: str | None = None):
    session = _require_login(request)
    bot = await _require_bot_access(session, bot_id)
    can_edit = _is_agency(session) or session.get("role") == "client_admin"
    error = ""
    templates: list[dict] = []
    try:
        payload = await meta_provider.list_message_templates(bot_id)
        templates = payload.get("data") or []
    except Exception as exc:
        error = str(exc)
    rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(t.get("name") or "-")}</strong><br><span class="muted">{html.escape(t.get("language") or "-")}</span></td>
          <td><span class="badge">{html.escape(t.get("category") or "-")}</span></td>
          <td><span class="badge {'b-calificado' if (t.get("status") or "").upper() == "APPROVED" else 'b-pendiente'}">{html.escape(t.get("status") or "-")}</span></td>
        </tr>
        """
        for t in templates
    ) or '<tr><td colspan="3" class="empty">Sin plantillas cargadas desde Meta.</td></tr>'
    error_html = f'<div class="err">{html.escape(error)}</div>' if error else ""
    notice = '<div class="trend">Solicitud de plantilla enviada a Meta.</div>' if saved else ""
    form = f"""
      <div class="panel">
        <h2>Crear plantilla simple</h2>
        <form method="post" action="/admin/bots/{bot_id}/whatsapp/templates">
          <label>Nombre</label><input name="name" placeholder="asistto_demo_v1" required {'readonly' if not can_edit else ''}>
          <label>Idioma</label><input name="language" value="es_MX" required {'readonly' if not can_edit else ''}>
          <label>Categoria</label><select name="category" {'disabled' if not can_edit else ''}><option value="UTILITY">Utility</option><option value="MARKETING">Marketing</option></select>
          <label>Texto del cuerpo</label><textarea name="body_text" class="short" required {'readonly' if not can_edit else ''}>Hola, soy {{1}} de Asistto by Humanio. Te contacto para continuar con la atencion de {{2}}.</textarea>
          <div class="actions" style="margin-top:14px">{'<button class="btn" type="submit">Crear plantilla</button>' if can_edit else '<span class="badge">Solo lectura</span>'}</div>
        </form>
      </div>
    """
    body = f"""
    <div class="topbar"><div><a class="sub" href="/admin/bots/{bot_id}/whatsapp">Volver</a><h1>Plantillas Meta</h1><div class="sub">{html.escape(bot["name"])} - evidencia para whatsapp_business_management.</div>{notice}</div></div>
    {error_html}
    <section class="grid split">
      <div class="table-wrap"><table><thead><tr><th>Plantilla</th><th>Categoria</th><th>Estado</th></tr></thead><tbody>{rows}</tbody></table></div>
      {form}
    </section>
    """
    return HTMLResponse(_layout("Plantillas Meta", "bots", body, session=session))


@router.post("/bots/{bot_id}/whatsapp/templates")
async def bot_whatsapp_templates_submit(
    request: Request,
    bot_id: int,
    name: str = Form(...),
    language: str = Form("es_MX"),
    category: str = Form("UTILITY"),
    body_text: str = Form(...),
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    try:
        await meta_provider.create_message_template(bot_id, name, language, category, body_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/admin/bots/{bot_id}/whatsapp/templates?saved=1", status_code=302)


@router.get("/bots/{bot_id}/prompt", response_class=HTMLResponse)
async def bot_prompt_page(request: Request, bot_id: int, saved: str | None = None):
    session = _require_login(request)
    bot = await _require_bot_access(session, bot_id)
    prompt = await db.get_active_bot_prompt(bot_id)
    content = (prompt or {}).get("content") or config.SYSTEM_PROMPT
    source = "Postgres" if prompt else "Archivo base"
    can_edit = _is_agency(session) or session.get("role") == "client_admin"
    notice = '<div class="trend">Prompt publicado.</div>' if saved else ""
    button = (
        '<button class="btn" type="submit">Publicar prompt</button>'
        if can_edit else
        '<span class="badge">Solo lectura</span>'
    )
    readonly = "" if can_edit else "readonly"
    default_provider = (config.PROMPT_ASSISTANT_PROVIDER or "openai_compatible").strip()
    default_model = config.PROMPT_ASSISTANT_MODEL or config.OPENAI_MODEL
    assistant_base_url = config.PROMPT_ASSISTANT_BASE_URL
    base_url_hint = config.PROMPT_ASSISTANT_BASE_URL or config.OPENAI_BASE_URL or "OpenAI directo"
    has_configured_key = bool(
        config.PROMPT_ASSISTANT_API_KEY
        or config.OPENAI_API_KEY
        or config.ANTHROPIC_API_KEY
    )
    key_state = "API configurada" if has_configured_key else "Pega una API key temporal"

    def selected_provider(value: str) -> str:
        return "selected" if default_provider in {value, value.replace("_", "-")} else ""

    assistant_panel = f"""
      <aside class="panel prompt-assistant">
        <h2>Asistente de IA</h2>
        <div class="sub">{html.escape(key_state)}</div>
        <form id="promptAssistantForm">
          <label>Proveedor</label>
          <select name="provider" id="assistantProvider">
            <option value="openai_compatible" {selected_provider("openai_compatible")}>OpenAI / compatible</option>
            <option value="openrouter" {selected_provider("openrouter")}>OpenRouter</option>
            <option value="anthropic" {selected_provider("anthropic")}>Claude</option>
          </select>
          <label>API key temporal</label>
          <input type="password" name="api_key" autocomplete="off" placeholder="Opcional si ya esta configurada">
          <label>Base URL</label>
          <input name="base_url" placeholder="{html.escape(base_url_hint)}" value="{html.escape(assistant_base_url)}">
          <label>Modelo</label>
          <input name="model" placeholder="Modelo" value="{html.escape(default_model)}">
          <label>Que quieres cambiar</label>
          <textarea name="instruction" required placeholder="Ej. Hazlo para una clinica dental, agenda citas y califica urgencias."></textarea>
          <div class="actions" style="margin-top:14px">
            <button class="btn" id="runPromptAssistant" type="submit">Generar con IA</button>
            <button class="btn secondary" id="applyAssistantResult" type="button" disabled>Usar sugerencia</button>
          </div>
          <div id="assistantStatus" class="prompt-status">Listo.</div>
        </form>
        <label>Sugerencia generada</label>
        <textarea id="assistantResult" class="result" readonly></textarea>
      </aside>
    """ if can_edit else """
      <aside class="panel">
        <h2>Asistente de IA</h2>
        <div class="sub">Tu usuario tiene acceso de solo lectura.</div>
      </aside>
    """
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/bots/{bot_id}">Volver</a><h1>Prompt</h1><div class="sub">{html.escape(bot["name"])} - origen actual: {source}</div></div>
    </div>
    <section class="grid prompt-workspace">
      <div class="panel editor">
        <form method="post" action="/admin/bots/{bot_id}/prompt">
          <label>Instrucciones del agente</label>
          <textarea id="promptContent" name="content" {readonly} required>{html.escape(content)}</textarea>
          <div class="actions" style="margin-top:14px">{button}{notice}</div>
        </form>
      </div>
      {assistant_panel}
    </section>
    <script>
      (() => {{
        const form = document.getElementById("promptAssistantForm");
        const promptContent = document.getElementById("promptContent");
        const result = document.getElementById("assistantResult");
        const status = document.getElementById("assistantStatus");
        const runButton = document.getElementById("runPromptAssistant");
        const applyButton = document.getElementById("applyAssistantResult");
        const setStatus = (message, className = "") => {{
          if (!status) return;
          status.className = `prompt-status ${{className}}`;
          status.textContent = message;
        }};
        form?.addEventListener("submit", async (event) => {{
          event.preventDefault();
          const payload = new FormData(form);
          payload.set("current_prompt", promptContent?.value || "");
          setStatus("Generando prompt...");
          if (runButton) runButton.disabled = true;
          if (applyButton) applyButton.disabled = true;
          try {{
            const response = await fetch("/admin/bots/{bot_id}/prompt/assist", {{
              method: "POST",
              headers: {{ "Accept": "application/json" }},
              body: payload,
            }});
            const data = await response.json().catch(() => ({{}}));
            if (!response.ok || !data.ok) {{
              throw new Error(data.error || "No se pudo generar el prompt.");
            }}
            result.value = data.prompt || "";
            setStatus(`Listo con ${{data.provider_label || "IA"}}.`, "ok");
            if (applyButton) applyButton.disabled = !result.value.trim();
          }} catch (error) {{
            setStatus(error.message || "No se pudo generar el prompt.", "err");
          }} finally {{
            if (runButton) runButton.disabled = false;
          }}
        }});
        applyButton?.addEventListener("click", () => {{
          const suggestion = result?.value?.trim() || "";
          if (!suggestion || !promptContent) return;
          promptContent.value = suggestion;
          promptContent.focus();
          setStatus("Sugerencia colocada en el editor. Publica para guardar.", "ok");
        }});
      }})();
    </script>
    """
    return HTMLResponse(_layout("Prompt", "bots", body))


@router.post("/bots/{bot_id}/prompt")
async def save_bot_prompt_page(
    request: Request,
    bot_id: int,
    content: str = Form(...),
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    clean = content.strip()
    if not clean:
        raise HTTPException(status_code=400, detail="El prompt no puede estar vacio")
    await db.publish_bot_prompt(bot_id, clean)
    return RedirectResponse(f"/admin/bots/{bot_id}/prompt?saved=1", status_code=302)


@router.post("/bots/{bot_id}/prompt/assist", response_class=JSONResponse)
async def assist_bot_prompt_page(
    request: Request,
    bot_id: int,
    instruction: str = Form(...),
    current_prompt: str = Form(""),
    provider: str = Form(""),
    api_key: str = Form(""),
    base_url: str = Form(""),
    model: str = Form(""),
):
    from app import prompt_assistant

    session = _require_login(request)
    bot = await _require_bot_editor(session, bot_id)
    try:
        knowledge_docs = await db.list_bot_knowledge(bot_id, active_only=True)
        result = await prompt_assistant.assist_prompt(
            bot=bot,
            current_prompt=current_prompt,
            instruction=instruction,
            knowledge_docs=knowledge_docs,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        return JSONResponse(result)
    except prompt_assistant.PromptAssistantError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": prompt_assistant.safe_error(exc)},
            status_code=502,
        )


@router.get("/bots/{bot_id}/knowledge", response_class=HTMLResponse)
async def bot_knowledge_page(request: Request, bot_id: int, saved: str | None = None):
    session = _require_login(request)
    bot = await _require_bot_access(session, bot_id)
    docs = await db.list_bot_knowledge(bot_id, active_only=False)
    can_edit = _is_agency(session) or session.get("role") == "client_admin"
    rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(doc["title"])}</strong><br><div class="knowledge-preview">{html.escape(_clip(doc.get("content"), 260))}</div></td>
          <td><span class="badge">{html.escape(doc.get("status") or "active")}</span></td>
          <td>{_fmt_dt(doc.get("updated_at") or doc.get("created_at"))}</td>
          <td><a class="btn secondary" href="/admin/bots/{bot_id}/knowledge/{doc["id"]}">Editar</a></td>
        </tr>
        """
        for doc in docs
    ) or '<tr><td colspan="4" class="empty">Sin documentos de conocimiento.</td></tr>'
    create_form = ""
    if can_edit:
        create_form = f"""
        <div class="panel">
          <h2>Agregar documento</h2>
          <form method="post" action="/admin/bots/{bot_id}/knowledge">
            <label>Titulo</label><input name="title" placeholder="Servicios, precios, politicas..." required>
            <label>Contenido</label><textarea name="content" rows="12" required></textarea>
            <div class="actions" style="margin-top:14px"><button class="btn" type="submit">Guardar documento</button></div>
          </form>
        </div>
        """
    notice = '<div class="trend">Cambios guardados.</div>' if saved else ""
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/bots/{bot_id}">Volver</a><h1>Base de conocimiento</h1><div class="sub">{html.escape(bot["name"])} usa estos documentos junto con su prompt activo.</div>{notice}</div>
    </div>
    <section class="grid split">
      <div class="table-wrap"><table><thead><tr><th>Documento</th><th>Estado</th><th>Actualizado</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>
      {create_form or '<div class="panel"><h2>Permisos</h2><div class="sub">Tu usuario tiene acceso de solo lectura.</div></div>'}
    </section>
    """
    return HTMLResponse(_layout("Knowledge", "bots", body))


@router.post("/bots/{bot_id}/knowledge")
async def create_bot_knowledge_page(
    request: Request,
    bot_id: int,
    title: str = Form(...),
    content: str = Form(...),
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    clean_title = title.strip()
    clean_content = content.strip()
    if not clean_title or not clean_content:
        raise HTTPException(status_code=400, detail="Titulo y contenido son obligatorios")
    await db.create_bot_knowledge(bot_id, clean_title, clean_content)
    return RedirectResponse(f"/admin/bots/{bot_id}/knowledge?saved=1", status_code=302)


@router.get("/bots/{bot_id}/knowledge/{knowledge_id}", response_class=HTMLResponse)
async def edit_bot_knowledge_page(
    request: Request,
    bot_id: int,
    knowledge_id: int,
    saved: str | None = None,
):
    session = _require_login(request)
    bot = await _require_bot_access(session, bot_id)
    doc = await db.get_bot_knowledge(bot_id, knowledge_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    can_edit = _is_agency(session) or session.get("role") == "client_admin"
    readonly = "" if can_edit else "readonly"
    button = (
        '<button class="btn" type="submit">Guardar cambios</button>'
        if can_edit else
        '<span class="badge">Solo lectura</span>'
    )
    archive_section = (
        f"""
        <form method="post" action="/admin/bots/{bot_id}/knowledge/{knowledge_id}/archive" style="margin-top:10px">
          <button class="btn secondary" type="submit">Archivar</button>
        </form>
        """
        if can_edit and doc.get("status") != "archived" else ""
    )
    notice = '<div class="trend">Documento actualizado.</div>' if saved else ""
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/bots/{bot_id}/knowledge">Volver</a><h1>{html.escape(doc["title"])}</h1><div class="sub">{html.escape(bot["name"])} - {html.escape(doc.get("status") or "active")}</div></div>
    </div>
    <section class="panel editor">
      <form method="post" action="/admin/bots/{bot_id}/knowledge/{knowledge_id}">
        <label>Titulo</label><input name="title" value="{html.escape(doc["title"])}" {readonly} required>
        <label>Contenido</label><textarea name="content" {readonly} required>{html.escape(doc.get("content") or "")}</textarea>
        <div class="actions" style="margin-top:14px">{button}{notice}</div>
      </form>
      {archive_section}
    </section>
    """
    return HTMLResponse(_layout("Knowledge", "bots", body))


@router.post("/bots/{bot_id}/knowledge/{knowledge_id}")
async def update_bot_knowledge_page(
    request: Request,
    bot_id: int,
    knowledge_id: int,
    title: str = Form(...),
    content: str = Form(...),
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    clean_title = title.strip()
    clean_content = content.strip()
    if not clean_title or not clean_content:
        raise HTTPException(status_code=400, detail="Titulo y contenido son obligatorios")
    updated = await db.update_bot_knowledge(
        bot_id,
        knowledge_id,
        clean_title,
        clean_content,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return RedirectResponse(
        f"/admin/bots/{bot_id}/knowledge/{knowledge_id}?saved=1",
        status_code=302,
    )


@router.post("/bots/{bot_id}/knowledge/{knowledge_id}/archive")
async def archive_bot_knowledge_page(
    request: Request,
    bot_id: int,
    knowledge_id: int,
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    archived = await db.archive_bot_knowledge(bot_id, knowledge_id)
    if not archived:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return RedirectResponse(f"/admin/bots/{bot_id}/knowledge?saved=1", status_code=302)


INTEGRATION_TYPES = (
    ("google_calendar", "Google Calendar"),
    ("external_api", "API externa"),
    ("webhook", "Webhook"),
    ("crm", "CRM"),
    ("custom", "Personalizada"),
)


def _integration_type_options(selected: str = "external_api") -> str:
    return "".join(
        f'<option value="{html.escape(value)}" {"selected" if value == selected else ""}>{html.escape(label)}</option>'
        for value, label in INTEGRATION_TYPES
    )


def _default_integration_config(integration_type: str) -> dict:
    if integration_type == "external_api":
        return {
            "base_url": "",
            "method": "GET",
            "allowed_methods": ["GET", "POST"],
            "headers": {"Accept": "application/json"},
            "auth_header": "Authorization",
            "auth_scheme": "Bearer",
            "timeout_seconds": 20,
            "test": {"method": "GET", "path": "/health", "params": {}},
            "operations": [
                {
                    "name": "buscar_cliente",
                    "description": "Busca un cliente por telefono o correo.",
                    "method": "GET",
                    "path": "/clientes",
                    "params": {"phone": "{{telefono}}"},
                },
                {
                    "name": "crear_lead",
                    "description": "Registra un prospecto calificado.",
                    "method": "POST",
                    "path": "/leads",
                    "json": {"name": "{{nombre}}", "phone": "{{telefono}}"},
                },
            ],
        }
    if integration_type == "webhook":
        return {
            "url": "",
            "method": "POST",
            "allowed_methods": ["POST"],
            "headers": {"Content-Type": "application/json"},
            "auth_header": "Authorization",
            "auth_scheme": "Bearer",
            "timeout_seconds": 20,
        }
    if integration_type == "google_calendar":
        return {"calendar_id": "primary", "timezone": "America/Chihuahua"}
    return {}


def _parse_json_list(value: str, field_name: str) -> list:
    clean = (value or "").strip()
    if not clean:
        return []
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} invalido: {exc.msg}") from exc
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail=f"{field_name} debe ser una lista.")
    return parsed


def _clean_methods(value: str | list | None) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[,\s]+", value or "")
    methods = []
    for item in raw:
        method = str(item or "").strip().upper()
        if method and method not in methods:
            methods.append(method)
    return methods or ["GET", "POST"]


def _safe_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _clean_operations(value: str) -> list[dict]:
    operations = []
    for item in _parse_json_list(value, "Operaciones JSON"):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Cada operacion debe ser un objeto.")
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or item.get("url") or "").strip()
        if not name or not path:
            raise HTTPException(status_code=400, detail="Cada operacion necesita name y path/url.")
        operation = {
            "name": name,
            "description": str(item.get("description") or "").strip(),
            "method": str(item.get("method") or "GET").strip().upper(),
        }
        if item.get("url"):
            operation["url"] = str(item.get("url")).strip()
        else:
            operation["path"] = path
        for key in ("params", "json", "data"):
            if item.get(key) is not None:
                if not isinstance(item.get(key), dict):
                    raise HTTPException(
                        status_code=400,
                        detail=f"{key} de {name} debe ser un objeto.",
                    )
                operation[key] = item[key]
        operations.append(operation)
    return operations


def _external_api_config_from_form(
    *,
    base_url: str,
    method: str,
    default_path: str,
    allowed_methods: str,
    headers_json: str,
    auth_header: str,
    auth_scheme: str,
    timeout_seconds: int,
    test_method: str,
    test_path: str,
    test_params_json: str,
    operations_json: str,
) -> dict:
    headers = _parse_config_json(headers_json)
    test_params = _parse_config_json(test_params_json)
    clean_timeout = _safe_int(timeout_seconds, 20, 3, 60)
    return {
        "base_url": base_url.strip().rstrip("/"),
        "method": (method or "GET").strip().upper(),
        "path": default_path.strip(),
        "allowed_methods": _clean_methods(allowed_methods),
        "headers": headers,
        "auth_header": (auth_header or "Authorization").strip(),
        "auth_scheme": (auth_scheme or "Bearer").strip(),
        "timeout_seconds": clean_timeout,
        "test": {
            "method": (test_method or "GET").strip().upper(),
            "path": test_path.strip() or default_path.strip() or "/",
            "params": test_params,
        },
        "operations": _clean_operations(operations_json),
    }


def _external_api_operations_rows(operations: list) -> str:
    rows = []
    for operation in operations or []:
        if not isinstance(operation, dict):
            continue
        rows.append(
            f"""
            <tr>
              <td><strong>{html.escape(str(operation.get("name") or ""))}</strong><br><span class="muted">{html.escape(str(operation.get("description") or ""))}</span></td>
              <td><span class="badge">{html.escape(str(operation.get("method") or "GET").upper())}</span></td>
              <td><span class="code">{html.escape(str(operation.get("path") or operation.get("url") or ""))}</span></td>
            </tr>
            """
        )
    return "".join(rows) or '<tr><td colspan="3" class="empty">Sin operaciones configuradas.</td></tr>'


def _external_api_builder_panel(
    bot_id: int,
    integration_id: int,
    integration: dict,
    can_edit: bool,
) -> str:
    if integration.get("integration_type") != "external_api":
        return ""
    cfg = integration.get("config") or {}
    test_cfg = cfg.get("test") if isinstance(cfg.get("test"), dict) else {}
    readonly = "" if can_edit else "readonly"
    disabled = "" if can_edit else "disabled"
    headers_json = _pretty_json(cfg.get("headers") if isinstance(cfg.get("headers"), dict) else {})
    test_params_json = _pretty_json(test_cfg.get("params") if isinstance(test_cfg.get("params"), dict) else {})
    operations = cfg.get("operations") if isinstance(cfg.get("operations"), list) else []
    operations_json = json.dumps(
        operations or _default_integration_config("external_api")["operations"],
        ensure_ascii=True,
        indent=2,
    )
    methods = ", ".join(_clean_methods(cfg.get("allowed_methods") or ["GET", "POST"]))
    operations_rows = _external_api_operations_rows(operations)
    test_button = (
        '<button class="btn secondary" id="testExternalApi" type="button">Probar conexion</button>'
        if can_edit else ""
    )
    return f"""
    <section class="grid split" style="margin-top:14px">
      <div class="panel editor">
        <h2>Constructor API externa</h2>
        <form method="post" action="/admin/bots/{bot_id}/integrations/{integration_id}/external-api">
          <label>Base URL</label>
          <input name="base_url" value="{html.escape(str(cfg.get("base_url") or ""))}" placeholder="https://api.cliente.com" {readonly} required>
          <label>Metodo por defecto</label>
          <select name="method" {disabled}>
            {''.join(f'<option value="{m}" {"selected" if str(cfg.get("method") or "GET").upper() == m else ""}>{m}</option>' for m in ("GET", "POST", "PUT", "PATCH"))}
          </select>
          <label>Ruta por defecto</label>
          <input name="default_path" value="{html.escape(str(cfg.get("path") or ""))}" placeholder="/clientes" {readonly}>
          <label>Metodos permitidos</label>
          <input name="allowed_methods" value="{html.escape(methods)}" placeholder="GET, POST" {readonly}>
          <label>Headers sin secretos</label>
          <textarea class="short" name="headers_json" {readonly}>{html.escape(headers_json)}</textarea>
          <label>Autenticacion</label>
          <div class="control-grid">
            <input name="auth_header" value="{html.escape(str(cfg.get("auth_header") or "Authorization"))}" placeholder="Authorization" {readonly}>
            <input name="auth_scheme" value="{html.escape(str(cfg.get("auth_scheme") or "Bearer"))}" placeholder="Bearer" {readonly}>
          </div>
          <label>Timeout segundos</label>
          <input name="timeout_seconds" type="number" min="3" max="60" value="{_safe_int(cfg.get("timeout_seconds"), 20, 3, 60)}" {readonly}>
          <label>Prueba segura</label>
          <div class="control-grid">
            <select name="test_method" id="apiTestMethod" {disabled}>
              {''.join(f'<option value="{m}" {"selected" if str(test_cfg.get("method") or "GET").upper() == m else ""}>{m}</option>' for m in ("GET", "HEAD"))}
            </select>
            <input name="test_path" id="apiTestPath" value="{html.escape(str(test_cfg.get("path") or "/health"))}" placeholder="/health" {readonly}>
          </div>
          <label>Parametros de prueba</label>
          <textarea class="short" name="test_params_json" id="apiTestParams" {readonly}>{html.escape(test_params_json)}</textarea>
          <label>Operaciones que puede usar el bot</label>
          <textarea class="short" name="operations_json" {readonly}>{html.escape(operations_json)}</textarea>
          <div class="actions" style="margin-top:14px">
            {'<button class="btn" type="submit">Guardar API</button>' if can_edit else '<span class="badge">Solo lectura</span>'}
            {test_button}
          </div>
          <div id="apiTestStatus" class="sync-status">Guarda cambios antes de probar. La prueba solo usa GET o HEAD.</div>
        </form>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Operacion</th><th>Metodo</th><th>Ruta</th></tr></thead>
          <tbody>{operations_rows}</tbody>
        </table>
      </div>
    </section>
    <script>
      (() => {{
        const btn = document.getElementById("testExternalApi");
        const status = document.getElementById("apiTestStatus");
        const setStatus = (message, className = "") => {{
          if (!status) return;
          status.className = `sync-status ${{className}}`;
          status.textContent = message;
        }};
        btn?.addEventListener("click", async () => {{
          const payload = new FormData();
          payload.set("method", document.getElementById("apiTestMethod")?.value || "GET");
          payload.set("path", document.getElementById("apiTestPath")?.value || "/");
          payload.set("params_json", document.getElementById("apiTestParams")?.value || "{{}}");
          btn.disabled = true;
          setStatus("Probando conexion...");
          try {{
            const response = await fetch("/admin/bots/{bot_id}/integrations/{integration_id}/test", {{
              method: "POST",
              headers: {{ "Accept": "application/json" }},
              body: payload,
            }});
            const data = await response.json().catch(() => ({{}}));
            if (!response.ok || !data.ok) throw new Error(data.error || "La API no respondio correctamente.");
            setStatus(`OK HTTP ${{data.status_code}} en ${{data.elapsed_ms}} ms`, "ok");
          }} catch (error) {{
            setStatus(error.message || "No se pudo probar la API.", "err");
          }} finally {{
            btn.disabled = false;
          }}
        }});
      }})();
    </script>
    """


@router.get("/bots/{bot_id}/integrations", response_class=HTMLResponse)
async def bot_integrations_page(request: Request, bot_id: int, saved: str | None = None):
    session = _require_login(request)
    bot = await _require_bot_access(session, bot_id)
    integrations = await db.list_bot_integrations(bot_id, include_archived=True)
    can_edit = _is_agency(session) or session.get("role") == "client_admin"
    rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(item["name"])}</strong><br><span class="muted code">{html.escape(item["integration_type"])}</span></td>
          <td><span class="badge {'b-calificado' if item.get("enabled") else 'b-descalificado'}">{'activa' if item.get("enabled") else 'inactiva'}</span></td>
          <td>{int(item.get("secret_count") or 0)} secretos</td>
          <td>{_fmt_dt(item.get("updated_at") or item.get("created_at"))}</td>
          <td><a class="btn secondary" href="/admin/bots/{bot_id}/integrations/{item["id"]}">Abrir</a></td>
        </tr>
        """
        for item in integrations
    ) or '<tr><td colspan="5" class="empty">Sin integraciones configuradas.</td></tr>'
    create_form = ""
    if can_edit:
        create_form = f"""
        <div class="panel editor">
          <h2>Nueva integracion</h2>
          <form method="post" action="/admin/bots/{bot_id}/integrations">
            <label>Nombre</label><input name="name" placeholder="Agenda principal, CRM ventas, API cliente..." required>
            <label>Tipo</label><select name="integration_type">{_integration_type_options()}</select>
            <label>Config JSON sin secretos</label><textarea class="short" name="config_json" required>{html.escape(_pretty_json(_default_integration_config("external_api")))}</textarea>
            <label><input type="checkbox" name="enabled" checked style="width:auto"> Activa</label>
            <div class="actions" style="margin-top:14px"><button class="btn" type="submit">Crear integracion</button></div>
          </form>
        </div>
        """
    notice = '<div class="trend">Cambios guardados.</div>' if saved else ""
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/bots/{bot_id}">Volver</a><h1>Integraciones</h1><div class="sub">{html.escape(bot["name"])} puede conectarse a agenda, CRM, APIs o webhooks por cliente.</div>{notice}</div>
    </div>
    <section class="grid split">
      <div class="table-wrap"><table><thead><tr><th>Integracion</th><th>Estado</th><th>Secretos</th><th>Actualizada</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>
      {create_form or '<div class="panel"><h2>Permisos</h2><div class="sub">Tu usuario tiene acceso de solo lectura.</div></div>'}
    </section>
    """
    return HTMLResponse(_layout("Integraciones", "bots", body))


@router.post("/bots/{bot_id}/integrations")
async def create_bot_integration_page(
    request: Request,
    bot_id: int,
    name: str = Form(...),
    integration_type: str = Form(...),
    config_json: str = Form("{}"),
    enabled: str | None = Form(None),
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    config_data = _parse_config_json(config_json)
    if not config_data:
        config_data = _default_integration_config(integration_type.strip() or "custom")
    integration_id = await db.create_bot_integration(
        bot_id=bot_id,
        integration_type=integration_type.strip() or "custom",
        name=clean_name,
        config_data=config_data,
        enabled=enabled == "on",
    )
    return RedirectResponse(
        f"/admin/bots/{bot_id}/integrations/{integration_id}?saved=1",
        status_code=302,
    )


@router.get("/bots/{bot_id}/integrations/{integration_id}", response_class=HTMLResponse)
async def edit_bot_integration_page(
    request: Request,
    bot_id: int,
    integration_id: int,
    saved: str | None = None,
):
    session = _require_login(request)
    bot = await _require_bot_access(session, bot_id)
    integration = await db.get_bot_integration(bot_id, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integracion no encontrada")
    secret_rows = await db.list_integration_secrets(integration_id)
    can_edit = _is_agency(session) or session.get("role") == "client_admin"
    readonly = "" if can_edit else "readonly"
    disabled = "" if can_edit else "disabled"
    secret_html = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(secret["secret_name"])}</strong><br><span class="muted">Valor guardado y oculto</span></td>
          <td>{_fmt_dt(secret.get("updated_at") or secret.get("created_at"))}</td>
          <td>
            {'<form class="inline" method="post" action="/admin/bots/%s/integrations/%s/secrets/%s/delete"><button class="btn secondary" type="submit">Eliminar</button></form>' % (bot_id, integration_id, html.escape(secret["secret_name"])) if can_edit else '<span class="badge">Solo lectura</span>'}
          </td>
        </tr>
        """
        for secret in secret_rows
    ) or '<tr><td colspan="3" class="empty">Sin secretos guardados.</td></tr>'
    save_button = (
        '<button class="btn" type="submit">Guardar cambios</button>'
        if can_edit else
        '<span class="badge">Solo lectura</span>'
    )
    archive_form = (
        f"""
        <form method="post" action="/admin/bots/{bot_id}/integrations/{integration_id}/archive" style="margin-top:10px">
          <button class="btn secondary" type="submit">Desactivar integracion</button>
        </form>
        """
        if can_edit and integration.get("enabled") else ""
    )
    secret_form = ""
    if can_edit:
        secret_form = f"""
        <div class="panel">
          <h2>Guardar secreto</h2>
          <form method="post" action="/admin/bots/{bot_id}/integrations/{integration_id}/secrets">
            <label>Nombre del secreto</label><input name="secret_name" placeholder="api_key, access_token, refresh_token" required>
            <label>Valor</label><input name="secret_value" type="password" required>
            <div class="actions" style="margin-top:14px"><button class="btn" type="submit">Guardar secreto</button></div>
          </form>
        </div>
        """
    notice = '<div class="trend">Cambios guardados.</div>' if saved else ""
    checked = "checked" if integration.get("enabled") else ""
    external_api_panel = _external_api_builder_panel(
        bot_id,
        integration_id,
        integration,
        can_edit,
    )
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/bots/{bot_id}/integrations">Volver</a><h1>{html.escape(integration["name"])}</h1><div class="sub">{html.escape(bot["name"])} - {html.escape(integration["integration_type"])}</div>{notice}</div>
    </div>
    <section class="grid split">
      <div class="panel editor">
        <h2>Configuracion</h2>
        <form method="post" action="/admin/bots/{bot_id}/integrations/{integration_id}">
          <label>Nombre</label><input name="name" value="{html.escape(integration["name"])}" {readonly} required>
          <label>Tipo</label><select name="integration_type" {disabled}>{_integration_type_options(integration["integration_type"])}</select>
          <label>Config JSON sin secretos</label><textarea class="short" name="config_json" {readonly} required>{html.escape(_pretty_json(integration.get("config")))}</textarea>
          <label><input type="checkbox" name="enabled" {checked} {disabled} style="width:auto"> Activa</label>
          <div class="actions" style="margin-top:14px">{save_button}</div>
        </form>
        {archive_form}
      </div>
      {secret_form or '<div class="panel"><h2>Secretos</h2><div class="sub">Solo administradores pueden guardar secretos.</div></div>'}
    </section>
    <section class="table-wrap" style="margin-top:14px">
      <table><thead><tr><th>Secreto</th><th>Actualizado</th><th></th></tr></thead><tbody>{secret_html}</tbody></table>
    </section>
    {external_api_panel}
    """
    return HTMLResponse(_layout("Integracion", "bots", body))


@router.post("/bots/{bot_id}/integrations/{integration_id}")
async def update_bot_integration_page(
    request: Request,
    bot_id: int,
    integration_id: int,
    name: str = Form(...),
    integration_type: str = Form(...),
    config_json: str = Form("{}"),
    enabled: str | None = Form(None),
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    if not await db.get_bot_integration(bot_id, integration_id):
        raise HTTPException(status_code=404, detail="Integracion no encontrada")
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    updated = await db.update_bot_integration(
        bot_id=bot_id,
        integration_id=integration_id,
        integration_type=integration_type.strip() or "custom",
        name=clean_name,
        config_data=_parse_config_json(config_json),
        enabled=enabled == "on",
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Integracion no encontrada")
    return RedirectResponse(
        f"/admin/bots/{bot_id}/integrations/{integration_id}?saved=1",
        status_code=302,
    )


@router.post("/bots/{bot_id}/integrations/{integration_id}/external-api")
async def update_external_api_builder_page(
    request: Request,
    bot_id: int,
    integration_id: int,
    base_url: str = Form(...),
    method: str = Form("GET"),
    default_path: str = Form(""),
    allowed_methods: str = Form("GET, POST"),
    headers_json: str = Form("{}"),
    auth_header: str = Form("Authorization"),
    auth_scheme: str = Form("Bearer"),
    timeout_seconds: int = Form(20),
    test_method: str = Form("GET"),
    test_path: str = Form("/health"),
    test_params_json: str = Form("{}"),
    operations_json: str = Form("[]"),
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    integration = await db.get_bot_integration(bot_id, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integracion no encontrada")
    if integration.get("integration_type") != "external_api":
        raise HTTPException(status_code=400, detail="Solo aplica para API externa")
    config_data = _external_api_config_from_form(
        base_url=base_url,
        method=method,
        default_path=default_path,
        allowed_methods=allowed_methods,
        headers_json=headers_json,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        timeout_seconds=timeout_seconds,
        test_method=test_method,
        test_path=test_path,
        test_params_json=test_params_json,
        operations_json=operations_json,
    )
    await db.update_bot_integration(
        bot_id=bot_id,
        integration_id=integration_id,
        integration_type="external_api",
        name=integration["name"],
        config_data=config_data,
        enabled=bool(integration.get("enabled")),
    )
    return RedirectResponse(
        f"/admin/bots/{bot_id}/integrations/{integration_id}?saved=1",
        status_code=302,
    )


@router.post("/bots/{bot_id}/integrations/{integration_id}/test", response_class=JSONResponse)
async def test_external_api_integration_page(
    request: Request,
    bot_id: int,
    integration_id: int,
    method: str = Form("GET"),
    path: str = Form("/"),
    params_json: str = Form("{}"),
):
    from time import perf_counter
    import httpx
    from app import external_actions

    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    integration = await db.get_bot_integration(bot_id, integration_id)
    if not integration:
        return JSONResponse({"ok": False, "error": "Integracion no encontrada"}, status_code=404)
    if integration.get("integration_type") != "external_api":
        return JSONResponse({"ok": False, "error": "Solo aplica para API externa"}, status_code=400)
    clean_method = (method or "GET").strip().upper()
    if clean_method not in {"GET", "HEAD"}:
        return JSONResponse(
            {"ok": False, "error": "La prueba solo permite GET o HEAD para evitar escrituras."},
            status_code=400,
        )
    params = _parse_config_json(params_json)
    encrypted = await db.get_integration_secret_values(integration_id)
    secrets = {}
    for name, encrypted_value in encrypted.items():
        value = secure_store.decrypt_secret(encrypted_value)
        if value:
            secrets[name] = value

    cfg = dict(integration.get("config") or {})
    allowed = set(_clean_methods(cfg.get("allowed_methods") or ["GET", "POST"]))
    allowed.add(clean_method)
    cfg["allowed_methods"] = sorted(allowed)
    request_data = external_actions.build_request(
        {
            "action_type": "external_api_request",
            "payload": {"method": clean_method, "path": path, "params": params},
        },
        {"config": cfg},
        secrets,
    )
    if not request_data:
        return JSONResponse(
            {"ok": False, "error": "No se pudo construir la solicitud. Revisa Base URL y ruta."},
            status_code=400,
        )
    timeout = int(cfg.get("timeout_seconds") or 20)
    started = perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                request_data.pop("method"),
                request_data.pop("url"),
                **request_data,
            )
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc)[:500]},
            status_code=502,
        )
    elapsed_ms = int((perf_counter() - started) * 1000)
    ok = response.status_code < 400
    return JSONResponse(
        {
            "ok": ok,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "preview": (response.text or "")[:500],
            "error": "" if ok else f"HTTP {response.status_code}",
        },
        status_code=200 if ok else 502,
    )


@router.post("/bots/{bot_id}/integrations/{integration_id}/archive")
async def archive_bot_integration_page(
    request: Request,
    bot_id: int,
    integration_id: int,
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    archived = await db.archive_bot_integration(bot_id, integration_id)
    if not archived:
        raise HTTPException(status_code=404, detail="Integracion no encontrada")
    return RedirectResponse(f"/admin/bots/{bot_id}/integrations?saved=1", status_code=302)


@router.post("/bots/{bot_id}/integrations/{integration_id}/secrets")
async def upsert_bot_integration_secret_page(
    request: Request,
    bot_id: int,
    integration_id: int,
    secret_name: str = Form(...),
    secret_value: str = Form(...),
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    if not await db.get_bot_integration(bot_id, integration_id):
        raise HTTPException(status_code=404, detail="Integracion no encontrada")
    clean_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", secret_name.strip()).strip("_")
    if not clean_name:
        raise HTTPException(status_code=400, detail="Nombre de secreto invalido")
    encrypted = secure_store.encrypt_secret(secret_value)
    await db.upsert_integration_secret(integration_id, clean_name, encrypted)
    return RedirectResponse(
        f"/admin/bots/{bot_id}/integrations/{integration_id}?saved=1",
        status_code=302,
    )


@router.post("/bots/{bot_id}/integrations/{integration_id}/secrets/{secret_name}/delete")
async def delete_bot_integration_secret_page(
    request: Request,
    bot_id: int,
    integration_id: int,
    secret_name: str,
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    if not await db.get_bot_integration(bot_id, integration_id):
        raise HTTPException(status_code=404, detail="Integracion no encontrada")
    await db.delete_integration_secret(integration_id, secret_name)
    return RedirectResponse(
        f"/admin/bots/{bot_id}/integrations/{integration_id}?saved=1",
        status_code=302,
    )


SKILL_TYPES = (
    ("google_calendar", "Google Calendar"),
    ("webhook", "Webhook"),
    ("external_api", "API externa"),
    ("crm", "CRM"),
)


def _default_skill_config(skill_type: str) -> dict:
    if skill_type == "google_calendar":
        return {"mode": "schedule_and_cancel"}
    if skill_type == "webhook":
        return {"mode": "post_marker_payload"}
    if skill_type == "external_api":
        return {"mode": "marker_based", "allowed_methods": ["GET", "POST"]}
    if skill_type == "crm":
        return {"mode": "lead_sync_marker"}
    return {}


def _default_skill_enabled(skill_type: str) -> bool:
    return skill_type == "google_calendar"


@router.get("/bots/{bot_id}/skills", response_class=HTMLResponse)
async def bot_skills_page(request: Request, bot_id: int, saved: str | None = None):
    session = _require_login(request)
    bot = await _require_bot_access(session, bot_id)
    rows = {row["skill_type"]: row for row in await db.list_bot_skills(bot_id)}
    can_edit = _is_agency(session) or session.get("role") == "client_admin"
    cards = []
    for skill_type, label in SKILL_TYPES:
        row = rows.get(skill_type)
        enabled = _default_skill_enabled(skill_type) if row is None else bool(row.get("enabled"))
        cfg = row.get("config") if row else _default_skill_config(skill_type)
        checked = "checked" if enabled else ""
        disabled = "" if can_edit else "disabled"
        readonly = "" if can_edit else "readonly"
        button = (
            '<button class="btn" type="submit">Guardar habilidad</button>'
            if can_edit else
            '<span class="badge">Solo lectura</span>'
        )
        cards.append(
            f"""
            <div class="panel editor">
              <h2>{html.escape(label)}</h2>
              <form method="post" action="/admin/bots/{bot_id}/skills/{html.escape(skill_type)}">
                <label><input type="checkbox" name="enabled" {checked} {disabled} style="width:auto"> Activa</label>
                <label>Config JSON</label><textarea class="short" name="config_json" {readonly} required>{html.escape(_pretty_json(cfg))}</textarea>
                <div class="actions" style="margin-top:14px">{button}</div>
              </form>
            </div>
            """
        )
    notice = '<div class="trend">Cambios guardados.</div>' if saved else ""
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/bots/{bot_id}">Volver</a><h1>Habilidades</h1><div class="sub">{html.escape(bot["name"])} ejecuta estas capacidades durante la conversacion.</div>{notice}</div>
    </div>
    <section class="grid split">
      {''.join(cards)}
    </section>
    """
    return HTMLResponse(_layout("Habilidades", "bots", body))


@router.post("/bots/{bot_id}/skills/{skill_type}")
async def update_bot_skill_page(
    request: Request,
    bot_id: int,
    skill_type: str,
    config_json: str = Form("{}"),
    enabled: str | None = Form(None),
):
    session = _require_login(request)
    await _require_bot_editor(session, bot_id)
    allowed = {item[0] for item in SKILL_TYPES}
    if skill_type not in allowed:
        raise HTTPException(status_code=404, detail="Habilidad no soportada")
    await db.upsert_bot_skill(
        bot_id=bot_id,
        skill_type=skill_type,
        enabled=enabled == "on",
        config_data=_parse_config_json(config_json),
    )
    return RedirectResponse(f"/admin/bots/{bot_id}/skills?saved=1", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    session = _require_login(request)
    scoped_bot_id, has_data_scope = await _data_scope_bot_id(session)
    if has_data_scope:
        await db.qualify_leads_with_action_link(
            config.QUALIFIED_CTA_URL,
            bot_id=scoped_bot_id,
        )
        metrics = await db.admin_metrics(bot_id=scoped_bot_id)
        crm_counts = await db.crm_counts(bot_id=scoped_bot_id)
        latest = await db.list_conversation_threads(limit=5, bot_id=scoped_bot_id)
    else:
        metrics = _empty_metrics()
        crm_counts = {}
        latest = []
    escalation_counts = (
        await db.escalation_counts()
        if _is_agency(session)
        else {"pendiente": int(metrics.get("pending_escalations") or 0)}
    )

    qualified = int(metrics.get("qualified") or 0)
    leads = int(metrics.get("leads") or 0)
    conversion = round((qualified / leads) * 100) if leads else 0
    demo_pipeline = [
        ("Contactados", max(leads + 7, 18), 100),
        ("Respondieron", max(leads + 2, 12), 72),
        ("Calificados", max(qualified, 5), 42),
        ("Cita agendada", 3, 24),
    ]
    recent_rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(_display_name(r.get("nombre"), r["wa_id"]))}</strong><br><span class="muted">{html.escape(r["wa_id"])}</span></td>
          <td>{html.escape(_clip(r.get("last_content"), 90))}</td>
          <td><span class="badge b-{html.escape(r.get("qualification_status") or "en_progreso")}">{html.escape((r.get("qualification_status") or "en_progreso").replace("_", " "))}</span></td>
          <td>{_fmt_dt(r.get("last_message_at"))}</td>
        </tr>
        """
        for r in latest
    ) or '<tr><td colspan="4" class="empty">Aun no hay conversaciones.</td></tr>'
    scope_notice = (
        ""
        if has_data_scope
        else '<div class="err">Este usuario todavia no tiene un bot asignado a su cliente.</div>'
    )

    body = f"""
    <div class="topbar">
      <div>
        <h1>Dashboard</h1>
        <div class="sub">Datos reales del bot combinados con bloques demo para visualizar la operacion en vivo.</div>
      </div>
      <span class="badge demo">Datos demo en graficas</span>
    </div>
    {scope_notice}
    <section class="grid kpis">
      <div class="card"><div class="k">Conversaciones</div><div class="n">{metrics.get("conversations", 0)}</div><div class="trend">+12% demo vs. semana anterior</div></div>
      <div class="card"><div class="k">Mensajes</div><div class="n">{metrics.get("messages", 0)}</div><div class="trend">Tiempo medio demo: 38s</div></div>
      <div class="card"><div class="k">Leads</div><div class="n">{leads}</div><div class="trend">Conversion real: {conversion}%</div></div>
      <div class="card"><div class="k">Escalaciones pendientes</div><div class="n">{metrics.get("pending_escalations", 0)}</div><div class="trend demo">SLA demo: 22 min</div></div>
    </section>
    <section class="grid split">
      <div class="panel">
        <h2>Embudo comercial demo</h2>
        <div class="bars">
          {''.join(f'<div class="bar-row"><div class="bar-label"><span>{label}</span><strong>{count}</strong></div><div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div></div>' for label, count, pct in demo_pipeline)}
        </div>
      </div>
      <div class="panel">
        <h2>Estado actual</h2>
        <div class="bars">
          <div class="bar-row"><div class="bar-label"><span>En progreso</span><strong>{crm_counts.get("en_progreso", 0)}</strong></div><div class="bar-track"><div class="bar-fill" style="width:55%"></div></div></div>
          <div class="bar-row"><div class="bar-label"><span>Calificados</span><strong>{crm_counts.get("calificado", 0)}</strong></div><div class="bar-track"><div class="bar-fill" style="width:35%"></div></div></div>
          <div class="bar-row"><div class="bar-label"><span>Descalificados</span><strong>{crm_counts.get("descalificado", 0)}</strong></div><div class="bar-track"><div class="bar-fill" style="width:18%"></div></div></div>
          <div class="bar-row"><div class="bar-label"><span>Escalaciones</span><strong>{sum(escalation_counts.values())}</strong></div><div class="bar-track"><div class="bar-fill" style="width:24%"></div></div></div>
        </div>
      </div>
    </section>
    <section class="table-wrap" style="margin-top:14px">
      <table><thead><tr><th>Contacto</th><th>Ultimo mensaje</th><th>CRM</th><th>Fecha</th></tr></thead><tbody>{recent_rows}</tbody></table>
    </section>
    """
    return HTMLResponse(_layout("Dashboard", "dashboard", body))


@router.get("/conversations", response_class=HTMLResponse)
async def conversations(request: Request, wa_id: str | None = None, bot_id: int | None = None):
    session = _require_login(request)
    has_data_scope = True
    if bot_id:
        await _require_bot_access(session, bot_id)
    elif not _is_agency(session):
        bot = await _first_allowed_bot(session)
        if bot:
            bot_id = bot["id"]
        else:
            has_data_scope = False
    if has_data_scope:
        await db.qualify_leads_with_action_link(
            config.QUALIFIED_CTA_URL,
            bot_id=bot_id,
        )
    threads = (
        await db.list_conversation_threads(limit=100, bot_id=bot_id)
        if has_data_scope else []
    )
    selected = wa_id or (threads[0]["wa_id"] if threads else None)
    messages = await db.list_conversation_messages(selected, limit=120, bot_id=bot_id) if selected else []
    lead = await db.get_lead(selected, bot_id=bot_id) if selected else None
    bot_qs = f"&bot_id={bot_id}" if bot_id else ""
    scope_notice = (
        ""
        if has_data_scope
        else '<div class="err">Este usuario todavia no tiene un bot asignado a su cliente.</div>'
    )

    thread_rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(_display_name(t.get("nombre"), t["wa_id"]))}</strong><br><span class="muted">{html.escape(_clip(t.get("last_content"), 70))}</span></td>
          <td><span class="badge b-{html.escape(t.get("qualification_status") or "en_progreso")}">{html.escape((t.get("qualification_status") or "en_progreso").replace("_", " "))}</span></td>
          <td>{_fmt_dt(t.get("last_message_at"))}</td>
          <td><a class="btn secondary" href="/admin/conversations?wa_id={html.escape(t["wa_id"])}{bot_qs}">Ver</a></td>
        </tr>
        """
        for t in threads
    ) or '<tr><td colspan="4" class="empty">Aun no hay conversaciones.</td></tr>'
    bubble_html = "".join(
        f"""
        <div class="bubble {html.escape(m["role"])}">
          <div class="meta">{html.escape("Bot" if m["role"] == "assistant" else "Cliente")} - {_fmt_dt(m.get("created_at"))}</div>
          <div>{html.escape(m["content"])}</div>
        </div>
        """
        for m in messages
    ) or '<div class="empty">Selecciona una conversacion para ver el historial.</div>'

    lead_block = ""
    if selected:
        status = (lead or {}).get("qualification_status", "en_progreso")
        lead_block = f"""
        <div class="panel" style="margin-bottom:14px">
          <h2>{html.escape(_display_name((lead or {}).get("nombre"), selected))}</h2>
          <div class="sub">{html.escape((lead or {}).get("negocio") or "Sin negocio detectado")} - <span class="badge b-{html.escape(status)}">{html.escape(status.replace("_", " "))}</span></div>
          <div class="actions" style="margin-top:14px">
            <a class="btn whatsapp" href="{_wa_link(selected)}" target="_blank">{ICONS["wa"]} Abrir WhatsApp</a>
          </div>
        </div>
        """

    body = f"""
    <div class="topbar"><div><h1>Conversaciones</h1><div class="sub">Historial real guardado desde WhatsApp.</div></div></div>
    {scope_notice}
    <section class="grid split">
      <div class="table-wrap"><table><thead><tr><th>Contacto</th><th>Estado</th><th>Ultimo</th><th></th></tr></thead><tbody>{thread_rows}</tbody></table></div>
      <div>
        {lead_block}
        <div class="panel chat-widget"><div class="messages">{bubble_html}</div></div>
      </div>
    </section>
    """
    return HTMLResponse(_layout("Conversaciones", "conversations", body))


@router.get("/crm", response_class=HTMLResponse)
async def crm(request: Request, status: str = "en_progreso"):
    session = _require_login(request)
    if status not in ("en_progreso", "calificado", "descalificado", "todos"):
        status = "en_progreso"
    scoped_bot_id, has_data_scope = await _data_scope_bot_id(session)
    if has_data_scope:
        await db.qualify_leads_with_action_link(
            config.QUALIFIED_CTA_URL,
            bot_id=scoped_bot_id,
        )
        counts = await db.crm_counts(bot_id=scoped_bot_id)
        leads = await db.list_leads(
            None if status == "todos" else status,
            limit=200,
            bot_id=scoped_bot_id,
        )
    else:
        counts = {}
        leads = []
    tabs = [
        ("en_progreso", "No cualificados"),
        ("calificado", "Calificados"),
        ("descalificado", "Descalificados"),
        ("todos", "Todos"),
    ]
    tabs_html = "".join(
        f'<a class="{"active" if key == status else ""}" href="/admin/crm?status={key}">{label} ({sum(counts.values()) if key == "todos" else counts.get(key, 0)})</a>'
        for key, label in tabs
    )
    rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(_display_name(l.get("nombre"), l["wa_id"]))}</strong><br><span class="muted">{html.escape(l["wa_id"])}</span></td>
          <td>{html.escape(l.get("negocio") or "-")}</td>
          <td><span class="badge b-{html.escape(l["qualification_status"])}">{html.escape(l["qualification_status"].replace("_", " "))}</span><br><span class="muted">{html.escape(l.get("disqualify_reason") or "")}</span></td>
          <td>{_fmt_dt(l.get("updated_at"))}</td>
          <td>
            <div class="actions">
              <form class="inline" method="post" action="/admin/crm/{html.escape(l["wa_id"])}/status"><button class="btn secondary" name="status" value="en_progreso">No cualificado</button></form>
              <form class="inline" method="post" action="/admin/crm/{html.escape(l["wa_id"])}/status"><button class="btn" name="status" value="calificado">Calificar</button></form>
              <form class="inline" method="post" action="/admin/crm/{html.escape(l["wa_id"])}/status"><button class="btn secondary" name="status" value="descalificado">Descartar</button></form>
            </div>
          </td>
        </tr>
        """
        for l in leads
    ) or '<tr><td colspan="5" class="empty">No hay leads en esta etapa.</td></tr>'
    body = f"""
    <div class="topbar"><div><h1>CRM</h1><div class="sub">Mueve prospectos de no cualificados a calificados conforme avanza la venta.</div></div></div>
    {'' if has_data_scope else '<div class="err">Este usuario todavia no tiene un bot asignado a su cliente.</div>'}
    <div class="tabs">{tabs_html}</div>
    <section class="table-wrap">
      <table><thead><tr><th>Prospecto</th><th>Negocio</th><th>Estado</th><th>Actualizado</th><th>Acciones</th></tr></thead><tbody>{rows}</tbody></table>
    </section>
    """
    return HTMLResponse(_layout("CRM", "crm", body))


@router.post("/crm/{wa_id}/status")
async def crm_update_status(
    request: Request,
    wa_id: str,
    status: str = Form(...),
):
    _require_agency(request)
    if status not in ("en_progreso", "calificado", "descalificado"):
        raise HTTPException(400, "Estado invalido")
    await db.update_lead_status(
        wa_id,
        status,
        disqualify_reason="Movido manualmente desde CRM" if status == "descalificado" else None,
    )
    return RedirectResponse("/admin/crm?status=" + status, status_code=302)


@router.get("/escalations", response_class=HTMLResponse)
async def escalations(request: Request, status: str = "pendiente"):
    _require_agency(request)
    if status not in ("pendiente", "en_proceso", "resuelto", "todos"):
        status = "pendiente"
    counts = await db.escalation_counts()
    rows = await db.list_escalations(
        status=None if status == "todos" else status,
        limit=200,
    )
    tabs = [
        ("pendiente", "Pendientes"),
        ("en_proceso", "En proceso"),
        ("resuelto", "Resueltos"),
        ("todos", "Todos"),
    ]
    tabs_html = "".join(
        f'<a class="{"active" if key == status else ""}" href="/admin/escalations?status={key}">{label} ({sum(counts.values()) if key == "todos" else counts.get(key, 0)})</a>'
        for key, label in tabs
    )
    rows_html = "".join(_escalation_row(r) for r in rows) or '<tr><td colspan="7" class="empty">No hay casos con este filtro.</td></tr>'
    body = f"""
    <div class="topbar"><div><h1>Escalaciones</h1><div class="sub">Casos que requieren seguimiento humano.</div></div></div>
    <div class="tabs">{tabs_html}</div>
    <section class="table-wrap">
      <table><thead><tr><th>Fecha</th><th>Cliente</th><th>Producto</th><th>Razon</th><th>Problema</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>{rows_html}</tbody></table>
    </section>
    """
    return HTMLResponse(_layout("Escalaciones", "escalations", body))


@router.get("/dashboard-old", response_class=HTMLResponse)
async def dashboard_old(request: Request, status: str = "pendiente"):
    return await escalations(request, status=status)


def _escalation_row(r: dict) -> str:
    reason_class = {
        "urgente_seguridad": "b-urgente",
        "hardware_daniado": "b-hardware",
        "media_recibida": "b-media",
        "bot_escalo": "b-en_proceso",
    }.get(r["reason"], "b-en_proceso")
    reason_label = {
        "urgente_seguridad": "Urgente",
        "hardware_daniado": "Hardware",
        "media_recibida": "Media",
        "bot_escalo": "Bot escalo",
    }.get(r["reason"], r["reason"])
    return f"""
    <tr>
      <td>{_fmt_dt(r.get("created_at"))}</td>
      <td><strong>{html.escape(r.get("customer_name") or "(sin nombre)")}</strong><br><span class="muted">{html.escape(r.get("city") or "")}<br>{html.escape(r["wa_id"])}</span></td>
      <td>{html.escape(r.get("product") or "-")}</td>
      <td><span class="badge {reason_class}">{html.escape(reason_label)}</span></td>
      <td>{html.escape(_clip(r.get("issue_summary"), 120))}</td>
      <td><span class="badge b-{html.escape(r["status"])}">{html.escape(r["status"].replace("_", " "))}</span></td>
      <td><div class="actions"><a class="btn whatsapp" href="{_wa_link(r["wa_id"])}" target="_blank">{ICONS["wa"]} WA</a><a class="btn secondary" href="/admin/escalations/{r["id"]}">Ver</a></div></td>
    </tr>
    """


@router.get("/escalations/{eid}", response_class=HTMLResponse)
async def escalation_detail(request: Request, eid: int):
    _require_agency(request)
    e = await db.get_escalation(eid)
    if not e:
        raise HTTPException(404, "Escalacion no encontrada")

    notes = html.escape(e.get("notes") or "")
    excerpt = html.escape(e.get("conversation_excerpt") or "(sin contexto)")
    resolved = _fmt_dt(e.get("resolved_at"))
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/escalations">Volver</a><h1>Caso #{e['id']}</h1><div class="sub">{html.escape(e['wa_id'])}</div></div>
      <a class="btn whatsapp" href="{_wa_link(e['wa_id'])}" target="_blank">{ICONS["wa"]} Abrir WhatsApp</a>
    </div>
    <section class="grid split">
      <div class="panel">
        <h2>Datos del cliente</h2>
        <table>
          <tr><th>Nombre</th><td>{html.escape(e.get('customer_name') or '-')}</td></tr>
          <tr><th>Ciudad</th><td>{html.escape(e.get('city') or '-')}</td></tr>
          <tr><th>Producto</th><td>{html.escape(e.get('product') or '-')}</td></tr>
          <tr><th>Compra</th><td>{html.escape(e.get('purchase_date') or '-')}</td></tr>
          <tr><th>Estado</th><td><span class="badge b-{html.escape(e['status'])}">{html.escape(e['status'].replace("_", " "))}</span></td></tr>
          <tr><th>Creado</th><td>{_fmt_dt(e.get('created_at'))}</td></tr>
          <tr><th>Resuelto</th><td>{resolved}</td></tr>
        </table>
      </div>
      <div class="panel">
        <h2>Seguimiento</h2>
        <form method="post" action="/admin/escalations/{e['id']}/update">
          <label>Notas internas</label>
          <textarea name="notes" rows="7">{notes}</textarea>
          <div class="actions" style="margin-top:12px">
            <button class="btn secondary" name="status" value="pendiente" type="submit">Reabrir</button>
            <button class="btn" name="status" value="en_proceso" type="submit">En proceso</button>
            <button class="btn" name="status" value="resuelto" type="submit">Resolver</button>
          </div>
        </form>
      </div>
    </section>
    <section class="panel" style="margin-top:14px">
      <h2>Contexto de la conversacion</h2>
      <div class="bubble" style="max-width:100%">{excerpt}</div>
    </section>
    """
    return HTMLResponse(_layout(f"Caso #{e['id']}", "escalations", body))


@router.post("/escalations/{eid}/update")
async def escalation_update(
    request: Request,
    eid: int,
    status: str = Form(...),
    notes: str = Form(""),
):
    _require_agency(request)
    if status not in ("pendiente", "en_proceso", "resuelto"):
        raise HTTPException(400, "Estado invalido")
    await db.update_escalation_status(eid, status, notes=notes or None)
    return RedirectResponse(f"/admin/escalations/{eid}", status_code=302)
