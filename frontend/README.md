# DocCite frontend

Vite + React + TypeScript UI for the DocCite FastAPI backend. Deployable on
**Vercel** as a static SPA; the API must be hosted separately (any host that
can run Python + FastAPI).

## Local development

Terminal 1 — API:

```bash
cd ..
source venv/bin/activate
python scripts/run_api.py
# http://127.0.0.1:8000
```

Terminal 2 — UI:

```bash
cd frontend
cp .env.example .env.local   # optional; defaults to http://127.0.0.1:8000
npm install
npm run dev
# http://localhost:5173
```

Ensure the API allows the Vite origin (`CORS_ORIGINS` in the repo root `.env`).

## Build

```bash
npm run build
# output: dist/
```

## Vercel

1. Import this Git repo in Vercel.
2. Set **Root Directory** to `frontend`.
3. Framework preset: Vite (build `npm run build`, output `dist`).
4. Environment variable:
   - `VITE_API_BASE_URL` = your public API base URL (e.g. `https://api.example.com`)
5. On the API host, set:
   - `CORS_ORIGINS` to include your production Vercel URL
     (e.g. `https://doccite.vercel.app`)
   - `CORS_ORIGIN_REGEX=https://.*\.vercel\.app` (already the default) for
     preview deployments

`vercel.json` rewrites all routes to `index.html` for client-side routing.

## Features

- Auto guest session (token in `localStorage`) with TTL banner from `/me`
- Register / login / logout
- Upload + document list, library summary, chat with citations
- Restore recent chat messages from the API
- Clear library (owner-scoped)
