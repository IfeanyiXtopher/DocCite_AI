# DocCite — MVP Step-by-Step Approach

**Project name:** DocCite  
**Repository / folder name:** `DocCite`

**Product (MVP):** A user uploads documents. The system extracts text, chunks and embeds it, stores it locally, produces a short summary of the uploaded library, and answers questions **only** from those documents. Every answer includes citations (filename, page number when available, short quote). If the documents do not contain the answer, the system refuses.

**Out of scope for the local Streamlit MVP loop (Phases 0–5):** production auth, compliance workflows, hybrid search, re-rankers, agents, OCR for scanned PDFs, live URL/Confluence ingestion, and production SSO. Prove ingest → retrieve → cite → refuse first.

**Product direction after that loop (Phase 6+):** a real backend + database, guest vs logged-in users, and the retention rules in section 1.4. Do not treat “local single-user forever” as the end state.

This document is the design bible (rules, stack, pipelines). For **where the build is** and step checklists with Verify commands, use [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md). Follow steps in order; do not skip a step’s Verify.

---

## 1. What we are building

### 1.1 User journey

1. Open the app.
2. Upload one or more files (`.pdf`, `.docx`, `.txt`, `.md`).
3. Watch each file move through `processing` → `ready` or `failed`.
4. Read an automatic **library summary** (what was uploaded and what it covers).
5. Ask a question in chat.
6. Receive an answer grounded only in retrieved excerpts, plus citations.
7. Ask something outside the documents and get a clear refusal.
8. Optionally clear the library and start over.
9. **Guest:** work without an account; after they finish or go inactive long enough, the system deletes their uploads, vectors, and chat history.
10. **Logged-in:** uploads, library, and recent chat history stay until the user clears them.

### 1.2 Non-negotiable product rules

- The model must **not** use general world knowledge to fill gaps.
- Answers must cite sources that were actually retrieved.
- PDF citations must include **page numbers**.
- DOCX / TXT / MD citations use **filename + chunk/section** (no fake page numbers).
- Empty, encrypted, or unreadable files fail visibly. They must not silently produce empty embeddings.
- The same embedding model is used at ingest and at query time.
- Only retrieved chunks are sent to the LLM for Q&A — never the entire library on every question.
- Guest data is **ephemeral** (TTL / inactivity cleanup). Logged-in data is **durable** until the user deletes it.
- User files and recent chat histories are stored in a **backend + database** (not only browser / Streamlit session) once multi-user is enabled.

### 1.3 Answer contract

Every successful answer has three parts:

1. **Answer** — concise, only from retrieved text.
2. **Citations** — `filename`, `page` (if PDF), `chunk_index`, and a short quote.
3. **Refusal** — if retrieval is weak or the excerpts do not support an answer:

   > I don’t have that in your uploaded documents.

### 1.4 User modes and data retention (product rules)

These rules are locked for the product. The local Streamlit MVP may still use one shared disk library; Phase 6 implements them with backend + DB.

| Mode | Identity | Files + vectors | Chat history | Cleared when |
|------|----------|-----------------|--------------|--------------|
| **Guest** | Anonymous session id (cookie / server session) | Scoped to that guest session | Stored for that session | User clears, **or** inactivity TTL expires (system job deletes uploads, chunks, registry rows, chat) |
| **Logged-in** | Authenticated user id | Owned by that user | Recent histories kept for that user | **Only** when the user clears library / deletes a chat (or account deletion later) |

**Guest cleanup**

- After the guest is done, or inactive for a configured TTL (e.g. 24h without activity — tune in config), a background job must purge:
  - uploaded files
  - vector chunks / collection namespace for that session
  - document registry rows
  - chat messages for that session
- Guests must not accumulate unbounded data on disk or in the DB.

**Logged-in persistence**

- Uploads and embeddings remain across browser restarts and devices (once auth + backend exist).
- Recent chat histories remain until the user clears them.
- “Clear library” deletes that user’s files + vectors + related chats (or only library — product choice: default = clear docs + chats tied to that library).

**Storage implication**

Streamlit `st.session_state` alone is **not** enough for multi-user. Phase 6 requires:

- a **backend API** (FastAPI) that owns ingest, RAG, clear, and auth
- a **database** for users, sessions, document metadata, and chat messages
- object / file storage for uploads (local disk or S3-compatible later)
- per-user / per-guest namespacing in the vector store

---

## 2. Locked tech stack

Use this stack for the MVP. Do not swap pieces mid-build unless a dependency is blocked.

