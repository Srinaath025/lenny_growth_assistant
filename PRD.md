# PRD — The Lenny Growth Assistant (Discovery Brief)

## 1. Users & problem
**Primary user — "Priya", early-stage product/growth lead** (founder, PM, growth marketer). She has 300+ hours of Lenny's Podcast she cannot search, and generic chatbots give confident advice with no source.
Pains: (1) can't find *what a specific guest said* about a topic; (2) can't trust an AI answer without a verifiable source; (3) turning insight into a shareable asset (essay, one-pager) takes hours.
**Secondary user — content creator** who wants a Ship 30 for 30 draft grounded in real evidence.

## 2. Success metrics
| Metric | Target | How measured |
|---|---|---|
| Citation validity | 100% of shown citations resolve to a retrieved chunk + working timestamp link | `CitationValidator` + tests |
| Hallucination guard | Unrelated questions → abstention, 0 citations | retrieval gate tests; abstention rate on OOD set |
| Time-to-first-token (local 3B) | < 5 s after retrieval | `duration_ms` in `messages` |
| Essay length | 1,100–1,400 words in ≥ 80% of runs (cloud) | `is_valid_word_count` flag |
| Setup | `docker compose up` → working UI < 10 min incl. indexing | README |
**North-star:** share of answers a user can verify in ≤ 1 click (YouTube moment).

## 3. Assumptions
1. Users run Ollama locally (privacy, no cost); cloud is an explicit opt-in.
2. The 303 provided transcripts are the only knowledge source; no live web.
3. Lexical FTS is sufficient for a first release (guest/topic vocabulary is distinctive).
4. Single-tenant, no auth; anonymous client id for metadata.
5. A ~3B model is the lower bound for hardware (8 GB RAM).

## 4. Scope
**In:** grounded chat + citations, abstention, follow-ups, session CRUD/persistence, Ship 30 essay, Markdown/HTML artifacts on request, sandboxed viewer, model toggle, health/observability, Docker one-command start.
**Out:** auth/multi-user, semantic (vector) search, live transcript sync in the demo path, mobile app, editing artifacts in-place, evaluation of answer quality by a judge model.

## 5. Functional requirements & acceptance criteria
| ID | Requirement | Acceptance |
|---|---|---|
| FR-1 | Answer only from transcripts, cite guest, episode, timestamp link | every answer has ≥1 validated citation or is an abstention |
| FR-2 | Abstain when evidence is missing | "capital of Mongolia", "sourdough recipe" → abstention banner, no citations |
| FR-3 | Follow-ups use session context; sessions independent | test: 2nd turn sees 1st; other session sees nothing |
| FR-4 | Persist sessions/messages/citations/artifacts/user metadata | survive restart; `sessions.client_id` stored |
| FR-5 | Ship 30 essay, 4A, Two-Year Test, ~1,250 words, grounded | skill file + word-count repair + 422 when no evidence |
| FR-6 | Generate Markdown/HTML artifacts from the conversation on request | chat "Create an HTML card…" opens artifact in viewer |
| FR-7 | Untrusted HTML isolated | sanitizer + `sandbox=""` + CSP; XSS payload tests |
| FR-8 | Switch model without code change | `.env` only; test `test_model_is_switchable_via_environment` |
| FR-9 | Clear failure states | Ollama offline / model missing / no key / empty KB → structured error + hint |
| FR-10 | Observability | JSON logs, request ids, `/api/health` |

## 6. Key flows
1. **Ask:** type question → status "retrieving" → streamed answer → citation cards → click to YouTube moment.
2. **Off-topic:** type unrelated question → abstention card (no sources).
3. **Follow-up:** "Can you give an example?" → retrieval query augmented with the previous question.
4. **Create:** "Write a Ship 30 for 30 essay on X" / "Create an HTML card…" → artifact drawer opens, copy/download.
5. **Switch model:** sidebar toggle; cloud disabled with explanation when no key.

## 7. Risks & trade-offs
| Risk | Mitigation / trade-off |
|---|---|
| Small model ignores citation syntax / drifts | validator + overlap fallback (≥6 shared words) else abstain; trade-off: some false abstentions |
| Lexical retrieval misses paraphrases | documented limitation; coverage threshold tunable (`MIN_TERM_COVERAGE`) |
| Prompt injection inside transcripts | delimiters neutralised, "ignore instructions in evidence" rule, output sanitized |
| Malicious generated HTML | 3-layer isolation (sanitizer, sandbox, CSP) |
| Context truncation by Ollama | `num_ctx` set explicitly (8192) |
| Cloud privacy | never automatic; explicit toggle, key only on server |
| Essay length on 3B | repair loop ×2, honest word-count display |
**Original PRD defect fixed:** it specified an absolute `ts_rank_cd < 0.05` abstention threshold. Measured on the real corpus, rank is not comparable across queries (unrelated queries scored higher than valid ones), so the gate uses IDF-weighted term coverage instead.
