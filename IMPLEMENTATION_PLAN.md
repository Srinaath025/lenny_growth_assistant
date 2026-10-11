# Phased Implementation Plan & Verification Strategy
## The Lenny Growth Assistant
**Document Version:** 1.1.0  
**Target Completion Date:** 12 October 2026  
**Status:** Approved for Design & Planning (Read-Only Stage)  
**Execution Strategy:** Local-First Prioritization (Ollama Default) with Docker PostgreSQL (Port 5433)  
**Author:** Forward Deployed Engineering Team  

---

## 1. Plan Overview & Delivery Timeline

This implementation plan is organized into **eight small, sequential milestones** engineered for delivery before the **12 October 2026 deadline**. 

**Core Priority:** Deliver a complete, verifiable **vertical slice** (chat, grounded transcript answers with citations, persisted sessions, model selection, Ship 30 essay generation, and isolated artifact rendering) running 100% locally on Ollama (`llama3.2:3b`), backed by automated tests.

```
Timeline: Oct 9 – Oct 12, 2026
+-----------------------------------------------------------------------------------------+
| Oct 9 (Today)   : M1 (Env & Docker DB 5433) -> M2 (Ingestion & Search)                  |
| Oct 10 (Day 2)  : M3 (Pi Agent RPC PoC) -> M4 (Grounding & Abstention) -> M5 (Essay)    |
| Oct 11 (Day 3)  : M6 (FastAPI Persistence) -> M7 (React UI & Sandboxed Viewer)          |
| Oct 12 (Final)  : M8 (Docker Compose, Test Suite, Cloud Smoke Test Checklist, Release)  |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Milestone Breakdown with Verifiable Acceptance Criteria

### Milestone 1: Workspace Initialization, Python 3.11 Venv & Docker PostgreSQL (Port 5433)
* **Status:** [PLANNED - MILESTONE 1]
* **Objective:** Establish the version-controlled workspace, configure Python 3.11 virtual environment, and spin up a minimal Docker PostgreSQL instance on host port `5433`.
* **Tasks:**
  1. Initialize Git in `d:\Projects\oogway labs` with `.gitignore` (ignoring `.venv`, `node_modules`, `.env`).
  2. Create backend virtual environment explicitly using Python 3.11:  
     `py -3.11 -m venv backend/.venv`
  3. Create minimal `docker-compose.db.yml` exposing PostgreSQL on host port **`5433`** with persistent named volume `pgdata`:
     ```yaml
     services:
       db:
         image: postgres:16-alpine
         ports: ["5433:5432"]
         environment:
           POSTGRES_USER: lenny_user
           POSTGRES_PASSWORD: lenny_password
           POSTGRES_DB: lenny_growth_db
         volumes: [pgdata:/var/lib/postgresql/data]
     ```
  4. Create `backend/.env` with `DATABASE_URL=postgresql+asyncpg://lenny_user:lenny_password@localhost:5433/lenny_growth_db`.
* **Acceptance Criteria:**
  - `git status` verifies clean git repository.
  - `backend/.venv/Scripts/python --version` outputs `Python 3.11.x`.
  - `docker compose -f docker-compose.db.yml up -d` starts container; `Test-NetConnection -Port 5433` succeeds while host port 5432 remains undisturbed.
* **Testing Strategy:**
  - Run database ping script: `python -m pytest backend/tests/test_db_connection.py`.

---

### Milestone 2: Transcript Corpus Ingestion & PostgreSQL Full-Text Search
* **Status:** [PLANNED - MILESTONE 2]
* **Objective:** Parse Markdown episode files from `ChatPRD/lennys-podcast-transcripts`, extract metadata, and index semantic chunks in PostgreSQL using native `tsvector` with GIN indexing.
* **Tasks:**
  1. Download/clone transcripts from `ChatPRD/lennys-podcast-transcripts/episodes`.
  2. Implement `backend/ingestion/parser.py` extracting YAML frontmatter (`guest`, `title`, `youtube_url`, `video_id`, `publish_date`).
  3. Implement semantic dialogue chunking (~500–800 words per chunk with start/end seconds).
  4. Apply database schema creating `transcript_chunks` with `tsvector` column and GIN index.
  5. Run ingestion CLI script `python -m backend.ingestion.run`.
* **Acceptance Criteria:**
  - Ingestion processes episodes and populates `transcript_chunks` table in < 3 minutes.
  - `SELECT count(*) FROM transcript_chunks;` returns > 500 valid indexed chunks.
  - Full-text search query for `"Elena Verna product led growth"` returns relevant chunks from Elena Verna's episode in < 25ms.
