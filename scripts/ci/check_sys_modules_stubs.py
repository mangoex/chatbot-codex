#!/usr/bin/env python3
"""Impide que una prueba nueva sustituya librerías en sys.modules.

Las pruebas viejas de la lista ya lo hacen y el arnés las aísla en otro
proceso. Copiarlas rompe la suite según el orden de importación. El mensaje
dice qué hacer en su lugar.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
LISTA = Path(__file__).with_name("sys_modules_allowlist.txt")
MARCA = "sys.modules"


def _permitidos() -> set[str]:
    rutas = set()
    for linea in LISTA.read_text(encoding="utf-8").splitlines():
        limpia = linea.split("#", 1)[0].strip()
        if limpia:
            rutas.add(limpia)
    return rutas


def main() -> int:
    if not LISTA.is_file():
        print(f"Falta la lista de pruebas viejas: {LISTA}", file=sys.stderr)
        return 1
    permitidos = _permitidos()
    fallos = []
    for path in sorted((RAIZ / "tests").rglob("*.py")):
        relativo = path.relative_to(RAIZ).as_posix()
        if relativo in permitidos:
            continue
        for numero, linea in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if MARCA in linea:
                fallos.append(f"{relativo}:{numero}")
    if fallos:
        print(
            "No sustituyas módulos en sys.modules. Importa fastapi, asyncpg y httpx "
            "de verdad, o usa monkeypatch sobre el objeto de la app. "
            "Las pruebas viejas están en scripts/ci/sys_modules_allowlist.txt; un archivo nuevo no entra.",
            file=sys.stderr,
        )
        for fallo in fallos:
            print(fallo, file=sys.stderr)
        return 1
    print(f"sys.modules: ninguna prueba nueva. {len(permitidos)} archivos viejos siguen en la lista.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