| Layer | Choice | Version target | Why |
|-------|--------|----------------|-----|
| Language | Python | 3.11+ | RAG ecosystem, loaders, typing |
| Package manager | `pip` + `venv` | — | Simple, no extra toolchain |
| Config / secrets | `python-dotenv` + `.env` | latest compatible | API keys stay out of git |
| Settings objects | `pydantic-settings` | v2 | Typed config (chunk size, models, paths) |
| Orchestration | LangChain | 0.3.x | loaders, splitters, retriever, RAG chain |
| LangChain extras | `langchain-openai`, `langchain-chroma`, `langchain-text-splitters`, `langchain-community` | matching 0.3 | Official integrations |
| Vector store | ChromaDB | 0.5.x+ | Local, persisted on disk, no cloud account |
| Embeddings | OpenAI `text-embedding-3-small` | API | Cheap, consistent, good enough for MVP |
| Chat LLM | OpenAI `gpt-4o-mini` | API | Fast/cheap for grounded Q&A and summaries |
| PDF extraction | PyMuPDF (`fitz`) | latest stable | Reliable per-page text |
| DOCX extraction | `python-docx` | latest stable | Paragraph text from Word |
| Token counting | `tiktoken` | latest compatible | Chunk sizing and cost logs |
| UI | Streamlit | 1.38+ | Fastest path to upload + chat |
| Logging | Python `logging` | stdlib | Stage timings and errors |
| Tests | `pytest` | latest | Ingest / retrieve / refuse checks |

### 2.1 Explicitly not in the local MVP stack (Phases 0–5)

| Deferred | When to add |
|----------|-------------|
| FastAPI backend + database (Postgres/SQLite) | **Phase 6** — user files + chat history + guest TTL |
| Auth (guest session + login) | **Phase 6** — retention rules in section 1.4 |
| React (or other) frontend | After FastAPI services wrap the same `src/` RAG code |
| Pinecone / PGVector / Qdrant | When you need remote / multi-tenant vector scale |
| LlamaIndex | Not needed if LangChain covers loaders + RAG |
| Hybrid BM25 / re-ranker | After citation quality is measured |
| Local LLM (Ollama) | If you want zero OpenAI cost later |
| OCR (`tesseract` / `unstructured`) | When scanned PDFs appear |
| Redis / query cache | When repeat questions become a cost issue |
| Docker Compose | When you want one-command demos / jobs |

### 2.2 Python dependencies to install (Phase 0)

```
python>=3.11
langchain
langchain-openai
langchain-chroma
langchain-text-splitters
langchain-community
chromadb
openai
tiktoken
pymupdf
python-docx
python-dotenv
pydantic-settings
streamlit
pytest
```

Pin exact versions in `requirements.txt` when you first get a working install (`pip freeze` of the venv after a successful run). Until then, the names above are the lock.

### 2.3 External services

- **OpenAI API key** in `.env` as `OPENAI_API_KEY`.
- No other cloud accounts for MVP.
- Internet is required only for OpenAI calls.

### 2.4 Runtime environment variables

```
OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-4o-mini
CHUNK_SIZE=800
CHUNK_OVERLAP=150
RETRIEVE_TOP_K=6
SIMILARITY_THRESHOLD=0.25
DATA_DIR=./data
CHROMA_DIR=./data/chroma
UPLOAD_DIR=./data/uploads
COLLECTION_NAME=doccite_mvp
```

Phase 6+ (backend / retention) will add settings such as:

```
GUEST_INACTIVITY_TTL_HOURS=24
DATABASE_URL=sqlite:///./data/doccite.db
# later: postgresql://...
AUTH_SECRET=
```

`SIMILARITY_THRESHOLD` is a first guess. Tune it in Phase 2 using real docs. Distance metrics differ by Chroma space; implement thresholding against the score Chroma actually returns and document the direction (higher similarity vs lower distance) in code comments.

---

## 3. Repository layout

Create this layout in Phase 0. Empty `__init__.py` files make packages importable.

```
DocCite/
├── APPROACH.md                 # this document
├── README.md                   # how to run (written at end of Phase 0)
├── requirements.txt
├── .env.example                # keys with empty values
├── .gitignore                  # .env, data/, venv, __pycache__, .streamlit
├── app.py                      # Streamlit entry (Phase 4)
├── src/
│   ├── __init__.py
│   ├── config.py               # pydantic settings
│   ├── logging_setup.py
│   ├── models.py               # dataclasses / pydantic: Document, Chunk, Citation, Answer
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── extract.py          # PDF / DOCX / TXT / MD → pages or blocks
│   │   ├── clean.py            # light text cleanup
│   │   ├── chunk.py            # split + attach metadata
│   │   └── pipeline.py         # extract → clean → chunk → embed → upsert
│   ├── store/
│   │   ├── __init__.py
│   │   ├── chroma_store.py     # add, query, delete, persist
│   │   └── registry.py         # document registry (JSON or SQLite)
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── retrieve.py
│   │   ├── summarize.py
│   │   ├── prompt.py           # system + user prompt templates
│   │   └── qa.py               # retrieve → generate → parse citations
│   └── ui/
│       ├── __init__.py
│       └── helpers.py          # Streamlit formatting helpers
├── scripts/
│   ├── ingest.py               # CLI: ingest one file or a folder
│   ├── ask.py                  # CLI: ask a question
│   ├── summarize.py            # CLI: print library summary
│   └── reset.py                # CLI: wipe uploads + chroma + registry
├── tests/
│   ├── fixtures/               # tiny sample pdf/txt (created in Phase 1)
│   ├── test_extract.py
│   ├── test_chunk.py
│   ├── test_retrieve.py
│   └── test_qa_refusal.py
└── data/                       # gitignored
    ├── uploads/
    ├── chroma/
    └── registry.json
```

