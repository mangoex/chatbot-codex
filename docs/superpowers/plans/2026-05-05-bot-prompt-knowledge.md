# Bot Prompt and Knowledge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each WhatsApp bot use an editable prompt and knowledge base stored in Postgres, managed from the admin panel without redeploying.

**Architecture:** Add DB helpers for active prompt and knowledge documents, then add a small `app/bot_content.py` runtime builder that falls back to file prompts when a bot has no DB content. Extend the existing FastAPI admin with bot-scoped editor pages guarded by existing agency/client permissions.

**Tech Stack:** FastAPI, asyncpg/Postgres, server-rendered HTML, unittest.

---

### Task 1: Runtime Bot Content

**Files:**
- Create: `app/bot_content.py`
- Modify: `app/db.py`
- Modify: `app/openai_client.py`
- Modify: `app/main.py`
- Test: `tests/test_bot_content.py`

- [x] Add DB helpers for prompt and knowledge:
  - `get_active_bot_prompt(bot_id)`
  - `publish_bot_prompt(bot_id, content)`
  - `list_bot_knowledge(bot_id, active_only=True)`
  - `get_bot_knowledge(bot_id, knowledge_id)`
  - `create_bot_knowledge(bot_id, title, content)`
  - `update_bot_knowledge(bot_id, knowledge_id, title, content, status='active')`
  - `archive_bot_knowledge(bot_id, knowledge_id)`
- [x] Add `app/bot_content.py` with `combine_prompt(base_prompt, knowledge_docs)` and `system_prompt_for_bot(bot_id)`.
- [x] Update `openai_client.complete(..., bot_id=None)` to call the bot-specific system prompt.
- [x] Pass `bot.id` from `app/main.py` into `openai_client.complete`.
- [x] Add unit tests for prompt/knowledge combination and fallback behavior.

### Task 2: Admin Editor

**Files:**
- Modify: `app/admin.py`

- [x] Add editor permission helper: agency admins and client admins may edit; client viewers may only see existing bot dashboards.
- [x] Add action links on `/admin/bots/{bot_id}` for "Prompt" and "Base de conocimiento".
- [x] Add `GET/POST /admin/bots/{bot_id}/prompt` to view and publish the active prompt.
- [x] Add `GET/POST /admin/bots/{bot_id}/knowledge` to list and create knowledge documents.
- [x] Add `GET/POST /admin/bots/{bot_id}/knowledge/{knowledge_id}` to edit one knowledge document.
- [x] Add `POST /admin/bots/{bot_id}/knowledge/{knowledge_id}/archive` to archive a document.

### Task 3: Docs and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/HANDOFF.md`
- Modify: `tests/test_db_multibot_schema.py`

- [x] Document the new admin endpoints and behavior.
- [x] Add DB helper signature tests.
- [x] Run:
  - `/Users/miguelgonzalez/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m compileall app`
  - `/Users/miguelgonzalez/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -v`
  - `rg -n "sk-|ghp_|github_pat_|EAA|token_real|password_real|secret_real|api_key_real" README.md .env.example docs prompts app tests Dockerfile requirements.txt`
