# ADR-0001 — Stack and retention direction

**Status:** Accepted  
**Date:** 2026-10-11

## Context

DocCite must answer questions only from uploaded documents, with citations.
We need a fast path to prove ingest → retrieve → cite → refuse, then a path to
multi-user storage with guest vs logged-in retention.

## Decision

### Local MVP (Steps 1–6)

| Layer | Choice |
| --- | --- |
| Language | Python 3.11+ |
| Orchestration | LangChain |
| Vectors | ChromaDB (local disk) |
| Embeddings / chat | OpenAI (`text-embedding-3-small`, `gpt-4o-mini`) |
| UI | Streamlit |
| Config | `pydantic-settings` + `.env` |

One local library, one Chroma collection. No production auth yet.

### After local MVP (Step 7+)

| Layer | Choice |
| --- | --- |
| API | FastAPI wrapping the same `src/` services |
| Database | SQLite first, Postgres-ready — users, sessions, documents, chats |
| Auth | Guest session + logged-in accounts |
| UI | Streamlit thin client, then optional React (Step 8) |

### Retention (product rule)

- **Guest:** uploads, vectors, and chat history purged after inactivity TTL.
- **Logged-in:** data remains until the user clears it (or account deletion later).

## Consequences

- Steps 0–6 stay small and learnable on one machine.
- Business logic must live in `src/`, not only in Streamlit, so Step 7 can wrap it.
- Changing embedding model later requires wipe + re-ingest of that collection.
