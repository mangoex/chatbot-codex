# Bot Skills Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn saved bot integrations into runtime skills, starting with per-bot Google Calendar scheduling and cancellation.

**Architecture:** Add helpers for `bot_skills` and encrypted integration secret lookup. Add a small runtime skill resolver that defaults existing bots to current behavior, then refactor `calendar_client` to use bot-specific Google Calendar integration when configured and fall back to global environment variables otherwise.

**Tech Stack:** FastAPI, asyncpg/Postgres, httpx, Google Calendar API, server-rendered HTML, unittest.

---

### Task 1: DB Runtime Helpers

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_db_multibot_schema.py`

- [x] Add helpers for active integration lookup and encrypted secret map lookup.
- [x] Add helpers for listing and upserting bot skills.
- [x] Keep existing global Asistto behavior as the default when no bot skill row exists.

### Task 2: Skill Runtime Resolver

**Files:**
- Create: `app/skill_runtime.py`

- [x] Add `skill_enabled(bot_id, skill_type, default=True)`.
- [x] Add `calendar_skill_enabled(bot_id)`.
- [x] Make disabled skills return deterministic, user-safe fallback messages.

### Task 3: Per-Bot Calendar Runtime

**Files:**
- Modify: `app/calendar_client.py`
- Modify: `app/agenda_guard.py`

- [x] Add runtime calendar settings from either bot integration or global env.
- [x] Decrypt `client_secret` and `refresh_token` from integration secrets.
- [x] Use integration config for `calendar_id`, `timezone`, appointment duration, buffer and summary prefix.
- [x] Keep global calendar diagnostics working.
- [x] Make scheduling/cancellation use the bot-specific runtime when `bot_id` is present.

### Task 4: Admin Skill Panel

**Files:**
- Modify: `app/admin.py`

- [x] Add `/admin/bots/{bot_id}/skills`.
- [x] Add link from bot detail to Habilidades.
- [x] Allow agency and `client_admin` to enable/disable `google_calendar`.

### Task 5: Docs and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/HANDOFF.md`

- [x] Document the runtime behavior and required integration fields/secrets.
- [x] Run compile, unit tests and secret scan.
