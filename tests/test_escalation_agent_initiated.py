from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app import client, db, escalations, main, meta_provider


@pytest.mark.asyncio
async def test_client_escalation_save_persists_escalate_when_agent_initiates():
    """Valida que client_escalation_save guarde correctamente el flag 'escalate_when_agent_initiates'."""
    req = MagicMock()
    session = {"user_id": 1, "client_id": 1, "role": "client_admin"}
    
    with patch("app.client._require_client_login", return_value=session), \
         patch("app.client._require_bot_editor", new_callable=AsyncMock), \
         patch("app.db.upsert_bot_skill", new_callable=AsyncMock) as mock_upsert:
         
        resp = await client.client_escalation_save(
            request=req,
            bot_id=10,
            enabled="on",
            keywords="queja, humano",
            escalate_on_media="on",
            escalate_when_agent_initiates="on",
        )
        
        assert resp.status_code == 302
        assert "tab=escalate" in resp.headers["location"]
        mock_upsert.assert_awaited_once_with(
            bot_id=10,
            skill_type="escalation",
            enabled=True,
            config_data={
                "keywords": ["queja", "humano"],
                "escalate_on_media": True,
                "escalate_when_agent_initiates": True,
            },
        )


@pytest.mark.asyncio
async def test_client_escalation_save_when_checkbox_is_off():
    """Valida que si no se marca la casilla, escalate_when_agent_initiates se guarde en False."""
    req = MagicMock()
    session = {"user_id": 1, "client_id": 1, "role": "client_admin"}
    
    with patch("app.client._require_client_login", return_value=session), \
         patch("app.client._require_bot_editor", new_callable=AsyncMock), \
         patch("app.db.upsert_bot_skill", new_callable=AsyncMock) as mock_upsert:
         
        resp = await client.client_escalation_save(
            request=req,
            bot_id=10,
            enabled="on",
            keywords="asesor",
            escalate_on_media=None,
            escalate_when_agent_initiates=None,
        )
        
        assert resp.status_code == 302
        mock_upsert.assert_awaited_once_with(
            bot_id=10,
            skill_type="escalation",
            enabled=True,
            config_data={
                "keywords": ["asesor"],
                "escalate_on_media": False,
                "escalate_when_agent_initiates": False,
            },
        )


@pytest.mark.asyncio
async def test_db_is_conversation_initiated_by_agent():
    """Valida la detección en base de datos si el primer mensaje fue enviado por el asesor."""
    with patch("app.db._pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        # Caso 1: Primer mensaje fue del asistente (asesor / outbound)
        mock_conn.fetchrow.return_value = {"role": "assistant"}
        is_agent = await db.is_conversation_initiated_by_agent(bot_id=5, wa_id="5215512345678")
        assert is_agent is True

        # Caso 2: Primer mensaje fue del usuario (cliente)
        mock_conn.fetchrow.return_value = {"role": "user"}
        is_agent = await db.is_conversation_initiated_by_agent(bot_id=5, wa_id="5215512345678")
        assert is_agent is False

        # Caso 3: No hay mensajes previos en la conversación
        mock_conn.fetchrow.return_value = None
        is_agent = await db.is_conversation_initiated_by_agent(bot_id=5, wa_id="5215512345678")
        assert is_agent is False


@pytest.mark.asyncio
async def test_strict_escalation_silences_bot_when_agent_initiated_text():
    """
    Verifica que el bot no responda bajo ninguna circunstancia si la regla está activa
    y la conversación fue iniciada por el asesor (texto entrante).
    """
    bot = MagicMock()
    bot.id = 10
    bot.name = "Bot Demo"
    bot.status = "active"
    bot.whatsapp_phone_number_id = "phone-10"
    bot.whatsapp_access_token = "token-10"

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-10"},
                            "messages": [
                                {
                                    "from": "5215512345678",
                                    "id": "wamid.msg123",
                                    "type": "text",
                                    "text": {"body": "Hola, gracias por escribirme ayer."},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    mock_escalation_skill = {
        "enabled": True,
        "config": {
            "escalate_when_agent_initiates": True,
        },
    }

    with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)), \
         patch.object(main.db, "was_processed", AsyncMock(return_value=False)), \
         patch.object(main.db, "mark_processed", AsyncMock(return_value=True)), \
         patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=None)), \
         patch.object(main.follow_ups, "cancel", AsyncMock()), \
         patch.object(main.db, "get_history", AsyncMock(return_value=[{"role": "assistant", "content": "Hola Sr. Cliente"}])), \
         patch.object(main.db, "get_bot_skill", AsyncMock(return_value=mock_escalation_skill)), \
         patch.object(main.db, "is_conversation_initiated_by_agent", AsyncMock(return_value=True)), \
         patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=False)), \
         patch.object(main.db, "save_message", AsyncMock()) as mock_save, \
         patch.object(main.db, "set_conversation_handoff_active", AsyncMock()) as mock_set_handoff, \
         patch.object(main.escalations, "record_agent_initiated_escalation", AsyncMock()) as mock_record_esc, \
         patch.object(main.openai_client, "complete", AsyncMock()) as mock_openai, \
         patch.object(main.whatsapp_client, "send_text", AsyncMock()) as mock_send_wa:

        await main._process_message(payload)

        # El mensaje del usuario se guardó
        mock_save.assert_awaited_once_with("5215512345678", "user", "Hola, gracias por escribirme ayer.", bot_id=10)
        
        # Se activó el handoff y se registró la escalación
        mock_set_handoff.assert_awaited_once_with(10, "5215512345678")
        mock_record_esc.assert_awaited_once()

        # El bot NO debe generar respuesta ni llamar a OpenAI ni enviar WhatsApp
        mock_openai.assert_not_called()
        mock_send_wa.assert_not_called()


