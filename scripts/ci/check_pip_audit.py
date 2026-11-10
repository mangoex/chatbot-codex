#!/usr/bin/env python3
"""Falla solo si pip-audit encuentra una vulnerabilidad que no esté en la línea base."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
LINEA_BASE = RAIZ / "docs" / "seguridad" / "pip-audit-baseline.json"


def _identidades(vuln: dict) -> set[str]:
    ids = {vuln.get("id")} | set(vuln.get("aliases") or [])
    return {ident for ident in ids if ident}


def _hallazgos(documento: dict) -> list[tuple[str, set[str]]]:
    encontrados = []
    for dependencia in documento.get("dependencies") or []:
        paquete = dependencia.get("name") or ""
        for vuln in dependencia.get("vulns") or []:
            ids = _identidades(vuln)
            if paquete and ids:
                encontrados.append((paquete, ids))
    return encontrados


def main() -> int:
    if not LINEA_BASE.is_file():
        print(f"Falta la línea base: {LINEA_BASE}", file=sys.stderr)
        return 1
    permitidos = set()
    crudo = json.loads(LINEA_BASE.read_text(encoding="utf-8"))
    for paquete, ids in (crudo.get("packages") or {}).items():
        for ident in ids:
            permitidos.add((paquete, ident))

    proceso = subprocess.run(
        [
            "pip-audit",
            "-r",
            str(RAIZ / "requirements.txt"),
            "--format",
            "json",
            "--progress-spinner",
            "off",
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    salida = proceso.stdout.strip()
    if not salida:
        print(proceso.stderr, file=sys.stderr)
        print("pip-audit no devolvió JSON", file=sys.stderr)
        return 1
    try:
        documento = json.loads(salida)
    except json.JSONDecodeError:
        print(salida, file=sys.stderr)
        print(proceso.stderr, file=sys.stderr)
        return 1

    nuevos = []
    for paquete, ids in _hallazgos(documento):
        if not any((paquete, ident) in permitidos for ident in ids):
            nuevos.append((paquete, sorted(ids)[0]))
    if nuevos:
        print("Vulnerabilidades nuevas, fuera de la línea base:", file=sys.stderr)
        for paquete, ident in nuevos:
            print(f"  {paquete} {ident}", file=sys.stderr)
        return 1
    print(f"pip-audit: {len(_hallazgos(documento))} hallazgos conocidos, ninguno nuevo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
