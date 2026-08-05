from __future__ import annotations

import unittest
import asyncio
import subprocess
import threading
import time
from datetime import date
from unittest.mock import AsyncMock, patch

from app import order_payments
from app import openai_client


CONFIG = {
    "currency": "MXN",
    "timezone": "America/Mazatlan",
    "catalog": {
        "ensalada_encurtidos": {
            "name": "Ensalada de encurtidos",
            "presentation": "Ración de 200 g",
            "unit_price_minor": 50000,
        },
        "croquetas_jamon": {
            "name": "Croquetas de jamón serrano",
            "presentation": "Ración de 6 piezas",
            "unit_price_minor": 50000,
        },
    },
    "bank_transfer": {
        "clabe": "123451234512345678",
        "beneficiary": "Sandra Herrera",
        "bank": "Inverlat",
    },
    "allowed_receipt_mime_types": ["image/jpeg", "image/png"],
    "receipt_max_bytes": 1024,
}


class QuoteTests(unittest.TestCase):
    def test_calculates_multiple_units_in_minor_currency(self) -> None:
        quote = order_payments.calculate_quote(
            "sabado",
            [{"product_id": "croquetas_jamon", "quantity": 3}],
            CONFIG,
        )

        self.assertEqual(quote["items"][0]["subtotal_minor"], 150000)
        self.assertEqual(quote["total_minor"], 150000)

    def test_sums_multiple_products(self) -> None:
        quote = order_payments.calculate_quote(
            "domingo",
            [
                {"product_id": "ensalada_encurtidos", "quantity": 2},
                {"product_id": "croquetas_jamon", "quantity": 3},
            ],
            CONFIG,
        )

        self.assertEqual(
            [item["subtotal_minor"] for item in quote["items"]],
            [100000, 150000],
        )
        self.assertEqual(quote["total_minor"], 250000)
        self.assertEqual(order_payments.format_money(250000, "MXN"), "$2,500 MXN")

    def test_rejects_non_positive_or_non_integer_quantity(self) -> None:
        for quantity in (0, -1, 1.5, "2", True):
            with self.subTest(quantity=quantity):
                with self.assertRaisesRegex(order_payments.OrderPaymentError, "invalid_quantity"):
                    order_payments.calculate_quote(
                        "sabado",
                        [{"product_id": "croquetas_jamon", "quantity": quantity}],
                        CONFIG,
                    )

    def test_rejects_unknown_product(self) -> None:
        with self.assertRaisesRegex(order_payments.OrderPaymentError, "unknown_product"):
            order_payments.calculate_quote(
                "sabado",
                [{"product_id": "inventado", "quantity": 1}],
                    CONFIG,
                )

    def test_rejects_zero_price_catalog_item(self) -> None:
        zero_price = {**CONFIG, "catalog": {"gratis": {"unit_price_minor": 0}}}
        with self.assertRaisesRegex(order_payments.OrderPaymentError, "invalid_unit_price"):
            order_payments.calculate_quote(
                "sabado", [{"product_id": "gratis", "quantity": 1}], zero_price,
            )


class ReceiptValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = {
            "day": "sabado",
            "amount_minor": 250000,
            "currency": "MXN",
        }
        self.extracted = {
            "amount": "2500.00",
            "currency": "MXN",
            "transfer_date": "2026-08-04",
            "reference": "Pago MARONA SABADO",
            "readable": True,
        }

    def test_matching_fields(self) -> None:
        result = order_payments.validate_receipt_fields(
            self.expected,
            self.extracted,
            today=date(2026, 8, 4),
        )
        self.assertEqual(result["status"], "matching_fields")

    def test_amount_mismatch(self) -> None:
        extracted = {**self.extracted, "amount": "2000.00"}
        result = order_payments.validate_receipt_fields(
            self.expected,
            extracted,
            today=date(2026, 8, 4),
        )
        self.assertEqual(result["status"], "amount_mismatch")
        self.assertEqual(result["observed_amount_minor"], 200000)

    def test_day_mismatch(self) -> None:
        extracted = {**self.extracted, "reference": "MARONA DOMINGO"}
        result = order_payments.validate_receipt_fields(
            self.expected,
            extracted,
            today=date(2026, 8, 4),
        )
        self.assertEqual(result["status"], "day_mismatch")

    def test_missing_day_is_insufficient_evidence(self) -> None:
        extracted = {**self.extracted, "reference": "Transferencia comida"}
        result = order_payments.validate_receipt_fields(
            self.expected,
            extracted,
            today=date(2026, 8, 4),
        )
        self.assertEqual(result["status"], "insufficient_evidence")

    def test_future_transfer_date_is_invalid(self) -> None:
        extracted = {**self.extracted, "transfer_date": "2026-08-05"}
        result = order_payments.validate_receipt_fields(
            self.expected,
            extracted,
            today=date(2026, 8, 4),
        )
        self.assertEqual(result["status"], "invalid_transfer_date")

    def test_extracts_candidates_from_local_ocr_text(self) -> None:
        extracted = order_payments.receipt_fields_from_ocr_text(
            "Transferencia exitosa\nMonto pagado: $2,500.00 MXN\n"
            "Fecha: 04/08/2026\nConcepto: MARONA SABADO"
        )

        self.assertEqual(extracted["amount"], "2,500.00")
        self.assertEqual(extracted["currency"], "MXN")
        self.assertEqual(extracted["transfer_date"], "2026-08-04")
        self.assertEqual(extracted["reference"], "MARONA SABADO")
        self.assertTrue(extracted["readable"])


