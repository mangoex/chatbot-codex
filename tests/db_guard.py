"""La integración solo borra la instancia desechable publicada en el compose y en CI."""
from __future__ import annotations

from urllib.parse import unquote, urlparse

MENSAJE = (
    "TEST_DATABASE_URL tiene que ser la instancia desechable "
    "postgresql://asistto:asistto_test_only@127.0.0.1:5432/asistto_test "
    "(localhost también vale). Usuario, clave, puerto 5432 y nombre de base "
    "tienen que coincidir. Un reenvío a otra instancia, aunque la base se llame "
    "asistto_test, no pasa."
)


def destino_de_prueba(url: str) -> str:
    parsed = urlparse(url)
    nombre = unquote((parsed.path or "").lstrip("/"))
    host = (parsed.hostname or "").lower()
    usuario = unquote(parsed.username or "")
    clave = unquote(parsed.password or "")
    puerto = parsed.port or 5432
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or usuario != "asistto"
        or clave != "asistto_test_only"
        or nombre != "asistto_test"
        or host not in {"127.0.0.1", "localhost"}
        or puerto != 5432
    ):
        raise ValueError(MENSAJE)
    return url
