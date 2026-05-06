# Multi-Bot Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the first usable agency/client dashboard for managing multi-bot clients without changing the existing WhatsApp runtime behavior.

**Architecture:** Keep the current admin panel and session middleware, then add role-aware login, client/bot CRUD helpers, agency-only management pages, and client-scoped bot detail pages. Existing Asistto admin credentials remain the agency admin fallback.

**Tech Stack:** FastAPI HTML routes, Starlette sessions, Postgres via asyncpg, stdlib password hashing, unittest.

---

## Scope

In scope:

- Agency admin login with existing `ADMIN_USER`/`ADMIN_PASSWORD`.
- Client user login from Postgres `users` + `client_users`.
- Agency pages to list/create clients and bots.
- Agency page to create client admin/viewer users.
- Bot detail page with scoped conversations and leads.
- Client users can see only bots for their client.
- Tests for password hashing and new DB helper signatures.

Out of scope:

- Prompt editor.
- Knowledge editor.
- Generic API integration UI.
- Conversational Studio.
- Billing and advanced permissions.

## Tasks

1. Add `app/auth.py` with password hashing and verification.
2. Add DB helpers for clients, bots, users and bot-scoped lead/conversation views.
3. Update admin session logic to support `agency_admin`, `client_admin`, and `client_viewer`.
4. Add `/admin/clients`, `/admin/clients/{id}`, `/admin/bots`, `/admin/bots/{id}`.
5. Add client-scoped navigation and permission checks.
6. Add tests and docs.
7. Verify with `compileall` and `unittest`.
