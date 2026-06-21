from __future__ import annotations
"""Deterministic replies for core Asistto explanations.

These answers are intentionally handled before the model. They are product
truths that should stay stable even when model/provider behavior changes.
"""
import re
import unicodedata

_HOW_RE = re.compile(
    r"\b(c[oó]mo funciona|como funciona|qu[eé] es|que es|expl[ií]came|explicame)\b",
    re.IGNORECASE,
)
_UNCLEAR_RE = re.compile(
    r"\b(no entiendo|no entend[ií]|c[oó]mo\??|como\??|me explicas mejor|mas claro|más claro)\b",
    re.IGNORECASE,
)
_SERVICES_RE = re.compile(
    r"\b(servicios?|qu[eé]\s+(?:ofrecen|hacen|incluye)|cu[aá]les\s+son\s+(?:sus|los)\s+servicios|"
    r"que\s+(?:ofrecen|hacen|incluye)|planes?|paquetes?)\b",
    re.IGNORECASE,
)
_ATTENTION_APPOINTMENTS_RE = re.compile(
    r"\b(?:atenci[oó]n|clientes?|soporte|dudas|mensajes)\b.{0,50}\b(?:citas?|agenda|calendario)\b"
    r"|\b(?:citas?|agenda|calendario)\b.{0,50}\b(?:atenci[oó]n|clientes?|soporte|dudas|mensajes)\b",
    re.IGNORECASE | re.DOTALL,
)
_VET_RE = re.compile(r"\b(veterinaria|veterinario|mascota|mascotas|perro|gato)\b", re.IGNORECASE)
_DENTAL_RE = re.compile(r"\b(dental|dentista|odontolog|cl[ií]nica dental)\b", re.IGNORECASE)
_BEAUTY_RE = re.compile(r"\b(est[eé]tica|belleza|spa|cosmetolog|medicina est[eé]tica)\b", re.IGNORECASE)


def _norm(text: str) -> str:
    normalized = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _recent_text(user_text: str, history: list[dict], limit: int = 8) -> str:
    parts = [item.get("content", "") for item in history[-limit:]]
    parts.append(user_text)
    return "\n".join(parts)


def _example_for_context(text: str) -> str:
    if _VET_RE.search(text):
        return (
            "En una clínica veterinaria puede responder dudas sobre servicios, "
            "vacunas, estética, horarios y urgencias; pedir datos del dueño y "
            "la mascota; y ayudar a agendar citas."
        )
    if _DENTAL_RE.search(text):
        return (
            "En una clínica dental puede responder dudas sobre tratamientos, "
            "precios orientativos, horarios y disponibilidad; pedir datos del "
            "paciente; y ayudar a agendar valoración."
        )
    if _BEAUTY_RE.search(text):
        return (
            "En estética puede explicar servicios, horarios, cuidados previos, "
            "precios si ya están definidos y ayudar a agendar valoraciones."
        )
    return (
        "Por ejemplo, puede responder preguntas frecuentes, pedir datos del "
        "prospecto, detectar intención de compra y ayudar a agendar una llamada."
    )


def maybe_handle(user_text: str, history: list[dict]) -> str | None:
    text = user_text or ""
    joined = _recent_text(text, history)
    normalized = _norm(text.strip())

    wants_explanation = bool(_HOW_RE.search(text))
    wants_services = bool(_SERVICES_RE.search(text))
    wants_attention_and_appointments = bool(_ATTENTION_APPOINTMENTS_RE.search(text))
    asks_for_clarity = bool(_UNCLEAR_RE.search(text)) and any(
        _HOW_RE.search(item.get("content", "")) or "asistto" in _norm(item.get("content", ""))
        for item in history[-6:]
    )

    if wants_services:
        return (
            "Asistto puede ayudarte con estos servicios principales:\n"
            "- Atender mensajes de WhatsApp con IA.\n"
            "- Responder dudas frecuentes sobre tu negocio.\n"
            "- Capturar datos de prospectos.\n"
            "- Calificar leads y detectar oportunidades.\n"
            "- Agendar citas cuando el calendario está conectado.\n"
            "- Escalar a una persona cuando el caso lo necesita.\n"
            "¿Quieres enfocarlo en atención, citas o ambos?"
        )

    if wants_attention_and_appointments:
        return (
            "Perfecto. Para atención y citas, Asistto puede responder dudas frecuentes, "
            "pedir datos del cliente y crear citas en tu calendario cuando la integración está activa.\n"
            "Normalmente esto encaja mejor con el paquete PRO.\n"
            "¿Quieres que te muestre cómo sería una prueba o prefieres agendar una llamada?"
        )

    if not wants_explanation and not asks_for_clarity:
        return None

    example = _example_for_context(joined)
    if normalized in {"como", "como?", "cómo", "cómo?"} or asks_for_clarity:
        return (
            "Claro. Funciona así: conectamos el WhatsApp de tu negocio a un asistente de IA entrenado con tu información.\n"
            "El asistente responde dudas, pide datos importantes y, si tienes agenda activa, puede ayudar a crear citas.\n"
            f"{example}\n"
            "¿Qué parte quieres ver primero: respuestas, captura de datos o agenda?"
        )

    return (
        "Asistto conecta el WhatsApp de tu negocio con un asistente de IA entrenado con tu información.\n"
        "El asistente responde dudas, captura prospectos, califica oportunidades y puede agendar citas cuando la integración está activa.\n"
        f"{example}\n"
        "¿Qué tipo de negocio quieres automatizar?"
    )
