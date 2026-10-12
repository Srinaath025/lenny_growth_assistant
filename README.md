# The Lenny Growth Assistant

Retrieval-grounded chat, **Ship 30 for 30** essays and sandboxed Markdown/HTML artifacts built on the Lenny's Podcast transcript corpus (303 transcripts → 8,947 searchable chunks). Local-first (Ollama via the Pi coding agent), optional Anthropic cloud mode, PostgreSQL persistence.

## What it does
| Capability | How |
|---|---|
| Grounded Q&A with citations | PostgreSQL full-text search → evidence gate → LLM → citation validator. Every citation links to the YouTube moment (`&t=XXs`). |
| Abstention | Layer 1: retrieval returns **nothing** when the question's (IDF-weighted) terms are not covered. Layer 2: the prompt forces the refusal sentence. Layer 3: the validator rejects answers with no verifiable citation. |
| Follow-ups & session memory | The last N turns **of the same session** are loaded from PostgreSQL and injected as context (never as evidence). Sessions are isolated. |
| Ship 30 for 30 essay | Skill file `backend/skills/ship30/SKILL.md` (4A framework, Two-Year Test, WHO/SO-THAT hook); length-repair loop targets 1,100–1,400 words; refuses when there is no evidence. |
| Markdown / HTML artifacts on request | "Create an HTML card…", "Turn this into a Markdown brief" are routed (deterministic router) to the artifact skill; output is sanitized, cited and stored. |
| Safe rendering | Server allow-list sanitizer → `<iframe sandbox="">` (no scripts / same-origin / forms / popups) → injected CSP `default-src 'none'`. |
| Model switching | Edit `.env` (`OLLAMA_MODEL`, `ANTHROPIC_MODEL`, …) — no code change. UI toggle for Local ↔ Cloud (cloud is never used silently). |
| Observability | JSON logs with request IDs (`X-Request-ID`), structured errors `{error:{code,message,hint,request_id}}`, `/api/health` (DB, Ollama, model installed, cloud key, ingestion state). |

## Quick start (Docker — one command)
Prerequisites: Docker, [Ollama](https://ollama.com) running on the host.
```bash
ollama pull llama3.2:3b          # or any model, then set OLLAMA_MODEL in .env
copy .env.example .env            #cp .env.example .env
Turn on the docker desktop and turn on the Engine
docker compose up --build
```
Open http://localhost:3000. On first start the backend creates the schema and **auto-indexes `data/transcripts` (~15 s)**; the header badge shows progress and `/api/health` reports `ingestion.state`.
Optional cloud mode: put `ANTHROPIC_API_KEY` in `.env`, restart, pick "Cloud Claude" in the sidebar.

## Manual setup (no Docker for the app)
```bash
docker compose -f docker-compose.db.yml up -d            # PostgreSQL on 5433
python -m venv .venv && source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
(cd proof-of-concept && npm ci)                           # Pi coding-agent CLI (optional: HTTP fallback exists)
cp .env.example .env
python -m backend.ingestion.run --no-sync                 # optional: API also auto-ingests when DB is empty
uvicorn backend.main:app --port 8000
cd frontend && npm install && npm run dev                 # http://localhost:5173
```

## Tests
```bash
pytest backend/tests --ignore=backend/tests/test_agent_live_integration.py   # 101 tests; self-bootstraps schema + corpus
cd frontend && npm test                                                       # 9 tests (sandbox, CSP, markdown XSS, a11y wiring)
pytest backend/tests/test_agent_live_integration.py                           # needs a running Ollama (live LLM)
```
Manual UI checklist: `MANUAL_TEST_PLAN.md`. Demo walkthrough: `DEMO_SCRIPT.md`.

## Configuration reference
See `.env.example` (every variable documented). Key ones: `OLLAMA_MODEL`, `OLLAMA_NUM_CTX` (prompts are long — Ollama truncates at its context size), `MIN_TERM_COVERAGE` (evidence gate; calibrated: on-topic ≥ 0.91, unrelated ≤ 0.67), `HISTORY_TURNS`, `CORS_ORIGINS`, `LOG_FORMAT`.

## Notes
* The Pi coding-agent CLI requires **Node ≥ 22.19**; the backend image installs Node 22. With an older Node, Pi exits immediately and the backend automatically uses the Ollama HTTP fallback (slower to start, same answers).

## Known limitations:
* Retrieval is lexical (Postgres FTS), not semantic embeddings: paraphrased questions using none of the transcript's words can be missed. The gate trades recall for precision.
* A 3B local model often under-writes essays; the repair loop retries twice and the UI shows the real word count if the target is still missed.
* The gate cannot detect questions whose words *do* appear in a transcript by coincidence (e.g. "train for a marathon" matches an anecdote); layers 2–3 handle those.
* Pi RPC and the Ollama HTTP fallback were both exercised against a stub server; Docker build, real model quality and the browser UI must be checked with `MANUAL_TEST_PLAN.md`.
* No authentication (single-tenant demo); sessions carry an anonymous client id for metadata only.

Further docs: `PRD.md` (discovery brief), `architecture.md`, `design.md`, `AUDIT_REPORT.md` (what was wrong and what changed), `EVALUATION_REPORT.md`.
