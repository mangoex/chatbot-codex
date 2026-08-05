from __future__ import annotations
"""Deterministic order totals and receipt-field validation, scoped per bot."""

import asyncio
import json
import logging
import re
import subprocess
import tempfile
import threading
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from app import db, whatsapp_client

log = logging.getLogger("order-payments")

_MARKER_RE = re.compile(
    r"\[\[(MARONA_QUOTE|MARONA_PAYMENT):\s*(\{.*?\})\s*\]\]",
    re.DOTALL,
)
_CONFIG_RE = re.compile(
    r"<order_payments_config>\s*(\{.*?\})\s*</order_payments_config>",
    re.DOTALL,
)
_ALLOWED_DAYS = {"sabado", "domingo"}
_OCR_CONCURRENCY = 2
_OCR_TIMEOUT_SECONDS = 15
_OCR_SEMAPHORE = threading.BoundedSemaphore(_OCR_CONCURRENCY)
_MAX_RECEIPT_BYTES = 10 * 1024 * 1024


class OrderPaymentError(ValueError):
    """A safe, deterministic order/payment validation failure."""


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower().strip()


def _day(value: Any) -> str:
    day = _plain(value)
    if day not in _ALLOWED_DAYS:
        raise OrderPaymentError("invalid_day")
    return day