@pytest.mark.asyncio
async def test_strict_escalation_silences_bot_when_agent_initiated_media():
    """
    Verifica que el bot no responda con audios o imágenes entrantes si la regla está activa
    y la conversación fue iniciada por el asesor.
    """
    bot = MagicMock()
    bot.id = 10
    bot.name = "Bot Demo"
    bot.status = "active"
    bot.whatsapp_phone_number_id = "phone-10"
    bot.whatsapp_access_token = "token-10"

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-10"},
                            "messages": [
                                {
                                    "from": "5215512345678",
                                    "id": "wamid.msg456",
                                    "type": "image",
                                    "image": {"id": "media-1", "mime_type": "image/jpeg", "caption": "Aquí la foto"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    mock_escalation_skill = {
        "enabled": True,
        "config": {
            "escalate_when_agent_initiates": True,
        },
    }

    with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)), \
         patch.object(main.db, "was_processed", AsyncMock(return_value=False)), \
         patch.object(main.db, "mark_processed", AsyncMock(return_value=True)), \
         patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=None)), \
         patch.object(main.follow_ups, "cancel", AsyncMock()), \
         patch.object(main.db, "get_history", AsyncMock(return_value=[])), \
         patch.object(main.db, "get_bot_skill", AsyncMock(return_value=mock_escalation_skill)), \
         patch.object(main.db, "is_conversation_initiated_by_agent", AsyncMock(return_value=True)), \
         patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=False)), \
         patch.object(main.db, "save_message", AsyncMock()) as mock_save, \
         patch.object(main.db, "set_conversation_handoff_active", AsyncMock()) as mock_set_handoff, \
         patch.object(main.escalations, "record_agent_initiated_escalation", AsyncMock()) as mock_record_esc, \
         patch.object(main.whatsapp_client, "send_text", AsyncMock()) as mock_send_wa:

        await main._process_message(payload)

        # Se guardó el mensaje del archivo entrante
        mock_save.assert_awaited_once_with("5215512345678", "user", "Aquí la foto", bot_id=10)
        
        # Se activó el handoff y se registró la escalación
        mock_set_handoff.assert_awaited_once_with(10, "5215512345678")
        mock_record_esc.assert_awaited_once()

        # No se envió ninguna respuesta automática
        mock_send_wa.assert_not_called()


