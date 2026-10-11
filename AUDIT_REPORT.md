# Audit report — document vs. project

Source of truth: *Forward Deployed Engineer Take-Home Assignment (12 Oct 2026)*. Every claim below was verified by running the code (Postgres 16 + 303-transcript ingest, 101 backend tests, 9 frontend tests, live API run against a stub Ollama).

## A. Defects found in the project (all fixed)
| # | Severity | Finding | Evidence | Fix |
|---|---|---|---|---|
| 1 | **Critical** | Fresh start had **no tables**: `main.py` imported `create_schema`, which did not exist (`init_db`); the ImportError was swallowed. Compose never ingested → empty DB. 12 of 59 tests failed on a clean DB. | reproduced | `create_schema()` + idempotent migrations; auto-ingest on empty DB; tests self-bootstrap |
| 2 | **Critical** | **No conversation memory**: `agent.ask(query)` ignored history → follow-ups ("tell me more") failed, violating §4.1. | code | history loaded per session, injected as context; follow-up retrieval augmentation |
| 3 | **Critical** | **No Markdown/HTML artifact generation from chat** (§4.3): only the essay endpoint existed. | code | deterministic intent router + artifact skill + `artifact` SSE event |
| 4 | High | Abstention claim false: off-topic queries returned full result sets; PRD's `ts_rank_cd < 0.05` threshold is mathematically wrong (valid query 0.01, unrelated 2.6). | probe on real corpus | IDF-weighted term-coverage gate (calibrated) |
| 5 | High | **XSS in essay renderer**: list/paragraph/quote text from the LLM inserted unescaped. | code | escape-first renderer + test |
| 6 | High | Viewer used `allow-scripts` with **no CSP in srcdoc** (the documented CSP only applied to `/raw`) → generated JS could call out to the network. Markdown artifacts were rendered as raw text/HTML. | code | scriptless sandbox, CSP injected first, server allow-list sanitizer, safe Markdown renderer |
| 7 | High | Fabricated "verified" citations: if the model cited nothing, the top chunk was attached regardless of overlap. | code | ≥6-word overlap rule, else abstention |
| 8 | High | Model not configurable: `OLLAMA_MODEL` only affected `/health`; agent hard-coded `llama3.2:3b`; cloud model hard-coded to a **retired** Claude model (also in UI, and overwritten by health polling). Violates §3.2. | code | `backend/config.py`, env-driven everywhere, health exposes models |
| 9 | High | Docker: Pi CLI never installed (`npm ci` missing); Pi `models.json` pointed to `localhost` (wrong inside a container); Pi-missing raised instead of using the fallback. | Dockerfile/code | `npm ci`, runtime `models.json` from `OLLAMA_BASE_URL`, fallback |
| 10 | Medium | Infra failures reported as "topic not discussed" abstention; no preflight; errors were raw FastAPI `detail`. | code | structured errors, preflight (Ollama offline / model missing / no key / empty KB), `MODEL_ERROR` |
| 11 | Medium | No user metadata stored; messages had no model/latency (§3.1). | schema | `client_id`, `user_agent`, `client_ip_hash`; `model_*`, `duration_ms` |
| 12 | Medium | Logging not structured; no request ids (§3.3). CORS `*` + credentials. | code | JSON logs, `X-Request-ID`, restricted CORS |
| 13 | Medium | Essay: no retry when length misses, no refusal on empty evidence, hyphen-splitting word count, duplicated title, Google-Fonts dependency (contradicts "offline"). | code | repair loop, `NO_EVIDENCE`, fixes |
| 14 | Medium | Ollama prompt truncation (default context) — long retrieval prompts silently cut. | design | `num_ctx` option (8192) |
| 15 | Low | Duplicated episodes under different slugs gave duplicate sources. | data | dedupe by video id |
| 16 | Low | Model selector not keyboard accessible; hard-coded "Claude 3.5" label; `.env`, `frontend/dist`, venv shipped in the zip. | UI/zip | radiogroup roles; labels from health; cleaned package, `.dockerignore` |

## B. Document ↔ project gaps (documentation fixed)
README "283 chunks" (actual 8,947) · "59 tests" (58+1 fragile) · "Claude 3.5 Sonnet" · architecture file names (`agents/pi_rpc.py` vs `agent/pi_client.py`), DB password, CSP text, status "Read-only stage" · PRD lacked success metrics, assumptions, scope, risks, flows, acceptance criteria · design.md lacked IA/accessibility/decisions · no manual test plan / demo script. All rewritten.

## C. Not changed (deliberate) / limitations
Lexical retrieval (no embeddings), no auth, evaluation by LLM-judge out of scope. The Pi RPC path was executed against a stub OpenAI-compatible server (installed with yarn; npm crashed in the sandbox): it used `/v1/chat/completions` with the base URL from `OLLAMA_BASE_URL`, streamed deltas and returned a cited answer. Not executed anywhere in the audit: `docker compose up --build`, real Ollama models, a real browser. Please run `DEMO_SCRIPT.md` once on your machine with real Ollama before submitting.

## D. Verification summary
Backend 101/101 pass · Frontend 9/9 pass · `tsc` clean + `vite build` OK · Live run: grounded answer with YouTube deep-link citation, follow-up using session memory, out-of-domain abstention (0 tokens, 0 citations), essay via chat, hostile model output (`<script>`, `onclick`) stripped and logged as `artifact_sanitized`.
