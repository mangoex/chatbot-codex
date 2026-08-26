from __future__ import annotations

import re


PRIVATE_DIRECTORY_FILENAMES = {
    "colaboradores.csv",
    "empleados.csv",
    "directorio_colaboradores.csv",
}


def normalized_source_filename(title: str | None) -> str:
    """Return a normalized source filename, removing connector prefixes."""
    clean = (title or "").strip().lower().replace("\\", "/")
    clean = re.sub(r"^\[(?:google drive|drive)\]\s*", "", clean)
    return clean.rsplit("/", 1)[-1]


def is_private_directory_title(title: str | None) -> bool:
    """Classify bot-scoped employee directories that must never enter general RAG."""
    return normalized_source_filename(title) in PRIVATE_DIRECTORY_FILENAMES