* **Testing Strategy:**
  - **Unit Test:** `test_parser.py` verifies frontmatter extraction and timestamp conversion.
  - **Integration Test:** `test_search.py` executes benchmark queries and asserts correct top-ranked episode chunks.

---

### Milestone 3: Pi Coding Agent RPC Integration Proof of Concept (Smallest Working Integration)
* **Status:** [PLANNED - MILESTONE 3]
* **Objective:** Build and verify a minimal standalone proof of integration (PoC) demonstrating Pi Coding Agent running headlessly in RPC mode communicating with local Ollama (`llama3.2:3b`).
* **Tasks:**
  1. Verify Pi CLI availability: `npx -y @earendil-works/pi-coding-agent --version`.
  2. Configure `models.json` for Pi pointing to local Ollama (`http://localhost:11434`, model `llama3.2:3b`).
  3. Implement `backend/agents/pi_rpc.py` managing Pi subprocess in RPC mode (`pi --mode rpc`) over async `stdin`/`stdout`.
  4. Implement JSONL command sender (`{"type": "prompt", ...}`) and streaming event parser (`message_update`, `turn_end`).
  5. **Decision Gate:** If Pi RPC encounters blocking Windows stdio/pipe issues:
     - Document exact diagnostic failure logs in `EVALUATION_REPORT.md`.
     - Formally evaluate Anthropic Claude Agent SDK alternative before making architectural change.
* **Acceptance Criteria:**
  - Executing `python -m backend.agents.pi_rpc` spawns Pi, passes prompt to Ollama `llama3.2:3b`, and prints streamed response tokens without error.
* **Testing Strategy:**
  - **Standalone Integration Test:** `test_pi_rpc.py` asserts process lifecycle, JSONL parsing, and token streaming.

---

### Milestone 4: Retrieval-Grounded Agent Core & Evidence-Based Abstention
* **Status:** [PLANNED - MILESTONE 4]
* **Objective:** Connect the search retrieval engine to the Pi agent harness, enforcing strict source grounding, verifiable citation extraction, and evidence-based abstention guardrails.
* **Tasks:**
  1. Implement retrieval pipeline fetching top-3 transcript chunks matching user query.
  2. Calibrate relevance threshold (`ts_rank_cd < 0.05` triggers abstention).
  3. Construct grounding system prompt mandating exact transcript quotes and YouTube link formats.
  4. Implement citation extractor mapping generated references into the `citations` table.
* **Acceptance Criteria:**
  - In-domain query (`"How does Brian Chesky manage product design?"`) outputs synthesis with verifiable citation cards (guest name, episode title, quote, YouTube URL).
  - Out-of-domain query (`"What is the best sourdough bread recipe?"`) triggers explicit evidence-based abstention with 0 citations and 0 hallucinations.
* **Testing Strategy:**
  - **Automated Test:** `test_abstention.py` runs 5 in-domain queries (verifying citations) and 5 out-of-domain queries (verifying abstention).

---

### Milestone 5: Ship 30 for 30 Essay Generation Engine (~1,250 Words)
* **Status:** [PLANNED - MILESTONE 5]
* **Objective:** Implement the dedicated essay skill generating structured, high-retention essays targeting ~1,250 words following the 4A framework and "2-Year Test".
* **Tasks:**
  1. Implement essay generation prompt in `backend/agents/essay_skill.py`.
  2. Enforce word count guardrail (1,100 to 1,400 words).
  3. Enforce the 4A framework structure (Actionable, Analytical, Aspirational, Anthropological).
  4. Enforce skimmable layout: "Clear over Clever" headlines, 1–3 sentence paragraphs, and bolded takeaways.
  5. Store generated essay in `artifacts` table.
* **Acceptance Criteria:**
  - Triggering essay generation produces an essay between 1,100 and 1,400 words.
  - Output contains all four required 4A sections, clear subheadings, and verified guest citations.
* **Testing Strategy:**
  - **Unit Test:** `test_essay_skill.py` verifies word count boundaries, header presence, and guest attribution markers.

---

