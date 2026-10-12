# DocCite — Build Plan and Progress Tracker

Cited document Q&A: upload PDFs / DOCX / TXT / MD, get a library summary, ask
questions answered **only** from those files, with citations (filename, page when
available, short quote). Outside the docs → refuse. Design detail lives in
[`APPROACH.md`](../APPROACH.md). This file is the single source of truth for
**where the build is**. It is updated at every milestone. Read the *Current
position* line first, then the step it points at.

## How to read this file

Status marks:

- `[ ]` not started
- `[~]` in progress
- `[x]` done and verified
- `[!]` blocked (reason given inline)

Every step lists: **Goal**, numbered **Tasks**, the **Artifact** it produces,
and a **Verify** command or check that proves it is done. Nothing is marked
`[x]` unless *Verify* passes.

Product rules that every later step obeys (see `APPROACH.md` §1.2–1.4):

1. No answer from general world knowledge — only retrieved excerpts.
2. Citations come from the **retriever**, not from model-invented pages.
3. PDF citations include **page numbers**; other types use filename + chunk.
4. **Guest** data is ephemeral (inactivity TTL purge). **Logged-in** data stays
   until the user clears it. Backend + database own files and chat history
   (Step 7); local Streamlit MVP (Steps 1–6) is single-user on disk first.

## Current position

> **Step 4 — Multi-file library, summary, reset: `[x]` done.**
> Next: **Step 5 — Streamlit UI.**
> Note: `.env` lines 18–20 are not `KEY=value` yet (email paste) — fix format
> when you want mail; not required for Steps 5–6.

## Prerequisites on the developer machine

Checked on **2026-10-11**. Status marks below mean: ready on this machine, or
action still needed from you.

| Tool | Why we need it | Needed from | Status |
| --- | --- | --- | --- |
| Python 3.11+ | Language for the whole app (ingest, RAG, CLI, later API) | Step 1 | `[x]` 3.12.0 |
| `pip` + `venv` | Install packages into an isolated project environment | Step 1 | `[x]` pip 23.2.1 + venv ok |
| OpenAI API key | Embeddings + chat LLM (live path) | Step 2+ | `[x]` present in `.env` (verified length; value never logged) |
| Git | Version history; Step 0 init | Step 0 | `[x]` 2.52.0 — repo on `main`, first commit done |
| Docker | Optional later (Compose / purge worker) | Step 7+ | `[x]` 29.4 — not needed for Steps 0–6 |
| Node 20+ | Optional later React UI | Step 8 | `[x]` 24.15 — not needed for Streamlit MVP |
| Streamlit | Upload + chat UI | Step 5 | `[x]` installed in project `venv` (Step 1) |
| `.gitignore` | Keeps `.env` and `data/` out of git | Step 0 | `[x]` added |
| `.env.example` | Template of required keys (no secrets) | Step 0 | `[x]` added |
| `.env` | Your real secrets + local settings | Step 1–2 | `[x]` key set; file gitignored |

### Prerequisites checklist

- `[x]` Tools on machine (Python, pip/venv, Git, Docker, Node)
- `[x]` `.gitignore`, `.env.example`, `.env` with `OPENAI_API_KEY`
- `[x]` Project `venv` + `pip install -r requirements.txt`

Optional later: OpenAI billing/credits so embed + chat calls succeed; Docker
Desktop running only when we reach Compose jobs.

### Mental model (learning)

- **`.env`** = secrets and knobs for *your machine*. Gitignored. Real key here.
- **`.env.example`** = same knobs with empty secrets. Safe to commit so others
  know what to configure.
- **`venv`** = a private Python “room” for this project so DocCite packages do
  not fight with other projects. We create it in Step 1.
- **OpenAI key** = not needed to finish Step 0 (folders/README), but required
  before live ingest/Q&A in Steps 2–3. Unit tests can mock the API; real demos
  cannot.

Folder names: single repo `DocCite/`. Core library under `src/`; CLIs under
`scripts/`; Streamlit entry `app.py`; FastAPI later under `api/` (Step 7).

