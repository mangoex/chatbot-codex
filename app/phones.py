"""Identidad de un teléfono. Un solo lugar para el alias mexicano y los 10 dígitos."""
from __future__ import annotations

import re


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def canonical(value: str | None) -> str:
    """Identidad internacional. El único alias aceptado es 521 de 13 dígitos, que pasa a 52."""
    numero = digits(value)
    if len(numero) == 13 and numero.startswith("521"):
        return "52" + numero[3:]
    return numero


def last10(value: str | None) -> str:
    """Últimos 10 dígitos, para comparar sin prefijo 52, 521 o 1."""
    numero = digits(value)
    if len(numero) >= 10:
        return numero[-10:]
    return numero
