# ADR-0002 — Auth and retention

**Status:** Accepted  
**Date:** 2026-10-12

## Context

After the local Streamlit MVP, DocCite needs multi-user storage with different
lifetimes for guests and logged-in users.

## Decision

- **API:** FastAPI owns ingest / ask / summarize / clear (business logic).
- **DB:** SQLite first (`DATABASE_URL`), SQLAlchemy models; `create_all` as the
  initial schema bootstrap (Alembic can replace later).
- **Auth:** Opaque session tokens (`X-DocCite-Session` or `Authorization: Bearer`).
  - Guest: `POST /auth/guest` → `owner_id=guest:<session_id>`
  - Logged-in: email + password (`POST /auth/register`, `/auth/login`) →
    `owner_id=user:<user_id>`
- **Vectors:** Chroma metadata `owner_id`; all queries/deletes filtered by owner.
- **Retention:**
  - Guests purged when `last_active_at` older than `GUEST_INACTIVITY_TTL_HOURS`
    (`scripts/purge_guests.py` or `POST /admin/purge-guests`).
  - Logged-in data never auto-purged; only explicit clear / future account delete.

## Consequences

- Streamlit remains a local demo path; production clients should use the API.
- Guest UX must disclose temporary storage.
- Cron/ops must run the purge job regularly in deployed environments.