Data: gitignored `data/` (`uploads/`, `chroma/`, `registry.json`). Secrets only
in `.env` (template `.env.example`).

Companion design doc: `APPROACH.md` (do not diverge from locked stack / rules
without an explicit decision note in the Progress log).

---

## Step 0 — Scope and repository foundation `[x]`

**Goal.** Lock what is being built, for whom, and the rules every later step
obeys. Produce the tracker and a place for code to land.

1. `[x]` 0.1 Write `APPROACH.md`: product rules, stack, data model, pipelines,
   phases, guest vs logged-in retention, Phase 6 backend outline.
2. `[x]` 0.2 Write this tracker (`docs/BUILD_PLAN.md`).
3. `[x]` 0.3 Initialize git repository (`main`), root `.gitignore`
   (`.env`, `venv/`, `data/`, `__pycache__/`, `.pytest_cache/`, `.streamlit/`).
4. `[x]` 0.4 Create empty package layout from `APPROACH.md` §3 (`src/`,
   `scripts/`, `tests/`, `data/` local dirs, empty `__init__.py` + placeholders).
5. `[x]` 0.5 `.env.example` with keys from `APPROACH.md` §2.4 (empty secrets).
6. `[x]` 0.6 Short `README.md`: one-paragraph product description, Python
   version, venv setup, copy `.env`, pointer to this tracker and `APPROACH.md`.
7. `[x]` 0.7 `docs/adr/0001-stack.md`: Python + LangChain + Chroma + OpenAI +
   Streamlit for local MVP; FastAPI + DB + auth in Step 7; guests TTL-purged,
   logged-in durable until self-clear.

**Artifact.** `APPROACH.md`, `docs/BUILD_PLAN.md`, repo skeleton, `.gitignore`,
`.env.example`, `README.md`, `docs/adr/0001-stack.md`.

**Verify.** Passed 2026-10-11: layout matches §3; `git check-ignore -v .env`
shows `.gitignore` rule; README has the one-paragraph product description;
branch is `main`.

---

## Step 1 — Toolchain, config, and domain models `[x]`

**Goal.** Empty app that imports, loads typed settings from `.env`, and defines
the pydantic/dataclass types used everywhere. No Streamlit, no OpenAI calls yet.

1. `[x]` 1.1 Create `venv`, activate, write `requirements.txt` (names from
   `APPROACH.md` §2.2), `pip install -r requirements.txt`. Pin versions with
   `pip freeze` → `requirements.lock.txt`.
2. `[x]` 1.2 `src/config.py` via `pydantic-settings`: `OPENAI_*`, chunk sizes,
   `RETRIEVE_TOP_K`, `SIMILARITY_THRESHOLD`, `DATA_DIR`, `CHROMA_DIR`,
   `UPLOAD_DIR`, `COLLECTION_NAME`. Ensures `data/` dirs; resolves relative
   paths against the repo root.
3. `[x]` 1.3 `src/logging_setup.py` — INFO default; no full document text at INFO.
4. `[x]` 1.4 `src/models.py` — `Document`, `Chunk`, `Citation`, `Answer` per
   `APPROACH.md` §4 (`owner_id` optional until Step 7).
5. `[x]` 1.5 Smoke: `python -c "from src.config import settings; print(settings.collection_name)"`.

**Artifact.** Working `venv/`, `requirements.txt`, `requirements.lock.txt`,
`src/config.py`, `src/logging_setup.py`, `src/models.py`.

**Verify.** Passed 2026-10-11: prints `doccite_mvp`; `key_loaded: True`;
`data/uploads` and `data/chroma` exist; models + logging import cleanly.
First `pip install` hit a network drop on `kubernetes`; retry with
`--resume-retries 20` succeeded. `.env` remains gitignored.

**Do not start Streamlit or ingest yet.**

---

## Step 2 — Ingest one PDF end-to-end (CLI) `[x]`

**Goal.** One PDF becomes persisted Chroma chunks with page metadata. Prove
extract → clean → chunk → embed → upsert → registry.

1. `[x]` 2.1 `src/ingest/extract.py` — PDF via PyMuPDF; 1-based pages; empty /
   scanned-all-empty fails with a clear error (OCR out of scope).
