# Architecture

```
Browser (React/Vite, nginx :3000) ──/api──▶ FastAPI :8000 ──▶ PostgreSQL 16 (sessions, messages, citations, artifacts, transcript_chunks + GIN tsvector)
                                               │
                                               ├─ router (intent) ─▶ chat | essay | artifact_markdown | artifact_html
                                               ├─ retriever (FTS + IDF coverage gate)
                                               ├─ LLM: Pi RPC (node CLI) ─▶ Ollama   (fallback: Ollama HTTP /api/generate)
                                               │       Anthropic Messages API (explicit opt-in)
                                               └─ citation validator · HTML sanitizer · structured logging
```

## Request lifecycle (`POST /api/chat`)
1. Validate (Pydantic) → load session → resolve provider → **preflight** (cloud key / DB non-empty / Ollama reachable / model installed) → structured error *before* anything is stored.
2. Load last `HISTORY_TURNS` messages of **this session** (isolation), persist the user message.
3. `route_intent` (deterministic regex rules; small models are unreliable at tool choice).
4. Skill runs; events stream over SSE: `status`, `token`, `artifact`, `complete`, `error`, `done`. The producer task persists results even if the client disconnects.

### Chat skill
retrieval query (augmented with the previous user question for vague follow-ups) → `retrieve_relevant_chunks` → dedupe by video → grounded prompt (history = context only; evidence in `<<<UNTRUSTED_EVIDENCE>>>` with delimiters neutralised) → LLM → `CitationValidator` → persist message + citations. No chunks ⇒ immediate abstention without calling the LLM.

### Retrieval & evidence gate
`to_tsquery('english', t1 | t2 …)` over `transcript_chunks.search_vector` (GIN). Candidates are ordered by IDF-weighted matched terms then `ts_rank_cd`; a chunk is evidence only if it covers ≥ `MIN_TERM_COVERAGE` (0.8) of the weighted terms. Calibrated on the real corpus (in-domain ≥ 0.91, unrelated ≤ 0.67). `ts_rank_cd` alone is not scale-free (measured), so it is not used as a threshold.

### Citation validation
Only `[citation:<chunk_id>]` ids that were actually retrieved survive; fabricated ids are stripped. If the model omitted citations, the best-overlapping retrieved chunk is attached **only if ≥ 6 distinctive words overlap**; otherwise the answer is converted to an abstention. Turn-level timestamps are resolved to `&t=XXs` deep links.

### Essay skill
`backend/skills/ship30/SKILL.md` (principles from the Ship 30 for 30 guide) is loaded into the prompt. Evidence required (else 422 `NO_EVIDENCE`). Length-repair loop (`ESSAY_MAX_ATTEMPTS`). Output: styled HTML (escape-first renderer, sources footer) + Markdown source, both stored as artifacts.

### Artifact skill
Prompt → fenced output → HTML: allow-list sanitizer; Markdown: citations resolved to links + Sources section → stored with `message_id`. Command words are stripped from the retrieval query (topic only).

## Artifact security (untrusted HTML)
| Layer | Control |
|---|---|
| 1 Server | `html_sanitizer.py`: allow-list tags/attrs, drops script/iframe/form/svg/object/link/meta, event handlers, `javascript:`, non-`data:` images, CSS `@import`/`url()`/`expression`; logs `artifact_sanitized` |
| 2 Viewer | `<iframe sandbox="">` — no scripts, forms, popups, same-origin, top navigation |
| 3 Policy | CSP meta injected **first** in `srcdoc`: `default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:` (no network, no exfiltration). `/raw` endpoint sends the same CSP plus `sandbox`. |
Markdown is rendered by an escape-first renderer. Permitted: static HTML, inline CSS, data: images. Blocked: JS, network, forms, navigation. Rationale: generated "HTML/CSS snippets" never need scripts.

## Data model (PostgreSQL)
`sessions(id, title, model_provider, model_name, client_id, user_agent, client_ip_hash, created_at, updated_at)` · `messages(id, session_id→, role, content, is_abstention, model_provider, model_name, duration_ms, created_at)` · `citations(id, message_id→, episode_title, guest_name, youtube_url, timestamp_seconds, quote_text)` · `artifacts(id, session_id→, message_id→, title, artifact_type, content, word_count, created_at)` · `transcript_chunks(id, episode_slug, episode_title, guest_name, youtube_url, video_id, chunk_index, speaker, start/end timestamp+seconds, content, search_vector GIN)`.
`create_schema()` runs at startup, is idempotent and applies additive migrations (`ADD COLUMN IF NOT EXISTS`) so upgraded volumes keep working. IP is stored only as a truncated hash.

## API
| Method & path | Purpose |
|---|---|
| GET `/api/health` | DB, Ollama (+model installed), cloud key/model, ingestion state |
| GET/POST `/api/sessions`, GET/PATCH/DELETE `/api/sessions/{id}` | session CRUD (detail includes messages, citations, artifacts) |
| POST `/api/chat` | SSE (default) or JSON (`stream:false`); routes to chat/essay/artifacts |
| POST `/api/essay` | direct Ship 30 skill |
| GET `/api/artifacts/{id}` · `/raw` | artifact JSON · sandboxed raw HTML |
Errors: `{"error":{"code","message","hint","request_id"},"detail"}`. Codes: `CLOUD_CREDENTIALS_MISSING 400`, `OLLAMA_OFFLINE 503`, `MODEL_MISSING 422`, `KNOWLEDGE_BASE_EMPTY 503`, `DATABASE_UNAVAILABLE 503`, `NO_EVIDENCE 422`, `MODEL_ERROR 502`, `VALIDATION_ERROR 422`, `NOT_FOUND 404`.

## Failure behaviour
Pi CLI missing/crashes → Ollama HTTP fallback (logged). Ollama down → preflight 503 (nothing stored). Cloud selected without key → 400; **no silent cross-provider fallback** (privacy). DB down → `/api/health` unhealthy, chat 503. Schema failure at boot → API still starts and reports it.

## Configuration
All via env (`backend/config.py`, `.env.example`). Docker Compose passes them through; inside Docker the Pi `models.json` is regenerated at runtime from `OLLAMA_BASE_URL`/`OLLAMA_MODEL`.

## Observability
JSON logs (`LOG_FORMAT=json`) with `request_id`; events: `http_request`, `intent_routed`, `retrieval` (terms, coverage, returned), `chat_query`, `artifact_sanitized`, `artifact_generated`, `essay_length_repair`, `auto_ingest_*`, `app_error`. Message rows record provider, model, latency.
