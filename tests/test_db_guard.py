"""El guardia de la base de prueba rechaza el caso del review de PR #18."""
import pytest

from tests.db_guard import destino_de_prueba

URL_BUENA = "postgresql://asistto:asistto_test_only@127.0.0.1:5432/asistto_test"
URL_DEL_REVIEW = "postgresql://asistto:clave-ficticia@prod.example/clientdb?application_name=asistto_test"


def test_la_base_local_de_prueba_pasa():
    assert destino_de_prueba(URL_BUENA) == URL_BUENA
    assert (
        destino_de_prueba("postgresql://asistto:asistto_test_only@localhost:5432/asistto_test")
        == "postgresql://asistto:asistto_test_only@localhost:5432/asistto_test"
    )


def test_un_nombre_de_base_de_cliente_en_la_query_no_pasa():
    with pytest.raises(ValueError, match="asistto_test"):
        destino_de_prueba(URL_DEL_REVIEW)


def test_el_mismo_nombre_en_otro_host_no_pasa():
    with pytest.raises(ValueError):
        destino_de_prueba("postgresql://asistto:asistto_test_only@db.cliente.ejemplo:5432/asistto_test")


def test_un_reenvio_local_hacia_otra_instancia_no_pasa():
    with pytest.raises(ValueError):
        destino_de_prueba("postgresql://cliente:clave-ficticia@127.0.0.1:5432/asistto_test")
    with pytest.raises(ValueError):
        destino_de_prueba("postgresql://asistto:asistto_test_only@127.0.0.1:5433/asistto_test")
