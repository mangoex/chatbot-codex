from __future__ import annotations
"""Módulo de integración con Google Drive API v3 para sincronización de Base de Conocimiento."""
import base64
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from app import db, file_parser, rag

log = logging.getLogger("whatsapp-bot")

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


def extract_folder_id(url_or_id: str | None) -> str:
    """Extrae el ID limpio de una carpeta de Google Drive a partir de una URL o ID directo."""
    if not url_or_id:
        return ""
    clean = url_or_id.strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", clean)
    if match:
        return match.group(1)
    match_id = re.search(r"id=([a-zA-Z0-9_-]+)", clean)
    if match_id:
        return match_id.group(1)
    return clean.split("?")[0].strip()


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def generate_service_account_jwt(service_account_info: dict, scope: str = DRIVE_READONLY_SCOPE) -> str:
    """Genera y firma un JWT con RS256 para autenticación con Service Account de Google."""
    client_email = service_account_info.get("client_email")
    private_key_pem = service_account_info.get("private_key")
    token_uri = service_account_info.get("token_uri") or DEFAULT_TOKEN_URI

    if not client_email or not private_key_pem:
        raise ValueError("El JSON de la Service Account debe contener 'client_email' y 'private_key'.")

    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": client_email,
        "scope": scope,
        "aud": token_uri,
        "exp": now + 3600,
        "iat": now,
    }

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    signing_input = f"{_base64url_encode(header_bytes)}.{_base64url_encode(payload_bytes)}".encode("utf-8")

    private_key = load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())  # type: ignore[arg-type]

    return f"{signing_input.decode('utf-8')}.{_base64url_encode(signature)}"


async def get_drive_access_token(service_account_info: dict) -> str:
    """Obtiene un token de acceso OAuth2 válido utilizando la Service Account."""
    token_uri = service_account_info.get("token_uri") or DEFAULT_TOKEN_URI
    signed_jwt = generate_service_account_jwt(service_account_info)

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed_jwt,
            },
        )
        if response.status_code != 200:
            log.error("Error obteniendo token de Google Drive: %s", response.text)
            raise ValueError(f"Google OAuth error ({response.status_code}): {response.text}")
        payload = response.json()
        return str(payload.get("access_token") or "")


async def list_folder_files(access_token: str, folder_id: str) -> list[dict[str, Any]]:
    """Lista todos los archivos activos dentro de una carpeta de Google Drive."""
    headers = {"Authorization": f"Bearer {access_token}"}
    query = f"'{folder_id}' in parents and trashed = false"
    url = f"{DRIVE_API_BASE}/files"
    params = {
        "q": query,
        "fields": "files(id, name, mimeType, modifiedTime, size)",
        "pageSize": 100,
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }

    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(url, headers=headers, params=params)
        if response.status_code != 200:
            log.error("Error listando archivos de Drive: %s", response.text)
            raise ValueError(f"Error listando carpeta de Drive ({response.status_code}): {response.text}")
        data = response.json()
        return data.get("files", [])


async def download_file_content(access_token: str, file_info: dict) -> str:
    """Descarga o exporta un archivo de Google Drive y extrae su texto limpio."""
    file_id = file_info["id"]
    name = file_info.get("name", "Documento")
    mime_type = file_info.get("mimeType", "")
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=45) as client:
        # Caso 1: Google Docs -> exportar a texto plano
        if mime_type == "application/vnd.google-apps.document":
            export_url = f"{DRIVE_API_BASE}/files/{file_id}/export"
            res = await client.get(export_url, headers=headers, params={"mimeType": "text/plain"})
            res.raise_for_status()
            return res.text.strip()

        # Caso 2: Google Sheets -> exportar a CSV
        elif mime_type == "application/vnd.google-apps.spreadsheet":
            export_url = f"{DRIVE_API_BASE}/files/{file_id}/export"
            res = await client.get(export_url, headers=headers, params={"mimeType": "text/csv"})
            res.raise_for_status()
            return file_parser.parse_file(res.content, f"{name}.csv")

        # Caso 3: Archivos binarios soportados (PDF, Word, Excel, CSV, TXT)
        else:
            download_url = f"{DRIVE_API_BASE}/files/{file_id}"
            res = await client.get(download_url, headers=headers, params={"alt": "media"})
            res.raise_for_status()
            return file_parser.parse_file(res.content, name)


