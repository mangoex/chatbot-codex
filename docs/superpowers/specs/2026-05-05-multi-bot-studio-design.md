# Multi-Bot Studio Design

## Context

`mangoex/chatbot-codex` is currently a working WhatsApp Cloud API bot for
Asistto. It runs on FastAPI, Postgres and Easypanel, uses OpenRouter/OpenAI for
responses, stores conversations/leads, and can create/cancel real Google
Calendar appointments.

The next product step is to turn the single Asistto bot into a multi-client
platform where Humanio can create personalized WhatsApp bots for customers.
Each customer should also have access to configure and operate their own bot.

## Product Direction

The selected direction is:

- Dashboard Multi-Bot for Humanio agency operations.
- Conversational Studio for creating and configuring bots.
- Client panel where each customer can view and edit their own bot.

This avoids creating one GitHub repository per customer. One backend serves
many bots and routes each incoming WhatsApp message by Meta `phone_number_id`.

## Users And Permissions

### Humanio Agency Admin

Agency admins can:

- Create clients.
- Create one or more bots per client.
- Assign WhatsApp numbers and `phone_number_id` values.
- Configure provider-level settings and sensitive integrations.
- Use the Studio to generate prompts, knowledge and skills.
- View all conversations, leads, appointments, errors and integration health.
- Access any bot for support.

### Client Admin

Client admins can:

- View conversations, CRM/leads, appointments and basic metrics for their bots.
- Edit bot identity, tone, prompt and business rules.
- Edit knowledge base documents.
- Enable or disable allowed skills.
- Configure their own service/API integrations.
- Test changes in a simulator before publishing them.

Client admins should not see full platform secrets such as WhatsApp access
tokens, Google refresh tokens owned by Humanio, OpenRouter keys, database URLs
or webhook secrets. When they configure their own API credentials, the app must
store those credentials securely and show only masked values after saving.

### Client Viewer

Client viewers can:

- View conversations, leads, appointments and metrics.
- Open WhatsApp links for manual follow-up.

Client viewers cannot edit bot behavior, knowledge or integrations.

## Core UX

### Agency Dashboard

The agency dashboard is the operating center for Humanio.

Primary views:

- Clients list: name, active bots, status, last activity and alerts.
- Bots list: client, bot name, WhatsApp number, `phone_number_id`, health,
  conversations, leads, appointments and latest error.
- Bot detail: prompt, knowledge, skills, integrations, logs and diagnostics.
- Integration health: WhatsApp, IA provider, Google Calendar, client APIs.

### Conversational Studio

The Studio is an internal assistant that helps Humanio create a bot from a
brief. It should ask targeted questions and then generate a draft
configuration.

Example input:

```text
Crea un bot para una clinica dental que responda dudas, capture leads y agende
citas en Google Calendar.
```

Expected output:

- Bot name and description.
- Draft system prompt.
- Suggested knowledge sections.
- Recommended skills.
- Required integration checklist.
- Test conversation examples.

The generated configuration is saved as a draft. A Humanio admin reviews and
publishes it.

### Client Panel

The client panel is scoped to the logged-in client's bots.

Primary views:

- Conversations.
- CRM/leads.
- Appointments.
- Bot settings.
- Prompt editor.
- Knowledge editor.
- Skills and integrations.
- Simulator.

The client can edit behavior and integrations, but the UI must make sensitive
actions explicit and reversible where possible.

## Data Model

The current single-bot tables should evolve by adding `client_id` and `bot_id`
where needed. New tables should be additive so the current Asistto bot keeps
working during migration.

Recommended tables:

- `clients`: customer businesses.
- `users`: login identities.
- `client_users`: maps users to clients and roles.
- `bots`: one bot configuration per client use case.
- `bot_whatsapp_numbers`: WhatsApp number metadata and `phone_number_id`.
- `bot_prompts`: active and draft prompt versions.
- `bot_knowledge`: knowledge documents or snippets.
- `bot_skills`: enabled skills and per-skill settings.
- `bot_integrations`: external systems connected to a bot.
- `integration_secrets`: encrypted credentials or secret references.
- `conversations`: add `bot_id`.
- `leads`: add `bot_id`.
- `calendar_appointments`: add `bot_id`.
- `processed_messages`: include message/bot routing metadata.

## Routing

Incoming webhook flow:

1. Meta sends a WhatsApp webhook payload.
2. The app extracts `phone_number_id` from the payload metadata.
3. The app finds the matching row in `bot_whatsapp_numbers`.
4. The app loads the bot configuration, prompt, knowledge, skills and
   integrations.
5. The app stores the message with `bot_id`.
6. The selected bot responds using its own settings.
7. The response is sent using the credentials and phone number assigned to that
   bot.

If no bot matches the incoming `phone_number_id`, the app should log the event
and return 200 to Meta without responding, to avoid webhook retries.

## Prompt And Knowledge

The existing file-based prompt should remain as the default template and local
fallback:

