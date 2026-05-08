# External API CRM Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each WhatsApp bot call a configured webhook, external API, or CRM using its own integration secrets.

**Architecture:** The LLM emits explicit internal markers only when a skill is enabled. A new runtime module removes those markers from the user-visible reply, resolves the active bot integration, decrypts secrets, and performs the HTTP request without logging secret values.

**Tech Stack:** FastAPI, async Python, Postgres integration rows, encrypted integration secrets, httpx, unittest.

---

### Task 1: Marker Parser And Runtime

**Files:**
- Create: `app/external_actions.py`
- Test: `tests/test_external_actions.py`

- [x] Write failing tests for marker stripping, request payload parsing, and secret-backed headers.
- [x] Implement marker parsing and execution helpers.
- [x] Run the focused test file until green.

### Task 2: Wire Into Bot Runtime

**Files:**
- Modify: `app/main.py`
- Modify: `app/openai_client.py`
- Modify: `app/skill_runtime.py`
- Modify: `app/admin.py`
- Test: `tests/test_db_multibot_schema.py`

- [x] Add external skill toggles with safe defaults.
- [x] Add skill cards for webhook, external API, and CRM.
- [x] Append system instructions only when the bot has active external skills.
- [x] Process markers before sending the final WhatsApp reply.

### Task 3: Docs And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/HANDOFF.md`

- [x] Document JSON config examples and marker formats.
- [ ] Run compile, unit tests, and secret scan.
- [ ] Commit and push the branch for review.