---

## 4. Data model

### 4.1 Document (registry)

| Field | Type | Notes |
|-------|------|--------|
| `doc_id` | `str` | UUID |
| `filename` | `str` | Original name |
| `stored_path` | `str` | Path under `data/uploads/` |
| `file_type` | `pdf` \| `docx` \| `txt` \| `md` | From extension |
| `size_bytes` | `int` | |
| `page_count` | `int` \| `null` | PDFs only |
| `chunk_count` | `int` | After ingest |
| `status` | `processing` \| `ready` \| `failed` | |
| `error` | `str` \| `null` | User-visible reason if failed |
| `uploaded_at` | ISO datetime | |
| `ingested_at` | ISO datetime \| `null` | |
| `owner_id` | `str` \| omit in local MVP | Phase 6: `user:<id>` or `guest:<session_id>` |

Store the registry as `data/registry.json` for the local MVP. One file, easy to inspect. Phase 6 moves documents + chats into a real database (SQLite → Postgres) and namespaces vectors by `owner_id`.

### 4.2 Chunk (vector store metadata + document)

| Field | Type | Notes |
|-------|------|--------|
| `chunk_id` | `str` | `{doc_id}:{chunk_index}` |
| `doc_id` | `str` | |
| `filename` | `str` | |
| `file_type` | `str` | |
| `page` | `int` \| `null` | 1-based page for PDFs |
| `chunk_index` | `int` | 0-based in that document |
| `text` | `str` | The chunk body |
| `embedding` | vector | Stored by Chroma, not in registry |

Chroma document = `text`. Chroma id = `chunk_id`. Chroma metadata = all fields except `text` and `embedding`.

Chroma metadata values must be scalars (`str`, `int`, `float`, `bool`). Store missing page as a sentinel (e.g. page `0` plus `has_page: false`) or omit the key consistently. Pick one scheme in `chroma_store.py` and use it everywhere.

### 4.3 Citation (returned to UI)

| Field | Type |
|-------|------|
| `filename` | `str` |
| `page` | `int` \| `null` |
| `chunk_id` | `str` |
| `quote` | `str` (truncated excerpt, ~240 chars) |

### 4.4 Answer

| Field | Type |
|-------|------|
| `text` | `str` |
| `citations` | `list[Citation]` |
| `refused` | `bool` |
| `retrieved_chunk_ids` | `list[str]` |
| `model` | `str` |
| `latency_ms` | `dict` (`retrieve`, `generate`, `total`) |
| `token_usage` | `dict` \| `null` |

### 4.5 Chat history (Phase 6 database; local MVP uses `st.session_state` only)

| Field | Type | Notes |
|-------|------|--------|
| `message_id` | `str` | UUID |
| `owner_id` | `str` | `user:<id>` or `guest:<session_id>` |
| `thread_id` | `str` | Conversation id |
| `role` | `user` \| `assistant` | |
| `content` | `str` | Question or answer text |
| `citations_json` | JSON \| `null` | Assistant messages only |
| `refused` | `bool` \| `null` | Assistant messages only |
| `created_at` | ISO datetime | |
| `last_active_at` | on session row | Drives guest TTL purge |

Keep a bounded “recent” window in the UI (e.g. last N messages or last M days). Logged-in full history can grow; guests are wiped entirely when TTL fires.

---

## 5. Pipeline design

### 5.1 Offline ingest (per file)

```
save upload
  → detect type
  → extract (page-aware for PDF)
  → clean
  → reject if no usable text
  → chunk with overlap
  → embed all chunks (batch)
  → upsert into Chroma
  → write registry row (ready)
  → invalidate / regenerate library summary
```

If any step fails, set `status=failed` with `error`, do not upsert partial junk without recording it. Prefer **all-or-nothing per file**: if embed/upsert fails, delete any chunks already written for that `doc_id`.

### 5.2 Online summary (after ingest, and on demand)

```
list ready documents
  → if none: "No documents uploaded."
  → gather titles + page/chunk counts
  → sample: first chunk + a middle chunk per doc (cap total tokens)
  → LLM: short library summary (bullets)
  → cache summary in registry or a small JSON sidecar until library changes
```

Do not send every chunk of every file into the summarizer. That is expensive and slow. Map-reduce (summarize per doc, then combine) is the fallback if sampled context is too thin.

### 5.3 Online Q&A