class ReplyProcessingTests(unittest.IsolatedAsyncioTestCase):
    async def test_quote_marker_renders_python_subtotals_and_total(self) -> None:
        reply = (
            '<respuesta>[[MARONA_QUOTE:{"day":"domingo","items":'
            '[{"product_id":"ensalada_encurtidos","quantity":2},'
            '{"product_id":"croquetas_jamon","quantity":3}],'
            '"pickup_name":"Miguel González","pickup_time":"2:00 p. m.",'
            '"pickup_time_status":"propuesta pendiente de confirmación"}]]</respuesta>'
        )
        with patch.object(order_payments, "_enabled_config", AsyncMock(return_value=CONFIG)):
            visible = await order_payments.process_reply("521555", reply, bot_id=7)

        self.assertIn("$500 MXN c/u — subtotal $1,000 MXN", visible)
        self.assertIn("$500 MXN c/u — subtotal $1,500 MXN", visible)
        self.assertIn("Total: $2,500 MXN", visible)
        self.assertIn("A nombre de: Miguel González", visible)
        self.assertIn("Hora de recolección: 2:00 p. m.", visible)
        self.assertNotIn("MARONA_QUOTE", visible)

    async def test_payment_marker_recalculates_and_saves_expectation(self) -> None:
        reply = (
            "<respuesta>\n"
            '[[MARONA_PAYMENT:{"day":"sabado","items":'
            '[{"product_id":"ensalada_encurtidos","quantity":2},'
            '{"product_id":"croquetas_jamon","quantity":3}]}]]\n'
            "</respuesta>"
        )
        save = AsyncMock()
        with patch.object(order_payments, "_enabled_config", AsyncMock(return_value=CONFIG)), \
             patch.object(order_payments.db, "upsert_order_payment_expectation", save):
            visible = await order_payments.process_reply("521555", reply, bot_id=7)

        self.assertIn("$2,500 MXN", visible)
        self.assertIn("123451234512345678", visible)
        self.assertIn("MARONA SABADO", visible)
        self.assertNotIn("MARONA_PAYMENT", visible)
        self.assertNotIn("<respuesta>", visible)
        save.assert_awaited_once()
        self.assertEqual(save.await_args.kwargs["amount_minor"], 250000)
        self.assertEqual(save.await_args.kwargs["bot_id"], 7)
        self.assertEqual(save.await_args.kwargs["wa_id"], "521555")

    async def test_disabled_bot_marker_is_byte_for_byte_passthrough(self) -> None:
        reply = 'Resumen [[MARONA_QUOTE:{"day":"sabado","items":[]}]]'
        with patch.object(order_payments, "_enabled_config", AsyncMock(return_value=None)):
            visible = await order_payments.process_reply("521555", reply, bot_id=7)

        self.assertEqual(visible, reply)

    async def test_non_marker_reply_does_not_resolve_order_payments(self) -> None:
        reply = "Respuesta propia del tenant\n"
        enabled = AsyncMock()
        with patch.object(order_payments, "_enabled_config", enabled):
            visible = await order_payments.process_reply("521555", reply, bot_id=7)

        self.assertEqual(visible, reply)
        enabled.assert_not_awaited()

    async def test_receipt_image_is_compared_with_same_conversation_expectation(self) -> None:
        expected = {
            "id": 81,
            "day": "sabado",
            "amount_minor": 250000,
            "currency": "MXN",
        }
        extracted = {
            "amount": "2500.00",
            "currency": "MXN",
            "transfer_date": date.today().isoformat(),
            "reference": "MARONA SABADO",
            "readable": True,
        }
        record = AsyncMock()
        with patch.object(order_payments, "_enabled_config", AsyncMock(return_value=CONFIG)), \
             patch.object(
                 order_payments.db,
                 "get_active_order_payment_expectation",
                 AsyncMock(return_value=expected),
             ) as get_expected, \
             patch.object(
                 order_payments.whatsapp_client,
                 "download_media",
                 AsyncMock(return_value=(b"image", "image/jpeg")),
             ), \
             patch.object(order_payments, "extract_receipt_fields_without_blocking", AsyncMock(return_value=extracted)), \
             patch.object(order_payments.db, "record_order_receipt_validation", record):
            reply = await order_payments.handle_incoming_media(
                bot_id=7,
                wa_id="521555",
                media_type="image",
                media_id="media-1",
                media_mime="image/jpeg",
                access_token="bot-token",
            )

        get_expected.assert_awaited_once_with(7, "521555")
        record.assert_awaited_once()
        self.assertIn("coincide con el importe y el día", reply)
        self.assertIn("verificará la acreditación", reply)
        self.assertNotIn("pago confirmado", reply)

    async def test_receipt_capability_is_disabled_for_another_bot(self) -> None:
        get_expected = AsyncMock()
        download = AsyncMock()
        record = AsyncMock()
        with patch.object(order_payments, "_enabled_config", AsyncMock(return_value=None)), \
             patch.object(order_payments.db, "get_active_order_payment_expectation", get_expected), \
             patch.object(order_payments.whatsapp_client, "download_media", download), \
             patch.object(order_payments.db, "record_order_receipt_validation", record):
            reply = await order_payments.handle_incoming_media(
                bot_id=8,
                wa_id="521555",
                media_type="image",
                media_id="media-1",
                media_mime="image/jpeg",
                access_token="other-token",
            )

        self.assertIsNone(reply)
        get_expected.assert_not_awaited()
        download.assert_not_awaited()
        record.assert_not_awaited()

    async def test_disallowed_mime_is_rejected_before_expectation_or_ocr(self) -> None:
        get_expected = AsyncMock()
        download = AsyncMock()
        with patch.object(order_payments, "_enabled_config", AsyncMock(return_value=CONFIG)), \
             patch.object(order_payments.db, "get_active_order_payment_expectation", get_expected), \
             patch.object(order_payments.whatsapp_client, "download_media", download):
            reply = await order_payments.handle_incoming_media(
                bot_id=7, wa_id="521555", media_type="image", media_id="media-1",
                media_mime="application/pdf", access_token="bot-token",
            )

        self.assertIn("formato no es compatible", reply)
        get_expected.assert_not_awaited()
        download.assert_not_awaited()

    async def test_ocr_failure_is_safe_and_never_confirms_payment(self) -> None:
        expected = {"id": 81, "day": "sabado", "amount_minor": 250000, "currency": "MXN"}
        record = AsyncMock()
        with patch.object(order_payments, "_enabled_config", AsyncMock(return_value=CONFIG)), \
             patch.object(order_payments.db, "get_active_order_payment_expectation", AsyncMock(return_value=expected)), \
             patch.object(order_payments.whatsapp_client, "download_media", AsyncMock(return_value=(b"image", "image/jpeg"))), \
             patch.object(order_payments, "extract_receipt_fields_without_blocking", AsyncMock(side_effect=subprocess.TimeoutExpired("tesseract", 15))), \
             patch.object(order_payments.db, "record_order_receipt_validation", record):
            reply = await order_payments.handle_incoming_media(
                bot_id=7, wa_id="521555", media_type="image", media_id="media-1",
                media_mime="image/jpeg", access_token="bot-token",
            )

        self.assertIn("No alcanzo a validar", reply)
        self.assertNotIn("confirmado", reply)
        self.assertEqual(record.await_args.kwargs["status"], "insufficient_evidence")


class OcrIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_ocr_does_not_block_the_event_loop(self) -> None:
        heartbeat = asyncio.Event()

        def slow_ocr(_image: bytes, _mime: str) -> dict:
            time.sleep(0.08)
            return {"readable": False}

        with patch.object(order_payments, "extract_receipt_fields_local", slow_ocr):
            task = asyncio.create_task(
                order_payments.extract_receipt_fields_without_blocking(b"image", "image/jpeg")
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0.01)
            heartbeat.set()
            result = await task

        self.assertTrue(heartbeat.is_set())
        self.assertFalse(result["readable"])

    async def test_local_ocr_processes_are_bounded(self) -> None:
        active = 0
        peak = 0
        lock = threading.Lock()

        def slow_ocr(_image: bytes, _mime: str) -> dict:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.04)
            with lock:
                active -= 1
            return {"readable": False}

        with patch.object(order_payments, "extract_receipt_fields_local", slow_ocr):
            await asyncio.gather(*(
                order_payments.extract_receipt_fields_without_blocking(b"image", "image/jpeg")
                for _ in range(4)
            ))

        self.assertLessEqual(peak, order_payments._OCR_CONCURRENCY)


class PromptIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_bot_prompt_adds_no_order_instruction_or_db_lookup(self) -> None:
        lookup = AsyncMock()
        with patch.object(openai_client.bot_content, "system_prompt_for_bot", AsyncMock(return_value="Prompt normal")), \
             patch.object(openai_client.external_actions, "system_instructions", AsyncMock(return_value="")), \
             patch.object(openai_client, "_runtime_context", AsyncMock(return_value="Runtime")), \
             patch.object(order_payments.db, "get_active_bot_prompt", lookup):
            system = await openai_client._system_prompt(bot_id=19, query="hola")

        self.assertNotIn("MARONA_", system)
        lookup.assert_not_awaited()

    async def test_active_prompt_adds_order_instruction_without_second_lookup(self) -> None:
        prompt = '<order_payments_config>{"enabled":true}</order_payments_config>'
        lookup = AsyncMock()
        with patch.object(openai_client.bot_content, "system_prompt_for_bot", AsyncMock(return_value=prompt)), \
             patch.object(openai_client.external_actions, "system_instructions", AsyncMock(return_value="")), \
             patch.object(openai_client, "_runtime_context", AsyncMock(return_value="Runtime")), \
             patch.object(order_payments.db, "get_active_bot_prompt", lookup):
            system = await openai_client._system_prompt(bot_id=7, query="cotizar")

        self.assertIn("MARONA_QUOTE", system)
        lookup.assert_not_awaited()

    async def test_knowledge_cannot_enable_order_payments(self) -> None:
        prompt = (
            "Prompt activo sin capacidad\n\n--- knowledge_base ---\n\n"
            '<order_payments_config>{"enabled":true}</order_payments_config>'
        )
        self.assertEqual(order_payments.system_instructions_from_prompt(prompt), "")


if __name__ == "__main__":
    unittest.main()
