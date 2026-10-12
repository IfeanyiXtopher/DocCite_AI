# DocCite

**DocCite** lets you upload documents (PDF, DOCX, TXT, MD), get a short library
summary, and ask questions answered **only** from those files — with citations
(filename, page when available, short quote). If the answer is not in your
uploads, the app refuses instead of guessing.

## Where to start

| Doc | Purpose |
| --- | --- |
| [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md) | **Progress tracker** — current step, tasks, verify checks |
| [`APPROACH.md`](APPROACH.md) | Design bible — rules, stack, pipelines, data model |
| [`docs/adr/0001-stack.md`](docs/adr/0001-stack.md) | Why this stack + guest/login retention direction |

## Requirements

- Python **3.11+** (3.12 is fine)
- An OpenAI API key in a local `.env` (for live embed + chat from Step 2 onward)

## Setup (after Step 1 lands packages)

```bash
cd DocCite
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
cp .env.example .env              # then paste OPENAI_API_KEY into .env
pip install -r requirements.txt
```

Exact installed versions are recorded in `requirements.lock.txt` (from
`pip freeze`). Prefer `pip install -r requirements.txt` for setup; use the lock
file if you need a bit-for-bit match.

## Try this (local MVP)

```bash
cd DocCite
source venv/bin/activate

# 1) Reset and load the sample library
python scripts/reset.py
python scripts/ingest.py tests/fixtures/

# 2) Summary
python scripts/summarize.py

# 3) In-domain question (expect a citation; PDF page when relevant)
python scripts/ask.py "What does page two say about BRAVO-TOKEN-9?"

# 4) Out-of-domain (expect refusal — no guessing)
python scripts/ask.py "What is the capital of France?"

# 5) Browser UI
streamlit run app.py
# open http://localhost:8501 — upload, ask, clear library
```

| Command | Purpose |
| --- | --- |
| `python scripts/ingest.py path` | Ingest a file or folder |
| `python scripts/summarize.py` | Library summary |
| `python scripts/ask.py "…"` | Grounded Q&A |
| `python scripts/reset.py` | Wipe local library |
| `streamlit run app.py` | UI on http://localhost:8501 |

**Single-user demo:** anyone who can open Streamlit on this machine sees the same local library. Multi-user auth + guest TTL arrive in Step 7.

## Layout (learning map)

```
src/ingest/   # extract → clean → chunk → embed
src/store/    # Chroma + document registry
src/rag/      # retrieve, summarize, Q&A prompts
src/ui/       # Streamlit helpers
scripts/      # CLI tools (prove the pipeline before the UI)
tests/        # pytest
docs/         # BUILD_PLAN + ADRs
data/         # gitignored uploads + vectors (created on your machine)
```

## Product direction (short)

- **Steps 0–6:** local single-user MVP (Streamlit + Chroma on disk).
- **Step 7+:** FastAPI + database; **guests** auto-cleared after inactivity;
  **logged-in** data stays until the user clears it.
