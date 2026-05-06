# Multi-Bot Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first multi-bot foundation so one deployment can route WhatsApp messages by Meta `phone_number_id` while preserving the current Asistto bot behavior.

**Architecture:** Keep the current single-bot path as the fallback default, then add additive Postgres tables for clients, bots and WhatsApp numbers. The webhook extracts `phone_number_id`, resolves a `BotContext`, stores messages/leads/appointments with `bot_id`, and sends replies using the resolved bot's WhatsApp number/token.

**Tech Stack:** FastAPI, asyncpg/Postgres, WhatsApp Cloud API, OpenRouter/OpenAI-compatible API, unittest, httpx.

---

## Scope

This plan implements Phase 1 from `docs/superpowers/specs/2026-05-05-multi-bot-studio-design.md`.

In scope:

- Extract WhatsApp `phone_number_id` from incoming webhook metadata.
- Add a `BotContext` resolver with safe fallback to the current Asistto config.
- Add additive multi-bot tables: `clients`, `users`, `client_users`, `bots`, `bot_whatsapp_numbers`, `bot_prompts`, `bot_knowledge`, `bot_skills`, `bot_integrations`, `integration_secrets`.
- Add nullable `bot_id` to existing operational records.
- Route incoming messages by `phone_number_id`.
- Keep the existing Asistto bot working as the default bot.
- Add tests and docs.

Out of scope for this phase:

- Client dashboard UI.
- Prompt/knowledge editor UI.
- Conversational Studio UI.
- Generic REST connector runtime.
- Secret encryption implementation.

## File Structure

- Modify `app/whatsapp_client.py`: extract `phone_number_id` and allow bot-specific sending.
- Create `app/bots.py`: define `BotContext`, `default_bot()`, and `resolve_by_phone_number_id()`.
- Modify `app/db.py`: add schema, migrations, default seed, lookup helpers, and optional `bot_id` arguments.
- Modify `app/main.py`: resolve bot per message and pass bot context through the response path.
- Modify `app/leads.py`: accept `bot_id` and pass it to lead writes.
- Modify `app/calendar_client.py`: accept `bot_id` for appointment save/cancel lookup.
- Modify `app/agenda_guard.py`: pass `bot_id` into calendar operations.
- Create `tests/test_whatsapp_client.py`: metadata extraction and bot-specific send URL tests.
- Create `tests/test_bots.py`: default and DB-backed bot resolution tests.
- Create `tests/test_db_multibot_schema.py`: schema and signature tests.
- Update `.env.example`, `README.md`, and `docs/HANDOFF.md`.

## Task 1: WhatsApp Metadata Extraction

**Files:** `app/whatsapp_client.py`, `tests/test_whatsapp_client.py`

- [ ] Write `tests/test_whatsapp_client.py` with two tests:
  - `test_extract_message_includes_phone_number_metadata`
  - `test_send_text_can_use_bot_specific_number_and_token`
- [ ] Run `python3 -m unittest tests/test_whatsapp_client.py -v` and verify failure.
- [ ] Update `send_text()` to accept optional `phone_number_id` and `access_token`.
- [ ] In `extract_message()`, read `value["metadata"]` and include `phone_number_id` and `display_phone_number` in the returned dict.
- [ ] Re-run `python3 -m unittest tests/test_whatsapp_client.py -v` and verify pass.
- [ ] Commit: `feat: extract whatsapp phone number metadata`.

Expected implementation shape:

```python
async def send_text(
    to_wa_id: str,
    body: str,
    phone_number_id: str | None = None,
    access_token: str | None = None,
) -> dict:
    sender_phone_number_id = phone_number_id or config.WHATSAPP_PHONE_NUMBER_ID
    token = access_token or config.WHATSAPP_API_TOKEN
```

Returned message dict must include:

```python
"phone_number_id": metadata.get("phone_number_id", ""),
"display_phone_number": metadata.get("display_phone_number", ""),
```

## Task 2: Bot Context Resolver

**Files:** `app/bots.py`, `app/config.py`, `.env.example`, `tests/test_bots.py`

- [ ] Add `DEFAULT_BOT_SLUG = _env("DEFAULT_BOT_SLUG", default="asistto")` to `app/config.py`.
- [ ] Add `DEFAULT_BOT_SLUG=asistto` to `.env.example`.
- [ ] Create `app/bots.py` with `BotContext`, `default_bot()`, `_from_row()`, and `resolve_by_phone_number_id()`.
- [ ] Create tests for default fallback, DB-backed lookup, and missing DB row fallback.
- [ ] Run `python3 -m unittest tests/test_bots.py tests/test_config.py -v`.
- [ ] Commit: `feat: add bot context resolver`.

Core type:

```python
@dataclass(frozen=True)
class BotContext:
    id: int
    client_id: int | None
    slug: str
    name: str
    whatsapp_phone_number_id: str
    whatsapp_access_token: str
    display_phone_number: str = ""
    openai_model: str = ""
```

## Task 3: Multi-Bot Schema

**Files:** `app/db.py`, `tests/test_db_multibot_schema.py`

- [ ] Add schema tests that assert all new tables exist in `SCHEMA_SQL`.
- [ ] Add tests that existing tables include `bot_id BIGINT` and indexes include:
  - `idx_conv_bot_wa_ts`
  - `idx_leads_bot_status`
  - `idx_calendar_appts_bot_status`