```
user question
  → reject empty question
  → embed question (same embedding model)
  → similarity search top_k
  → drop hits below threshold (if implemented)
  → if no hits: refuse, no LLM call (or a tiny refuse message)
  → build prompt (rules + excerpts with filename/page)
  → LLM generate
  → attach citations from the retrieved set (not from model invention)
  → log timings + tokens
```

**Citation source of truth is the retriever**, not the model. The model may mention sources; the UI always renders citations from retrieved chunks.

### 5.4 Reset

```
delete Chroma collection
  → delete data/uploads/*
  → reset registry
  → clear cached summary
```

---

## 6. Extraction rules (do not skip)

### 6.1 Allowed extensions

| Extension | Extractor | Citation unit |
|-----------|-----------|---------------|
| `.pdf` | PyMuPDF, iterate `page_number` + `page.get_text("text")` | page (1-based) |
| `.docx` | `python-docx` paragraphs, joined with newlines | chunk index |
| `.txt` | UTF-8 read; try `utf-8` then `latin-1` fallback | chunk index |
| `.md` | same as text | chunk index |

Everything else: `failed` — “Unsupported file type”.

### 6.2 PDF specifics

- Use 1-based page numbers in metadata and UI (`page + 1` if the library is 0-based).
- Skip pages that are empty or whitespace-only; they do not become chunks.
- If **every** page is empty, fail: “No extractable text. If this is a scanned PDF, OCR is not supported in the MVP.”
- Do not invent text from images.
- Preserve form-feed / page boundaries: chunk **within a page first**. If a single page is longer than `CHUNK_SIZE`, split that page with overlap. A chunk should not silently mix page 3 and page 12. If a split must cross a page only when a page is tiny, still tag the chunk with the **starting page** and keep the text contiguous — prefer no cross-page chunks in MVP.

### 6.3 DOCX / TXT / MD

- Join paragraphs with blank lines.
- If the result is empty or under a minimum (e.g. 20 characters), fail: “No extractable text.”

### 6.4 Cleaning (light only)

Apply in `clean.py`, in this order:

1. Normalize newlines to `\n`.
2. Collapse 3+ blank lines to 2.
3. Strip trailing spaces on each line.
4. Replace `\x00` and other nulls.
5. Optionally collapse hyphenated line-break artifacts (`word-\nword` → `wordword`) only if you add tests. If unsure, skip this in MVP.

Do **not** lowercase, do **not** strip punctuation, do **not** remove numbers. Those destroy citations and proper nouns.

### 6.5 Duplicate uploads

If the same filename is uploaded again:

- Treat as a **replace**: delete old chunks for that filename (or `doc_id` mapped to that name), then ingest the new file as a new `doc_id`.
- Keep one registry row per current filename.

Do not leave two live copies of `handbook.pdf` in the collection.

### 6.6 File save convention

Save uploads as `{doc_id}_{safe_filename}` under `data/uploads/` so two different users’ files cannot clash on disk even in a single-user MVP. `safe_filename` strips path separators.

Max file size: **25 MB** per file for MVP. Reject larger with a clear error.

---

## 7. Chunking rules (do not skip)

### 7.1 Algorithm

Use LangChain `RecursiveCharacterTextSplitter` with:

- `chunk_size = 800` (characters for the splitter unless you implement token-based splitting)
- `chunk_overlap = 150`
- separators: `["\n\n", "\n", ". ", " ", ""]`

**Preferred MVP approach:** character-based recursive split, then optionally warn if a chunk exceeds ~1,000 tokens via `tiktoken`. Token-accurate splitting is nicer but not required for v1.

### 7.2 Per-page PDF chunking

For each PDF page with text:

1. Clean the page text.
2. If `len(text) <= CHUNK_SIZE`, one chunk, `page=N`.
3. Else split that page with overlap; every sub-chunk still has `page=N`.

### 7.3 Metadata on every chunk

Always set: `doc_id`, `filename`, `file_type`, `page` or `has_page`, `chunk_index`.

`chunk_index` restarts at 0 for each document and increments across that document’s chunks only.

### 7.4 What not to do in MVP

- No sentence-window / parent-child index yet.
- No heading-aware legal splitters yet.
- No different chunk sizes per file type yet.

Tune `CHUNK_SIZE` / `CHUNK_OVERLAP` only after Phase 2 retrieval inspection.

---

## 8. Embeddings and Chroma (do not skip)

### 8.1 Embedding

- Model: `text-embedding-3-small` (1536 dimensions).
- Batch embed on ingest (`embed_documents`).
- Single embed on query (`embed_query`).
- Never mix with another embedding model in the same collection. If you change models later, **wipe and re-ingest**.

### 8.2 Collection

- One collection: `doccite_mvp`.
- Persist directory: `data/chroma`.
- Cosine space if you choose explicitly; otherwise use Chroma defaults and keep them stable.

### 8.3 Operations to implement

| Operation | Behavior |
|-----------|----------|
| `add_chunks(chunks)` | Upsert ids + documents + metadatas + embeddings |
| `query(query_text, k)` | Embed query, return texts, metadatas, scores |
| `delete_by_doc_id(doc_id)` | Remove all chunks for a file |
| `delete_collection()` | Full reset |
| `count()` | Number of vectors |

