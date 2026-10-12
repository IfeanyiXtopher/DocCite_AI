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

## Run (filled in as we build)

| When | Command |
| --- | --- |
| Step 2+ | `python scripts/ingest.py tests/fixtures/two_page_fixture.pdf` |
| Step 3+ | `python scripts/ask.py "What does page two say about BRAVO-TOKEN-9?"` |
| Step 4+ | `python scripts/ingest.py tests/fixtures/` then `summarize.py` / `reset.py` |
| Step 5+ | `streamlit run app.py` |

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
