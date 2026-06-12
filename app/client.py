"""FastAPI Client Router for multi-tenant customer-facing dashboard."""
import html
import json
import logging
import re
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app import db, config, auth, secure_store, meta_provider, prompt_assistant, skill_runtime, calendar_client, file_parser

log = logging.getLogger("client-panel")
router = APIRouter(prefix="/client", tags=["client-portal"])

# Reusable icons for the client dashboard sidebar and tabs
ICONS = {
    "dashboard": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 13h8V3H3v10Z"/><path d="M13 21h8V11h-8v10Z"/><path d="M13 3h8v6h-8V3Z"/><path d="M3 21h8v-6H3v6Z"/></svg>',
    "wa": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    "prompt": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
    "hours": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    "escalate": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    "knowledge": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
    "integrations": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/></svg>',
    "out": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>',
    "success": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="green"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    "error": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="red"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    "chat": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z"/></svg>',
    "leads": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
}

CLIENT_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@300;400;500;600;700&display=swap');

  :root {
    --bg: #f8fafc;
    --panel: #ffffff;
    --ink: #0f172a;
    --muted: #64748b;
    --line: #e2e8f0;
    --line-strong: #cbd5e1;
    --primary: #0d9488;
    --primary-dark: #0f766e;
    --primary-light: #ccfbf1;
    --amber: #d97706;
    --red: #e11d48;
    --blue: #2563eb;
    --green: #059669;
    --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
    --font: 'Inter', system-ui, sans-serif;
    --font-display: 'Outfit', sans-serif;
    --transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: var(--font);
    -webkit-font-smoothing: antialiased;
  }
  
  .layout {
    display: grid;
    grid-template-columns: 260px 1fr;
    min-height: 100vh;
  }

  /* Sidebar styling */
  .sidebar {
    background: #0f172a;
    color: #e2e8f0;
    padding: 24px 18px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    height: 100vh;
    position: sticky;
    top: 0;
    z-index: 50;
    border-right: 1px solid rgba(255, 255, 255, 0.05);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 32px;
  }
  .brand-logo {
    width: 38px;
    height: 38px;
    background: var(--primary);
    color: white;
    font-family: var(--font-display);
    font-weight: 800;
    font-size: 16px;
    border-radius: 10px;
    display: grid;
    place-items: center;
    box-shadow: 0 4px 12px rgba(13, 148, 136, 0.3);
  }
  .brand-text strong {
    display: block;
    font-size: 16px;
    color: white;
    font-family: var(--font-display);
  }
  .brand-text span {
    font-size: 11px;
    color: #94a3b8;
  }
  .sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex-grow: 1;
  }
  .sidebar-link {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 11px 14px;
    color: #94a3b8;
    font-size: 14px;
    font-weight: 500;
    border-radius: 8px;
    cursor: pointer;
    transition: var(--transition);
  }
  .sidebar-link:hover {
    background: rgba(255, 255, 255, 0.05);
    color: white;
  }
  .sidebar-link.active {
    background: var(--primary);
    color: white;
    font-weight: 600;
    box-shadow: 0 4px 12px rgba(13, 148, 136, 0.25);
  }
  .sidebar-link svg {
    width: 18px;
    height: 18px;
  }
  .logout-form {
    margin-top: auto;
  }
  .btn-logout {
    width: 100%;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #cbd5e1;
    border-radius: 8px;
    padding: 10px;
    cursor: pointer;
    font-weight: 500;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-size: 13px;
    transition: var(--transition);
  }
  .btn-logout:hover {
    background: var(--red);
    border-color: var(--red);
    color: white;
  }
  
  /* Main Content Area */
  .main-content {
    padding: 30px 40px;
    overflow-y: auto;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 28px;
  }
  .header h1 {
    font-family: var(--font-display);
    font-size: 28px;
    font-weight: 800;
    margin: 0;
    color: var(--ink);
  }
  .header p {
    margin: 4px 0 0;
    color: var(--muted);
    font-size: 14px;
  }
  .header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  
  /* Badges & Widgets */
  .badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    background: #e2e8f0;
    color: #475569;
  }
  .badge.success { background: #d1fae5; color: #065f46; }
  .badge.warning { background: #fef3c7; color: #b45309; }
  .badge.danger { background: #ffe4e6; color: #9f1239; }
  .badge-toggle {
    transition: opacity 0.2s ease, transform 0.1s ease;
  }
  .badge-toggle:hover {
    opacity: 0.85;
    transform: translateY(-1px);
  }
  .badge-toggle:active {
    transform: translateY(0);
  }
  
  /* Tab Panel */
  .tab-panel {
    display: none;
    animation: fadeIn 0.2s ease-in-out;
  }
  .tab-panel.active {
    display: block;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  /* Grid Layouts */
  .grid-2 {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 24px;
  }
  .grid-3 {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
  }
  .grid-cards {
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.8fr);
    gap: 24px;
  }

  /* UI Cards */
  .card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 12px;
    box-shadow: var(--shadow);
    padding: 24px;
    margin-bottom: 24px;
  }
  .card-header {
    margin-bottom: 18px;
  }
  .card-header h2 {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 700;
    margin: 0;
    color: var(--ink);
  }
  .card-header p {
    font-size: 13px;
    color: var(--muted);
    margin: 4px 0 0;
  }
  
  /* KPI Widget */
  .kpi-card {
    background: white;
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 20px;
    box-shadow: var(--shadow);
    position: relative;
    overflow: hidden;
  }
  .kpi-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .kpi-value {
    font-family: var(--font-display);
    font-size: 28px;
    font-weight: 800;
    margin-top: 10px;
    color: var(--ink);
  }
  .kpi-status {
    font-size: 12px;
    margin-top: 6px;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  
  /* Form elements */
  label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
    margin: 14px 0 6px;
  }
  input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]):not([type="hidden"]), select, textarea {
    width: 100%;
    border: 1px solid var(--line-strong);
    border-radius: 8px;
    padding: 11px 13px;
    background: white;
    color: var(--ink);
    transition: var(--transition);
    outline: none;
  }
  input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]):not([type="hidden"]):focus, select:focus, textarea:focus {
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.15);
  }
  .checkbox-group {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 12px 0;
  }
  .checkbox-group input {
    width: 18px;
    height: 18px;
    accent-color: var(--primary);
  }
  
  /* Buttons */
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    background: var(--ink);
    color: white;
    border: 1px solid var(--ink);
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 600;
    font-size: 13px;
    cursor: pointer;
    transition: var(--transition);
  }
  .btn:hover {
    background: #1e293b;
    border-color: #1e293b;
    transform: translateY(-1px);
    box-shadow: 0 4px 6px rgba(0,0,0,0.06);
  }
  .btn:active {
    transform: translateY(0);
  }
  .btn.primary-btn {
    background: var(--primary);
    border-color: var(--primary);
    box-shadow: 0 4px 10px rgba(13, 148, 136, 0.2);
  }
  .btn.primary-btn:hover {
    background: var(--primary-dark);
    border-color: var(--primary-dark);
  }
  .btn.secondary {
    background: white;
    color: var(--ink);
    border-color: var(--line-strong);
  }
  .btn.secondary:hover {
    background: #f8fafc;
  }
  .btn.whatsapp-btn {
    background: #128c7e;
    border-color: #128c7e;
    box-shadow: 0 4px 10px rgba(18, 140, 126, 0.2);
  }
  .btn.whatsapp-btn:hover {
    background: #075e54;
    border-color: #075e54;
  }
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none !important;
    box-shadow: none !important;
  }

  /* Table styling */
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th, td {
    padding: 12px 16px;
    border-bottom: 1px solid var(--line);
    text-align: left;
  }
  th {
    background: #f8fafc;
    color: var(--muted);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  tr:hover td {
    background: rgba(13, 148, 136, 0.01);
  }
  
  /* Alert banners */
  .notice-banner {
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 8px;
    border: 1px solid transparent;
  }
  .notice-banner svg {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }
  .notice-banner.success {
    background: #d1fae5;
    border-color: #a7f3d0;
    color: #065f46;
  }
  .notice-banner.error {
    background: #ffe4e6;
    border-color: #fecdd3;
    color: #9f1239;
  }
  
  /* Helper Classes */
  .muted-text { color: var(--muted); font-size: 13px; }
  .bold-text { font-weight: 600; }
  .sync-status { font-size: 12px; font-weight: 500; color: var(--muted); margin-top: 8px; }
  .sync-status.ok { color: var(--green); }
  .sync-status.err { color: var(--red); }
  
  /* Weekday Grid for Schedules */
  .weekday-row {
    display: grid;
    grid-template-columns: 140px 110px 1fr 1fr;
    gap: 16px;
    align-items: center;
    padding: 12px 8px;
    border-bottom: 1px solid var(--line);
  }
  .weekday-row:last-child {
    border-bottom: 0;
  }
  
  /* Prompt Assistant block */
  .prompt-workspace {
    display: grid;
    grid-template-columns: 1fr 1.2fr;
    gap: 20px;
  }
  .chat-bubble-container {
    max-height: 380px;
    overflow-y: auto;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 12px;
    background: #f8fafc;
  }
  .bubble {
    max-width: 85%;
    padding: 10px 12px;
    border-radius: 8px;
    margin-bottom: 8px;
    font-size: 13px;
    line-height: 1.4;
  }
  .bubble.user {
    background: white;
    border: 1px solid var(--line);
  }
  .bubble.assistant {
    background: var(--primary-light);
    color: var(--primary-dark);
    margin-left: auto;
    border: 1px solid rgba(13, 148, 136, 0.1);
  }
  .bubble-meta {
    font-size: 10px;
    color: var(--muted);
    margin-bottom: 4px;
  }

  @media (max-width: 1024px) {
    .layout { grid-template-columns: 1fr; }
    .sidebar { height: auto; position: static; }
    .grid-2, .grid-cards, .prompt-workspace { grid-template-columns: 1fr; }
  }
  .password-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    width: 100%;
  }
  .password-wrapper input {
    padding-right: 40px !important;
  }
  .password-toggle {
    position: absolute;
    right: 10px;
    background: none;
    border: none;
    cursor: pointer;
    color: var(--muted);
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: var(--transition);
    z-index: 10;
  }
  .password-toggle:hover {
    color: var(--primary);
  }

  /* Scrollbar styling */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 999px; }
  ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

  /* Chatwoot Layout */
  .chatwoot-layout {
    display: grid;
    grid-template-columns: 300px 1fr 280px;
    height: calc(100vh - 220px);
    background: white;
    border: 1px solid var(--line);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: var(--shadow);
    margin-top: 14px;
  }
  .chat-sidebar, .chat-main, .chat-crm {
    min-height: 0;
  }
  .chat-sidebar {
    border-right: 1px solid var(--line);
    background: #f8fafc;
    display: flex;
    flex-direction: column;
  }
  .chat-sidebar-header {
    padding: 16px;
    border-bottom: 1px solid var(--line);
    font-weight: 700;
    font-size: 15px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .chat-list {
    overflow-y: auto;
    flex: 1;
  }
  .chat-item {
    padding: 14px 16px;
    border-bottom: 1px solid var(--line);
    cursor: pointer;
    transition: var(--transition);
    text-decoration: none;
    display: block;
    color: inherit;
  }
  .chat-item:hover { background: rgba(13, 148, 136, 0.05); }
  .chat-item.active { background: white; border-left: 3px solid var(--primary); }
  .chat-item-header { display: flex; justify-content: space-between; margin-bottom: 4px; align-items: center; }
  .chat-item-name { font-weight: 600; color: var(--ink); font-size: 14px; }
  .chat-item-time { font-size: 11px; color: var(--muted); }
  .chat-item-preview { font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  
  .chat-main {
    display: flex;
    flex-direction: column;
    background: white;
  }
  .chat-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--line);
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .chat-avatar {
    width: 36px; height: 36px; border-radius: 50%; background: var(--primary-light); color: var(--primary-dark);
    display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px;
  }
  .chat-header-info { display: flex; flex-direction: column; }
  .chat-header-info strong { font-size: 15px; }
  .chat-header-info small { color: var(--muted); font-size: 12px; }
  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    background: #f8fafc;
  }
  .chat-crm {
    border-left: 1px solid var(--line);
    background: white;
    padding: 20px;
    overflow-y: auto;
  }
  .crm-section { margin-bottom: 24px; }
  .crm-section h3 { font-size: 11px; text-transform: uppercase; color: var(--muted); font-weight: 700; margin: 0 0 12px 0; letter-spacing: 0.05em; }

  .bubble {
    max-width: min(720px, 85%);
    padding: 12px 14px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: white;
    box-shadow: 0 2px 4px rgba(0,0,0,0.02);
  }
  .bubble.assistant { margin-left: auto; background: #ccfbf1; border-color: #99f6e4; color: var(--primary-dark); }
  .bubble .meta { font-size: 11px; color: var(--muted); margin-bottom: 6px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.02em; }

  .tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
  .tabs a {
    border: 1px solid var(--line);
    background: white;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 500;
    color: var(--muted);
    text-decoration: none;
    transition: var(--transition);
  }
  .tabs a:hover { border-color: var(--line-strong); color: var(--ink); }
  .tabs a.active { background: var(--ink); border-color: var(--ink); color: white; font-weight: 600; }

  .b-en_progreso, .b-pendiente { background: #fef3c7; color: #b45309; }
  .b-calificado, .b-resuelto { background: #d1fae5; color: #065f46; }
  .b-descalificado, .b-urgente { background: #ffe4e6; color: #9f1239; }
</style>
"""

def _require_client_login(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    session = {
        "user": user,
        "role": request.session.get("role", "client_viewer"),
        "client_id": request.session.get("client_id"),
        "user_id": request.session.get("user_id"),
        "name": request.session.get("name") or user,
    }
    if session["role"] == "agency_admin" and not session["client_id"]:
        # Superadmin preview: fallback to first client if none in session
        pass
    elif not session["client_id"]:
        raise HTTPException(status_code=403, detail="Sesión inválida: sin cliente asignado.")
    return session

async def _require_bot_access(session: dict, bot_id: int) -> dict:
    bot = await db.get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")
    if session.get("role") != "agency_admin" and bot.get("client_id") != session.get("client_id"):
        raise HTTPException(status_code=403, detail="Sin acceso a este bot")
    return bot

async def _require_bot_editor(session: dict, bot_id: int) -> dict:
    bot = await _require_bot_access(session, bot_id)
    if session.get("role") in ("agency_admin", "client_admin"):
        return bot
    raise HTTPException(status_code=403, detail="Tu rol es de solo lectura. No puedes modificar este bot.")

async def _first_allowed_bot(session: dict) -> dict | None:
    client_id = session.get("client_id")
    bots = await db.list_bots(client_id=client_id, limit=1)
    return bots[0] if bots else None

def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else "-"


def _clip(value: str | None, size: int = 160) -> str:
    text = (value or "").strip()
    return text if len(text) <= size else text[: size - 1].rstrip() + "..."


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


def _layout(title: str, body: str, session: dict, active_tab: str = "inicio", notice: str = "", bots_list: list = [], selected_bot_id: int | None = None) -> str:
    bot_options = "".join(
        f'<option value="{b["id"]}" {"selected" if b["id"] == selected_bot_id else ""}>{html.escape(b["name"])}</option>'
        for b in bots_list
    )
    
    sidebar_links = [
        ("inicio", "Inicio", ICONS["dashboard"]),
        ("conversations", "Conversaciones", ICONS["chat"]),
        ("crm", "CRM de Leads", ICONS["leads"]),
        ("whatsapp", "Conectar WhatsApp", ICONS["wa"]),
        ("prompt", "Comportamiento (IA)", ICONS["prompt"]),
        ("hours", "Horarios", ICONS["hours"]),
        ("escalate", "Reglas de Escalado", ICONS["escalate"]),
        ("knowledge", "Base de Conocimiento", ICONS["knowledge"]),
        ("integrations", "Integraciones", ICONS["integrations"]),
    ]
    
    links_html = "".join(
        f'<div class="sidebar-link {"active" if key == active_tab else ""}" onclick="switchTab(\'{key}\')">{icon}<span>{label}</span></div>'
        for key, label, icon in sidebar_links
    )
    
    selector_html = ""
    if len(bots_list) > 1:
        selector_html = f"""
        <div style="margin-bottom: 20px;">
          <label style="color:#94a3b8; font-size:12px; margin-top:0;">Seleccionar Bot</label>
          <select id="sidebarBotSelector" onchange="changeActiveBot(this.value)" style="background:#1e293b; color:white; border-color:rgba(255,255,255,0.1); font-size:13px; padding:8px 10px;">
            {bot_options}
          </select>
        </div>
        """

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - Asistto</title>
  {CLIENT_CSS}
  <script>
    function togglePasswordVisibility(btn) {{
      const input = btn.previousElementSibling;
      if (input.type === "password") {{
        input.type = "text";
        btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`;
      }} else {{
        input.type = "password";
        btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
      }}
    }}
  </script>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <div>
        <div class="brand">
          <div class="brand-logo">AH</div>
          <div class="brand-text">
            <strong>Asistto</strong>
            <span>by Humanio</span>
          </div>
        </div>
        <div style="padding: 0 16px; margin: -10px 0 16px; font-size: 11px; color: #94a3b8;">
          ID del Bot: <strong style="color: #38bdf8;">{selected_bot_id}</strong>
        </div>
        {selector_html}
        <nav class="sidebar-nav">
          {links_html}
        </nav>
      </div>
      <form method="post" action="/admin/logout" class="logout-form">
        <button class="btn-logout" type="submit">{ICONS["out"]} Salir del panel</button>
      </form>
    </aside>
    <main class="main-content">
      {notice}
      {body}
    </main>
  </div>
  
  <script>
    function switchTab(tabId) {{
      // Update sidebar links
      document.querySelectorAll('.sidebar-link').forEach(link => {{
        link.classList.remove('active');
        if (link.getAttribute('onclick').includes(tabId)) {{
          link.classList.add('active');
        }}
      }});
      // Update tab panels
      document.querySelectorAll('.tab-panel').forEach(panel => {{
        panel.classList.remove('active');
      }});
      const activePanel = document.getElementById('panel-' + tabId);
      if (activePanel) {{
        activePanel.classList.add('active');
      }}
      
      // Auto-scroll chat messages if switching to conversations tab
      if (tabId === 'conversations') {{
        const chatMessages = document.querySelector('.chat-messages');
        if (chatMessages) {{
          chatMessages.scrollTop = chatMessages.scrollHeight;
        }}
      }}
      
      // Save tab to URL state
      const url = new URL(window.location.href);
      url.searchParams.set("tab", tabId);
      window.history.replaceState(null, "", url);
    }}
    
    function changeActiveBot(botId) {{
      const url = new URL(window.location.href);
      url.searchParams.set("bot_id", botId);
      window.location.href = url.toString();
    }}
    
    // Auto-activate tab from URL parameters
    window.addEventListener('DOMContentLoaded', () => {{
      const params = new URLSearchParams(window.location.search);
      const tab = params.get("tab") || "inicio";
      switchTab(tab);
      
      // Auto-scroll chat messages on load
      const chatMessages = document.querySelector('.chat-messages');
      if (chatMessages) {{
        chatMessages.scrollTop = chatMessages.scrollHeight;
      }}
    }});

    // Auto-refresh chat list and messages in background (Conversations tab)
    setInterval(async () => {{
      if (document.hidden) return;
      
      const chatLayout = document.querySelector('.chatwoot-layout');
      if (!chatLayout || chatLayout.offsetParent === null) return;
      
      try {{
        const response = await fetch(window.location.href);
        if (response.ok) {{
          const html = await response.text();
          const parser = new DOMParser();
          const doc = parser.parseFromString(html, 'text/html');
          
          const newChatList = doc.querySelector('.chat-list');
          const currentChatList = document.querySelector('.chat-list');
          if (newChatList && currentChatList) {{
            if (currentChatList.innerHTML !== newChatList.innerHTML) {{
              currentChatList.innerHTML = newChatList.innerHTML;
            }}
          }}
          
          const newMessages = doc.querySelector('.chat-messages');
          const currentMessages = document.querySelector('.chat-messages');
          if (newMessages && currentMessages) {{
            if (currentMessages.innerHTML !== newMessages.innerHTML) {{
              const hadNewMessages = newMessages.children.length !== currentMessages.children.length;
              const wasAtBottom = currentMessages.scrollHeight - currentMessages.scrollTop <= currentMessages.clientHeight + 100;
              
              currentMessages.innerHTML = newMessages.innerHTML;
              
              if (hadNewMessages && wasAtBottom) {{
                currentMessages.scrollTop = currentMessages.scrollHeight;
              }}
            }}
          }}
          
          const newCrm = doc.querySelector('.chat-crm');
          const currentCrm = document.querySelector('.chat-crm');
          if (newCrm && currentCrm) {{
            if (currentCrm.innerHTML !== newCrm.innerHTML) {{
              currentCrm.innerHTML = newCrm.innerHTML;
            }}
          }}

          const newHeader = doc.querySelector('.chat-header');
          const currentHeader = document.querySelector('.chat-header');
          if (newHeader && currentHeader) {{
            if (currentHeader.innerHTML !== newHeader.innerHTML) {{
              currentHeader.innerHTML = newHeader.innerHTML;
            }}
          }}
        }}
      }} catch (err) {{
        console.error("Error refreshing conversations:", err);
      }}
    }}, 4000);
  </script>
</body>
</html>"""

@router.get("/app", response_class=HTMLResponse)
async def client_app(
    request: Request,
    bot_id: int | None = None,
    tab: str = "inicio",
    saved: str | None = None,
    wa_id: str | None = None,
    status: str = "en_progreso",
):
    session = _require_client_login(request)
    client_id = session.get("client_id")
    
    # Query client's bots
    bots = await db.list_bots(client_id=client_id, limit=50)
    if not bots:
        return HTMLResponse(
            f"""<!doctype html>
            <html><head><title>Bienvenido a Asistto</title>{CLIENT_CSS}</head>
            <body style="background:#f8fafc; display:grid; place-items:center; min-height:100vh; padding:20px;">
              <div class="card" style="max-width:480px; text-align:center;">
                <div class="brand-logo" style="margin:0 auto 16px; width:48px; height:48px; font-size:18px;">AH</div>
                <h1 style="font-family:Outfit; font-size:24px; font-weight:800;">¡Bienvenido a Asistto!</h1>
                <p class="muted-text" style="margin-top:10px;">Tu cuenta está activa, pero aún no tienes ningún bot de WhatsApp configurado. Por favor, contacta a tu ejecutivo de cuenta para dar de alta tu primer bot y comenzar.</p>
                <form action="/admin/logout" method="post" style="margin-top:20px;">
                  <button class="btn secondary" type="submit">Cerrar Sesión</button>
                </form>
              </div>
            </body></html>"""
        )
    
    selected_bot = None
    if bot_id:
        # Validate bot access
        try:
            selected_bot = await _require_bot_access(session, bot_id)
        except Exception:
            pass
            
    if not selected_bot:
        selected_bot = bots[0]
        bot_id = int(selected_bot["id"])
        
    # Notice banners
    notice_html = ""
    if saved == "1":
        notice_html = f'<div class="notice-banner success">{ICONS["success"]} Configuración guardada correctamente.</div>'
    elif saved == "err":
        notice_html = f'<div class="notice-banner error">{ICONS["error"]} Ocurrió un error al guardar la configuración. Revisa los datos.</div>'
    elif saved == "err_parse":
        notice_html = f'<div class="notice-banner error">{ICONS["error"]} Error al leer o procesar el archivo. Asegúrate de que no esté dañado y sea de un tipo compatible (PDF, DOCX, MD, XLSX, CSV).</div>'

    # 1. FETCH STATE
    # WhatsApp config
    wa_row = await db.get_bot_whatsapp_number(bot_id)
    wa_info = wa_row or {}
    
    # Check if access token is actually saved
    integration = await db.get_active_bot_integration(bot_id, "whatsapp_cloud")
    access_token_val = ""
    if integration:
        encrypted = await db.get_integration_secret_values(int(integration["id"]))
        for name in ("access_token", "whatsapp_access_token", "token"):
            enc_val = encrypted.get(name)
            if enc_val:
                dec = secure_store.decrypt_secret(enc_val)
                if dec:
                    access_token_val = dec
                    break
    has_token = bool(access_token_val)
    
    # Active prompt
    prompt_row = await db.get_active_bot_prompt(bot_id)
    current_prompt_content = prompt_row.get("content", "") if prompt_row else ""
    
    # Business Hours Skill
    hours_skill = await db.get_bot_skill(bot_id, "business_hours")
    hours_config = (hours_skill.get("config") or {}) if hours_skill else {}
    hours_enabled = hours_skill.get("enabled", True) if hours_skill else True
    
    # Escalation Skill
    escalate_skill = await db.get_bot_skill(bot_id, "escalation")
    escalate_config = (escalate_skill.get("config") or {}) if escalate_skill else {}
    escalate_enabled = escalate_skill.get("enabled", True) if escalate_skill else True
    
    # Knowledge docs
    knowledge_docs = await db.list_bot_knowledge(bot_id, active_only=True)
    
    # Integrations
    calendar_status = await calendar_client.runtime_status(bot_id)
    calendar_config = {}
    calendar_integration = await db.get_active_bot_integration(bot_id, "google_calendar")
    if calendar_integration:
        calendar_config = calendar_integration.get("config") or {}
        
    api_integration = await db.get_active_bot_integration(bot_id, "external_api")
    api_config = {}
    api_secrets = []
    if api_integration:
        api_config = api_integration.get("config") or {}
        api_secrets = await db.list_integration_secrets(int(api_integration["id"]))
        
    chatwoot_integration = await db.get_active_bot_integration(bot_id, "chatwoot")
    chatwoot_config = {}
    chatwoot_secrets = {}
    chatwoot_enabled = False
    if chatwoot_integration:
        chatwoot_config = chatwoot_integration.get("config") or {}
        chatwoot_enabled = chatwoot_integration.get("enabled", False)
        # Fetch token secret
        enc_secrets = await db.get_integration_secret_values(int(chatwoot_integration["id"]))
        if "api_token" in enc_secrets:
            chatwoot_secrets["api_token"] = secure_store.decrypt_secret(enc_secrets["api_token"])
        
    env_rows_html = ""
    for sec in api_secrets:
        key_safe = html.escape(sec["secret_name"])
        env_rows_html += f'''
        <div class="env-var-row" style="display:flex; gap:8px; align-items:center; width:100%;">
          <input name="env_key" placeholder="KEY (Ej. STRIPE_KEY)" value="{key_safe}" style="flex:1; margin:0;" readonly>
          <div class="password-wrapper" style="flex:2;">
            <input type="password" name="env_val" placeholder="Valor del secreto" value="********" autocomplete="new-password" style="margin:0;">
            <button type="button" class="password-toggle" onclick="togglePasswordVisibility(this)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
            </button>
          </div>
          <button type="button" class="btn secondary" style="padding:8px 12px; color:var(--red);" onclick="this.parentElement.remove()">X</button>
        </div>
        '''
        
    # Metrics
    metrics = await db.admin_metrics(bot_id=bot_id)
    
    # Recent conversation threads
    recent_threads = await db.list_conversation_threads(limit=5, bot_id=bot_id)

    # Fetch Conversations and CRM info for client tabs
    await db.qualify_leads_with_action_link(
        config.QUALIFIED_CTA_URL,
        bot_id=bot_id,
    )
    
    threads = await db.list_conversation_threads(limit=100, bot_id=bot_id)
    selected_wa_id = wa_id or (threads[0]["wa_id"] if threads else None)
    messages = await db.list_conversation_messages(selected_wa_id, limit=120, bot_id=bot_id) if selected_wa_id else []
    selected_lead = await db.get_lead(selected_wa_id, bot_id=bot_id) if selected_wa_id else None
    
    # CRM info
    crm_counts = await db.crm_counts(bot_id=bot_id)
    crm_leads = await db.list_leads(
        None if status == "todos" else status,
        limit=200,
        bot_id=bot_id,
    )

    thread_items = "".join(
        f"""
        <a class="chat-item {'active' if selected_wa_id == t['wa_id'] else ''}" href="/client/app?bot_id={bot_id}&tab=conversations&wa_id={html.escape(t["wa_id"])}">
          <div class="chat-item-header">
            <span class="chat-item-name">{html.escape(_display_name(t.get("nombre"), t["wa_id"]))}</span>
            <span class="chat-item-time">{_fmt_dt(t.get("last_message_at")).split(" ")[-1]}</span>
          </div>
          <div class="chat-item-preview">{html.escape(_clip(t.get("last_content"), 60))}</div>
        </a>
        """
        for t in threads
    ) or '<div class="empty" style="padding: 20px; text-align: center; color: var(--muted);">Aún no hay conversaciones.</div>'

    bubble_html = "".join(
        f"""
        <div class="bubble {html.escape(m["role"])}">
          <div class="meta">{html.escape("Bot" if m["role"] == "assistant" else "Cliente")} - {_fmt_dt(m.get("created_at"))}</div>
          <div>{html.escape(m["content"])}</div>
        </div>
        """
        for m in messages
    ) or '<div class="empty" style="padding: 20px; text-align: center; color: var(--muted);">Selecciona una conversación para ver el historial.</div>'

    chat_header = ""
    crm_sidebar = ""
    if selected_wa_id:
        lead_status = (selected_lead or {}).get("qualification_status", "en_progreso")
        name_display = html.escape(_display_name((selected_lead or {}).get("nombre"), selected_wa_id))
        initials = name_display[:2].upper() if name_display else "??"
        
        chat_header = f"""
        <div class="chat-header">
          <div class="chat-avatar">{initials}</div>
          <div class="chat-header-info">
            <strong>{name_display}</strong>
            <small>{html.escape(selected_wa_id)}</small>
          </div>
        </div>
        """
        
        crm_sidebar = f"""
        <div class="chat-crm">
          <div class="crm-section">
            <h3>Detalles del Contacto</h3>
            <div style="font-weight:600;font-size:15px;margin-bottom:4px;">{name_display}</div>
            <div style="color:var(--muted);font-size:13px;margin-bottom:12px;">{html.escape((selected_lead or {}).get("negocio") or "Sin negocio")}</div>
            <a class="btn whatsapp" href="{_wa_link(selected_wa_id)}" target="_blank" style="width:100%; justify-content:center; display:flex; align-items:center; gap:8px; background:#25d366; color:white; border:none; text-decoration:none; border-radius:8px; padding:10px; font-weight:600; font-size:13px;">Conectar por WhatsApp</a>
          </div>
          <div class="crm-section">
            <h3>Estado del Lead</h3>
            <span class="badge b-{html.escape(lead_status)}">{html.escape(lead_status.replace("_", " "))}</span>
          </div>
          <div class="crm-section">
            <h3>Notas</h3>
            <div style="font-size:13px;color:var(--muted);background:#f8fafc;padding:10px;border-radius:8px;border:1px solid var(--line);">
              {html.escape((selected_lead or {}).get("notes") or "Sin notas guardadas.")}
            </div>
          </div>
        </div>
        """

    crm_tabs = [
        ("en_progreso", "No cualificados"),
        ("calificado", "Calificados"),
        ("descalificado", "Descalificados"),
        ("todos", "Todos"),
    ]
    crm_tabs_html = "".join(
        f'<a class="{"active" if key == status else ""}" href="/client/app?bot_id={bot_id}&tab=crm&status={key}">{label} ({sum(crm_counts.values()) if key == "todos" else crm_counts.get(key, 0)})</a>'
        for key, label in crm_tabs
    )
    
    crm_rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(_display_name(l.get("nombre"), l["wa_id"]))}</strong><br><span class="muted">{html.escape(l["wa_id"])}</span></td>
          <td>{html.escape(l.get("negocio") or "-")}</td>
          <td><span class="badge b-{html.escape(l["qualification_status"])}">{html.escape(l["qualification_status"].replace("_", " "))}</span><br><span class="muted">{html.escape(l.get("disqualify_reason") or "")}</span></td>
          <td>{_fmt_dt(l.get("updated_at"))}</td>
          <td>
            <div class="actions" style="display:flex; gap:6px;">
              <form class="inline" method="post" action="/client/bots/{bot_id}/crm/{html.escape(l["wa_id"])}/status"><button class="btn secondary" name="status" value="en_progreso" style="padding:6px 10px; font-size:12px; cursor:pointer;">No cualificado</button></form>
              <form class="inline" method="post" action="/client/bots/{bot_id}/crm/{html.escape(l["wa_id"])}/status"><button class="btn primary-btn" name="status" value="calificado" style="padding:6px 10px; font-size:12px; cursor:pointer;">Calificar</button></form>
              <form class="inline" method="post" action="/client/bots/{bot_id}/crm/{html.escape(l["wa_id"])}/status"><button class="btn secondary" name="status" value="descalificado" style="padding:6px 10px; font-size:12px; color:var(--red); cursor:pointer;">Descartar</button></form>
            </div>
          </td>
        </tr>
        """
        for l in crm_leads
    ) or '<tr><td colspan="5" class="empty" style="text-align:center; padding:20px; color:var(--muted);">No hay leads en esta etapa.</td></tr>'

    bot_status = selected_bot.get("status") or "active"
    if bot_status == "active":
        status_class = "success"
        status_label = "Activo"
        dot_color = "#10b981"
        status_title = "Haz clic para PAUSAR el bot (modo humano únicamente)"
    else:
        status_class = "warning"
        status_label = "Pausado"
        dot_color = "#f59e0b"
        status_title = "Haz clic para REANUDAR las respuestas autónomas del bot"

    # 2. RENDER SECTIONS
    body_html = f"""
    <div class="header">
      <div>
        <h1>{html.escape(selected_bot["name"])}</h1>
        <p>Configuración del asistente inteligente para tu negocio</p>
      </div>
      <div class="header-actions">
        <span class="badge" style="background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd;">ID del Bot: {bot_id}</span>
        <form action="/client/bots/{bot_id}/toggle-status" method="post" class="inline" style="margin:0; padding:0;">
          <button type="submit" class="badge {status_class} badge-toggle" style="border: none; cursor: pointer; display: inline-flex; gap: 6px; align-items: center;" title="{status_title}">
            <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:{dot_color};"></span>
            Bot: {status_label}
          </button>
        </form>
        <span class="badge">WhatsApp: {html.escape(wa_info.get("display_phone_number") or "sin conectar")}</span>
      </div>
    </div>
    
    <!-- 1. TAF PANEL: INICIO -->
    <div id="panel-inicio" class="tab-panel active">
      <div class="grid-3" style="margin-bottom: 24px;">
        <div class="kpi-card">
          <div class="kpi-title">Chats Activos</div>
          <div class="kpi-value">{metrics.get("conversations", 0)}</div>
          <div class="kpi-status ok">Historial guardado</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">Mensajes Procesados</div>
          <div class="kpi-value">{metrics.get("messages", 0)}</div>
          <div class="kpi-status ok">Respuestas autónomas</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-title">Leads Registrados</div>
          <div class="kpi-value">{metrics.get("leads", 0)}</div>
          <div class="kpi-status ok">CRM de Leads</div>
        </div>
      </div>
      
      <div class="grid-cards">
        <div>
          <div class="card">
            <div class="card-header">
              <h2>Conversaciones Recientes</h2>
              <p>Últimos hilos de chat iniciados en WhatsApp</p>
            </div>
            {_render_conversations_table(recent_threads)}
          </div>
        </div>
        <div>
          <div class="card">
            <div class="card-header">
              <h2>Estado del Asistente</h2>
              <p>Estado operacional de tus servicios</p>
            </div>
            <div style="display:flex; flex-direction:column; gap:12px; margin-top:14px;">
              <div style="display:flex; justify-content:space-between; align-items:center; padding-bottom:8px; border-bottom:1px solid var(--line);">
                <span class="bold-text" style="font-size:13px;">WhatsApp Cloud API</span>
                <span class="badge {"success" if wa_info.get("phone_number_id") else "danger"}">
                  {"Conectado" if wa_info.get("phone_number_id") else "Desconectado"}
                </span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; padding-bottom:8px; border-bottom:1px solid var(--line);">
                <span class="bold-text" style="font-size:13px;">Google Calendar</span>
                <span class="badge {"success" if calendar_status.get("enabled") else "warning"}">
                  {"Activo" if calendar_status.get("enabled") else "Inactivo"}
                </span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; padding-bottom:8px; border-bottom:1px solid var(--line);">
                <span class="bold-text" style="font-size:13px;">Reglas de Escalado</span>
                <span class="badge {"success" if escalate_enabled else "warning"}">
                  {"Habilitado" if escalate_enabled else "Deshabilitado"}
                </span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="bold-text" style="font-size:13px;">Base de Conocimiento</span>
                <span class="badge success">{len(knowledge_docs)} Docs</span>
              </div>
            </div>
          </div>
        </div>
    </div>
  </div>
"""

    # 1b. TAB PANEL: CONVERSACIONES
    if chatwoot_enabled and chatwoot_config.get("base_url"):
        cw_url = chatwoot_config.get("base_url").rstrip("/")
        cw_account = chatwoot_config.get("account_id", "")
        # Render Chatwoot Iframe
        conversations_panel_html = f"""
        <div id="panel-conversations" class="tab-panel">
          <div style="height: calc(100vh - 220px); border-radius: 12px; overflow: hidden; border: 1px solid var(--line); box-shadow: var(--shadow); margin-top: 14px; background: white;">
            <iframe src="{html.escape(cw_url)}/app/accounts/{html.escape(cw_account)}/dashboard" width="100%" height="100%" frameborder="0" style="background: white;"></iframe>
          </div>
        </div>
        """
    else:
        conversations_panel_html = f"""
        <div id="panel-conversations" class="tab-panel">
          <div class="chatwoot-layout">
            <div class="chat-sidebar">
              <div class="chat-sidebar-header">
                Chats activos
                <span class="badge">{len(threads)}</span>
              </div>
              <div class="chat-list">
                {thread_items}
              </div>
            </div>
            <div class="chat-main">
              {chat_header}
              <div class="chat-messages">
                {bubble_html}
              </div>
            </div>
            {crm_sidebar}
          </div>
        </div>
        """

    body_html += conversations_panel_html + f"""
    <!-- 1c. TAB PANEL: CRM -->
    <div id="panel-crm" class="tab-panel">
      <div class="card" style="margin-bottom:20px;">
        <div class="card-header">
          <h2>CRM de Leads</h2>
          <p>Mueve prospectos de no cualificados a calificados conforme avanza la venta.</p>
        </div>
      </div>
      <div class="tabs" style="margin-bottom:16px;">
        {crm_tabs_html}
      </div>
      <section class="table-wrap" style="background:white; border:1px solid var(--line); border-radius:12px; overflow:hidden; box-shadow:var(--shadow);">
        <table style="width:100%; border-collapse:collapse; text-align:left;">
          <thead>
            <tr style="background:#f8fafc; border-bottom:1px solid var(--line);">
              <th style="padding:14px 16px; font-weight:600; color:var(--muted); font-size:13px;">Prospecto</th>
              <th style="padding:14px 16px; font-weight:600; color:var(--muted); font-size:13px;">Negocio</th>
              <th style="padding:14px 16px; font-weight:600; color:var(--muted); font-size:13px;">Estado</th>
              <th style="padding:14px 16px; font-weight:600; color:var(--muted); font-size:13px;">Actualizado</th>
              <th style="padding:14px 16px; font-weight:600; color:var(--muted); font-size:13px;">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {crm_rows}
          </tbody>
        </table>
      </section>
    </div>
    
    <!-- 2. TAB PANEL: WHATSAPP -->
    <div id="panel-whatsapp" class="tab-panel">
      <div class="grid-cards">
        <div class="panel">
          <div class="card">
            <div class="card-header">
              <h2>Meta Embedded Signup (Recomendado)</h2>
              <p>Vincula el número de WhatsApp de tu empresa de forma guiada y segura a través de Asistto como Tech Provider.</p>
            </div>
            
            <div style="margin:20px 0; padding:16px; background:#f0fdfa; border:1px solid #99f6e4; border-radius:8px;">
              <span class="bold-text" style="color:var(--primary-dark); font-size:14px; display:block; margin-bottom:6px;">Instrucciones para Embedded Signup:</span>
              <ol style="margin:0; padding-left:20px; font-size:13px; color:#1e293b; line-height:1.6;">
                <li>Haz clic en el botón verde "Abrir Embedded Signup" abajo.</li>
                <li>Inicia sesión con tu cuenta de negocio de Facebook.</li>
                <li>Selecciona el portafolio comercial de tu negocio y el WABA o número a vincular.</li>
                <li>Una vez completado, los datos de IDs se llenarán automáticamente en el formulario de la derecha. Revísalos y presiona "Guardar conexión".</li>
              </ol>
            </div>
            
            <div style="margin-top:20px;">
              <button class="btn whatsapp-btn" type="button" id="launchMetaSignup">Abrir Embedded Signup de Meta</button>
            </div>
            <div id="metaSignupStatus" class="sync-status">Esperando inicio de vinculación...</div>
          </div>
        </div>
        
        <div>
          <div class="card">
            <div class="card-header">
              <h2>Detalles de la Conexión</h2>
              <p>Completa o edita las credenciales de conexión del bot.</p>
            </div>
            <form method="post" action="/client/bots/{bot_id}/whatsapp/connect">
              <label>Authorization Code de Meta (si aplica)</label>
              <input id="metaAuthCode" name="authorization_code" autocomplete="off" placeholder="Llenado automáticamente">
              
              <label>Access Token (Manual o Temporal)</label>
              <div class="password-wrapper">
                <input type="password" name="access_token" placeholder="EAW..." autocomplete="new-password" value="{html.escape(access_token_val)}">
                <button type="button" class="password-toggle" onclick="togglePasswordVisibility(this)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                </button>
              </div>
              
              <label>Business Portfolio ID</label>
              <input id="metaBusinessId" name="business_id" value="{html.escape(wa_info.get("business_id") or "")}">
              
              <label>WABA ID (WhatsApp Business Account)</label>
              <input id="metaWabaId" name="waba_id" value="{html.escape(wa_info.get("waba_id") or "")}">
              
              <label>Phone Number ID</label>
              <input id="metaPhoneId" name="phone_number_id" value="{html.escape(wa_info.get("phone_number_id") or "")}" required>
              
              <label>Número de WhatsApp Visible</label>
              <input id="metaDisplayPhone" name="display_phone_number" value="{html.escape(wa_info.get("display_phone_number") or "")}" placeholder="+52...">
              
              <div style="margin-top:20px;">
                <button class="btn primary-btn" type="submit" {"disabled" if session["role"] == "client_viewer" else ""}>Guardar conexión cifrada</button>
              </div>
            </form>
          </div>
        </div>
      </div>
      
      <script async defer crossorigin="anonymous" src="https://connect.facebook.net/en_US/sdk.js"></script>
      <script>
        (() => {{
          const app_id = "{config.META_APP_ID or ""}";
          const config_id = "{config.META_CONFIG_ID or ""}";
          const status = document.getElementById("metaSignupStatus");
          
          window.fbAsyncInit = function() {{
            if (!app_id) return;
            FB.init({{ appId: app_id, cookie: true, xfbml: true, version: 'v19.0' }});
          }};
          
          window.addEventListener("message", (event) => {{
            if (!event.origin.endsWith("facebook.com")) return;
            let data = event.data;
            try {{ if (typeof data === "string") data = JSON.parse(data); }} catch (_) {{ return; }}
            const payload = data?.data || data;
            if (payload?.phone_number_id) document.getElementById("metaPhoneId").value = payload.phone_number_id;
            if (payload?.waba_id) document.getElementById("metaWabaId").value = payload.waba_id;
            if (payload?.business_id) document.getElementById("metaBusinessId").value = payload.business_id;
            if (payload?.display_phone_number) document.getElementById("metaDisplayPhone").value = payload.display_phone_number;
            if (payload?.phone_number_id) status.innerHTML = "<span class='sync-status ok'>Datos recibidos de Meta. Revisa y pulsa 'Guardar conexión'.</span>";
          }});
          
          document.getElementById("launchMetaSignup")?.addEventListener("click", () => {{
            if (!window.FB) {{
              status.innerHTML = "<span class='sync-status err'>Meta SDK no está listo todavía. Inténtalo en un momento.</span>";
              return;
            }}
            FB.login((response) => {{
              const code = response?.authResponse?.code;
              if (code) {{
                document.getElementById("metaAuthCode").value = code;
                status.innerHTML = "<span class='sync-status ok'>Vínculo inicial exitoso. Completa y guarda.</span>";
              }} else {{
                status.innerHTML = "<span class='sync-status err'>Meta canceló el flujo o no regresó código.</span>";
              }}
            }}, {{
              config_id: config_id,
              response_type: "code",
              override_default_response_type: true,
              extras: {{ 
                featureType: "whatsapp_business_app_onboarding",
                sessionInfoVersion: "3",
                setup: {{}}
              }}
            }});
          }});
        }})();
      </script>
    </div>
    
    <!-- 3. TAB PANEL: COMPORTAMIENTO (PROMPT) -->
    <div id="panel-prompt" class="tab-panel">
      <div class="prompt-workspace">
        <div class="card">
          <div class="card-header">
            <h2>Asistente de Prompt con IA</h2>
            <p>Escribe qué quieres que haga tu bot en WhatsApp y la IA generará el prompt final integrando tu base de conocimientos.</p>
          </div>
          <div style="margin-bottom:14px;">
            <label>Describe el comportamiento que buscas</label>
            <textarea id="aiPromptInstruction" style="min-height: 120px;" placeholder="Ej. Eres un bot de la Clínica Dental Smile. Tu objetivo es agendar citas de diagnóstico dental. Saluda amablemente, solicita nombre completo y busca un espacio libre. Si tienen urgencias de dolor fuerte, pásalo a humano de inmediato..."></textarea>
          </div>
          <div>
            <button class="btn primary-btn" type="button" id="btnAssistPrompt" onclick="requestAIPrompt()">
              Generar instrucciones con IA
            </button>
            <span id="aiAssistLoader" style="display:none; margin-left:12px; font-size:13px; color:var(--primary); font-weight:600;">Generando prompt óptimo...</span>
          </div>
          
          <div id="promptPreviewBlock" style="margin-top:24px; display:none;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <span class="bold-text" style="font-size:13px; color:var(--primary-dark);">Vista previa del prompt generado</span>
              <button class="btn secondary" style="padding:4px 10px; font-size:11px;" onclick="applyGeneratedPrompt()">Aplicar Preview</button>
            </div>
            <textarea id="aiPromptPreview" style="min-height: 240px; background:#f8fafc; font-family:monospace; font-size:12px; border-color:var(--primary-light);" readonly></textarea>
          </div>
        </div>
        
        <div class="card">
          <div class="card-header">
            <h2>Instrucciones del Bot (Prompt de Sistema)</h2>
            <p>Este es el texto completo con el comportamiento operativo del bot. Puedes editarlo libremente.</p>
          </div>
          <form method="post" action="/client/bots/{bot_id}/prompt/save">
            <textarea id="activePromptEditor" name="prompt" style="min-height: 380px; font-family:monospace; font-size:12.5px; line-height:1.5;" placeholder="System prompt...">{html.escape(current_prompt_content)}</textarea>
            <div style="margin-top:16px;">
              <button class="btn" type="submit" {"disabled" if session["role"] == "client_viewer" else ""}>Publicar comportamiento</button>
            </div>
          </form>
        </div>
      </div>
      
      <script>
        async function requestAIPrompt() {{
          const instruction = document.getElementById("aiPromptInstruction").value.trim();
          const current = document.getElementById("activePromptEditor").value;
          if (!instruction) {{
            alert("Por favor escribe una descripción para el comportamiento del bot.");
            return;
          }}
          
          const loader = document.getElementById("aiAssistLoader");
          const btn = document.getElementById("btnAssistPrompt");
          const previewBlock = document.getElementById("promptPreviewBlock");
          const previewArea = document.getElementById("aiPromptPreview");
          
          loader.style.display = "inline";
          btn.disabled = true;
          
          const formData = new FormData();
          formData.append("instruction", instruction);
          formData.append("current_prompt", current);
          
          try {{
            const response = await fetch("/client/bots/{bot_id}/prompt/assist", {{
              method: "POST",
              body: formData
            }});
            if (!response.ok) {{
              const err = await response.json();
              throw new Error(err.detail || "Error generando el prompt");
            }}
            const data = await response.json();
            if (data.ok) {{
              previewArea.value = data.prompt;
              previewBlock.style.display = "block";
            }} else {{
              alert("Error: " + data.error);
            }}
          }} catch (e) {{
            alert(e.message);
          }} finally {{
            loader.style.display = "none";
            btn.disabled = false;
          }}
        }}
        
        function applyGeneratedPrompt() {{
          const generated = document.getElementById("aiPromptPreview").value;
          document.getElementById("activePromptEditor").value = generated;
          document.getElementById("promptPreviewBlock").style.display = "none";
          alert("Prompt copiado al editor de la derecha. Haz clic en 'Publicar comportamiento' para guardarlo definitivamente.");
        }}
      </script>
    </div>
    
    <!-- 4. TAB PANEL: HORARIOS -->
    <div id="panel-hours" class="tab-panel">
      <div class="card" style="max-width:840px;">
        <div class="card-header">
          <h2>Horarios de Atención y Agendado</h2>
          <p>Define las horas y días laborales del bot en las que está permitido programar llamadas o citas en tu calendario. Fuera de estas horas, el bot avisará de forma determinista al cliente.</p>
        </div>
        <form method="post" action="/client/bots/{bot_id}/hours">
          <div class="checkbox-group" style="margin-bottom:20px;">
            <input type="checkbox" name="enabled" id="hoursEnabledToggle" {"checked" if hours_enabled else ""}>
            <label for="hoursEnabledToggle" style="margin:0; font-size:14px; font-weight:600; cursor:pointer;">Activar restricción de horarios de atención para agendado</label>
          </div>
          
          <div style="border: 1px solid var(--line); border-radius:8px; overflow:hidden; background:white;">
            <div class="weekday-row" style="background:#f8fafc; font-weight:700; font-size:11px; text-transform:uppercase; color:var(--muted); border-bottom: 2px solid var(--line);">
              <div>Día</div>
              <div>¿Abierto?</div>
              <div>Hora Inicio</div>
              <div>Hora Cierre</div>
            </div>
            
            {_render_hours_rows(hours_config)}
          </div>
          
          <div style="margin-top:20px;">
            <button class="btn primary-btn" type="submit" {"disabled" if session["role"] == "client_viewer" else ""}>Guardar horarios</button>
          </div>
        </form>
      </div>
    </div>
    
    <!-- 5. TAB PANEL: ESCALADO -->
    <div id="panel-escalate" class="tab-panel">
      <div class="card" style="max-width: 720px;">
        <div class="card-header">
          <h2>Reglas de Escalado Humano</h2>
          <p>Configura las condiciones bajo las cuales el bot debe detenerse y marcar la conversación para que un asesor humano tome el control en WhatsApp.</p>
        </div>
        
        <form method="post" action="/client/bots/{bot_id}/escalation">
          <div class="checkbox-group" style="margin-bottom:18px;">
            <input type="checkbox" name="enabled" id="escalateEnabledToggle" {"checked" if escalate_enabled else ""}>
            <label for="escalateEnabledToggle" style="margin:0; font-size:14px; font-weight:600; cursor:pointer;">Activar escalación humana de conversaciones</label>
          </div>
          
          <div style="margin-bottom:20px;">
            <label>Palabras clave o frases de activación (una por línea o separadas por comas)</label>
            <textarea name="keywords" style="min-height: 120px;" placeholder="Ej. queja, hablar con humano, operador, urgente, reclamo, costo extra">{html.escape(", ".join(escalate_config.get("keywords", [])))}</textarea>
            <p class="muted-text" style="margin-top:4px;">Si el usuario escribe cualquiera de estas frases, el bot registrará la escalación y se marcará en color rojo como 'pendiente' en el panel.</p>
          </div>
          
          <div class="checkbox-group">
            <input type="checkbox" name="escalate_on_media" id="escalateOnMedia" {"checked" if escalate_config.get("escalate_on_media", True) else ""}>
            <label for="escalateOnMedia" style="margin:0; font-weight:500; cursor:pointer;">Escalar automáticamente si el cliente envía un archivo (imagen, audio, pdf, etc.)</label>
          </div>
          
          <div style="margin-top:20px;">
            <button class="btn primary-btn" type="submit" {"disabled" if session["role"] == "client_viewer" else ""}>Guardar reglas de escalado</button>
          </div>
        </form>
      </div>
    </div>
    
    <!-- 6. TAB PANEL: CONOCIMIENTO -->
    <div id="panel-knowledge" class="tab-panel">
      <div class="grid-cards">
        <div class="card">
          <div class="card-header">
            <h2>Base de Conocimiento Activa</h2>
            <p>Información que el bot puede leer como contexto para contestar preguntas sobre precios, servicios, ubicaciones o preguntas frecuentes.</p>
          </div>
          {_render_knowledge_table(knowledge_docs, bot_id, session["role"])}
        </div>
        
        <div>
          <div class="card">
            <div class="card-header">
              <h2>Agregar Documento o Archivo</h2>
              <p>Sube preguntas frecuentes, menús de servicio o políticas operativas. Puedes escribir texto directamente o subir un archivo.</p>
            </div>
            <form method="post" action="/client/bots/{bot_id}/knowledge" enctype="multipart/form-data">
              <label>Título del Documento (Opcional si subes archivo)</label>
              <input name="title" placeholder="Preguntas Frecuentes Dentales">
              
              <label>Contenido del Conocimiento (Escribe texto...)</label>
              <textarea name="content" style="min-height: 140px;" placeholder="Ej. &#10;¿Tienen estacionamiento? Sí, gratuito en plaza.&#10;¿Precios de Limpieza? Desde $500 MXN.&#10;¿Aceptan tarjeta? Sí, Visa y Mastercard."></textarea>
              
              <label style="margin-top:14px; display:block; font-weight:600;">...o Sube un Archivo (PDF, Word, MD, Excel, CSV)</label>
              <input type="file" name="file" accept=".pdf,.docx,.doc,.xlsx,.csv,.md,.txt" style="margin-top:6px; font-size:13px; color:var(--muted);">
              
              <div style="margin-top:18px;">
                <button class="btn primary-btn" type="submit" {"disabled" if session["role"] == "client_viewer" else ""}>Guardar documento</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 7. TAB PANEL: INTEGRACIONES -->
    <div id="panel-integrations" class="tab-panel">
      <div class="grid-2">
        <div class="card">
          <div class="card-header">
            <h2>Chatwoot (Bandeja Multicanal)</h2>
            <p>Conecta tu cuenta de Chatwoot para responder manualmente a tus clientes cuando la IA transfiere el chat.</p>
          </div>
          
          <div style="margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; padding-bottom:8px; border-bottom:1px solid var(--line);">
            <span class="bold-text">Estado de Integración</span>
            <span class="badge {"success" if chatwoot_enabled else "warning"}">
              {"Conectado" if chatwoot_enabled else "Desconectado"}
            </span>
          </div>
          
          <form method="post" action="/client/bots/{bot_id}/integrations/chatwoot">
            <div class="checkbox-group">
              <input type="checkbox" name="enabled" id="chatwootToggle" {"checked" if chatwoot_enabled else ""}>
              <label for="chatwootToggle" style="margin:0; font-weight:600; cursor:pointer;">Habilitar Sincronización con Chatwoot</label>
            </div>
            
            <label>URL Base de Chatwoot</label>
            <input name="base_url" placeholder="https://app.chatwoot.com" value="{html.escape(chatwoot_config.get("base_url") or "")}">
            
            <div style="display:flex; gap:10px;">
              <div style="flex:1;">
                <label>Account ID</label>
                <input name="account_id" placeholder="Ej. 1" value="{html.escape(chatwoot_config.get("account_id") or "")}">
              </div>
              <div style="flex:1;">
                <label>Inbox ID</label>
                <input name="inbox_id" placeholder="Ej. 12" value="{html.escape(chatwoot_config.get("inbox_id") or "")}">
              </div>
            </div>
            
            <label>User API Token</label>
            <div class="password-wrapper">
              <input type="password" name="api_token" placeholder="********" autocomplete="new-password" value="{"" if not chatwoot_secrets.get("api_token") else "********"}">
              <button type="button" class="password-toggle" onclick="togglePasswordVisibility(this)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
              </button>
            </div>
            
            <div style="margin-top:20px; display:flex; gap:10px;">
              <button class="btn primary-btn" type="submit" {"disabled" if session["role"] == "client_viewer" else ""}>Guardar Chatwoot</button>
            </div>
          </form>
        </div>

        <div class="card">
          <div class="card-header">
            <h2>Agenda (Google Calendar)</h2>
            <p>Conecta la cuenta de Google Calendar de tu negocio para agendar de forma autónoma.</p>
          </div>
          
          <div style="margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; padding-bottom:8px; border-bottom:1px solid var(--line);">
            <span class="bold-text">Habilidad de Calendario</span>
            <span class="badge {"success" if calendar_status.get("enabled") else "warning"}">
              {"Activa" if calendar_status.get("enabled") else "Inactiva"}
            </span>
          </div>
          
          <form method="post" action="/client/bots/{bot_id}/integrations/calendar">
            <div class="checkbox-group">
              <input type="checkbox" name="enabled" id="calendarSkillToggle" {"checked" if calendar_status.get("skill_enabled", True) else ""}>
              <label for="calendarSkillToggle" style="margin:0; font-weight:600; cursor:pointer;">Habilitar reserva automática</label>
            </div>
            
            <label>Google Client ID</label>
            <input name="client_id" placeholder="12345-abcde.apps.googleusercontent.com" value="{html.escape(calendar_config.get("client_id") or "")}">
            
            <label>Google Client Secret</label>
            <div class="password-wrapper">
              <input type="password" name="client_secret" placeholder="********" autocomplete="new-password" value="{"" if not calendar_status.get("secret_client_secret_saved") else "********"}">
              <button type="button" class="password-toggle" onclick="togglePasswordVisibility(this)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
              </button>
            </div>
            
            <label>Google Refresh Token</label>
            <div class="password-wrapper">
              <input type="password" name="refresh_token" placeholder="1//0..." autocomplete="new-password" value="{"" if not calendar_status.get("secret_refresh_token_saved") else "********"}">
              <button type="button" class="password-toggle" onclick="togglePasswordVisibility(this)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
              </button>
            </div>
            
            <label>Google Calendar ID</label>
            <input name="calendar_id" placeholder="ej. primary o email@gmail.com" value="{html.escape(calendar_config.get("calendar_id") or "primary")}">
            
            <label>Zona Horaria</label>
            <input name="timezone" placeholder="America/Chihuahua" value="{html.escape(calendar_config.get("timezone") or config.GOOGLE_CALENDAR_TIMEZONE)}">
            
            <div style="margin-top:20px; display:flex; gap:10px;">
              <button class="btn primary-btn" type="submit" {"disabled" if session["role"] == "client_viewer" else ""}>Guardar Agenda</button>
            </div>
          </form>
        </div>
        
        <div class="card">
          <div class="card-header">
            <h2>Variables de Entorno (API / Webhook)</h2>
            <p>Configura variables dinámicas (Ej. <code>MERCADOPAGO_TOKEN</code>) para usarlas en llamadas externas reemplazando su nombre con llaves: <code>{{MERCADOPAGO_TOKEN}}</code>.</p>
          </div>
          
          <form method="post" action="/client/bots/{bot_id}/integrations/api">
            <label>URL Base del API (Opcional)</label>
            <input name="base_url" placeholder="https://api.miclinicadental.com/v1" value="{html.escape(api_config.get("base_url") or "")}">
            
            <div style="margin-top: 16px;">
              <label>Variables de Entorno</label>
              <div id="envVarsContainer" style="display:flex; flex-direction:column; gap:8px;">
                {env_rows_html}
              </div>
              <button type="button" class="btn secondary" style="margin-top:12px; font-size:12px;" onclick="addEnvVarRow()">+ Agregar Variable</button>
            </div>
            
            <div style="margin-top:24px;">
              <button class="btn primary-btn" type="submit" {"disabled" if session["role"] == "client_viewer" else ""}>Guardar Variables</button>
            </div>
          </form>
          
          <script>
            function addEnvVarRow() {{
              const container = document.getElementById('envVarsContainer');
              const row = document.createElement('div');
              row.className = 'env-var-row';
              row.style.cssText = 'display:flex; gap:8px; align-items:center; margin-top:4px;';
              row.innerHTML = `
                <input name="env_key" placeholder="KEY (Ej. API_KEY)" style="flex:1; margin:0;" required>
                <div class="password-wrapper" style="flex:2;">
                  <input type="password" name="env_val" placeholder="Valor del secreto" autocomplete="new-password" style="margin:0;" required>
                  <button type="button" class="password-toggle" onclick="togglePasswordVisibility(this)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                  </button>
                </div>
                <button type="button" class="btn secondary" style="padding:8px 12px; color:var(--red);" onclick="this.parentElement.remove()">X</button>
              `;
              container.appendChild(row);
            }}
          </script>
        </div>
      </div>
    </div>
    """
    
    return HTMLResponse(_layout(
        title="Panel de Control",
        body=body_html,
        session=session,
        active_tab=tab,
        notice=notice_html,
        bots_list=bots,
        selected_bot_id=bot_id
    ))

def _render_conversations_table(threads: list) -> str:
    if not threads:
        return '<div style="padding:28px 0; text-align:center; color:var(--muted)">Sin conversaciones registradas todavía.</div>'
        
    rows = ""
    for thread in threads:
        wa_id = thread["wa_id"]
        last_role = thread["last_role"]
        last_content = thread["last_content"] or ""
        role_badge = '<span class="badge" style="padding:2px 6px; font-size:10px;">Cliente</span>' if last_role == "user" else '<span class="badge success" style="padding:2px 6px; font-size:10px;">Bot</span>'
        
        display_name = thread["nombre"] or wa_id
        lead_badge = ""
        status = thread["qualification_status"] or "en_progreso"
        if status == "calificado":
            lead_badge = '<span class="badge success" style="padding:2px 6px; font-size:10px;">Calificado</span>'
        elif status == "descalificado":
            lead_badge = '<span class="badge danger" style="padding:2px 6px; font-size:10px;">Descalificado</span>'
        else:
            lead_badge = '<span class="badge warning" style="padding:2px 6px; font-size:10px;">En progreso</span>'
            
        rows += f"""
        <tr>
          <td style="font-weight:600; font-size:13px; width:180px;">{html.escape(display_name)}<br><span class="muted-text" style="font-size:11px;">{html.escape(wa_id)}</span></td>
          <td style="font-size:13px; max-width:320px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{role_badge} {html.escape(last_content[:100])}</td>
          <td style="width:120px; text-align:right;">{lead_badge}</td>
        </tr>
        """
        
    return f"""
    <div style="overflow-x:auto;">
      <table style="width:100%;">
        <thead>
          <tr>
            <th>Contacto</th>
            <th>Último mensaje</th>
            <th style="text-align:right;">CRM</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>
    """

def _render_hours_rows(config_data: dict) -> str:
    days = [
        ("lunes", "Lunes"),
        ("martes", "Martes"),
        ("miercoles", "Miércoles"),
        ("jueves", "Jueves"),
        ("viernes", "Viernes"),
        ("sabado", "Sábado"),
        ("domingo", "Domingo"),
    ]
    
    rows_html = ""
    for key, label in days:
        day_cfg = config_data.get(key, {})
        is_open = day_cfg.get("open", key not in ("sabado", "domingo"))
        start_time = day_cfg.get("start", "09:00")
        end_time = day_cfg.get("end", "18:00")
        
        rows_html += f"""
        <div class="weekday-row">
          <div class="bold-text" style="font-size:14px;">{label}</div>
          <div>
            <input type="checkbox" name="open_{key}" {"checked" if is_open else ""} style="width:18px; height:18px; accent-color:var(--primary); cursor:pointer;">
          </div>
          <div>
            <input type="text" name="start_{key}" value="{html.escape(start_time)}" style="max-width:110px; text-align:center; padding:6px 10px;" placeholder="09:00">
          </div>
          <div>
            <input type="text" name="end_{key}" value="{html.escape(end_time)}" style="max-width:110px; text-align:center; padding:6px 10px;" placeholder="18:00">
          </div>
        </div>
        """
    return rows_html

def _render_knowledge_table(docs: list, bot_id: int, role: str) -> str:
    if not docs:
        return '<div style="padding:28px 0; text-align:center; color:var(--muted)">No tienes documentos de conocimiento activos. Agrega uno a la derecha.</div>'
        
    rows = ""
    for doc in docs:
        title = doc["title"]
        content = doc["content"]
        created_at = doc.get("created_at")
        dt_str = created_at.strftime("%d/%m/%Y") if created_at else "-"
        
        archive_form = ""
        if role in ("agency_admin", "client_admin"):
            archive_form = f"""
            <form method="post" action="/client/bots/{bot_id}/knowledge/{doc["id"]}/archive" style="display:inline;">
              <button class="btn secondary" style="padding:5px 10px; font-size:11px; color:var(--red); border-color:rgba(225, 29, 72, 0.2); background:#fff5f5;" type="submit">Archivar</button>
            </form>
            """
            
        rows += f"""
        <tr>
          <td style="font-weight:600; font-size:13.5px; width:220px;">{html.escape(title)}<br><span class="muted-text" style="font-size:11px;">Creado: {dt_str}</span></td>
          <td style="font-size:12.5px; color:var(--muted); max-width:380px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{html.escape(content[:160])}</td>
          <td style="width:100px; text-align:right;">{archive_form}</td>
        </tr>
        """
        
    return f"""
    <div style="overflow-x:auto;">
      <table style="width:100%;">
        <thead>
          <tr>
            <th>Documento</th>
            <th>Previsualización</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>
    """

# --- POST ENDPOINTS FOR SAVING CLIENT CONFIGURATIONS ---

@router.post("/bots/{bot_id}/whatsapp/connect")
async def client_whatsapp_connect(
    request: Request,
    bot_id: int,
    authorization_code: str = Form(""),
    access_token: str = Form(""),
    business_id: str = Form(""),
    waba_id: str = Form(""),
    phone_number_id: str = Form(...),
    display_phone_number: str = Form(""),
):
    session = _require_client_login(request)
    await _require_bot_editor(session, bot_id)
    try:
        await meta_provider.connect_bot_from_embedded_signup(
            meta_provider.MetaConnectionInput(
                bot_id=bot_id,
                phone_number_id=phone_number_id.strip(),
                display_phone_number=display_phone_number.strip(),
                waba_id=waba_id.strip(),
                business_id=business_id.strip(),
                authorization_code=authorization_code.strip(),
                access_token=access_token.strip(),
            )
        )
        return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=whatsapp&saved=1", status_code=302)
    except Exception as exc:
        log.exception("Error vinculando WhatsApp desde panel cliente")
        return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=whatsapp&saved=err", status_code=302)

@router.post("/bots/{bot_id}/prompt/save")
async def client_prompt_save(request: Request, bot_id: int, prompt: str = Form(...)):
    session = _require_client_login(request)
    await _require_bot_editor(session, bot_id)
    clean = prompt.strip()
    if not clean:
        raise HTTPException(status_code=400, detail="El prompt no puede estar vacío")
    await db.publish_bot_prompt(bot_id, clean)
    return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=prompt&saved=1", status_code=302)

@router.post("/bots/{bot_id}/prompt/assist", response_class=JSONResponse)
async def client_prompt_assist(
    request: Request,
    bot_id: int,
    instruction: str = Form(...),
    current_prompt: str = Form(""),
):
    session = _require_client_login(request)
    bot = await _require_bot_editor(session, bot_id)
    try:
        knowledge_docs = await db.list_bot_knowledge(bot_id, active_only=True)
        result = await prompt_assistant.assist_prompt(
            bot=bot,
            current_prompt=current_prompt,
            instruction=instruction,
            knowledge_docs=knowledge_docs,
        )
        return JSONResponse(result)
    except prompt_assistant.PromptAssistantError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": prompt_assistant.safe_error(exc)}, status_code=502)

@router.post("/bots/{bot_id}/hours")
async def client_hours_save(request: Request, bot_id: int, enabled: str | None = Form(None)):
    session = _require_client_login(request)
    await _require_bot_editor(session, bot_id)
    
    # Parse form parameters for each weekday
    days = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    hours_config = {}
    form_data = await request.form()
    
    for day in days:
        is_open = form_data.get(f"open_{day}") == "on"
        start_time = str(form_data.get(f"start_{day}") or "09:00").strip()
        end_time = str(form_data.get(f"end_{day}") or "18:00").strip()
        
        # Validar formato HH:MM
        if not re.match(r"^\d{2}:\d{2}$", start_time) or not re.match(r"^\d{2}:\d{2}$", end_time):
            return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=hours&saved=err", status_code=302)
            
        hours_config[day] = {
            "open": is_open,
            "start": start_time,
            "end": end_time
        }
        
    await db.upsert_bot_skill(
        bot_id=bot_id,
        skill_type="business_hours",
        enabled=enabled == "on",
        config_data=hours_config
    )
    return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=hours&saved=1", status_code=302)

@router.post("/bots/{bot_id}/escalation")
async def client_escalation_save(
    request: Request,
    bot_id: int,
    enabled: str | None = Form(None),
    keywords: str = Form(""),
    escalate_on_media: str | None = Form(None),
):
    session = _require_client_login(request)
    await _require_bot_editor(session, bot_id)
    
    # Process comma-separated or newline-separated keywords
    words_list = []
    for chunk in re.split(r"[,\n]", keywords):
        clean = chunk.strip().lower()
        if clean:
            words_list.append(clean)
            
    escalation_config = {
        "keywords": words_list,
        "escalate_on_media": escalate_on_media == "on"
    }
    
    await db.upsert_bot_skill(
        bot_id=bot_id,
        skill_type="escalation",
        enabled=enabled == "on",
        config_data=escalation_config
    )
    return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=escalate&saved=1", status_code=302)

@router.post("/bots/{bot_id}/knowledge")
async def client_knowledge_create(
    request: Request,
    bot_id: int,
    title: str = Form(""),
    content: str = Form(""),
    file: UploadFile | None = File(None),
):
    session = _require_client_login(request)
    await _require_bot_editor(session, bot_id)
    clean_title = title.strip()
    clean_content = content.strip()
    
    if file and file.filename:
        filename = file.filename
        try:
            file_bytes = await file.read()
            if len(file_bytes) > 0:
                parsed_text = file_parser.parse_file(file_bytes, filename)
                if not parsed_text.strip():
                    raise ValueError("El archivo está vacío o no contiene texto legible.")
                clean_content = parsed_text.strip()
                if not clean_title:
                    clean_title = filename
        except Exception as e:
            log.exception(f"Error parseando archivo: {filename}")
            return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=knowledge&saved=err_parse", status_code=302)
            
    if not clean_title or not clean_content:
        raise HTTPException(status_code=400, detail="El título y el contenido son obligatorios (o sube un archivo válido).")
        
    try:
        await db.create_bot_knowledge(
            bot_id=bot_id,
            title=clean_title,
            content=clean_content
        )
    except Exception as e:
        log.exception(f"Error guardando documento de conocimiento en base de datos: {clean_title}")
        return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=knowledge&saved=err", status_code=302)
        
    return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=knowledge&saved=1", status_code=302)

@router.post("/bots/{bot_id}/knowledge/{knowledge_id}/archive")
async def client_knowledge_archive(request: Request, bot_id: int, knowledge_id: int):
    session = _require_client_login(request)
    await _require_bot_editor(session, bot_id)
    
    success = await db.archive_bot_knowledge(bot_id, knowledge_id)
    if not success:
         raise HTTPException(status_code=404, detail="Documento no encontrado o no pertenece a tu bot.")
         
    return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=knowledge&saved=1", status_code=302)

@router.post("/bots/{bot_id}/toggle-status")
async def client_bot_toggle_status(request: Request, bot_id: int):
    session = _require_client_login(request)
    bot = await _require_bot_editor(session, bot_id)
    
    current_status = bot.get("status") or "active"
    new_status = "paused" if current_status == "active" else "active"
    
    await db.update_bot_status(bot_id, new_status)
    
    referer = request.headers.get("referer") or f"/client/app?bot_id={bot_id}"
    return RedirectResponse(referer, status_code=302)

@router.post("/bots/{bot_id}/integrations/calendar")
async def client_calendar_save(
    request: Request,
    bot_id: int,
    enabled: str | None = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(""),
    refresh_token: str = Form(""),
    calendar_id: str = Form("primary"),
    timezone: str = Form("America/Chihuahua"),
):
    session = _require_client_login(request)
    await _require_bot_editor(session, bot_id)
    
    # Form data validation
    clean_cid = client_id.strip()
    clean_cal = calendar_id.strip() or "primary"
    clean_tz = timezone.strip() or "America/Chihuahua"
    
    # Search or create bot integration record
    integration = await db.get_active_bot_integration(bot_id, "google_calendar")
    
    config_data = {
        "client_id": clean_cid,
        "calendar_id": clean_cal,
        "timezone": clean_tz
    }
    
    if integration:
        integration_id = int(integration["id"])
        await db.update_bot_integration(
            bot_id=bot_id,
            integration_id=integration_id,
            integration_type="google_calendar",
            name=integration["name"],
            config_data=config_data,
            enabled=enabled == "on"
        )
    else:
        integration_id = await db.create_bot_integration(
            bot_id=bot_id,
            integration_type="google_calendar",
            name="Google Calendar Cliente",
            config_data=config_data,
            enabled=enabled == "on"
        )
        
    # Save secrets if provided
    clean_secret = client_secret.strip()
    if clean_secret and clean_secret != "********":
        encrypted_secret = secure_store.encrypt_secret(clean_secret)
        await db.upsert_integration_secret(integration_id, "client_secret", encrypted_secret)
        
    clean_refresh = refresh_token.strip()
    if clean_refresh and clean_refresh != "********":
        encrypted_refresh = secure_store.encrypt_secret(clean_refresh)
        await db.upsert_integration_secret(integration_id, "refresh_token", encrypted_refresh)
        
    # Sync status also in bot_skills (for enabling calendar)
    await db.upsert_bot_skill(
        bot_id=bot_id,
        skill_type="google_calendar",
        enabled=enabled == "on",
        config_data={}
    )
    
    return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=integrations&saved=1", status_code=302)

@router.post("/bots/{bot_id}/integrations/api")
async def client_api_save(
    request: Request,
    bot_id: int,
):
    session = _require_client_login(request)
    await _require_bot_editor(session, bot_id)
    
    form_data = await request.form()
    base_url = str(form_data.get("base_url", "")).strip()
    
    env_keys = form_data.getlist("env_key")
    env_vals = form_data.getlist("env_val")
        
    integration = await db.get_active_bot_integration(bot_id, "external_api")
    
    config_data = {
        "base_url": base_url,
    }
    
    if integration:
        integration_id = int(integration["id"])
        await db.update_bot_integration(
            bot_id=bot_id,
            integration_id=integration_id,
            integration_type="external_api",
            name=integration["name"],
            config_data=config_data,
            enabled=True
        )
    else:
        integration_id = await db.create_bot_integration(
            bot_id=bot_id,
            integration_type="external_api",
            name="API Cliente",
            config_data=config_data,
            enabled=True
        )
        
    # Handle dynamic secrets
    submitted_keys = []
    for k, v in zip(env_keys, env_vals):
        k_clean = str(k).strip()
        v_clean = str(v).strip()
        if not k_clean:
            continue
        submitted_keys.append(k_clean)
        
        # Only upsert if it's a new value (not the masked placeholder)
        if v_clean and v_clean != "********":
            encrypted_val = secure_store.encrypt_secret(v_clean)
            await db.upsert_integration_secret(integration_id, k_clean, encrypted_val)
            
    # Delete removed secrets
    existing_secrets = await db.list_integration_secrets(integration_id)
    for sec in existing_secrets:
        sec_name = sec["secret_name"]
        if sec_name not in submitted_keys:
            await db.delete_integration_secret(integration_id, sec_name)
        
    # Enable skill
    await db.upsert_bot_skill(
        bot_id=bot_id,
        skill_type="external_api",
        enabled=True,
        config_data={}
    )
    
    return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=integrations&saved=1", status_code=302)

@router.post("/bots/{bot_id}/integrations/chatwoot")
async def client_chatwoot_save(
    request: Request,
    bot_id: int,
    enabled: str | None = Form(None),
    base_url: str = Form(""),
    account_id: str = Form(""),
    inbox_id: str = Form(""),
    api_token: str = Form(""),
):
    session = _require_client_login(request)
    await _require_bot_editor(session, bot_id)
    
    clean_base_url = base_url.strip()
    clean_account_id = account_id.strip()
    clean_inbox_id = inbox_id.strip()
    
    integration = await db.get_active_bot_integration(bot_id, "chatwoot")
    
    config_data = {
        "base_url": clean_base_url,
        "account_id": clean_account_id,
        "inbox_id": clean_inbox_id
    }
    
    is_enabled = (enabled == "on")
    
    if integration:
        integration_id = int(integration["id"])
        await db.update_bot_integration(
            bot_id=bot_id,
            integration_id=integration_id,
            integration_type="chatwoot",
            name=integration["name"],
            config_data=config_data,
            enabled=is_enabled
        )
    else:
        integration_id = await db.create_bot_integration(
            bot_id=bot_id,
            integration_type="chatwoot",
            name="Chatwoot Bandeja",
            config_data=config_data,
            enabled=is_enabled
        )
        
    clean_api_token = api_token.strip()
    if clean_api_token and clean_api_token != "********":
        encrypted_token = secure_store.encrypt_secret(clean_api_token)
        await db.upsert_integration_secret(integration_id, "api_token", encrypted_token)
        
    return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=integrations&saved=1", status_code=302)

@router.post("/bots/{bot_id}/crm/{wa_id}/status")
async def client_crm_update_status(
    request: Request,
    bot_id: int,
    wa_id: str,
    status: str = Form(...),
):
    session = _require_client_login(request)
    await _require_bot_editor(session, bot_id)
    if status not in ("en_progreso", "calificado", "descalificado"):
        raise HTTPException(400, "Estado inválido")
    
    # Verify the lead belongs to this bot
    lead = await db.get_lead(wa_id, bot_id=bot_id)
    if not lead:
        raise HTTPException(404, "Lead no encontrado o no pertenece a este bot")
        
    await db.update_lead_status(
        wa_id,
        status,
        disqualify_reason="Movido manualmente desde panel cliente" if status == "descalificado" else None,
    )
    return RedirectResponse(f"/client/app?bot_id={bot_id}&tab=crm&status={status}", status_code=302)
