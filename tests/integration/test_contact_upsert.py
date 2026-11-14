"""El directorio de un bot no duplica el mismo WhatsApp. Semilla ficticia."""
from __future__ import annotations

import pytest

from app import db

pytestmark = pytest.mark.integration


async def test_el_mismo_wa_id_no_crea_otro_contacto(base_ficticia):
    bot_id = base_ficticia["taqueria"]
    await db.upsert_contact(bot_id, "5215550100202", name="Ana Primera")
    await db.upsert_contact(bot_id, "+52 1 555 010 0202", name="Ana Actualizada")

    filas = await db.list_contacts(bot_id, search="5215550100202")

    assert len(filas) == 1
    assert filas[0]["wa_id"] == "5215550100202"
    assert filas[0]["name"] == "Ana Actualizada"
