"""Admin frontend: login, dashboard, conversations, CRM and escalations."""
import html
import json
import re
import secrets
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import auth, config, db, secure_store

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_login(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    return {
        "user": user,
        "role": request.session.get("role", "agency_admin"),
        "client_id": request.session.get("client_id"),
        "user_id": request.session.get("user_id"),
        "name": request.session.get("name") or user,
    }


def _is_agency(session: dict) -> bool:
    return session.get("role") == "agency_admin"


def _require_agency(request: Request) -> dict:
    session = _require_login(request)
    if not _is_agency(session):
        raise HTTPException(status_code=403, detail="Solo agencia")
    return session


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().strip())
    return slug.strip("-") or "cliente"


async def _first_allowed_bot(session: dict) -> dict | None:
    bots = await db.list_bots(
        client_id=None if _is_agency(session) else int(session["client_id"]),
        limit=1,
    )
    return bots[0] if bots else None


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
  .editor textarea { min-height: 520px; line-height: 1.45; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
  .editor textarea.short { min-height: 220px; }
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


def _nav(active: str) -> str:
    items = [
        ("dashboard", "Dashboard", "/admin/dashboard", ICONS["dashboard"]),
        ("clients", "Clientes", "/admin/clients", ICONS["building"]),
        ("bots", "Bots", "/admin/bots", ICONS["building"]),
        ("conversations", "Conversaciones", "/admin/conversations", ICONS["chat"]),
        ("crm", "CRM", "/admin/crm", ICONS["crm"]),
        ("escalations", "Escalaciones", "/admin/escalations", ICONS["alert"]),
    ]
    links = "".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{icon}<span>{label}</span></a>'
        for key, label, href, icon in items
    )
    return f"""
    <aside class="side">
      <div class="brand">
        <div class="mark">WA</div>
        <div><strong>WhatsApp Bot</strong><span>Panel admin</span></div>
      </div>
      <nav class="nav">{links}</nav>
      <form method="post" action="/admin/logout" class="logout">
        <button class="btn secondary" type="submit">{ICONS["out"]} Salir</button>
      </form>
    </aside>
    """


def _layout(title: str, active: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - WhatsApp Bot</title>
{BASE_CSS}
</head><body><div class="shell">{_nav(active)}<main class="main">{body}</main></div></body></html>"""


def _login_layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - WhatsApp Bot</title>
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
        <div class="mark">WA</div>
        <div><strong>WhatsApp Bot</strong><span>Panel privado</span></div>
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
        return RedirectResponse("/admin/dashboard", status_code=302)
    user = await db.get_user_login(username)
    if user and auth.verify_password(password, user.get("password_hash")):
        request.session["user"] = user["email"]
        request.session["role"] = user["role"]
        request.session["client_id"] = user["client_id"]
        request.session["user_id"] = user["user_id"]
        request.session["name"] = user.get("name") or user["email"]
        return RedirectResponse("/admin/dashboard", status_code=302)
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
    return RedirectResponse("/admin/dashboard", status_code=302)


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
        <a class="btn secondary" href="/admin/bots/{bot_id}/prompt">Editar prompt</a>
        <a class="btn secondary" href="/admin/bots/{bot_id}/knowledge">Base de conocimiento</a>
        <a class="btn secondary" href="/admin/bots/{bot_id}/integrations">Integraciones</a>
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
    body = f"""
    <div class="topbar">
      <div><a class="sub" href="/admin/bots/{bot_id}">Volver</a><h1>Prompt</h1><div class="sub">{html.escape(bot["name"])} - origen actual: {source}</div></div>
    </div>
    <section class="panel editor">
      <form method="post" action="/admin/bots/{bot_id}/prompt">
        <label>Instrucciones del agente</label>
        <textarea name="content" {readonly} required>{html.escape(content)}</textarea>
        <div class="actions" style="margin-top:14px">{button}{notice}</div>
      </form>
    </section>
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
            <label>Config JSON sin secretos</label><textarea class="short" name="config_json" required>{html.escape(_pretty_json({"base_url": "", "calendar_id": "primary", "timezone": "America/Chihuahua"}))}</textarea>
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
)


def _default_skill_config(skill_type: str) -> dict:
    if skill_type == "google_calendar":
        return {"mode": "schedule_and_cancel"}
    return {}


@router.get("/bots/{bot_id}/skills", response_class=HTMLResponse)
async def bot_skills_page(request: Request, bot_id: int, saved: str | None = None):
    session = _require_login(request)
    bot = await _require_bot_access(session, bot_id)
    rows = {row["skill_type"]: row for row in await db.list_bot_skills(bot_id)}
    can_edit = _is_agency(session) or session.get("role") == "client_admin"
    cards = []
    for skill_type, label in SKILL_TYPES:
        row = rows.get(skill_type)
        enabled = True if row is None else bool(row.get("enabled"))
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
    await db.qualify_leads_with_action_link(config.QUALIFIED_CTA_URL)
    scoped_bot = None if _is_agency(session) else await _first_allowed_bot(session)
    scoped_bot_id = scoped_bot["id"] if scoped_bot else None
    metrics = await db.admin_metrics(bot_id=scoped_bot_id)
    crm_counts = await db.crm_counts(bot_id=scoped_bot_id)
    escalation_counts = await db.escalation_counts()
    latest = await db.list_conversation_threads(limit=5, bot_id=scoped_bot_id)

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

    body = f"""
    <div class="topbar">
      <div>
        <h1>Dashboard</h1>
        <div class="sub">Datos reales del bot combinados con bloques demo para visualizar la operacion en vivo.</div>
      </div>
      <span class="badge demo">Datos demo en graficas</span>
    </div>
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
    await db.qualify_leads_with_action_link(config.QUALIFIED_CTA_URL)
    if bot_id:
        await _require_bot_access(session, bot_id)
    elif not _is_agency(session):
        bot = await _first_allowed_bot(session)
        bot_id = bot["id"] if bot else None
    threads = await db.list_conversation_threads(limit=100, bot_id=bot_id)
    selected = wa_id or (threads[0]["wa_id"] if threads else None)
    messages = await db.list_conversation_messages(selected, limit=120, bot_id=bot_id) if selected else []
    lead = await db.get_lead(selected, bot_id=bot_id) if selected else None
    bot_qs = f"&bot_id={bot_id}" if bot_id else ""

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
    await db.qualify_leads_with_action_link(config.QUALIFIED_CTA_URL)
    if status not in ("en_progreso", "calificado", "descalificado", "todos"):
        status = "en_progreso"
    scoped_bot = None if _is_agency(session) else await _first_allowed_bot(session)
    scoped_bot_id = scoped_bot["id"] if scoped_bot else None
    counts = await db.crm_counts(bot_id=scoped_bot_id)
    leads = await db.list_leads(None if status == "todos" else status, limit=200, bot_id=scoped_bot_id)
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