2. `[x]` 2.2 `src/ingest/clean.py` — light cleanup only (`APPROACH.md` §6.4).
3. `[x]` 2.3 `src/ingest/chunk.py` — recursive character split (~800 / 150);
   **per-page** PDF chunking; metadata on every chunk.
4. `[x]` 2.4 `src/store/chroma_store.py` — `add_chunks`, `query`, `count`,
   persist under `data/chroma`; page sentinel (`page=0` + `has_page=false`).
5. `[x]` 2.5 `src/store/registry.py` — JSON registry at `data/registry.json`.
6. `[x]` 2.6 `src/ingest/pipeline.py` — single-file path; all-or-nothing per
   `doc_id`; status `processing` → `ready` / `failed`; INFO timings.
7. `[x]` 2.7 `scripts/ingest.py` — `python scripts/ingest.py path/to/file.pdf`
   prints `doc_id`, pages, chunks, timings.
8. `[x]` 2.8 `tests/fixtures/two_page_fixture.pdf` (ALPHA/BRAVO tokens);
   `tests/test_extract.py`, `tests/test_chunk.py`; `scripts/make_fixture_pdf.py`.
9. `[x]` 2.9 Manual: ingest fixture → reopen store → `count()` unchanged →
   query `BRAVO-TOKEN-9` → `page==2`.

**Artifact.** PDF ingest CLI, Chroma persistence, registry, extract/chunk tests,
fixture PDF.

**Verify.** Passed 2026-10-12:

```bash
pytest tests/test_extract.py tests/test_chunk.py -q   # 4 passed
python scripts/ingest.py tests/fixtures/two_page_fixture.pdf
# count=2; BRAVO-TOKEN-9 → page 2; reopen count unchanged
```

Empty PDF raises `ExtractError`. Live OpenAI embeddings used for upsert.

**Do not build Q&A or UI yet.**

---

## Step 3 — Ask one question (CLI) `[x]`

**Goal.** Grounded answer + citations from retrieved chunks; refusal when
unsupported. Still CLI-only.

1. `[x]` 3.1 `src/rag/retrieve.py` — embed query, top_k, scores; cosine
   distance filtered with `SIMILARITY_THRESHOLD` as min similarity
   (`distance <= 1 - threshold`); zero hits → no chat call.
2. `[x]` 3.2 `src/rag/prompt.py` — system prompt (answer only from excerpts;
   refuse if insufficient) + context packer
   (`[Source N] file=... page=...`).
3. `[x]` 3.3 `src/rag/qa.py` — retrieve → generate → `Answer` with citations
   **from hits**; `refused=True` path; one OpenAI retry on transient errors.
4. `[x]` 3.4 `scripts/ask.py` — prints answer, citations, timings, tokens.
5. `[x]` 3.5 Happy path: BRAVO-TOKEN-9 → answer + page=2 citation. Out-of-domain
   France → refusal with `generate_ms=0` (no LLM).
6. `[x]` 3.6 `tests/test_retrieve.py`, `tests/test_qa_refusal.py` (mocked store/LLM).

**Artifact.** `scripts/ask.py`, retrieve + QA modules, refusal tests.

**Verify.** Passed 2026-10-12:

```bash
pytest tests/test_retrieve.py tests/test_qa_refusal.py -q   # 7 passed
python scripts/ask.py "What does page two say about BRAVO-TOKEN-9?"
python scripts/ask.py "What is the capital of France?"       # refused, no LLM
```

Empty collection → “Upload documents first.” Citations from retriever metadata.

**Do not build the UI yet.**

---

## Step 4 — Multi-file library, summary, reset `[x]`

**Goal.** Real library behavior: four file types, replace-on-duplicate,
sampled library summary, full reset.

1. `[x]` 4.1 DOCX / TXT / MD extractors in `extract.py`; unsupported → failed
   “Unsupported file type”; empty text → failed; max **25 MB** enforced.
2. `[x]` 4.2 Pipeline accepts file or directory; duplicate filename → delete
   old chunks + replace; `delete_by_doc_id` on replace and failed rollback.