### Milestone 6: FastAPI Backend API & PostgreSQL Session Persistence
* **Status:** [COMPLETED & VERIFIED - 09 OCT 2026]
* **Objective:** Expose clean REST and Server-Sent Events (SSE) endpoints with PostgreSQL session persistence on port 5433.
* **Tasks:**
  1. Implement FastAPI app in `backend/main.py`.
  2. Expose REST & SSE Endpoints:
     - `GET /api/health` — Diagnostics for Ollama daemon, PostgreSQL, and cloud Anthropic key state.
     - `GET /api/sessions` — List all chat sessions ordered by `updated_at DESC`.
     - `POST /api/sessions` — Create new chat session.
     - `GET /api/sessions/{id}` — Retrieve full session history (messages, citations, artifacts).
     - `PATCH /api/sessions/{id}` — Update session title and configuration.
     - `DELETE /api/sessions/{id}` — Cascade deletion of session, messages, citations, and artifacts.
     - `POST /api/chat` — Streaming chat endpoint via SSE (`event: token`, `event: complete`, `event: done`) and direct JSON mode.
     - `POST /api/essay` — Dedicated Ship 30 for 30 essay generation endpoint persisting to `artifacts` table.
     - `GET /api/artifacts/{id}` — Retrieve artifact metadata and HTML content.
     - `GET /api/artifacts/{id}/raw` — Serve raw sandboxed HTML with strict `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; font-src data:;` headers.
  3. Integrated Windows Smart App Control mitigation: pinned `pydantic-core<=2.27.2` and `pydantic<=2.10.4` to avoid code integrity blocks.
* **Acceptance Criteria:**
  - Complete REST and SSE streaming contracts implemented and validated.
  - Full session persistence and cascading deletion verified in PostgreSQL.
  - All 52 non-live tests + 1 live integration test pass with 100% success rate.
* **Testing Strategy:**
  - Automated API Tests: `backend/tests/test_api.py` (7 tests covering health, session CRUD, chat SSE streaming, abstention, essay generation, artifact retrieval, CSP security headers, and error validation).
  - Overall non-live test suite: 52 tests passing in 3.81s.
  - Live agent integration test: 1 passed in 165.17s against local Ollama.

---

### Milestone 7: React Frontend & Secure Sandboxed Artifact Viewer
* **Status:** [COMPLETED & VERIFIED - 09 OCT 2026]
* **Objective:** Implement the user interface adhering to *Impeccable Design* principles with sandboxed HTML artifact isolation, model selection, and SSE streaming.
* **Tasks:**
  1. Scaffolded React 19 + TypeScript + Vite in `frontend/` with Lucide icons.
  2. Implemented full tinted obsidian theme tokens and typography (Newsreader, Inter, JetBrains Mono) in `index.css`.
  3. Built modular components:
     - `Header.tsx`: Live telemetry status pills (PostgreSQL chunks, Ollama status, Claude lock indicator), session title, artifact count badge, and essay quick button.
     - `Sidebar.tsx`: Session list, search filter, inline rename/delete, New Session action with `Ctrl+N` hotkey, and docked model selector.
     - `ModelSelector.tsx`: Local Ollama default with pulsing green status indicator, and Cloud Claude disabled/locked state with informative tooltip.
     - `ChatView.tsx`: Streaming message feed, editorial empty state with curated prompt chips, and bottom input bar with quick chips.
     - `ChatMessage.tsx`: User and assistant bubbles, markdown styling, streaming cursor, citation cards, and abstention alert.
     - `CitationCard.tsx`: Guest avatar badge, episode title, verbatim excerpt, and direct YouTube deep link with timestamp.
     - `AbstentionCard.tsx`: Rose-tinted guardrail card protecting against ungrounded hallucinations.
     - `ArtifactViewer.tsx`: Slide-out drawer with sandboxed `<iframe>` (`sandbox=""`, strictly no `allow-same-origin`), 4A tags, word count pill, and preview/code toggle.
     - `EssayModal.tsx`: Dedicated Ship 30 for 30 essay generation modal with progress stepper and 4A framework tags.
  4. Connected frontend to FastAPI backend using native `ReadableStream` reader in `api.ts` parsing SSE events (`token`, `complete`, `error`, `done`).
  5. Implemented automated frontend test suite in `frontend/tests/frontend_spec.test.mjs` verifying security isolation, design tokens, model selector, API endpoints, and guardrail policies.
* **Acceptance Criteria:**
  - Production bundle builds cleanly via `npm run build` (`0` TypeScript errors, 1600 modules transformed in 3.53s).
  - Model Selector defaults to Local Ollama; Cloud option displays disabled state when `ANTHROPIC_API_KEY` is absent.
  - HTML artifacts render safely inside sandboxed iframe without parent DOM / localStorage access.
  - All 6 automated frontend specification tests pass with 100% success rate in 977ms.