async def sync_google_drive_to_bot_knowledge(
    bot_id: int,
    folder_id_or_url: str,
    service_account_data: dict | str,
) -> dict[str, Any]:
    """
    Sincroniza todos los documentos de una carpeta de Google Drive con la Base de Conocimiento (bot_knowledge).
    """
    folder_id = extract_folder_id(folder_id_or_url)
    if not folder_id:
        raise ValueError("Se requiere un Folder ID o URL válida de Google Drive.")

    if isinstance(service_account_data, str):
        try:
            sa_info = json.loads(service_account_data.strip())
        except Exception as exc:
            raise ValueError(f"El formato del Service Account JSON es inválido: {exc}")
    else:
        sa_info = service_account_data

    access_token = await get_drive_access_token(sa_info)
    files = await list_folder_files(access_token, folder_id)

    synced_files = []
    skipped_files = []
    total_synced = 0

    prefix = "[Google Drive]"

    async with db._pool.acquire() as conn:
        async with conn.transaction():
            # Obtener documentos de Drive previos en la BD para este bot
            rows = await conn.fetch(
                """
                SELECT id, title
                FROM bot_knowledge
                WHERE bot_id = $1 AND title LIKE $2
                """,
                bot_id,
                f"{prefix} %",
            )
            existing_by_title = {row["title"]: int(row["id"]) for row in rows}
            active_new_titles = set()

            for f in files:
                fname = f.get("name", "Documento").strip()
                mime = f.get("mimeType", "")
                
                # Ignorar carpetas hijas y accesos directos
                if mime in ("application/vnd.google-apps.folder", "application/vnd.google-apps.shortcut"):
                    continue

                try:
                    text_content = await download_file_content(access_token, f)
                    if not text_content or not text_content.strip():
                        skipped_files.append({"name": fname, "reason": "Contenido vacío"})
                        continue

                    doc_title = f"{prefix} {fname}"
                    active_new_titles.add(doc_title)

                    if doc_title in existing_by_title:
                        # Actualizar documento existente
                        knowledge_id = existing_by_title[doc_title]
                        await conn.execute(
                            """
                            UPDATE bot_knowledge
                            SET content = $1, status = 'active', updated_at = now()
                            WHERE id = $2 AND bot_id = $3
                            """,
                            text_content,
                            knowledge_id,
                            bot_id,
                        )
                    else:
                        # Insertar nuevo documento
                        k_row = await conn.fetchrow(
                            """
                            INSERT INTO bot_knowledge(bot_id, title, content, status)
                            VALUES($1, $2, $3, 'active')
                            RETURNING id
                            """,
                            bot_id,
                            doc_title,
                            text_content,
                        )
                        knowledge_id = int(k_row["id"])

                    # Indexar en RAG vectorial
                    await rag.index_document(conn, bot_id, knowledge_id, text_content)

                    synced_files.append({"id": f["id"], "name": fname, "size": len(text_content)})
                    total_synced += 1
                except Exception as exc:
                    log.warning("No se pudo procesar archivo de Drive %s: %s", fname, exc)
                    skipped_files.append({"name": fname, "error": str(exc)})

            # Archivar documentos de Drive que ya no están en la carpeta
            for old_title, old_id in existing_by_title.items():
                if old_title not in active_new_titles:
                    await conn.execute(
                        """
                        UPDATE bot_knowledge
                        SET status = 'archived', updated_at = now()
                        WHERE id = $1 AND bot_id = $2
                        """,
                        old_id,
                        bot_id,
                    )
                    await rag.delete_document_chunks(conn, bot_id, old_id)

    # Actualizar metadata en bot_integrations
    integration = await db.get_active_bot_integration(bot_id, "google_drive")
    if integration:
        config_data = integration.get("config") or {}
        config_data["last_synced_at"] = datetime.now(timezone.utc).isoformat()
        config_data["files_count"] = total_synced
        config_data["folder_id"] = folder_id
        config_data["client_email"] = sa_info.get("client_email", "")
        await db.update_bot_integration(
            bot_id=bot_id,
            integration_id=int(integration["id"]),
            integration_type="google_drive",
            name=integration.get("name", "Google Drive"),
            config_data=config_data,
            enabled=integration.get("enabled", True),
        )


    log.info(
        "Sincronización Google Drive para bot %s completada: %d archivos sincronizados, %d omitidos.",
        bot_id,
        total_synced,
        len(skipped_files),
    )

    return {
        "ok": True,
        "bot_id": bot_id,
        "folder_id": folder_id,
        "synced_count": total_synced,
        "synced_files": synced_files,
        "skipped_files": skipped_files,
    }