3. `[x]` 4.3 `src/rag/summarize.py` — sample first + middle chunk per doc; LLM
   bullets; cache (`data/summary.json` keyed by hash of ready `doc_id`s).
4. `[x]` 4.4 `scripts/summarize.py`, `scripts/reset.py` (wipe Chroma, uploads,
   registry, summary cache).
5. `[x]` 4.5 Ingested fixtures (2 PDFs + TXT + MD + DOCX); summarize; asked
   DELTA-TOKEN-3 and ZEBRA-TOKEN-9; reset → count 0, uploads gone.
6. `[x]` 4.6 `tests/test_unsupported.py` (+ multi-type extract coverage).

**Artifact.** Multi-type ingest, summary CLI, reset CLI, replace semantics,
extra fixtures under `tests/fixtures/`.

**Verify.** Passed 2026-10-12:

```bash
pytest -q   # 15 passed (unit suite)
python scripts/reset.py
python scripts/ingest.py tests/fixtures/
python scripts/summarize.py
python scripts/ask.py "What is DELTA-TOKEN-3?"
python scripts/ask.py "Where does ZEBRA-TOKEN-9 appear?"
python scripts/reset.py   # chroma=0, docs=0, uploads=0
```

---

## Step 5 — Streamlit UI `[ ]`

**Goal.** A person can use the product without the terminal. Single page
`app.py` per `APPROACH.md` §10.

1. `[ ]` 5.1 Layout: header **DocCite**; sidebar uploader + doc list + Clear;
   main summary + chat + question input.
2. `[ ]` 5.2 Upload → save under `data/uploads/` → `pipeline.ingest` → refresh
   list + regenerate/cached summary; statuses `processing` / `ready` / `failed`.
3. `[ ]` 5.3 Chat wired to `qa.answer`; citation cards (filename, page or n/a,
   quote); refused styling; spinners.
4. `[ ]` 5.4 Disable Ask when no `ready` documents; Clear uses same reset as
   CLI and clears chat history in `st.session_state`.
5. `[ ]` 5.5 Sanitized errors for OpenAI / empty library (no stack traces in UI).
6. `[ ]` 5.6 Click-test full journey: upload, summary, ask, refuse, clear,
   browser refresh still shows documents (disk persist).

**Artifact.** `app.py`, `src/ui/helpers.py`, runnable local demo UI.

**Verify.**

```bash
streamlit run app.py
```

Walk `APPROACH.md` §15 items 1–10 manually. Refresh keeps documents. Clear
resets list, summary, and chat.

This step is not done after a screenshot — walk the flow as a user.

---

## Step 6 — Hardening and local MVP definition of done `[ ]`

**Goal.** Safe to demo; README enough for a clean machine; still single-user
local (no multi-tenant auth yet).

1. `[ ]` 6.1 One retry with short backoff on transient OpenAI errors; then fail
   with a user-safe message.
2. `[ ]` 6.2 Guard empty / whitespace-only questions; cap chat display to last N
   messages.
3. `[ ]` 6.3 README “try this” with the fixture PDF (commands + expected
   refusal example).
4. `[ ]` 6.4 Full `pytest` (unit + optional integration with key).
5. `[ ]` 6.5 Run manual QA script `APPROACH.md` §15 end-to-end; fix gaps.
6. `[ ]` 6.6 Confirm §14 definition of done (upload types, summary, cite,
   refuse, clear, persist, no empty-context answers, logs, tests).

**Artifact.** Hardened demo, complete README, green test suite, QA notes in
Progress log.

**Verify.**

```bash
pytest -q
# Manual: APPROACH.md §15 checklist all pass
```

Bad PDF / empty file / huge file / bad API key fail gracefully. Section 14
items 1–9 true → local MVP complete; only then start Step 7.

---

## Step 7 — Backend, database, guest TTL, logged-in persistence `[ ]`

**Goal.** Multi-user DocCite: FastAPI owns business logic; database stores
users, sessions, document metadata, and recent chat histories; vector store
namespaced by owner. Guests auto-purged; logged-in data stays until self-clear.