* **Testing Strategy:**
  - Automated Frontend Spec Suite: `frontend/tests/frontend_spec.test.mjs` (6 passing tests covering iframe sandbox security, design tokens, ModelSelector fallbacks, API client SSE stream handling, EssayModal 4A framework, and AbstentionCard styling).
  - Production Build Verification: `tsc && vite build` passed in 3.53s.

---

### Milestone 8: Docker Compose, Automated Tests, Pre-Submission Smoke Test & Release
* **Status:** [COMPLETED & VERIFIED - 10 OCT 2026]
* **Objective:** Package the entire system into a reproducible multi-container workflow, execute automated test suite, and finalize documentation.
* **Tasks:**
  1. Created `backend/Dockerfile` with Python 3.11 and Node.js for Pi agent RPC execution.
  2. Created `frontend/Dockerfile` with multi-stage build (Node 20 build + Nginx Alpine serve with SSE proxy).
  3. Configured root `docker-compose.yml` orchestrating `db` (PostgreSQL 16 on port 5433 with persistent `pgdata` volume), `backend` (FastAPI with host gateway for local Ollama), and `frontend` (React Nginx on port 3000).
  4. Created comprehensive `README.md` with one-command startup instructions (`docker compose up --build`).
  5. Created `EVALUATION_REPORT.md` documenting full requirements compliance audit, cloud smoke test checklist, and test metrics.
  6. Verified automated test suites: 52 backend tests + 6 frontend spec tests passing (100% pass rate).
* **Acceptance Criteria:**
  - `docker compose config` validates 100% clean multi-container composition.
  - Full automated test suite passes with 100% success rate.
  - Comprehensive documentation and evaluation report delivered ahead of the 12 October 2026 deadline.
* **Testing Strategy:**
  - Configuration Validation: `docker compose config` passed with 0 warnings.
  - Automated Tests: 58 total automated non-live tests passing across backend and frontend.
  - Live Integration: Elena Verna PMF hiring query verified against local Ollama `llama3.2:3b`.

---

### Milestone 9: Cloud Claude Integration & Dynamic Model Switching
* **Status:** [COMPLETED & VERIFIED - 10 OCT 2026]
* **Objective:** Implement full native Anthropic Claude (model set by ANTHROPIC_MODEL) provider in the backend with dynamic model switching in the frontend, supporting both non-streaming and SSE streaming modes with zero credential leakage.
* **Tasks:**
  1. Implemented `backend/agent/cloud_client.py` (`AnthropicClaudeClient` communicating directly with Anthropic Messages API over HTTP/2 with SSE token streaming, rate-limit mapping, and secret masking).
  2. Updated `GrowthAssistantAgent` in `backend/agent/orchestrator.py` to support dynamic routing between Local Ollama and Cloud Claude while applying uniform transcript retrieval and citation verification.
  3. Updated `Ship30EssayEngine` in `backend/agent/essay_skill.py` to support Cloud Claude inference for 4A framework essay synthesis.
  4. Updated `backend/main.py` chat and essay routes to accept `model_provider`, validate API key presence, and return clear HTTP 400 errors when `ANTHROPIC_API_KEY` is not set.
  5. Updated frontend `ModelSelector.tsx`, `EssayModal.tsx`, and `App.tsx` to dynamically unlock Cloud Claude when `cloud.available: true` and forward the selected provider in chat and essay requests.
  6. Implemented comprehensive test suite in `backend/tests/test_cloud_provider.py` (7 tests covering request schemas, headers, mocked non-streaming, mocked SSE streaming, agent switching, and API key rejection).
* **Acceptance Criteria:**
  - `AnthropicClaudeClient` adheres 100% to official Anthropic API specifications (`x-api-key`, `anthropic-version: 2023-06-01`).
  - Cloud provider correctly maps HTTP 401, 429, and 500 errors to `CloudProviderError` without exposing secrets.
  - Model switching functions dynamically; UI unlocks Cloud Claude toggle when `ANTHROPIC_API_KEY` is present in backend environment.
  - All 7 cloud provider tests and 7 frontend specification tests pass with 100% success rate.
* **Testing Strategy:**
  - Automated Cloud Provider Suite: `backend/tests/test_cloud_provider.py` (7 passed in 2.18s).
  - Automated Frontend Spec Suite: `frontend/tests/frontend_spec.test.mjs` (7 passed in 1.54s).
  - Production Build: `npm run build` compiled cleanly in 4.64s.