- [ ] Add tables: `clients`, `users`, `client_users`, `bots`, `bot_whatsapp_numbers`, `bot_prompts`, `bot_knowledge`, `bot_skills`, `bot_integrations`, `integration_secrets`.
- [ ] Add nullable `bot_id` columns to `leads`, `pending_follow_ups`, `conversations`, `processed_messages`, `calendar_appointments`, and `escalations`.
- [ ] Add `ensure_default_bot()` to seed Humanio/Asistto/default WhatsApp number.
- [ ] Add `get_bot_by_phone_number_id(phone_number_id: str)`.
- [ ] Call `ensure_default_bot()` from `run_migrations()` after schema setup.
- [ ] Run `python3 -m unittest tests/test_db_multibot_schema.py -v`.
- [ ] Commit: `feat: add multi-bot database foundation`.

Default seed must use existing env values and not require new secrets.

## Task 4: Scope Core Records By Bot

**Files:** `app/db.py`, `app/leads.py`, `app/calendar_client.py`

- [ ] Add tests that these functions accept `bot_id`:
  - `db.save_message`
  - `db.get_history`
  - `db.upsert_lead`
  - `db.save_calendar_appointment`
  - `db.list_active_calendar_appointments`
- [ ] Update `db.get_history(wa_id, limit, bot_id=None)` to filter by bot when provided.
- [ ] Update `db.save_message(..., bot_id=None)` to insert bot_id.
- [ ] Update `db.upsert_lead(wa_id, bot_id=None, **kwargs)` to store bot_id.
- [ ] Update `db.get_lead(wa_id, bot_id=None)`.
- [ ] Update `db.save_calendar_appointment(..., bot_id=None)`.
- [ ] Update `db.list_active_calendar_appointments(wa_id, bot_id=None)`.
- [ ] Update `leads.process_reply(..., bot_id=None)` and pass bot_id into all lead writes.
- [ ] Update `calendar_client.cancel_appointment(..., bot_id=None)` and `calendar_client.process_reply(..., bot_id=None)`.
- [ ] Run `python3 -m unittest tests/test_db_multibot_schema.py tests/test_config.py -v`.
- [ ] Commit: `feat: scope core records by bot`.

## Task 5: Route Webhook Messages By Bot Context

**Files:** `app/main.py`, `app/agenda_guard.py`

- [ ] Import `bots` in `app/main.py`.
- [ ] In `_process_message()`, after extracting `wa_id`, resolve bot:

```python
bot = await bots.resolve_by_phone_number_id(msg.get("phone_number_id"))
```

- [ ] Use `bot.id` when loading history and saving user/assistant messages.
- [ ] Change `_send_and_track()` to accept `bot: bots.BotContext`.
- [ ] Send WhatsApp replies with:

```python
await whatsapp_client.send_text(
    wa_id,
    reply,
    phone_number_id=bot.whatsapp_phone_number_id,
    access_token=bot.whatsapp_access_token,
)
```

- [ ] Pass `bot.id` through `leads.process_reply()`, `calendar_client.process_reply()`, and `agenda_guard.maybe_handle()`.
- [ ] Update `agenda_guard.maybe_handle(..., bot_id=None)` and pass bot_id to calendar operations.
- [ ] Run `python3 -m compileall app` and `python3 -m unittest discover -v`.
- [ ] Commit: `feat: route webhook messages by bot context`.

## Task 6: Keep Admin Compatible

**Files:** `app/db.py`, `app/admin.py`, `app/admin_tools.py`

- [ ] Keep existing agency admin views showing all data for this phase.
- [ ] Add optional `bot_id` parameters to conversation listing helpers without changing current callers.
- [ ] Make sure old rows with `bot_id IS NULL` do not break dashboard, CRM, conversations, escalations, reset-contact, AI status or calendar status.
- [ ] Run `python3 -m compileall app` and `python3 -m unittest discover -v`.
- [ ] Commit: `feat: prepare admin queries for bot scoping`.

Client-scoped UI filtering belongs to Phase 2.

## Task 7: Docs And Handoff

**Files:** `.env.example`, `README.md`, `docs/HANDOFF.md`

- [ ] Document `DEFAULT_BOT_SLUG=asistto`.
- [ ] Add a README section explaining that global env vars remain fallback/default Asistto config.
- [ ] Add handoff references to:
  - `docs/superpowers/specs/2026-05-05-multi-bot-studio-design.md`
  - `docs/superpowers/plans/2026-05-05-multi-bot-foundation.md`
- [ ] Run secret scan:

```bash
rg -n "sk-|ghp_|github_pat_|EAA|token_real|password_real|secret_real|api_key_real" README.md .env.example docs prompts app tests Dockerfile requirements.txt
```

- [ ] Commit: `docs: document multi-bot foundation`.

## Task 8: Final Verification And Deploy

- [ ] Run `python3 -m unittest discover -v`.
- [ ] Run `python3 -m compileall app`.
- [ ] Run `git status --short --branch`; expected clean.
- [ ] Push `main` to GitHub.
- [ ] Deploy `main` in Easypanel.
- [ ] Verify:
  - `https://bot.humanio.digital/health`
  - `https://bot.humanio.digital/admin/ai-status`
  - `https://bot.humanio.digital/admin/calendar-status`
- [ ] Run real WhatsApp regression:

```text
Hola
Quiero entender como funciona un chatbot de WhatsApp
Quiero agendar una llamada
Miguel Gonzalez
pasadomañana a las 9
gracias
```

Expected:

- Conversation appears in `/admin/conversations`.
- Bot replies as Asistto.
- Calendar appointment is created.
- No duplicate replies.
- No internal markers are visible.

## Self-Review

- Spec coverage: this plan covers Phase 1 only: tables, routing by `phone_number_id`, `bot_id` storage, default Asistto fallback, and regression safety.
- Intentional gaps: client UI, prompt editor, Studio, generic REST connector runtime, and encryption are later phases.
- Type consistency: `BotContext.id` maps to `bot_id`; WhatsApp metadata uses `phone_number_id`; global env values remain fallback defaults.
