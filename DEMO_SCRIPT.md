# Demo script (≈ 4 minutes, screen recording)

**Before recording:** `ollama pull llama3.2:3b` · `cp .env.example .env` · `docker compose up --build` · wait until the header shows the knowledge base ready (`/api/health` → `ingestion.state: done|skipped`). Open http://localhost:3000.

| Time | Action | Say / show |
|---|---|---|
| 0:00 | Open app, point at header badges | "Local-first: Postgres + Ollama; 8,947 indexed chunks; cloud is opt-in." |
| 0:20 | Click starter *"What are Elena Verna's rules for … self-serve pricing?"* | Streaming answer; open a **citation card** → click the YouTube link → lands at the timestamp. "Every claim is verifiable." |
| 1:00 | Type **"Can you give an example?"** | "Follow-up uses this session's memory; another session would not see it." |
| 1:25 | Type **"What is the capital of Mongolia?"** | Abstention card, no sources, no LLM call. "Gate at retrieval, prompt and validator." |
| 1:55 | Type **"Write a Ship 30 for 30 essay on retention loops"** | Status line → artifact drawer opens; show 4A sections, word count, Sources footer; toggle *Source*. "Skill lives in `backend/skills/ship30/SKILL.md`." |
| 2:45 | Type **"Create an HTML card summarizing the retention loop advice"** | HTML artifact in viewer. Open DevTools → iframe has `sandbox=""`; explain 3 layers (sanitizer, sandbox, CSP). |
| 3:20 | Stop Ollama (or set a wrong model) and send a message | Structured error with hint + request id; nothing stored. Restart Ollama. |
| 3:40 | Show `docker compose logs backend` | JSON logs: `intent_routed`, `retrieval` (coverage), `artifact_sanitized`, request ids. |
| 3:55 | Edit `.env` `OLLAMA_MODEL`, restart | "Model switch needs no code change." |

Fallback if the 3B model is slow: pick *Cloud Claude* (needs `ANTHROPIC_API_KEY`) to show the toggle.
