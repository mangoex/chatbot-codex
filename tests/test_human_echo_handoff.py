from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import BackgroundTasks

from app import automations, client, follow_ups, main, whatsapp_client


def _bot(bot_id: int, phone_number_id: str) -> MagicMock:
    bot = MagicMock()
    bot.id = bot_id
    bot.name = f"bot-{bot_id}"
    bot.status = "active"
    bot.whatsapp_phone_number_id = phone_number_id
    bot.whatsapp_access_token = "test-token"
    return bot


def _echo(message_id: str, recipient: str, *, message_type: str = "text") -> dict:
    message = {
        "from": "525511112222",
        "to": recipient,
        "id": message_id,
        "type": message_type,
    }
    if message_type == "text":
        message["text"] = {"body": "El asesor ya atiende este caso"}
    else:
        message[message_type] = {"id": f"media-{message_id}", "mime_type": "image/jpeg"}
    return message


def _echo_payload(*changes: dict) -> dict:
    return {"entry": [{"changes": list(changes)}]}


class HumanEchoHandoffTests(unittest.TestCase):
    def test_extracts_all_canonical_smb_message_echoes(self):
        payload = {
            "entry": [
                {"changes": [
                    {"field": "messages", "value": {"messages": []}},
                    {"field": "smb_message_echoes", "value": {
                        "metadata": {"phone_number_id": "phone-a"},
                        "message_echoes": [_echo("echo-1", "521000000001"), _echo("echo-2", "521000000002", message_type="image")],
                    }},
                ]},
                {"changes": [{"field": "smb_message_echoes", "value": {
                    "metadata": {"phone_number_id": "phone-b"},
                    "message_echoes": [_echo("echo-3", "521000000003")],
                }}]},
            ]
        }
        echoes = whatsapp_client.extract_human_message_echoes(payload)
        self.assertEqual([item["message_id"] for item in echoes], ["echo-1", "echo-2", "echo-3"])
        self.assertEqual(echoes[1]["type"], "image")
        self.assertEqual(echoes[2]["phone_number_id"], "phone-b")

    def test_human_initiates_then_next_customer_message_is_silent(self):
        async def run():
            bot = _bot(7, "phone-7")
            payload = _echo_payload({"field": "smb_message_echoes", "value": {
                "metadata": {"phone_number_id": "phone-7"},
                "message_echoes": [_echo("human-init-1", "5215512345678")],
            }})
            skill = {"enabled": True, "config": {"escalate_when_agent_initiates": True}}
            inbound = {"entry": [{"changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "phone-7"},
                "messages": [{"from": "5215512345678", "id": "customer-after-human", "type": "text", "text": {"body": "Gracias"}}],
            }}]}]}
            with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)), \
                 patch.object(main.db, "was_processed", AsyncMock(return_value=False)), \
                 patch.object(main.db, "mark_processed", AsyncMock(return_value=True)), \
                 patch.object(main.db, "get_bot_skill", AsyncMock(return_value=skill)), \
                 patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=None)), \
                 patch.object(main.db, "get_history", AsyncMock(return_value=[])), \
                 patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=True)), \
                 patch.object(main.db, "set_conversation_handoff_active", AsyncMock()) as handoff, \
                 patch.object(main.db, "save_message", AsyncMock()) as save, \
                 patch.object(main.escalations, "record_agent_initiated_escalation", AsyncMock()) as escalation, \
                 patch.object(main.follow_ups, "cancel", AsyncMock()) as cancel, \
                 patch.object(main.openai_client, "complete", AsyncMock()) as openai, \
                 patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send_text:
                await main._process_message(payload)
                await main._process_message(inbound)
                handoff.assert_awaited_once_with(7, "5215512345678")
                self.assertEqual(save.await_count, 2)
                escalation.assert_awaited_once()
                self.assertEqual(cancel.await_count, 2)
                openai.assert_not_awaited()
                send_text.assert_not_awaited()

        asyncio.run(run())

    def test_customer_then_human_intervention_silences_next_customer_message(self):
        async def run():
            bot = _bot(147, "phone-147")
            echo_payload = _echo_payload({"field": "smb_message_echoes", "value": {
                "metadata": {"phone_number_id": "phone-147"},
                "message_echoes": [_echo("human-intervenes", "5215512345678")],
            }})
            inbound = {"entry": [{"changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "phone-147"},
                "messages": [{"from": "5215512345678", "id": "customer-after-intervention", "type": "image", "image": {"id": "i", "mime_type": "image/jpeg"}}],
            }}]}]}
            skill = {"enabled": True, "config": {"escalate_when_agent_initiates": True}}
            with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)), \
                 patch.object(main.db, "was_processed", AsyncMock(return_value=False)), \
                 patch.object(main.db, "mark_processed", AsyncMock(return_value=True)), \
                 patch.object(main.db, "get_bot_skill", AsyncMock(return_value=skill)), \
                 patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=None)), \
                 patch.object(main.db, "get_history", AsyncMock(return_value=[])), \
                 patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=True)), \
                 patch.object(main.db, "set_conversation_handoff_active", AsyncMock()) as handoff, \
                 patch.object(main.db, "save_message", AsyncMock()), \
                 patch.object(main.escalations, "record_agent_initiated_escalation", AsyncMock()), \
                 patch.object(main.follow_ups, "cancel", AsyncMock()), \
                 patch.object(main.order_payments, "handle_incoming_media", AsyncMock()) as media_handler, \
                 patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send_text:
                await main._process_message(echo_payload)
                await main._process_message(inbound)
                handoff.assert_awaited_once_with(147, "5215512345678")
                media_handler.assert_not_awaited()
                send_text.assert_not_awaited()

        asyncio.run(run())

    def test_echo_is_ignored_when_rule_is_disabled_and_status_never_triggers(self):
        async def run():
            bot = _bot(7, "phone-7")
            echo_payload = _echo_payload({"field": "smb_message_echoes", "value": {
                "metadata": {"phone_number_id": "phone-7"},
                "message_echoes": [_echo("human-disabled", "5215512345678")],
            }})
            status_payload = {"entry": [{"changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "phone-7"},
                "statuses": [{"id": "not-human-proof", "status": "sent", "recipient_id": "5215512345678"}],
            }}]}]}
            disabled = {"enabled": False, "config": {"escalate_when_agent_initiates": True}}
            with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)), \
                 patch.object(main.db, "get_bot_skill", AsyncMock(return_value=disabled)), \
                 patch.object(main.db, "set_conversation_handoff_active", AsyncMock()) as handoff:
                await main._process_message(echo_payload)
                await main._process_message(status_payload)
                handoff.assert_not_awaited()

        asyncio.run(run())

    def test_duplicate_and_bot_contact_are_isolated(self):
        async def run():
            bot_a, bot_b = _bot(7, "phone-a"), _bot(8, "phone-b")
            payload = _echo_payload(
                {"field": "smb_message_echoes", "value": {"metadata": {"phone_number_id": "phone-a"}, "message_echoes": [_echo("duplicate", "521-a")]}},
                {"field": "smb_message_echoes", "value": {"metadata": {"phone_number_id": "phone-b"}, "message_echoes": [_echo("unique", "521-b", message_type="image")] }},
            )
            skill = {"enabled": True, "config": {"escalate_when_agent_initiates": True}}
            async def resolve(phone_id):
                return {"phone-a": bot_a, "phone-b": bot_b}.get(phone_id)
            with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(side_effect=resolve)), \
                 patch.object(main.db, "was_processed", AsyncMock(side_effect=[True, False])), \
                 patch.object(main.db, "mark_processed", AsyncMock(return_value=True)), \
                 patch.object(main.db, "get_bot_skill", AsyncMock(return_value=skill)), \
                 patch.object(main.db, "set_conversation_handoff_active", AsyncMock()) as handoff, \
                 patch.object(main.db, "save_message", AsyncMock()), \
                 patch.object(main.escalations, "record_agent_initiated_escalation", AsyncMock()), \
                 patch.object(main.follow_ups, "cancel", AsyncMock()):
                await main._process_message(payload)
                handoff.assert_awaited_once_with(8, "521-b")

        asyncio.run(run())

    def test_follow_up_does_not_generate_or_send_during_human_handoff(self):
        async def run():
            bot = _bot(147, "phone-147")
            due = [{"id": 77, "bot_id": 147, "wa_id": "5215512345678"}]
            with patch.object(follow_ups.config, "ENABLE_FOLLOW_UPS", True), \
                 patch.object(follow_ups.db, "get_due_follow_ups", AsyncMock(return_value=due)), \
                 patch.object(follow_ups.bots, "resolve_by_bot_id", AsyncMock(return_value=bot)), \
                 patch.object(follow_ups.db, "is_conversation_handoff_active", AsyncMock(return_value=True)), \
                 patch.object(follow_ups.db, "mark_follow_up_sent", AsyncMock()) as marked, \
                 patch.object(follow_ups.openai_client, "_chat", AsyncMock()) as chat, \
                 patch.object(follow_ups.whatsapp_client, "send_text", AsyncMock()) as send_text:
                await follow_ups._process_due()
                marked.assert_awaited_once_with(77)
                chat.assert_not_awaited()
                send_text.assert_not_awaited()

        asyncio.run(run())

    def test_automation_guard_is_isolated_by_bot_and_contact(self):
        async def run():
            with patch.object(automations.db, "is_conversation_handoff_active", AsyncMock(side_effect=[True, False])) as active:
                self.assertFalse(await automations._handoff_allows_automation(147, "521-a"))
                self.assertTrue(await automations._handoff_allows_automation(148, "521-a"))
                self.assertEqual(active.await_args_list[0].args, (147, "521-a"))
                self.assertEqual(active.await_args_list[1].args, (148, "521-a"))

        asyncio.run(run())

    def test_campaign_does_not_send_to_contact_with_human_handoff(self):
        async def run():
            broadcast = {"template_name": "promo", "language_code": "es_MX", "variable_mappings": "[]"}
            recipient = {"id": 9, "wa_id": "5215512345678"}
            with patch.object(client.db, "update_broadcast_status", AsyncMock()), \
                 patch.object(client.db, "get_broadcast", AsyncMock(return_value=broadcast)), \
                 patch.object(client.db, "get_pending_broadcast_recipients", AsyncMock(side_effect=[[recipient], []])), \
                 patch.object(client.db, "is_conversation_handoff_active", AsyncMock(side_effect=[False, True])), \
                 patch.object(client.db, "update_broadcast_recipient_status", AsyncMock()) as recipient_status, \
                 patch.object(client.meta_provider, "send_template_message", AsyncMock()) as send_template:
                await client.process_broadcast_queue(3, 147)
                recipient_status.assert_awaited_once_with(9, "skipped_human_handoff")
                send_template.assert_not_awaited()

        asyncio.run(run())

    def test_echo_failure_is_not_marked_and_retry_can_activate_handoff(self):
        async def run():
            bot = _bot(147, "phone-147")
            echo = whatsapp_client.extract_human_message_echoes(_echo_payload({"field": "smb_message_echoes", "value": {
                "metadata": {"phone_number_id": "phone-147"}, "message_echoes": [_echo("retry-echo", "5215512345678")],
            }}))[0]
            skill = {"enabled": True, "config": {"escalate_when_agent_initiates": True}}
            with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)), \
                 patch.object(main.db, "get_bot_skill", AsyncMock(return_value=skill)), \
                 patch.object(main.db, "was_processed", AsyncMock(return_value=False)), \
                 patch.object(main.db, "set_conversation_handoff_active", AsyncMock(side_effect=[RuntimeError("db down"), None])), \
                 patch.object(main.db, "save_message", AsyncMock()), \
                 patch.object(main.escalations, "record_agent_initiated_escalation", AsyncMock()), \
                 patch.object(main.follow_ups, "cancel", AsyncMock()), \
                 patch.object(main.db, "mark_processed", AsyncMock(return_value=True)) as marked:
                with self.assertRaisesRegex(RuntimeError, "db down"):
                    await main._process_human_message_echo(echo)
                marked.assert_not_awaited()
                await main._process_human_message_echo(echo)
                marked.assert_awaited_once_with("retry-echo", bot_id=147)

        asyncio.run(run())

    def test_webhook_persists_echo_before_ack_and_queues_customer_inbound(self):
        async def run():
            payload = _echo_payload({"field": "smb_message_echoes", "value": {
                "metadata": {"phone_number_id": "phone-147"}, "message_echoes": [_echo("ack-echo", "5215512345678")],
            }})
            request = MagicMock()
            request.body = AsyncMock(return_value=b'{"entry":[]}')
            request.json = AsyncMock(return_value=payload)
            request.headers = {"X-Hub-Signature-256": "valid"}
            background = BackgroundTasks()
            with patch.object(main.signature, "verify", return_value=True), \
                 patch.object(main, "_process_human_message_echoes", AsyncMock()) as persist, \
                 patch.object(main, "_process_inbound_messages_safe", AsyncMock()):
                response = await main.receive_webhook(request, background)
                persist.assert_awaited_once_with(payload)
                self.assertEqual(response, {"status": "received"})
                self.assertEqual(len(background.tasks), 1)
                self.assertIs(background.tasks[0].func, main._process_inbound_messages_safe)

        asyncio.run(run())

    def test_webhook_echo_failure_propagates_instead_of_acknowledging(self):
        async def run():
            payload = _echo_payload({"field": "smb_message_echoes", "value": {
                "metadata": {"phone_number_id": "phone-147"}, "message_echoes": [_echo("fail-echo", "5215512345678")],
            }})
            request = MagicMock()
            request.body = AsyncMock(return_value=b"payload")
            request.json = AsyncMock(return_value=payload)
            request.headers = {"X-Hub-Signature-256": "valid"}
            with patch.object(main.signature, "verify", return_value=True), \
                 patch.object(main, "_process_human_message_echoes", AsyncMock(side_effect=RuntimeError("persistence failed"))):
                with self.assertRaisesRegex(RuntimeError, "persistence failed"):
                    await main.receive_webhook(request, BackgroundTasks())

        asyncio.run(run())

    def test_customer_only_webhook_stays_background(self):
        async def run():
            payload = {"entry": [{"changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "phone-147"},
                "messages": [{"from": "5215512345678", "id": "customer-async", "type": "text", "text": {"body": "hola"}}],
            }}]}]}
            request = MagicMock()
            request.body = AsyncMock(return_value=b"payload")
            request.json = AsyncMock(return_value=payload)
            request.headers = {"X-Hub-Signature-256": "valid"}
            background = BackgroundTasks()
            with patch.object(main.signature, "verify", return_value=True), \
                 patch.object(main, "_process_human_message_echoes", AsyncMock()) as persist:
                await main.receive_webhook(request, background)
                persist.assert_not_awaited()
                self.assertEqual(len(background.tasks), 1)

        asyncio.run(run())

    def test_inactivity_automation_rechecks_handoff_before_delivery(self):
        async def run():
            trigger = {"id": 4, "bot_id": 147, "trigger_config": {"inactivity_hours": 24}, "template_name": "promo", "language_code": "es_MX", "variable_mappings": []}
            conversation = {"wa_id": "5215512345678", "contact_name": "", "contact_business": ""}
            with patch.object(automations.db, "list_active_template_triggers_by_type", AsyncMock(return_value=[trigger])), \
                 patch.object(automations.db, "get_inactive_conversations_for_trigger", AsyncMock(return_value=[conversation])), \
                 patch.object(automations.db, "has_recent_trigger_execution", AsyncMock(return_value=False)), \
                 patch.object(automations.db, "is_conversation_handoff_active", AsyncMock(side_effect=[False, True])), \
                 patch.object(automations.meta_provider, "send_template_message", AsyncMock()) as send_template:
                await automations.evaluate_inactivity_triggers()
                send_template.assert_not_awaited()

        asyncio.run(run())

    def test_handoff_arriving_during_ai_generation_blocks_final_bot_send(self):
        async def run():
            bot = _bot(147, "phone-147")
            bot.openai_model = "test-model"
            payload = {"entry": [{"changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "phone-147"},
                "messages": [{"from": "5215512345678", "id": "race-inbound", "type": "text", "text": {"body": "hola"}}],
            }}]}]}
            with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)), \
                 patch.object(main.db, "was_processed", AsyncMock(return_value=False)), \
                 patch.object(main.db, "mark_processed", AsyncMock(return_value=True)), \
                 patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=None)), \
                 patch.object(main.follow_ups, "cancel", AsyncMock()), \
                 patch.object(main.follow_ups, "schedule", AsyncMock()) as schedule, \
                 patch.object(main.db, "get_history", AsyncMock(return_value=[])), \
                 patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(side_effect=[False, False, True])), \
                 patch.object(main.db, "save_message", AsyncMock()) as save, \
                 patch.object(main.openai_client, "complete", AsyncMock(return_value="respuesta tardía")) as complete, \
                 patch.object(main.order_payments, "process_reply", AsyncMock(return_value="respuesta tardía")), \
                 patch.object(main.external_actions, "process_reply", AsyncMock(return_value="respuesta tardía")), \
                 patch.object(main.calendar_client, "process_reply", AsyncMock(return_value=("respuesta tardía", False))), \
                 patch.object(main.leads, "process_reply", AsyncMock(return_value="respuesta tardía")), \
                 patch.object(main.whatsapp_client, "send_text", AsyncMock()) as send_text:
                await main._process_message(payload)
                complete.assert_awaited_once()
                send_text.assert_not_awaited()
                schedule.assert_not_awaited()
                assistant_saves = [call for call in save.await_args_list if call.args[1] == "assistant"]
                self.assertEqual(assistant_saves, [])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