### 8.4 Manual verification (Phase 1)

After ingesting a known PDF:

1. `count()` equals the number of chunks you created.
2. A query that uses a distinctive phrase from page 2 returns a chunk with `page=2`.
3. Restart the Python process and query again — data must still be there (persist works).

---

## 9. Retrieval and generation (do not skip)

### 9.1 Retrieval

- `k = RETRIEVE_TOP_K` (start at 6).
- Return score with each hit.
- If you apply `SIMILARITY_THRESHOLD`, drop weak hits **before** prompting.
- If zero hits remain: refuse. Do not call the chat model with an empty context.

### 9.2 Context packing

Format each excerpt exactly like this so the model sees citations:

```
[Source 1] file="handbook.pdf" page=12 chunk_id="abc:3"
<excerpt text>

[Source 2] file="policy.docx" page=null chunk_id="def:0"
<excerpt text>
```

Cap total context (e.g. ~6 chunks or ~6k tokens). If over cap, keep the highest-scoring chunks.

### 9.3 System prompt (Q&A)

Use this behavior, worded tightly in `prompt.py`:

- You are a document assistant.
- Answer **only** from the excerpts.
- If the excerpts are insufficient, say you don’t have that in the uploaded documents.
- Do not use outside knowledge.
- Be concise.
- After the answer, do not invent page numbers. The application will attach sources.

Ask the model for a short answer only. **Do not trust the model to emit a JSON citation list as the only source of truth.** The app attaches citations from retrieved chunks.

Optional: ask the model to include `[Source N]` markers in the answer text when it uses an excerpt. Nice-to-have, not required for MVP done.

### 9.4 Summary prompt

- Input: document list (name, type, pages, chunks) + sampled excerpts.
- Output: 5–8 bullets: what the library contains, main topics, and what kinds of questions it can support.
- No claims that are not supported by the samples. If samples are thin, say the summary is based on excerpts.

Cache the summary. Regenerate only when a document is added, replaced, or removed.

### 9.5 Failures

| Failure | User-facing behavior |
|---------|----------------------|
| OpenAI timeout / 429 | “The language service is busy. Try again.” Log exception. Do not show stack traces in UI. |
| OpenAI auth error | “API key missing or invalid.” |
| Chroma empty | “Upload documents first.” |
| Embed failure mid-ingest | Mark file `failed`, roll back that `doc_id`. |

Retry transient OpenAI errors **once** with a short backoff. Then fail.

---

## 10. UI requirements (Phase 4)

Streamlit single page (`app.py`).

### 10.1 Layout

1. **Header** — **DocCite** + one-line description.
2. **Sidebar**
   - File uploader (`pdf`, `docx`, `txt`, `md`), multiple files.
   - Upload button / auto-process on change (pick one; auto-process is fine).
   - Document list: filename, status, pages/chunks, error if failed.
   - “Clear library” with a confirm checkbox or second click.
3. **Main**
   - Library summary card (or “Upload documents to get a summary”).
   - Chat transcript.
   - Question input.

### 10.2 Chat message rendering

- User message: raw question.
- Assistant message:
  - Answer text.
  - If refused: distinct styling / prefix.
  - Citation cards: filename, page (or “n/a”), quote.
- While working: spinner “Searching your documents…” / “Generating answer…”.

### 10.3 Session state (local MVP)

Streamlit reruns on every interaction. Persist:

- chat history in `st.session_state` for the local demo only
- do **not** keep embeddings only in memory — Chroma on disk is the source of truth
- after rerun, document list loads from registry

**After Phase 6:** chat history and document metadata live in the database; Streamlit/React only holds UI state. Guests get a server session id; logged-in users load their library and recent chats from the API.

### 10.4 UX rules

- Disable Ask when no `ready` documents.
- Show ingest progress per file.
- Never block the whole app without a spinner.
- Clearing library also clears chat history (local MVP) / clears that user’s library + related chats (Phase 6).
- Guest UX should disclose that data is temporary and will be removed after inactivity.

---

## 11. Observability (MVP-level)

Implement from Phase 1, not as an afterthought.

Log at INFO:

- ingest: filename, pages, chunks, ms extract / chunk / embed / upsert
- query: question length, k, hit ids, retrieve ms, generate ms, prompt tokens, completion tokens
- errors: full traceback in logs, sanitized message in UI

Print the same on CLI scripts so Phase 1–3 are debuggable without Streamlit.

Do not log full document text at INFO (can be huge / sensitive). DEBUG only, and keep DEBUG off by default.

---

## 12. Testing (do not skip)

Use tiny fixtures you create (a 2-page PDF with known sentences, a short `.txt`).