### 7.A API and ownership

1. `[ ]` 7.1 FastAPI app (`api/` or `src/api/`) wrapping existing `src/ingest`,
   `src/rag`, `src/store` — Streamlit must not own business logic anymore
   (thin client or deferred UI swap).
2. `[ ]` 7.2 `owner_id` on documents and chunks (`user:<id>` / `guest:<session_id>`);
   all retrieve / delete / summarize scoped by owner. Guest A never sees B/C.
3. `[ ]` 7.3 Endpoints: session/auth, upload, list docs, summarize, ask,
   list/clear chats, clear library. Touch `last_active_at` on guest activity.

### 7.B Database and files

4. `[ ]` 7.4 Database (SQLite first via `DATABASE_URL`, Postgres-ready): tables
   `users`, `sessions` (`last_active_at`), `documents`, `chat_threads`,
   `chat_messages`, optional `library_summaries`. Migrations (Alembic or
   equivalent).
5. `[ ]` 7.5 Uploads on disk (or object storage later) keyed by owner; Chroma
   filter / collection namespace by `owner_id`.
6. `[ ]` 7.6 Persist recent chat messages for guests and users; UI loads history
   from API, not only browser memory.

### 7.C Auth and retention

7. `[ ]` 7.7 Guest: anonymous session cookie / token; no password. Logged-in:
   minimal auth (email+password or magic-link — pick one; document in ADR).
8. `[ ]` 7.8 Config `GUEST_INACTIVITY_TTL_HOURS` (default 24). Background job /
   cron: purge expired **guest** owners only — files, vectors, DB rows (docs +
   chats + session). Logged-in **never** auto-purged.
9. `[ ]` 7.9 Logged-in clear library deletes only that user’s files, vectors,
   and related chats. Guest clear does the same for that session.
10. `[ ]` 7.10 Tests: cross-tenant isolation; guest purge removes all three
    stores; logged-in survives TTL job; clear is owner-scoped.
11. `[ ]` 7.11 Guest UX copy: data is temporary and removed after inactivity.
    Update README for API + retention.

**Artifact.** FastAPI service, DB schema + migrations, owner-scoped Chroma,
guest purge job, auth/session, API tests for isolation and retention.

**Verify.**

```bash
# Example shape — adjust to whatever Makefile/scripts Step 7 adds:
pytest tests/test_owner_isolation.py tests/test_guest_purge.py -q
# Manual:
# 1) Guest upload + ask → force purge / expire TTL → DB + disk + Chroma empty for that guest
# 2) Logged-in upload + ask → wait / run purge job → data still present
# 3) Logged-in clear → only that user gone
# 4) Guest A cannot retrieve Guest B / User C chunks
```

**Acceptance (must all pass before marking Step 7 `[x]`):**

- [ ] Guest upload + ask works; after TTL (or forced purge), guest data gone
      from DB, disk, and vector store
- [ ] Logged-in user returns later and still sees files + recent chats
- [ ] Logged-in clear library removes only that user’s data
- [ ] Guest A cannot retrieve Guest B / User C chunks

---

## Step 8 — Production-shaped frontend (optional after Step 7) `[ ]`

**Goal.** Replace or complement Streamlit with a proper web UI against the
FastAPI API. Same product rules; guest vs login visible in UX.

1. `[ ]` 8.1 Scaffold frontend (Vite + React + TypeScript recommended) talking
   only to the API.
2. `[ ]` 8.2 Screens: upload + doc list, library summary, chat with citations,
   clear library, guest banner (TTL notice), login / logout.
3. `[ ]` 8.3 Load recent chats for logged-in users; guest session restore until
   TTL.
4. `[ ]` 8.4 `npm run build` green; smoke against local API.

**Artifact.** Frontend app folder; README run instructions for API + UI.

**Verify.** `npm run build` passes; manual walk of guest + logged-in journeys
against Step 7 API.

---

## Step 9 — Scale and quality backlog (do not start early) `[ ]`

**Goal.** Keep post-MVP improvements queued so Steps 1–7 stay small. Pick up
only after Step 7 Verify passes and real usage shows need.