@pytest.mark.asyncio
async def test_normal_flow_when_customer_initiated():
    """
    Verifica que si la conversación fue iniciada por el cliente (is_conversation_initiated_by_agent=False),
    el bot responde normalmente con IA.
    """
    bot = MagicMock()
    bot.id = 10
    bot.name = "Bot Demo"
    bot.status = "active"
    bot.openai_model = "gpt-4o-mini"
    bot.whatsapp_phone_number_id = "phone-10"
    bot.whatsapp_access_token = "token-10"

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-10"},
                            "messages": [
                                {
                                    "from": "5215512345678",
                                    "id": "wamid.msg789",
                                    "type": "text",
                                    "text": {"body": "Hola, qué precio tienen?"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    mock_escalation_skill = {
        "enabled": True,
        "config": {
            "escalate_when_agent_initiates": True,
        },
    }

    with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)), \
         patch.object(main.db, "was_processed", AsyncMock(return_value=False)), \
         patch.object(main.db, "mark_processed", AsyncMock(return_value=True)), \
         patch.object(main.db, "get_active_bot_integration", AsyncMock(return_value=None)), \
         patch.object(main.follow_ups, "cancel", AsyncMock()), \
         patch.object(main.follow_ups, "schedule", AsyncMock()), \
         patch.object(main.db, "get_history", AsyncMock(return_value=[])), \
         patch.object(main.db, "get_bot_skill", AsyncMock(return_value=mock_escalation_skill)), \
         patch.object(main.db, "is_conversation_initiated_by_agent", AsyncMock(return_value=False)), \
         patch.object(main.db, "is_chatwoot_handoff_active", AsyncMock(return_value=False)), \
         patch.object(main.db, "save_message", AsyncMock()) as mock_save, \
         patch.object(main.db, "upsert_lead", AsyncMock()), \
         patch.object(main.db, "get_lead", AsyncMock(return_value={"qualification_status": "calificado"})), \
         patch.object(main.openai_client, "complete", AsyncMock(return_value="Nuestros precios empiezan en $100.")) as mock_openai, \
         patch.object(main.whatsapp_client, "send_text", AsyncMock()) as mock_send_wa, \
         patch.object(main.escalations, "record_if_escalated", AsyncMock()):

        await main._process_message(payload)

        # La IA fue llamada y se envió la respuesta al usuario
        mock_openai.assert_awaited_once()
        mock_send_wa.assert_awaited_once()


@pytest.mark.asyncio
async def test_meta_provider_send_template_and_test_saves_message():
    """Valida que send_template_message y send_test_message guarden el rol 'assistant' en conversaciones."""
    runtime = {
        "bot": {"id": 1, "phone_number_id": "12345", "whatsapp_access_token": "token123"},
        "integration": {"config": {}},
        "access_token": "token123",
    }
    
    with patch("app.meta_provider.get_bot_whatsapp_runtime", new_callable=AsyncMock, return_value=runtime), \
         patch("app.meta_provider.graph_post", new_callable=AsyncMock, return_value={"messages": [{"id": "wamid.1"}]}), \
         patch("app.db.save_message", new_callable=AsyncMock) as mock_save:

        # 1. Template message
        await meta_provider.send_template_message(
            bot_id=1,
            to_wa_id="5215512345678",
            template_name="recordatorio_cita",
            parameters=["Juan", "10:00 AM"],
        )
        mock_save.assert_awaited_with(
            "5215512345678",
            "assistant",
            "[Plantilla enviada: recordatorio_cita] (Juan, 10:00 AM)",
            bot_id=1,
        )

        # 2. Test message
        mock_save.reset_mock()
        await meta_provider.send_test_message(
            bot_id=1,
            to_wa_id="5215599998888",
            message_type="text",
            body_text="Hola prueba",
        )
        mock_save.assert_awaited_with(
            "5215599998888",
            "assistant",
            "Hola prueba",
            bot_id=1,
        )


@pytest.mark.asyncio
async def test_whatsapp_web_human_outbound_status_triggers_handoff_and_silences_bot():
    """
    Verifica que cuando un asesor humano escribe en WhatsApp Web, Meta envía un evento de status ('sent').
    El sistema debe detectar que el mensaje no fue emitido por Asistto, activar el relevo humano
    y silenciar al bot para los mensajes entrantes posteriores del cliente.
    """
    bot = MagicMock()
    bot.id = 170
    bot.name = "Mobi Muebles"
    bot.status = "active"
    bot.whatsapp_phone_number_id = "phone-170"
    bot.whatsapp_access_token = "token-170"

    # 1. Payload de webhook de Meta con status 'sent' para un mensaje enviado desde WhatsApp Web
    status_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-170"},
                            "statuses": [
                                {
                                    "id": "wamid.HUMAN_WEB_MSG_123",
                                    "status": "sent",
                                    "recipient_id": "5215512345678",
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    with patch.object(main.bots, "resolve_by_phone_number_id", AsyncMock(return_value=bot)), \
         patch.object(main.db, "is_bot_sent_message", AsyncMock(return_value=False)), \
         patch.object(main.db, "record_bot_sent_message", AsyncMock()) as mock_record_bot_msg, \
         patch.object(main.db, "set_conversation_handoff_active", AsyncMock()) as mock_set_handoff, \
         patch.object(main.db, "save_message", AsyncMock()) as mock_save, \
         patch.object(main.escalations, "record_agent_initiated_escalation", AsyncMock()) as mock_record_esc, \
         patch.object(main.follow_ups, "cancel", AsyncMock()) as mock_cancel_fu:

        await main._process_message(status_payload)

        # Se activó el relevo humano por intervención desde WhatsApp Web
        mock_set_handoff.assert_awaited_once_with(170, "5215512345678")
        mock_save.assert_awaited_once_with(
            "5215512345678", "assistant", "[Mensaje del asesor desde WhatsApp Web/App]", bot_id=170
        )
        mock_record_esc.assert_awaited_once()
        mock_cancel_fu.assert_awaited_once_with("5215512345678", 170)


@pytest.mark.asyncio
async def test_phrase_and_quote_keyword_detection_in_escalations():
    """Verifica que palabras o frases con comillas/puntuación configuradas por el usuario activen la escalación."""
    with patch("app.db.get_bot_skill", new_callable=AsyncMock) as mock_get_skill:
        mock_get_skill.return_value = {
            "enabled": True,
            "config": {
                "keywords": [
                    "hablar con una persona",
                    "queja",
                    "uniformes",
                    "camisas o playeras",
                ]
            }
        }

        # Caso 1: El usuario menciona 'queja'
        result = await escalations.detect_reason(
            user_text="Tengo una queja con mi entrega",
            bot_reply="",
            message_type="text",
            bot_id=170,
        )
        assert result is not None
        assert result[0] == "cliente_solicito_humano"

        # Caso 2: El usuario menciona una frase de varias palabras 'camisas o playeras'
        result2 = await escalations.detect_reason(
            user_text="Me pueden dar información sobre camisas o playeras por favor?",
            bot_reply="",
            message_type="text",
            bot_id=170,
        )
        assert result2 is not None
        assert result2[0] == "cliente_solicito_humano"