| Test | Assert |
|------|--------|
| `test_extract` PDF | Page 1 and page 2 text contain known phrases; page numbers are 1-based |
| `test_extract` empty | Empty txt → failed / exception you handle |
| `test_chunk` | Overlap exists; metadata present; no empty chunks |
| `test_retrieve` | Query with a unique phrase returns that chunk |
| `test_qa_refusal` | Unrelated question + threshold or empty hits → `refused=True` |
| `test_unsupported` | `.exe` or `.png` rejected |

LLM tests that call OpenAI should be marked `@pytest.mark.integration` and skipped unless `OPENAI_API_KEY` is set. Unit tests must not require the network: mock embeddings/LLM where needed.

---

## 13. Phase-by-phase build (follow in order)

### Phase 0 — Skeleton and toolchain

**Goal:** Empty app that imports, loads config, and ignores secrets/data.

Steps:

1. Create the folder tree in section 3.
2. Create `venv`, activate it, `pip install -r requirements.txt`.
3. Write `.gitignore` (`.env`, `venv/`, `data/`, `__pycache__/`, `.pytest_cache/`, `.streamlit/`).
4. Write `.env.example` and a local `.env` (never commit `.env`).
5. Implement `src/config.py` reading the variables in section 2.4.
6. Implement `src/logging_setup.py`.
7. Implement `src/models.py` with the types in section 4.
8. Write a short `README.md`: Python version, `venv`, copy `.env`, `streamlit run app.py` (placeholder until Phase 4), CLI commands.
9. `python -c "from src.config import settings; print(settings.collection_name)"` succeeds.

**Acceptance**

- [ ] Repo layout exists
- [ ] Settings load from `.env`
- [ ] `.env` is gitignored
- [ ] README explains setup

**Do not start Streamlit yet.**

---

### Phase 1 — Ingest one PDF end-to-end (CLI only)

**Goal:** One PDF becomes persisted Chroma chunks with page metadata.

Steps:

1. Implement `extract.py` for PDF first (ignore DOCX/TXT until this works).
2. Implement `clean.py`.
3. Implement `chunk.py` with per-page PDF rules.
4. Implement `chroma_store.py` (`add_chunks`, `count`, persist).
5. Implement `registry.py` (create/update document row).
6. Implement `ingest/pipeline.py` for a single path.
7. Implement `scripts/ingest.py`:

   ```
   python scripts/ingest.py path/to/file.pdf
   ```

   Prints: `doc_id`, pages, chunks, timings.

8. Create `tests/fixtures` with a small PDF (two pages, unique sentence on each page).
9. Run ingest on the fixture. Restart Python. Confirm `count()` unchanged.
10. Manually query Chroma for the unique page-2 sentence; confirm `page==2`.

**Acceptance**

- [ ] CLI ingest of a PDF completes with `status=ready`
- [ ] Chunk count > 0
- [ ] Every PDF chunk has a real page number
- [ ] Persist survives process restart
- [ ] Empty PDF fails with a clear error
- [ ] Unit tests for extract + chunk pass

**Do not build Q&A or UI yet.**

---

### Phase 2 — Ask one question (CLI only)

**Goal:** Grounded answer + citations; refusal when unsupported.

Steps:

1. Implement `retrieve.py` (top-k + scores + threshold).
2. Implement `prompt.py` (Q&A system prompt + context packer).
3. Implement `qa.py` (retrieve → generate → `Answer` object with citations from hits).
4. Implement `scripts/ask.py`:

   ```
   python scripts/ask.py "What does page two say about X?"
   ```

   Prints answer, citations, timings, tokens.

5. Ask a question the fixture PDF **does** answer. Confirm citation page is correct.
6. Ask a question the fixture PDF **cannot** answer. Confirm refusal and no fabricated citations.
7. Add `test_retrieve.py` and `test_qa_refusal.py` (mock LLM for refusal if needed).

**Acceptance**

- [ ] In-domain question returns answer + at least one citation with filename and page
- [ ] Out-of-domain question refuses
- [ ] Empty collection tells the user to ingest first
- [ ] Logs show retrieve ms and generate ms
- [ ] Citations come from retrieved chunks, not model-invented pages

**Do not build the UI yet.**

---

### Phase 3 — Multi-file types, multi-doc library, summary, reset

**Goal:** Real library behavior.

Steps:

1. Add DOCX, TXT, MD extractors to `extract.py`.
2. Extend `pipeline.py` to accept a file or a directory.
3. Duplicate filename → replace (section 6.5).
4. Implement `summarize.py` + cache sidecar (`data/summary.json` with a hash of `doc_id` list).
5. Implement `scripts/summarize.py`.
6. Implement `scripts/reset.py`.
7. Implement `delete_by_doc_id` and use it on replace and on failed rollback.
8. Ingest two PDFs + one TXT. Run summarize. Ask a question that requires doc A and a question that requires doc B.
9. Reset. Confirm collection count is 0 and uploads are gone.

**Acceptance**

