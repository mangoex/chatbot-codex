# Bot Integrations Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let agency and client admins configure per-bot integrations from the admin panel without committing secrets or redeploying for every client.

**Architecture:** Reuse `bot_integrations` and `integration_secrets` tables. Store public/non-secret integration configuration in JSONB, store secret values encrypted with `INTEGRATION_SECRET_KEY`, and expose bot-scoped admin routes under `/admin/bots/{bot_id}/integrations`.

**Tech Stack:** FastAPI, asyncpg/Postgres, JSONB, cryptography/Fernet, server-rendered HTML, unittest.

---

### Task 1: Secret Encryption

**Files:**
- Modify: `app/config.py`
- Create: `app/secret_store.py`
- Modify: `.env.example`
- Modify: `requirements.txt`

- [x] Add `INTEGRATION_SECRET_KEY` environment variable.
- [x] Implement Fernet encryption/decryption derived from `INTEGRATION_SECRET_KEY`, falling back to `SESSION_SECRET`.
- [x] Keep secret values write-only in UI and docs.

### Task 2: Integration DB Helpers

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_db_multibot_schema.py`

- [x] Add helpers to list, create, read, update, archive integrations.
- [x] Add helpers to upsert, list and delete secret names for an integration.
- [x] Store integration `config` through `$n::jsonb`.

### Task 3: Admin Integration Panel

**Files:**
- Modify: `app/admin.py`

- [x] Add link from `/admin/bots/{bot_id}` to integrations.
- [x] Add `/admin/bots/{bot_id}/integrations` list/create page.
- [x] Add `/admin/bots/{bot_id}/integrations/{integration_id}` edit page.
- [x] Add write-only secret form for API tokens, client secrets, refresh tokens or custom names.
- [x] Guard writes with existing bot editor permissions.

### Task 4: Docs and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/HANDOFF.md`

- [x] Document the new `INTEGRATION_SECRET_KEY`.
- [x] Document the new admin routes and purpose.
- [x] Run compile, unit tests and secret scan.
