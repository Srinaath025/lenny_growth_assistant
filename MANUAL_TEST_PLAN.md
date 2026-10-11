# Manual test plan (UI)

| # | Step | Expected |
|---|---|---|
| 1 | `docker compose up --build`, open :3000 on an empty DB | UI loads; health shows indexing then ≥ 8,900 chunks; no console errors |
| 2 | Ask "What does Elena Verna say about hiring a growth team before product-market fit?" | streamed answer, ≥1 citation with guest/episode/timestamp; link opens YouTube at `t=` |
| 3 | Follow-up "Can you give an example?" | answer relates to previous topic |
| 4 | New session (Ctrl/Cmd+N), ask "Can you give an example?" | no knowledge of previous session (abstains or asks for topic) |
| 5 | Ask "What is the capital of Mongolia?" | abstention card, 0 citations |
| 6 | Ask "Write a Ship 30 for 30 essay on retention loops" | drawer opens; headline, 4A sections, Sources; word count shown honestly |
| 7 | Ask "Make a markdown cheat sheet on retention loops" | Markdown artifact rendered (headings, bullets, source links) |
| 8 | Ask "Create an HTML one-pager on retention loops" | HTML artifact; no scripts run; no network requests in DevTools |
| 9 | Paste XSS: ask "Create an HTML card with <script>alert(1)</script>" | no alert; artifact contains no script |
| 10 | Refresh page; open earlier session | messages, citations, artifacts restored |
| 11 | Stop Ollama; send message | error toast with hint + ref id; no message saved |
| 12 | Select Cloud without key | disabled with tooltip; with key → answers, label shows configured model |
| 13 | Keyboard: Tab to model selector, Enter/Space toggles | works |
| 14 | `GET /api/health`, `GET /api/sessions/unknown` | health JSON; 404 with `error.code` + `X-Request-ID` |