- `prompts/system.md`
- `prompts/knowledge/*.md`

For multi-bot operation, the active prompt and knowledge should be loaded from
Postgres by `bot_id`.

Prompt versioning rules:

- Edits create a draft.
- Simulator can run against draft.
- Publishing makes the draft active.
- Previous versions remain available for rollback.

## Skills

Skills are capabilities a bot can use. Initial skill types:

- `lead_capture`: gather and qualify leads.
- `human_escalation`: create cases for manual follow-up.
- `google_calendar`: create, check and cancel appointments.
- `client_api`: call the customer's external API.
- `action_link`: send a CTA link when the lead is qualified.

Each skill should have:

- Enabled/disabled state.
- Human-readable description.
- Configuration schema.
- Optional secret requirements.
- Safe diagnostics.

## Client API Integrations

Clients must be able to configure APIs for their own services or systems.

Initial supported connector type:

- Generic REST API.

Supported authentication modes for v1:

- No auth.
- Bearer token.
- API key header.
- Basic auth.

Recommended fields:

- Integration name.
- Base URL.
- Auth type.
- Secret values.
- Allowed endpoints/actions.
- Test request configuration.
- Timeout.
- Whether the integration can read data, write data or both.

Security rules:

- Secrets are entered through secure forms.
- Secrets are encrypted at rest or stored as secret references.
- Saved secrets are displayed only as masked values.
- Client users can rotate their own integration secrets.
- Responses shown in diagnostics must redact tokens, passwords and headers.
- The bot can only call endpoints/actions explicitly configured for that bot.

Example client API skills:

- Check appointment availability in a custom system.
- Create a booking.
- Search customer by phone.
- Create lead in CRM.
- Get order status.
- Send quote request.

## Configuration And Secrets

The app should add a platform-level encryption key:

```env
APP_ENCRYPTION_KEY=
```

This key is stored only in Easypanel. It is used to encrypt client-provided API
secrets before saving them in Postgres. It must never be committed.

For the first implementation, existing global environment variables can remain
as the default Asistto bot configuration. Multi-bot settings should be added
gradually and fall back to the current globals when no bot-specific value
exists.

## Simulator

The simulator lets agency admins and client admins test a bot before publishing
changes.

It should support:

- Selecting active or draft prompt.
- Sending test messages.
- Showing which knowledge and skills were used.
- Showing whether a calendar/API action would run.
- Safe dry-run mode for write actions.

The simulator should not send real WhatsApp messages unless explicitly using a
dedicated test mode.

## Error Handling

- Missing bot for `phone_number_id`: log and return 200 to Meta.
- Missing integration credentials: reply with a safe fallback and create an
  admin alert.
- Client API timeout: retry only when the action is read-only; for write
  actions, avoid duplicate writes unless the connector supports idempotency.
- AI provider error: use the existing short fallback response.
- Permission failure: return 403 in admin routes and never leak resource names
  from another client.

## Implementation Phases

### Phase 1: Multi-Bot Foundation

- Add clients, users, bot tables and roles.
- Add `bot_id` to conversations, leads and appointments.
- Extract `phone_number_id` from WhatsApp payloads.
- Route incoming messages to a bot.
- Preserve current Asistto behavior as the default bot.

### Phase 2: Dashboard Multi-Bot

- Add agency dashboard views for clients and bots.
- Add bot detail page.
- Add health indicators for WhatsApp, IA and Calendar.
- Add client-scoped login access.

### Phase 3: Prompt And Knowledge Editing

- Store prompt and knowledge by bot in Postgres.
- Add prompt editor and knowledge editor.
- Add draft/publish/rollback flow.
- Keep file prompts as templates/fallback.

### Phase 4: Skills And Integrations

- Add skill registry.
- Add Google Calendar as a per-bot integration.
- Add generic REST API integration for client systems.
- Add encrypted secret storage.
- Add safe diagnostics and connection tests.

### Phase 5: Conversational Studio

- Add Studio page for agency admins.
- Generate bot drafts from natural-language briefs.
- Generate prompt, knowledge outline, skills and integration checklist.
- Save generated output as editable draft.

## Testing Strategy

- Unit tests for WhatsApp payload routing by `phone_number_id`.
- Unit tests for client/bot permission checks.
- Unit tests for prompt loading fallback behavior.
- Unit tests for secret masking/redaction.
- Integration-style tests for generic REST connector using mocked HTTP.
- Manual WhatsApp tests for the default Asistto bot after every routing change.
- Manual simulator tests before enabling client editing in production.

## Success Criteria

The first successful version is complete when:

- One deployment can run at least two bots with different `phone_number_id`
  values.
- Humanio can create and manage clients/bots from the admin panel.
- A client can log in and only see their own bot data.
- A client can edit prompt, knowledge and allowed API integrations.
- Secrets are not printed, exposed in admin views or committed.
- The existing Asistto WhatsApp bot still works after migration.