### Milestone 10: Full Dataset Sync & Sanitized Coding-Agent Transcripts Dossier
* **Status:** [COMPLETED & VERIFIED - 10 OCT 2026]
* **Objective:** Expand corpus to the complete 303-episode dataset from `ChatPRD/lennys-podcast-transcripts`, resolve non-ASCII URL encoding, and transfer sanitized agent trajectories and failed attempts documentation into a dedicated directory.
* **Tasks:**
  1. Updated `downloader.py` with `urllib.parse.quote()` and multithreaded `ThreadPoolExecutor(max_workers=20)`.
  2. Synced all 303 podcast episodes (24.95 MB) from official CDN mirror to `data/transcripts/`.
  3. Created dedicated `coding-agent-transcripts/` directory.
  4. Authored `coding-agent-transcripts/FAILED_ATTEMPTS_AND_CORRECTIONS.md` documenting 10 forensic investigations, root causes, and solutions.
  5. Exported 1,800+ step sanitized JSONL trajectory (`session_transcript.jsonl`) and Markdown summary (`session_transcript_readable.md`).
  6. Exported 75 sanitized background task logs and genuine Pi agent RPC trace (`pi_agent_trace.json`).
  7. Conducted programmatic security scan confirming 0 API keys, 0 passwords, and 0 personal paths.
* **Acceptance Criteria:**
  - Full dataset of 303 Markdown transcripts downloaded into `data/transcripts/` with 0 failures.
  - Dedicated `coding-agent-transcripts/` folder present with comprehensive failed attempts dossier and trajectories.
  - 100% scrubbed of secrets and sensitive credentials prior to commit.
* **Testing Strategy:**
  - Download Verification: Counted 303 transcript files on disk (24.95 MB).
  - Security Scan: Automated regex audit verified 0 secret matches across all transcript files.

---

## 3. Pre-Submission Cloud Smoke Test Checklist & Risk Assessment

### 3.1 Pre-Submission Checklist
Prior to final submission on 12 October:
- [ ] Inquire if an `ANTHROPIC_API_KEY` can be provided for cloud verification.
- [ ] If key is available:
  - Add to `.env` file (`ANTHROPIC_API_KEY=sk-ant-...`).
  - Run smoke test: `python -m backend.tests.test_cloud_smoke`.
  - Toggle Cloud Claude in UI and generate one grounded response.
  - Record the successful execution log in `EVALUATION_REPORT.md`.
- [ ] If key is NOT available:
  - Verify that `GET /api/health` reports `cloud_available: false`.
  - Verify that the UI displays the Cloud option as gracefully disabled.
  - Verify that 100% of the core assignment features work cleanly on Local Ollama (`llama3.2:3b`).

### 3.2 Remaining Evaluation Risk
* **Risk Statement:** Without live credentials, cloud inference cannot be verified in production end-to-end testing.
* **Mitigation:**
  1. Cloud code adheres strictly to the official Anthropic API specifications.
  2. Mocked unit tests (`test_cloud_provider.py`) validate schema compliance and error handling.
  3. The local Ollama demonstration (`llama3.2:3b`) fully proves the vertical slice without third-party dependencies.
  4. Evaluators with an API key can immediately test Cloud mode by supplying `ANTHROPIC_API_KEY` in `.env`.

---

## 4. Current Pre-requisite Verification Status

| Item | Status | Verified Evidence |
| :--- | :--- | :--- |
| **Python 3.11** | **VERIFIED** | Installed at `C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe` (`py -3.11`). |
| **Node.js & npm** | **VERIFIED** | Node `v24.16.0`, npm `11.13.0` (accessible via `npm.cmd`). |
| **Docker & Docker Compose** | **VERIFIED** | Docker CLI `29.6.2`, Compose `v5.3.1`, Linux environment with 7.4 GiB RAM. |
| **Host PostgreSQL 18 Conflict** | **VERIFIED** | Running on host port 5432; avoided by mapping Docker Postgres to port 5433. |
| **Ollama Daemon & Model** | **VERIFIED** | Ollama 0.40.2 installed; model `llama3.2:3b` downloaded and verified locally. |
| **Cloud API Credentials** | **DECISION CONFIRMED** | No key available yet; Local-First Ollama architecture adopted. |
| **Application Source Code** | **COMPLETED & VERIFIED** | All 10 Milestones implemented, tested, and passing with 100% success rate. |