- [ ] All four file types ingest (happy path)
- [ ] Unsupported type fails cleanly
- [ ] Duplicate filename replaces old vectors
- [ ] Summary lists all ready docs and does not claim unread content
- [ ] Q&A works across the whole library
- [ ] Reset wipes store, uploads, registry, summary cache
- [ ] 25 MB limit enforced

---

### Phase 4 — Streamlit UI

**Goal:** A person can use the product without the terminal.

Steps:

1. `app.py` layout per section 10.
2. Upload → save → `pipeline.ingest` → refresh list + summary.
3. Chat wired to `qa.answer`.
4. Render citation cards.
5. Disable ask when no ready docs.
6. Clear library calls the same reset as the CLI.
7. Spinners and error toasts for API failures.
8. Click-test the full journey in a browser (upload, summary, ask, refuse, clear).

**Acceptance**

- [ ] Multi-file upload works
- [ ] Statuses update (`processing` / `ready` / `failed`)
- [ ] Summary appears after ingest
- [ ] Chat shows answer + citations
- [ ] Out-of-scope question refuses in the UI
- [ ] Clear resets list, summary, and chat
- [ ] Refreshing the browser still shows documents (disk persist)

This phase is not done after a screenshot. Walk the flow as a user.

---

### Phase 5 — Hardening (still MVP)

**Goal:** Safe to demo; still not “scale”.

Steps:

1. Tighten error messages (no stack traces in UI).
2. Confirm retries (one) on transient OpenAI errors.
3. Guard empty question / whitespace-only question.
4. Cap chat history display if it grows huge (keep last N messages).
5. README: screenshots or a short “try this” with the fixture PDF.
6. Run `pytest` (unit + optional integration).
7. Manual checklist in section 14.

**Acceptance**

- [ ] Bad PDF / empty file / huge file / bad key all fail gracefully
- [ ] README is enough for you to run on a clean machine
- [ ] Section 14 checklist all pass

---

## 14. Definition of done (MVP)

A user can:

1. Upload several PDFs / DOCX / TXT / MD files.
2. See a library summary.
3. Ask questions and get answers **with filename + page (for PDFs) + quote**.
4. Ask something outside the docs and get a refusal.
5. Clear the library and start over.

Plus:

6. Data survives restart.
7. Answers are not generated from an empty retrieval.
8. Cost/latency are logged per question.
9. Tests for extract, chunk, retrieve, and refusal exist.

When 1–9 are true, the grassroots local MVP is done. Only then start **Phase 6** (backend + DB + guest TTL + logged-in persistence) per sections 1.4 and 18.1.

---

## 15. Manual QA script (run after Phase 4 and Phase 5)

Use a real PDF you know (e.g. a public policy or a 2-page fixture).

1. Reset library.
2. Upload the fixture PDF. Expect `ready`, chunk count > 0.
3. Read the summary. It should mention the fixture topic.
4. Ask a question whose answer is on page 1. Expect citation `page=1`.
5. Ask a question whose answer is on page 2. Expect citation `page=2`.
6. Ask “What is the capital of France?” (unless that text is in the PDF). Expect refusal.
7. Upload a `.txt` with a unique word `ZEBRA-TOKEN-9`. Ask about it. Expect the txt cited, page n/a.
8. Re-upload the same PDF filename with different content. Old answers must not linger.
9. Refresh the browser. Documents still listed.
10. Clear library. Upload empty. Ask disabled or “upload first”.
11. Upload a `.png` or `.zip`. Expect unsupported error.
12. Disconnect / bad API key. Expect a clean API error, not a crash.

---

## 16. Cost, latency, and accuracy (MVP discipline)

### 16.1 Cost

- Embeddings: billed per token of **chunks** at ingest, and a tiny embed per question.
- Chat: billed per prompt (excerpts + question) and completion.
- Summary: billed only when the library changes.

Prefer `gpt-4o-mini` + `text-embedding-3-small` until quality is clearly insufficient.

### 16.2 Latency budget (local, small library)

| Stage | Target |
|-------|--------|
| Ingest small PDF (≤20 pages) | a few seconds (embed-bound) |
| Retrieve | < 300 ms local |
| Generate | 1–3 s typical |
| End-to-end Q&A | aim under ~5 s for MVP |

If Q&A is slow, do not jump to a new vector DB. First: smaller `top_k`, shorter chunks in the prompt, `gpt-4o-mini` already selected.

### 16.3 Accuracy loop (before changing architecture)

If answers are wrong:

1. Inspect retrieved chunks. Wrong chunks → fix chunking / `k` / threshold, not the prompt.
2. Right chunks, wrong answer → tighten the prompt / refuse rule.
3. Missing page citations → fix metadata in extract/chunk, not the LLM.
4. Hallucinated facts → confirm empty-context refuse; lower `k` noise; strengthen “only excerpts”.

---

## 17. Security and privacy (MVP)