def _amount_minor(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    cleaned = str(value).strip().replace("$", "").replace("MXN", "").strip()
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        pieces = cleaned.split(",")
        cleaned = cleaned.replace(",", ".") if len(pieces[-1]) == 2 else cleaned.replace(",", "")
    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
    if amount < 0:
        return None
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_money(amount_minor: int, currency: str = "MXN") -> str:
    if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
        raise OrderPaymentError("invalid_amount")
    whole, cents = divmod(amount_minor, 100)
    suffix = f".{cents:02d}" if cents else ""
    return f"${whole:,}{suffix} {currency}"


def calculate_quote(day: Any, items: Any, config_data: dict[str, Any]) -> dict[str, Any]:
    normalized_day = _day(day)
    catalog = config_data.get("catalog")
    currency = str(config_data.get("currency") or "MXN").upper()
    if currency != "MXN" or not isinstance(catalog, dict) or not catalog:
        raise OrderPaymentError("invalid_catalog")
    if not isinstance(items, list) or not items:
        raise OrderPaymentError("empty_items")

    quote_items: list[dict[str, Any]] = []
    total_minor = 0
    for raw_item in items:
        if not isinstance(raw_item, dict):
            raise OrderPaymentError("invalid_item")
        product_id = str(raw_item.get("product_id") or "").strip()
        product = catalog.get(product_id)
        if not isinstance(product, dict):
            raise OrderPaymentError("unknown_product")
        quantity = raw_item.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise OrderPaymentError("invalid_quantity")
        unit_price_minor = product.get("unit_price_minor")
        if (
            isinstance(unit_price_minor, bool)
            or not isinstance(unit_price_minor, int)
            or unit_price_minor <= 0
        ):
            raise OrderPaymentError("invalid_unit_price")
        subtotal_minor = unit_price_minor * quantity
        total_minor += subtotal_minor
        quote_items.append(
            {
                "product_id": product_id,
                "name": str(product.get("name") or product_id),
                "presentation": str(product.get("presentation") or "").strip(),
                "quantity": quantity,
                "unit_price_minor": unit_price_minor,
                "subtotal_minor": subtotal_minor,
            }
        )

    return {
        "day": normalized_day,
        "currency": currency,
        "items": quote_items,
        "total_minor": total_minor,
    }


def validate_receipt_fields(
    expected: dict[str, Any],
    extracted: dict[str, Any],
    *,
    today: date,
) -> dict[str, Any]:
    if not extracted.get("readable"):
        return {"status": "insufficient_evidence"}

    observed_minor = _amount_minor(extracted.get("amount"))
    reference = _plain(extracted.get("reference"))
    transfer_date_raw = str(extracted.get("transfer_date") or "").strip()
    observed_currency = str(extracted.get("currency") or "").upper().strip()
    if observed_minor is None or not reference or not transfer_date_raw or not observed_currency:
        return {"status": "insufficient_evidence"}

    try:
        transfer_date = date.fromisoformat(transfer_date_raw)
    except ValueError:
        return {"status": "invalid_transfer_date"}
    if transfer_date > today:
        return {"status": "invalid_transfer_date"}

    expected_currency = str(expected.get("currency") or "MXN").upper()
    if observed_currency != expected_currency or observed_minor != expected.get("amount_minor"):
        return {
            "status": "amount_mismatch",
            "observed_amount_minor": observed_minor,
        }

    expected_day = _day(expected.get("day"))
    opposite_day = "domingo" if expected_day == "sabado" else "sabado"
    expected_reference = f"marona {expected_day}"
    if f"marona {opposite_day}" in reference:
        return {"status": "day_mismatch"}
    if expected_reference not in reference:
        return {"status": "insufficient_evidence"}

    return {
        "status": "matching_fields",
        "observed_amount_minor": observed_minor,
        "transfer_date": transfer_date.isoformat(),
    }


def receipt_fields_from_ocr_text(text: str) -> dict[str, Any]:
    """Extract conservative candidates from local OCR text; no network calls."""
    source = text or ""
    plain = _plain(source)
    amount_match = re.search(
        r"(?:importe|monto|total|cantidad)\s*(?:pagad[oa])?\s*[:\-]?\s*\$?\s*([0-9][0-9.,]*)",
        plain,
    )
    amount = amount_match.group(1) if amount_match else None

    transfer_date = None
    date_match = re.search(r"\b(20\d{2})[-/]([01]?\d)[-/]([0-3]?\d)\b", plain)
    if date_match:
        transfer_date = f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
    else:
        date_match = re.search(r"\b([0-3]?\d)[-/]([01]?\d)[-/](20\d{2})\b", plain)
        if date_match:
            transfer_date = f"{int(date_match.group(3)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(1)):02d}"

    reference = None
    reference_match = re.search(r"\bmarona\s+(sabado|domingo)\b", plain)
    if reference_match:
        reference = f"MARONA {reference_match.group(1).upper()}"

    currency = "MXN" if any(token in plain for token in ("mxn", "peso", "$")) else None
    return {
        "amount": amount,
        "currency": currency,
        "transfer_date": transfer_date,
        "reference": reference,
        "readable": len(source.strip()) >= 20,
    }


def extract_receipt_fields_local(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """Run Tesseract locally so bank-receipt pixels are not sent to a third party."""
    suffix_by_mime = {"image/jpeg": ".jpg", "image/png": ".png"}
    suffix = suffix_by_mime.get(mime_type)
    if not suffix:
        raise ValueError("unsupported_receipt_mime")
    with tempfile.NamedTemporaryFile(suffix=suffix) as image_file:
        image_file.write(image_bytes)
        image_file.flush()
        completed = subprocess.run(
            ["tesseract", image_file.name, "stdout", "-l", "spa+eng"],
            check=True,
            capture_output=True,
            text=True,
            timeout=_OCR_TIMEOUT_SECONDS,
        )
    return receipt_fields_from_ocr_text(completed.stdout)


async def extract_receipt_fields_without_blocking(
    image_bytes: bytes,
    mime_type: str,
) -> dict[str, Any]:
    """Bound local OCR processes while leaving the asyncio event loop available."""
    def _bounded_ocr() -> dict[str, Any]:
        # This lock lives inside the worker thread, so it is safe across the
        # application event loop and independent unittest event loops.
        with _OCR_SEMAPHORE:
            return extract_receipt_fields_local(image_bytes, mime_type)

    return await asyncio.to_thread(_bounded_ocr)


def _config_from_prompt(content: str) -> dict[str, Any] | None:
    match = _CONFIG_RE.search(content or "")
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        log.warning("Configuracion order_payments invalida en prompt activo")
        return None
    if not isinstance(parsed, dict) or parsed.get("enabled") is not True:
        return None
    return parsed


def enabled_config_from_prompt(prompt: str) -> dict[str, Any] | None:
    """Return an explicit per-bot configuration embedded in its active prompt."""
    # bot_content appends knowledge after this delimiter.  A knowledge document
    # must never grant a payment capability to its bot.
    active_prompt = (prompt or "").split("\n\n--- knowledge_base ---", 1)[0]
    return _config_from_prompt(active_prompt)


async def _enabled_config(bot_id: int | None) -> dict[str, Any] | None:
    """Resolve opt-in state only on paths which intentionally process payments."""
    if not bot_id:
        return None
    try:
        prompt = await db.get_active_bot_prompt(bot_id)
    except Exception:
        log.exception("No se pudo resolver order_payments para bot_id=%s", bot_id)
        return None
    return enabled_config_from_prompt(str((prompt or {}).get("content") or ""))


def _clean_reply(reply: str) -> str:
    without_wrapper = re.sub(r"</?respuesta>", "", reply or "", flags=re.IGNORECASE)
    return "\n".join(line.rstrip() for line in without_wrapper.splitlines() if line.strip()).strip()


def _render_quote(quote: dict[str, Any], payload: dict[str, Any]) -> str:
    day_label = "sábado" if quote["day"] == "sabado" else "domingo"
    lines = [f"Así queda tu solicitud para el {day_label}:"]
    for item in quote["items"]:
        presentation = f", {item['presentation']}" if item["presentation"] else ""
        unit_price = format_money(item["unit_price_minor"], quote["currency"])
        subtotal = format_money(item["subtotal_minor"], quote["currency"])
        lines.append(
            f"• {item['quantity']} × {item['name']}{presentation} — "
            f"{unit_price} c/u — subtotal {subtotal}"
        )
    pickup_name = " ".join(str(payload.get("pickup_name") or "").split())[:120]
    pickup_time = " ".join(str(payload.get("pickup_time") or "").split())[:80]
    pickup_status = " ".join(str(payload.get("pickup_time_status") or "").split())[:120]
    if pickup_name:
        lines.append(f"A nombre de: {pickup_name}")
    if pickup_time:
        status = f" ({pickup_status})" if pickup_status else ""
        lines.append(f"Hora de recolección: {pickup_time}{status}")
    lines.append(f"Total: {format_money(quote['total_minor'], quote['currency'])}")
    lines.append("¿Confirmas que la preparemos así?")
    return "\n".join(lines)


def _bank_details(config_data: dict[str, Any]) -> dict[str, str]:
    bank = config_data.get("bank_transfer")
    if not isinstance(bank, dict):
        raise OrderPaymentError("missing_bank_transfer")
    values = {
        "clabe": str(bank.get("clabe") or "").strip(),
        "beneficiary": str(bank.get("beneficiary") or "").strip(),
        "bank": str(bank.get("bank") or "").strip(),
    }
    if not re.fullmatch(r"\d{18}", values["clabe"]) or not values["beneficiary"] or not values["bank"]:
        raise OrderPaymentError("invalid_bank_transfer")
    return values


def _receipt_download_policy(config_data: dict[str, Any]) -> tuple[tuple[str, ...], int]:
    allowed = config_data.get("allowed_receipt_mime_types")
    max_bytes = config_data.get("receipt_max_bytes")
    if (
        not isinstance(allowed, list)
        or not allowed
        or any(not isinstance(value, str) or not value.startswith("image/") for value in allowed)
        or isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or max_bytes <= 0
    ):
        raise OrderPaymentError("invalid_receipt_download_policy")
    return tuple(value.lower() for value in allowed), min(max_bytes, _MAX_RECEIPT_BYTES)


def _render_payment(quote: dict[str, Any], config_data: dict[str, Any]) -> str:
    bank = _bank_details(config_data)
    day_reference = "MARONA SABADO" if quote["day"] == "sabado" else "MARONA DOMINGO"
    return (
        f"El total es {format_money(quote['total_minor'], quote['currency'])}. "
        "Por lo pronto puedes pagar por transferencia:\n"
        f"CLABE: {bank['clabe']}\n"
        f"A nombre de: {bank['beneficiary']}\n"
        f"Banco: {bank['bank']}\n"
        f"Escribe {day_reference} en el concepto o referencia y envíanos una foto "
        "o imagen legible del comprobante."
    )


async def process_reply(wa_id: str, reply: str, bot_id: int | None) -> str:
    matches = list(_MARKER_RE.finditer(reply or ""))
    if not matches:
        return reply
    config_data = await _enabled_config(bot_id)
    if config_data is None:
        # Safe tenant isolation policy: a disabled tenant's generated output is untouched.
        return reply
    clean = _clean_reply(_MARKER_RE.sub("", reply or ""))
    if len(matches) != 1:
        return "No pude validar la cotización. El equipo de Marona te ayudará a revisarla."

    marker_type, raw_payload = matches[0].groups()
    try:
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            raise OrderPaymentError("invalid_payload")
        quote = calculate_quote(payload.get("day"), payload.get("items"), config_data)
        if bot_id is None:
            raise OrderPaymentError("missing_bot")
        if marker_type == "MARONA_QUOTE":
            await db.create_order_payment_quote(
                bot_id=bot_id,
                wa_id=wa_id,
                day=quote["day"],
                amount_minor=quote["total_minor"],
                currency=quote["currency"],
                quote=quote,
            )
            return _render_quote(quote, payload)

        # Validate config before the database transition, but never expose bank
        # details until the exact canonical quote has been atomically promoted.
        _bank_details(config_data)
        promotion, _stored = await db.promote_order_payment_quote(
            bot_id=bot_id,
            wa_id=wa_id,
            quote=quote,
        )
        if promotion in {"missing_confirmation", "quote_mismatch", "not_confirmable"}:
            return "La confirmación no coincide con el último resumen. Vuelve a revisar y confirmar ese resumen antes de pagar."
        if promotion not in {"promoted", "already_promoted"}:
            log.warning("Transicion de pago inesperada para bot_id=%s", bot_id)
            return "No pude preparar el pago de forma segura. Intenta de nuevo más tarde."
        payment = _render_payment(quote, config_data)
        return "\n\n".join(part for part in (clean, payment) if part)
    except (json.JSONDecodeError, OrderPaymentError):
        log.warning("Marcador de pedido rechazado para bot_id=%s", bot_id)
        return (
            "No pude validar el total de forma segura. Conservamos tu selección y "
            "el equipo de Marona te ayudará a revisarla."
        )
    except Exception as exc:
        log.warning("Fallo de persistencia order_payments para bot_id=%s tipo=%s", bot_id, type(exc).__name__)
        if marker_type == "MARONA_QUOTE":
            return "No pude guardar el resumen de forma segura. Intenta de nuevo más tarde."
        return "No pude preparar el pago de forma segura. Intenta de nuevo más tarde."


def _receipt_reply(result: dict[str, Any], expected: dict[str, Any]) -> str:
    status = result["status"]
    expected_amount = format_money(int(expected["amount_minor"]), str(expected.get("currency") or "MXN"))
    expected_day = "sábado" if expected["day"] == "sabado" else "domingo"
    if status == "matching_fields":
        return (
            "Gracias. El comprobante coincide con el importe y el día de tu pedido. "
            "El equipo de Marona verificará la acreditación de la transferencia."
        )
    if status == "amount_mismatch":
        return (
            f"El importe de la imagen no coincide con el total esperado de {expected_amount}. "
            "¿Puedes revisarlo y enviarnos el comprobante correcto?"
        )
    if status == "day_mismatch":
        return (
            f"La referencia de la imagen no coincide con tu pedido del {expected_day}. "
            "¿Puedes enviarnos el comprobante correcto?"
        )
    if status == "invalid_transfer_date":
        return "No pude validar la fecha de operación. Envíanos una imagen donde se vea una fecha válida."
    return (
        "No alcanzo a validar importe, fecha y referencia. Envíanos otra foto completa, "
        "derecha, nítida y sin recortes, o pide apoyo al equipo de Marona."
    )


async def handle_incoming_media(
    *,
    bot_id: int,
    wa_id: str,
    media_type: str,
    media_id: str | None,
    media_mime: str | None,
    access_token: str,
) -> str | None:
    config_data = await _enabled_config(bot_id)
    if config_data is None:
        return None
    try:
        allowed, max_bytes = _receipt_download_policy(config_data)
    except OrderPaymentError:
        log.warning("Politica de comprobantes invalida para bot_id=%s", bot_id)
        return "No pude procesar el comprobante de forma segura. Pide apoyo al equipo del negocio."
    if media_type != "image" or not media_id:
        return "Para validar tu comprobante, envíanos una imagen JPG o PNG legible."

    if media_mime and media_mime.lower() not in allowed:
        return "Ese formato no es compatible. Envíanos el comprobante como imagen JPG o PNG."
    try:
        expected = await db.get_active_order_payment_expectation(bot_id, wa_id)
    except Exception as exc:
        log.warning("Fallo al consultar comprobante para bot_id=%s tipo=%s", bot_id, type(exc).__name__)
        return "No pude consultar el pago pendiente de forma segura. Intenta de nuevo más tarde."
    if not expected:
        return (
            "Recibimos la imagen, pero no encontramos un pago pendiente en esta conversación. "
            "Indícanos para qué pedido es o pide apoyo al equipo de Marona."
        )

    try:
        image_bytes, detected_mime = await whatsapp_client.download_media(
            media_id,
            access_token=access_token,
            max_bytes=max_bytes,
            allowed_mime_types=allowed,
        )
        if detected_mime.lower() not in allowed:
            return "Ese formato no es compatible. Envíanos el comprobante como imagen JPG o PNG."
        extracted = await extract_receipt_fields_without_blocking(image_bytes, detected_mime)
        timezone = str(config_data.get("timezone") or "America/Mazatlan")
        current_day = datetime.now(ZoneInfo(timezone)).date()
        result = validate_receipt_fields(expected, extracted, today=current_day)
    except Exception as exc:
        log.warning("Fallo al leer comprobante para bot_id=%s tipo=%s", bot_id, type(exc).__name__)
        result = {"status": "insufficient_evidence"}

    try:
        await db.record_order_receipt_validation(
            expectation_id=int(expected["id"]),
            status=result["status"],
            details={
                key: value
                for key, value in result.items()
                if key in {"status", "observed_amount_minor", "transfer_date"}
            },
        )
    except Exception as exc:
        log.warning("Fallo al registrar comprobante para bot_id=%s tipo=%s", bot_id, type(exc).__name__)
        return "No pude registrar la validación de forma segura. Intenta de nuevo más tarde."
    return _receipt_reply(result, expected)


def system_instructions_from_prompt(prompt: str) -> str:
    """Build instructions from the prompt already fetched for this exact bot."""
    if enabled_config_from_prompt(prompt) is None:
        return ""
    return (
        "Capacidad order_payments activa para este bot. Para cotizar usa exactamente un "
        "marcador MARONA_QUOTE con day, items, pickup_name, pickup_time y pickup_time_status. "
        "Después de un sí explícito usa MARONA_PAYMENT con el mismo day e items. "
        "Nunca calcules importes en lenguaje natural ni muestres los marcadores al cliente."
    )
