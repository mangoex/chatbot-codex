from __future__ import annotations
import json
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from app import google_drive_client, db


def generate_test_private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


class GoogleDriveClientUnitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.private_key_pem = generate_test_private_key_pem()
        self.service_account_dict = {
            "type": "service_account",
            "project_id": "test-project",
            "private_key": self.private_key_pem,
            "client_email": "asistto-drive@test-project.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }

    def test_extract_folder_id(self):
        self.assertEqual(
            google_drive_client.extract_folder_id("https://drive.google.com/drive/folders/1abcDEF-ghi123?usp=sharing"),
            "1abcDEF-ghi123",
        )
        self.assertEqual(
            google_drive_client.extract_folder_id("https://drive.google.com/drive/u/0/folders/1xyz789_ABC"),
            "1xyz789_ABC",
        )
        self.assertEqual(
            google_drive_client.extract_folder_id("https://drive.google.com/open?id=1folderId999"),
            "1folderId999",
        )
        self.assertEqual(
            google_drive_client.extract_folder_id("  1rawFolderId123  "),
            "1rawFolderId123",
        )
        self.assertEqual(google_drive_client.extract_folder_id(""), "")

    def test_generate_service_account_jwt(self):
        jwt_token = google_drive_client.generate_service_account_jwt(self.service_account_dict)
        parts = jwt_token.split(".")
        self.assertEqual(len(parts), 3)

    @patch("app.google_drive_client.httpx.AsyncClient")
    async def test_get_drive_access_token(self, mock_client_cls):
        mock_instance = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "ya29.fake_token_123", "expires_in": 3600}
        mock_instance.post.return_value = mock_resp

        token = await google_drive_client.get_drive_access_token(self.service_account_dict)
        self.assertEqual(token, "ya29.fake_token_123")

    @patch("app.google_drive_client.httpx.AsyncClient")
    async def test_list_folder_files(self, mock_client_cls):
        mock_instance = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "files": [
                {"id": "doc1", "name": "Politica_IA.docx", "mimeType": "application/vnd.google-apps.document"},
                {"id": "sheet1", "name": "Colaboradores.xlsx", "mimeType": "application/vnd.google-apps.spreadsheet"},
            ]
        }
        mock_instance.get.return_value = mock_resp

        files = await google_drive_client.list_folder_files("token", "folder_123")
        self.assertEqual(len(files), 2)
        self.assertEqual(files[0]["name"], "Politica_IA.docx")

    @patch("app.google_drive_client.httpx.AsyncClient")
    async def test_download_file_content_google_doc(self, mock_client_cls):
        mock_instance = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Texto exportado de Google Doc: Política Institucional."
        mock_resp.raise_for_status = MagicMock()
        mock_instance.get.return_value = mock_resp

        file_info = {"id": "doc1", "name": "Politica", "mimeType": "application/vnd.google-apps.document"}
        text = await google_drive_client.download_file_content("token", file_info)
        self.assertEqual(text, "Texto exportado de Google Doc: Política Institucional.")

    @patch("app.google_drive_client.httpx.AsyncClient")
    async def test_download_file_content_google_sheet(self, mock_client_cls):
        mock_instance = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_instance
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"Nombre,Telefono,Puesto\nMiguel Gonzalez,6671020672,Direccion\n"
        mock_resp.raise_for_status = MagicMock()
        mock_instance.get.return_value = mock_resp

        file_info = {"id": "sheet1", "name": "Colaboradores", "mimeType": "application/vnd.google-apps.spreadsheet"}
        text = await google_drive_client.download_file_content("token", file_info)
        self.assertIn("Miguel Gonzalez", text)
        self.assertIn("6671020672", text)


    @patch("app.rag.index_document", new_callable=AsyncMock)

    @patch("app.rag.delete_document_chunks", new_callable=AsyncMock)
    @patch("app.google_drive_client.download_file_content", new_callable=AsyncMock)
    @patch("app.google_drive_client.list_folder_files", new_callable=AsyncMock)
    @patch("app.google_drive_client.get_drive_access_token", new_callable=AsyncMock)
    async def test_sync_google_drive_to_bot_knowledge(
        self,
        mock_get_token,
        mock_list_files,
        mock_download,
        mock_delete_chunks,
        mock_index_doc,
    ):
        mock_get_token.return_value = "token_abc"
        mock_list_files.return_value = [
            {"id": "doc_1", "name": "Manual_Operaciones.docx", "mimeType": "application/vnd.google-apps.document"}
        ]
        mock_download.return_value = "Contenido del manual de operaciones 2026."

        mock_conn = AsyncMock()
        # Existing documents in DB: empty
        mock_conn.fetch.return_value = []
        mock_conn.fetchrow.return_value = {"id": 101}
        mock_conn.transaction = MagicMock()
        mock_conn.transaction.return_value.__aenter__ = AsyncMock()
        mock_conn.transaction.return_value.__aexit__ = AsyncMock()


        class MockPool:
            def acquire(self):
                class Ctx:
                    async def __aenter__(self):
                        return mock_conn
                    async def __aexit__(self, exc_type, exc_val, exc_tb):
                        pass
                return Ctx()

        with patch.object(db, "_pool", MockPool()):
            with patch("app.db.get_active_bot_integration", new_callable=AsyncMock) as mock_get_integ:
                with patch("app.db.update_bot_integration", new_callable=AsyncMock) as mock_upd_integ:
                    mock_get_integ.return_value = {"id": 5, "name": "Google Drive", "enabled": True, "config": {}}
                    result = await google_drive_client.sync_google_drive_to_bot_knowledge(
                        bot_id=170,
                        folder_id_or_url="https://drive.google.com/drive/folders/1myFolderId",
                        service_account_data=self.service_account_dict,
                    )

                    self.assertTrue(result["ok"])
                    self.assertEqual(result["synced_count"], 1)
                    self.assertEqual(result["synced_files"][0]["name"], "Manual_Operaciones.docx")
                    mock_index_doc.assert_awaited_once()
                    mock_upd_integ.assert_awaited_once()



if __name__ == "__main__":
    unittest.main()
