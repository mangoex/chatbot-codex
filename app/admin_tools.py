"""Herramientas administrativas pequenas para mantenimiento del bot."""
import html

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db

router = APIRouter(prefix="/admin", tags=["admin-tools"])


def _require_login(request: Request) -> str:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    return user


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - WhatsApp Bot</title>
<style>
  body {{ margin: 0; background: #f4f5f2; color: #151716; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }}
  main {{ max-width: 620px; margin: 48px auto; padding: 0 20px; }}
  .panel {{ background: white; border: 1px solid #dde2dc; border-radius: 8px; padding: 22px; box-shadow: 0 18px 45px rgba(24,31,27,.08); }}
  h1 {{ margin: 0 0 10px; font-size: 26px; }}
  p {{ color: #68706c; line-height: 1.5; }}
  label {{ display: block; margin: 16px 0 6px; color: #68706c; font-size: 13px; }}
  input {{ width: 100%; border: 1px solid #c9d0c8; border-radius: 8px; padding: 10px 11px; font: inherit; }}
  .actions {{ display: flex; gap: 8px; margin-top: 18px; flex-wrap: wrap; }}
  .btn {{ border: 1px solid #151716; background: #151716; color: white; border-radius: 8px; padding: 9px 12px; cursor: pointer; font: inherit; text-decoration: none; }}
  .btn.secondary {{ background: white; color: #151716; }}
  .danger {{ color: #95322d; }}
</style></head><body><main>{body}</main></body></html>"""


@router.get("/reset-contact", response_class=HTMLResponse)
async def reset_contact_page(request: Request, wa_id: str = ""):
    _require_login(request)
    clean_wa_id = "".join(ch for ch in wa_id if ch.isdigit())
    body = f"""
    <section class="panel">
      <h1>Limpiar conversacion</h1>
      <p>Esto borra historial, CRM, escalaciones y follow-ups pendientes de un contacto para probar desde cero.</p>
      <p class="danger">No borra mensajes dentro de WhatsApp; solo la memoria del bot y el panel.</p>
      <form method="post" action="/admin/reset-contact">
        <label>WhatsApp ID o telefono con lada</label>
        <input name="wa_id" value="{html.escape(clean_wa_id)}" placeholder="521667..." required autofocus>
        <div class="actions">
          <button class="btn" type="submit">Limpiar contacto</button>
          <a class="btn secondary" href="/admin/conversations">Cancelar</a>
        </div>
      </form>
    </section>
    """
    return HTMLResponse(_page("Limpiar conversacion", body))


@router.post("/reset-contact")
async def reset_contact_submit(request: Request, wa_id: str = Form(...)):
    _require_login(request)
    clean_wa_id = "".join(ch for ch in wa_id if ch.isdigit())
    if not clean_wa_id:
        raise HTTPException(400, "wa_id requerido")
    await db.clear_contact_data([clean_wa_id])
    return RedirectResponse("/admin/conversations", status_code=302)
