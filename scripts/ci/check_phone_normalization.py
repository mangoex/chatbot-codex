#!/usr/bin/env python3
"""Un solo lugar para el alias 521 y los últimos 10 dígitos.

Falla si otro módulo vuelve a copiar el recorte o el colapso. El mensaje dice
qué función usar.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DUENO = RAIZ / "app" / "phones.py"
RECORTE = re.compile(r"\[\s*-10\s*:")
COLAPSO = re.compile(
    r"""(?:return|=)\s*["']52["']\s*\+\s*[A-Za-z_][A-Za-z0-9_]*\[3:\]"""
)


def main() -> int:
    if not DUENO.is_file():
        print(
            "Falta app/phones.py. La identidad del teléfono vive ahí: "
            "app.phones.canonical y app.phones.last10.",
            file=sys.stderr,
        )
        return 1
    fallos: list[str] = []
    for path in sorted((RAIZ / "app").rglob("*.py")):
        if path.resolve() == DUENO.resolve():
            continue
        texto = path.read_text(encoding="utf-8")
        relativo = path.relative_to(RAIZ).as_posix()
        for numero, linea in enumerate(texto.splitlines(), start=1):
            if RECORTE.search(linea):
                fallos.append(
                    f"{relativo}:{numero}: no recortes los últimos 10 dígitos a mano. "
                    "Usa app.phones.last10."
                )
            if COLAPSO.search(linea):
                fallos.append(
                    f"{relativo}:{numero}: no reescribas el alias 521 por tu cuenta. "
                    "Usa app.phones.canonical."
                )
    if fallos:
        print("La identidad telefónica tiene un solo dueño, app/phones.py.", file=sys.stderr)
        for fallo in fallos:
            print(fallo, file=sys.stderr)
        return 1
    print("Teléfonos: app.phones es el único recorte y el único alias 521.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