1. `[ ]` 9.1 Hybrid search + re-ranker (after measuring citation misses).
2. `[ ]` 9.2 OCR path for scanned PDFs (empty-PDF failure already exists).
3. `[ ]` 9.3 Remote vector DB (Pinecone / PGVector / Qdrant) behind the store
   interface from `APPROACH.md` §8.3.
4. `[ ]` 9.4 Local LLM (Ollama) provider switch for zero-OpenAI demos.
5. `[ ]` 9.5 Query cache / Redis when repeat questions hurt cost.
6. `[ ]` 9.6 Docker Compose one-command demo (API + DB + purge worker + UI).
7. `[ ]` 9.7 Production SSO / compliance workflows (out of current product
   scope until requested).

**Artifact.** Per-item ADR + eval note when each is taken up.

**Verify.** Defined per item when scheduled; do not mark done from this backlog
without its own Verify.

---

## Progress log

| Date | Step | Note |
| --- | --- | --- |
| 2026-10-11 | 0 | `APPROACH.md` written (product rules, stack, pipelines, guest TTL vs logged-in persistence, Phase 6 backend outline). `docs/BUILD_PLAN.md` created as progress tracker. Repo still skeleton-only otherwise. |
| 2026-10-11 | Prerequisites | Verified Python 3.12, pip/venv, Git, Docker, Node. Added `.gitignore`, `.env.example`, and `.env` template. **Blocked on user pasting `OPENAI_API_KEY` into `.env`** (file was empty). |
| 2026-10-11 | 0 | Git init (`main`), package layout + placeholders, `README.md`, `docs/adr/0001-stack.md`. Verify passed. `OPENAI_API_KEY` still empty (ok until Step 2). No commit yet — ask before first commit. |
| 2026-10-11 | 0 | First commit `d4d852c` (`.env` excluded). User confirmed OpenAI key in `.env`. |
| 2026-10-11 | 1 | `venv` + deps installed (`requirements.lock.txt`); `config` / `logging_setup` / `models` implemented. Smoke: `doccite_mvp`, key loaded, data dirs created. |
| 2026-10-12 | 1 | Commit `e859930` Step 1 toolchain. |
| 2026-10-12 | 2 | PDF ingest path live: extract/clean/chunk/Chroma/registry + CLI. Fixture PDF with page tokens. 4 unit tests green; ingest → 2 chunks; `BRAVO-TOKEN-9` retrieves page 2; persist survives reopen. |
| 2026-10-12 | 2 | Commit `f550de6` Step 2 PDF ingest. |
| 2026-10-12 | 3 | Retrieve + grounded QA CLI. 7 unit tests green. Live: BRAVO question cites page 2; France refuses without LLM call. |
| 2026-10-12 | 3 | Commit `728de89` Step 3 Q&A. |
| 2026-10-12 | 4 | Multi-type ingest (pdf/docx/txt/md), summary cache, reset. 15 unit tests green. Folder ingest + cross-doc ask + wipe verified. `.env` lines 18–20 not KEY=value (email paste) — parked; template in `.env.example`. |

---

## Quick reference — step ↔ APPROACH phase

| Build plan step | APPROACH.md | Outcome |
| --- | --- | --- |
| 0 | §1–3, §20 | Scope, layout, tracker |
| 1 | Phase 0 | Config + models |
| 2 | Phase 1 | PDF → Chroma CLI |
| 3 | Phase 2 | Ask + refuse CLI |
| 4 | Phase 3 | Multi-type + summary + reset |
| 5 | Phase 4 | Streamlit UI |
| 6 | Phase 5 + §14–15 | Hardened local MVP |
| 7 | §1.4 + §18.1 | FastAPI + DB + retention |
| 8 | §18 (frontend) | React (or similar) UI |
| 9 | §18 backlog | Scale items |

Next concrete action: **finish Step 0** (git, folders, `.gitignore`,
`.env.example`, README), then **Step 1 only** — venv, requirements, config,
models. Do not skip ahead to Streamlit or FastAPI.