- `.env` never committed.
- Uploaded files live only under `data/` (gitignored).
- Treat uploads as private. Do not send whole files to the LLM — only chunks.
- OpenAI **will** receive retrieved excerpts and questions. If a later customer cannot allow that, add a local model in a later phase.
- No auth in Phases 0–5: anyone who can open Streamlit can see the local library. Document that this is single-user / local demo only.
- Phase 6 must isolate guest vs user data (no cross-tenant retrieval) and enforce guest purge + user self-clear.

---

## 18. What you will scale later (do not build in Phases 0–5)

Keep this list so the local loop stays small — but **guest TTL, login persistence, backend, and DB are planned product requirements**, not optional niceties.

| Later | Depends on MVP being solid |
|-------|----------------------------|
| **Phase 6: FastAPI + DB + guest/login retention** | Same `src/` ingest / RAG services |
| Auth, multi-user, per-user / per-guest collections | Registry + Chroma namespacing by `owner_id` |
| Persist uploads + recent chat histories in DB | Document registry + message tables |
| Guest inactivity purge job | TTL config + delete-by-owner APIs |
| React (or other) frontend | Same backend APIs |
| Hybrid search + re-ranker | Logged retrieval failures |
| Clause-aware chunking / compliance mode | Page-aware chunks already work |
| OCR | Failed empty-PDF path already exists |
| Pinecone / PGVector | `chroma_store.py` behind a store interface |
| Agents / tools | `qa.py` as a tool |
| Query cache | Same question logs |

When you add a store interface, do it by extracting methods already listed in section 8.3 — not by rewriting ingest.

### 18.1 Phase 6 outline — backend, database, retention

**Goal:** Multi-user DocCite with durable logged-in libraries and auto-cleared guest data.

**Backend**

- FastAPI wrapping existing `src/ingest`, `src/rag`, `src/store` (Streamlit stops owning business logic).
- Endpoints roughly: auth/session, upload, list docs, summarize, ask, list/clear chats, clear library.

**Database (required)**

Store at least:

| Entity | Purpose |
|--------|---------|
| `users` | Logged-in accounts |
| `sessions` | Guest + auth sessions; `last_active_at` for guest TTL |
| `documents` | File metadata, status, owner (`user_id` or `guest_session_id`) |
| `chat_threads` / `chat_messages` | Recent Q&A history per owner |
| (optional) `library_summaries` | Cached summary keyed by owner |

Uploads remain on disk (or object storage) keyed by owner; Chroma collections / metadata filtered by `owner_id`.

**Retention jobs**

1. Cron / background worker: find guest sessions with `now - last_active_at > GUEST_INACTIVITY_TTL_HOURS`.
2. For each: delete files, delete vectors for that owner, delete DB rows (docs + chats + session).
3. Logged-in owners are **never** purged by this job — only by explicit user clear (or future account deletion).

**Acceptance (Phase 6)**

- [ ] Guest upload + ask works; after TTL (or forced purge), guest data is gone from DB, disk, and vector store
- [ ] Logged-in user returns later and still sees files + recent chats
- [ ] Logged-in clear library removes only that user’s data
- [ ] Guest A cannot retrieve Guest B / User C chunks

---

## 19. Implementation order cheat sheet

| Order | Work | Entry point |
|------:|------|-------------|
| 0 | Skeleton, config, models | `src/config.py` |
| 1 | Extract PDF, chunk, Chroma, ingest CLI | `scripts/ingest.py` |
| 2 | Retrieve, prompt, QA CLI | `scripts/ask.py` |
| 3 | DOCX/TXT/MD, summary, reset, multi-file | `scripts/summarize.py`, `scripts/reset.py` |
| 4 | Streamlit | `app.py` |
| 5 | Hardening, README, QA script | section 15 |
| 6 | FastAPI + DB + guest TTL + login persistence | section 18.1 |

Next concrete action after this document: **Phase 0 only** — folders, venv, `requirements.txt`, config, models, README, gitignore.

---

## 20. Decisions already made (change only if you explicitly override)

1. Product is a **document Q&A** product (local MVP first), not a compliance platform.
2. Stack for Phases 0–5: **Python + LangChain + Chroma + OpenAI + Streamlit + PyMuPDF + python-docx**.
3. Grounding is **strict**: no answer outside uploaded docs.
4. Citations: **retriever metadata** (filename, page, quote).
5. UI is **Streamlit** until the CLI path is proven; then FastAPI (+ later a proper frontend).
6. Phases 0–5: one local library, one Chroma collection. **Phase 6+:** per-guest / per-user ownership with backend + database.
7. **Guests:** data auto-cleared after inactivity TTL. **Logged-in:** data remains until the user clears it.
8. Backend stores **user files (metadata + blobs) and recent chat histories**; vector store stays for embeddings.
9. Character-recursive chunks (~800 / 150 overlap), PDF split **per page**.
10. Summary is **sampled / cached**, not a full-document dump every time.
11. Tests exist before calling the UI done.
12. Multi-user / retention work (Phase 6) starts only after section 14 (local MVP) is complete.
