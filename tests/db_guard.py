"""La integración solo puede borrar la base desechable asistto_test en localhost."""
from __future__ import annotations

from urllib.parse import unquote, urlparse

MENSAJE = (
    "TEST_DATABASE_URL tiene que ser la base asistto_test en 127.0.0.1 o localhost. "
    "Usa postgresql://asistto:asistto_test_only@127.0.0.1:5432/asistto_test. "
    "No aceptes un nombre de base que solo aparezca en la query."
)


def destino_de_prueba(url: str) -> str:
    parsed = urlparse(url)
    nombre = unquote((parsed.path or "").lstrip("/"))
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError(MENSAJE)
    if nombre != "asistto_test" or host not in {"127.0.0.1", "localhost"}:
        raise ValueError(MENSAJE)
    return url
