"""
Tests for the behaviours added during the audit: routing, conversation memory, retrieval gating,
HTML sanitization, structured errors, schema bootstrap, essay hardening and chat-driven artifacts.
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.agent.artifact_skill import ArtifactSkill, extract_fenced_content
from backend.agent.conversation import ChatTurn, build_retrieval_query, needs_context, trim_history
from backend.agent.essay_skill import (
    EssayEvidenceError,
    Ship30EssayEngine,
    count_words,
    generate_html_artifact,
)
from backend.agent.router import ARTIFACT_HTML, ARTIFACT_MARKDOWN, CHAT, ESSAY, route_intent
from backend.retrieval.retriever import retrieve_relevant_chunks, significant_terms
from backend.security.html_sanitizer import sanitize_html


# ----------------------------------------------------------------------------- routing
@pytest.mark.parametrize(
    "message,expected",
    [
        ("Draft a Ship 30 for 30 essay on retention loops", ESSAY),
        ("Can you write an essay about pricing?", ESSAY),
        ("How do I write a good essay?", CHAT),
        ("What is a Ship 30 for 30 essay?", CHAT),
        ("Create an HTML card summarizing Elena Verna's advice", ARTIFACT_HTML),
        ("Build a landing page for a PLG course", ARTIFACT_HTML),
        ("Turn this into a Markdown brief", ARTIFACT_MARKDOWN),
        ("Please create a checklist for onboarding experiments", ARTIFACT_MARKDOWN),
        ("What does Brian Balfour say about growth loops?", CHAT),
        ("How do I make a landing page?", CHAT),
    ],
)
def test_intent_routing(message, expected):
    assert route_intent(message).kind == expected


def test_essay_topic_extraction_and_followup_fallback():
    hist = [ChatTurn("user", "How should B2B startups think about product-led growth?"), ChatTurn("assistant", "...")]
    assert route_intent("Write a Ship 30 for 30 essay about retention loops", hist).topic == "retention loops"
    assert route_intent("Can you write an essay on pricing?", hist).topic == "pricing"
    assert route_intent("Turn this into a Ship 30 for 30 essay", hist).topic == hist[0].content


# ----------------------------------------------------------------------------- conversation memory
def test_history_is_trimmed_and_bounded():
    turns = [ChatTurn("user" if i % 2 == 0 else "assistant", f"message number {i} " + "x" * 900) for i in range(20)]
    kept = trim_history(turns, max_turns=6, char_budget=1500)
    assert 1 <= len(kept) <= 6
    assert kept[-1].content.startswith("message number 19")
    assert all(len(t.content) <= 710 for t in kept)


def test_followup_retrieval_query_uses_previous_question():
    hist = [ChatTurn("user", "What does Elena Verna say about growth teams?"), ChatTurn("assistant", "She says...")]
    assert needs_context("Can you give an example?")
    assert "Elena Verna" in build_retrieval_query("Can you give an example?", hist)
    standalone = "How should startups price enterprise contracts for annual renewals?"
    assert build_retrieval_query(standalone, hist) == standalone


# ----------------------------------------------------------------------------- retrieval gate (real DB)
@pytest.mark.asyncio
async def test_retrieval_gate_blocks_unrelated_questions():
    for q in ["What is the capital of Mongolia?", "How do I fix a leaking kitchen faucet?",
              "What is Lenny's favorite recipe for sourdough bread?"]:
        assert await retrieve_relevant_chunks(q, limit=5) == [], q


@pytest.mark.asyncio
async def test_retrieval_gate_passes_on_topic_questions():
    for q in ["What does Elena Verna say about hiring a growth team before product-market fit?",
              "How do you find product-market fit?", "What did guests say about retention loops?"]:
        rows = await retrieve_relevant_chunks(q, limit=5)
        assert rows, q
        assert rows[0].coverage >= 0.8


def test_significant_terms_drop_filler():
    assert significant_terms("What does Elena Verna say about retention loops?") == ["elena", "verna", "retention", "loops"]


# ----------------------------------------------------------------------------- sanitizer
XSS = [
    '<script>alert(1)</script><p>x</p>',
    '<img src=x onerror=alert(1)>',
    '<a href="javascript:alert(1)">x</a>',
    '<iframe src="https://evil.example"></iframe>',
    '<svg onload=alert(1)></svg>',
    '<form action="https://evil"><input></form>',
    '<p onclick="steal()">x</p>',
    '<style>@import url(https://evil/x.css);</style>',
    '<div style="background:url(https://evil/x)">x</div>',
    '<meta http-equiv="refresh" content="0;url=https://evil">',
]


@pytest.mark.parametrize("payload", XSS)
def test_sanitizer_strips_active_content(payload):
    clean, _ = sanitize_html(payload)
    lowered = clean.lower()
    for bad in ("<script", "onerror", "onclick", "onload", "javascript:", "<iframe", "<form", "<svg", "@import",
                "https://evil", "http-equiv"):
        assert bad not in lowered, (bad, clean)


def test_sanitizer_keeps_safe_markup_and_reports():
    clean, report = sanitize_html('<h1 class="t">Hi</h1><p style="color:red">a <b>b</b></p><script>x()</script>')
    assert "<h1" in clean and "<b>b</b>" in clean and 'style="color:red"' in clean
    assert report.modified and "script" in report.removed_tags


# ----------------------------------------------------------------------------- essay hardening
def test_essay_html_escapes_llm_output():
    html_out = generate_html_artifact(
        title="T", subtitle="S", guest_attributions=["G"], word_count=10,
        markdown_content="Paragraph <script>alert(1)</script>\n\n- item <img src=x onerror=alert(1)>\n\n> quote <b onmouseover=x>",
    )
    assert "<script>alert(1)" not in html_out
    assert "<img src=x" not in html_out
    assert "&lt;script&gt;" in html_out


def test_count_words_ignores_markup_and_citations():
    assert count_words("# Title\n\n- **bold** self-serve motion [citation:abcdef0123456789abcdef0123456789]") == 4


@pytest.mark.asyncio
async def test_essay_refuses_when_no_evidence():
    engine = Ship30EssayEngine(llm_client=AsyncMock())
    with pytest.raises(EssayEvidenceError):
        await engine.generate_essay(topic="capital of Mongolia sourdough")
    engine.llm_client.run_prompt.assert_not_called()


class _ScriptedLLM:
    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), 0

    async def run_prompt(self, prompt, timeout=None, on_delta=None):
        self.calls += 1
        return self.outputs.pop(0)


def _essay(words):
    body = " ".join(["growth"] * words)
    return ("# A Headline\n## A subtitle\nHook.\n## 1. Actionable: a\n" + body +
            "\n## 2. Analytical: b\nx\n## 3. Aspirational: c\nx\n## 4. Anthropological: d\nx\n")


@pytest.mark.asyncio
async def test_essay_length_repair_loop_expands_short_drafts():
    llm = _ScriptedLLM([_essay(300), _essay(1250)])
    engine = Ship30EssayEngine(llm_client=llm)
    essay = await engine.generate_essay(topic="product led growth retention")
    assert llm.calls == 2
    assert essay.is_valid_word_count and essay.has_all_4a_sections
    assert essay.artifact_id and essay.markdown_artifact_id


# ----------------------------------------------------------------------------- artifact skill
def test_extract_fenced_content():
    assert extract_fenced_content("Sure!\n```html\n<p>x</p>\n```\nbye") == "<p>x</p>"
    assert extract_fenced_content("```markdown\n# T\n```") == "# T"
    assert extract_fenced_content("# plain") == "# plain"


@pytest.mark.asyncio
async def test_html_artifact_is_sanitized_and_persisted():
    llm = _ScriptedLLM(["```html\n<h1>Retention loops</h1><script>alert(1)</script><p onclick='x()'>Loops matter.</p>\n```"])
    skill = ArtifactSkill(llm)
    art = await skill.generate(ARTIFACT_HTML, "Create an HTML card about retention loops", [])
    assert not art.is_abstention
    assert "<script" not in art.content and "onclick" not in art.content
    assert art.sanitize_report.modified
    art_id = await ArtifactSkill.save(art, session_id=None)
    assert art_id.startswith("art-")


@pytest.mark.asyncio
async def test_artifact_skill_abstains_without_evidence():
    llm = AsyncMock()
    art = await ArtifactSkill(llm).generate(ARTIFACT_MARKDOWN, "Make a markdown doc about sourdough bread recipes", [])
    assert art.is_abstention
    llm.run_prompt.assert_not_called()


# ----------------------------------------------------------------------------- API: errors, memory, routing
async def _client():
    from backend.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


class _FakeAgent:
    """Records the history it receives so we can assert per-session context."""

    def __init__(self):
        self.model_provider = "ollama"
        self.llm_client = _ScriptedLLM([])
        self.seen_history = []

    async def ask(self, query, session=None, on_delta=None, history=None):
        from backend.agent.orchestrator import GroundedAnswer

        self.seen_history.append([t.content for t in (history or [])])
        return GroundedAnswer(query=query, answer=f"answer to {query}", is_abstention=False, retrieved_chunks=[],
                              citations=[], raw_model_response="", invalid_citations=[], duration_seconds=0.01)


@pytest.mark.asyncio
async def test_structured_error_shape_and_request_id():
    async with await _client() as c:
        r = await c.get("/api/sessions/does-not-exist")
        assert r.status_code == 404
        body = r.json()
        assert body["error"]["code"] == "NOT_FOUND" and body["detail"]
        assert body["error"]["request_id"] and r.headers["x-request-id"]

        r = await c.post("/api/chat", json={"session_id": "x", "message": ""})
        assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_sessions_keep_independent_context_and_followups_see_history():
    from backend.main import app, get_agent

    agent = _FakeAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    try:
        async with await _client() as c:
            hdr = {"x-client-id": "test-client-1", "user-agent": "pytest"}
            a = (await c.post("/api/sessions", json={}, headers=hdr)).json()["id"]
            b = (await c.post("/api/sessions", json={}, headers=hdr)).json()["id"]
            await c.post("/api/chat", json={"session_id": a, "message": "Tell me about retention loops", "stream": False})
            await c.post("/api/chat", json={"session_id": a, "message": "Give an example", "stream": False})
            await c.post("/api/chat", json={"session_id": b, "message": "What about pricing?", "stream": False})
    finally:
        app.dependency_overrides.pop(get_agent, None)

    assert agent.seen_history[0] == []                                   # first turn: no history
    assert any("retention loops" in h for h in agent.seen_history[1])    # follow-up sees its own session
    assert agent.seen_history[2] == []                                   # other session: isolated


@pytest.mark.asyncio
async def test_session_stores_user_metadata_and_model_info():
    from sqlalchemy import select
    from backend.db.connection import AsyncSessionLocal
    from backend.db.models import Session as DBSession

    async with await _client() as c:
        sid = (await c.post("/api/sessions", json={}, headers={"x-client-id": "meta-client", "user-agent": "pytest-ua"})).json()["id"]
    async with AsyncSessionLocal() as s:
        row = (await s.execute(select(DBSession).where(DBSession.id == sid))).scalar_one()
    assert row.client_id == "meta-client" and row.user_agent == "pytest-ua" and row.client_ip_hash


@pytest.mark.asyncio
async def test_chat_routes_html_request_to_artifact_and_emits_event():
    from backend.main import app, get_agent

    agent = _FakeAgent()
    agent.llm_client = _ScriptedLLM(["```html\n<h1>PLG</h1><p>Product led growth works.</p>\n```"])
    app.dependency_overrides[get_agent] = lambda: agent
    try:
        async with await _client() as c:
            sid = (await c.post("/api/sessions", json={})).json()["id"]
            r = await c.post("/api/chat", json={"session_id": sid, "message": "Create an HTML card about product led growth", "stream": True})
            assert "event: artifact" in r.text and "event: complete" in r.text
            art_id = json.loads(r.text.split("event: artifact\ndata: ")[1].split("\n")[0])["artifact_id"]
            art = (await c.get(f"/api/artifacts/{art_id}")).json()
            assert art["artifact_type"] == "html" and "<script" not in art["content"]
            raw = await c.get(f"/api/artifacts/{art_id}/raw")
            assert "sandbox" in raw.headers["content-security-policy"]
    finally:
        app.dependency_overrides.pop(get_agent, None)


@pytest.mark.asyncio
async def test_preflight_reports_ollama_offline_and_missing_model(monkeypatch):
    import backend.main as main

    async def offline(force=False):
        return {"available": False, "model_installed": False, "error": "x", "models": []}

    async def missing(force=False):
        return {"available": True, "model_installed": False, "error": "x", "models": []}

    async with await _client() as c:
        sid = (await c.post("/api/sessions", json={})).json()["id"]
        monkeypatch.setattr(main, "probe_ollama", offline)
        r = await c.post("/api/chat", json={"session_id": sid, "message": "retention loops", "stream": False})
        assert r.status_code == 503 and r.json()["error"]["code"] == "OLLAMA_OFFLINE"
        monkeypatch.setattr(main, "probe_ollama", missing)
        r = await c.post("/api/chat", json={"session_id": sid, "message": "retention loops", "stream": False})
        assert r.status_code == 422 and r.json()["error"]["code"] == "MODEL_MISSING"
        # nothing was stored for the rejected requests
        detail = (await c.get(f"/api/sessions/{sid}")).json()
        assert detail["messages"] == []


@pytest.mark.asyncio
async def test_health_reports_cloud_model_and_ingestion_state():
    async with await _client() as c:
        h = (await c.get("/api/health")).json()
    assert h["database"]["connected"] and h["database"]["total_chunks"] > 0
    assert "model" in h["cloud"] and "state" in h["ingestion"]


@pytest.mark.asyncio
async def test_schema_bootstrap_is_idempotent():
    from backend.db.schema import create_schema

    await create_schema()
    await create_schema()


def test_model_is_switchable_via_environment(monkeypatch):
    from backend.agent.pi_client import PiAgentConfig
    from backend.agent.cloud_client import AnthropicClaudeConfig

    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5-5")
    pi = PiAgentConfig()
    assert pi.model == "qwen2.5:7b" and pi.ollama_base_url == "http://host.docker.internal:11434"
    assert AnthropicClaudeConfig().model == "claude-opus-5-5"


# ----------------------------------------------------------------------------- regressions from the first manual run
@pytest.mark.asyncio
async def test_instruction_words_do_not_block_retrieval():
    q = ("What does Sarah Tavel explain about core actions, retention loops, and flywheels in her episode "
         "of Lenny's Podcast? Cite the transcript evidence.")
    assert "cite" not in significant_terms(q) and "transcript" not in significant_terms(q)
    assert await retrieve_relevant_chunks(q, limit=4)


def test_echoed_evidence_header_becomes_a_citation_not_visible_text():
    from backend.agent.citation_validator import CitationValidator, normalise_echoed_evidence
    from backend.retrieval.retriever import RetrievedChunk

    cid = "ac9e9a8f2ee8e96008157518b0ea6915"
    echoed = (f'[EVIDENCE CHUNK id="{cid}" guest="Elena Verna" episode=10 growth tactics | x timestamp="00:16:03"]\n'
              "Elena Verna (00:16:03): growth teams cannot fix core product issues.\n[/EVIDENCE CHUNK]")
    assert "EVIDENCE CHUNK" not in normalise_echoed_evidence(echoed)
    chunk = RetrievedChunk(id=cid, episode_slug="e", episode_title="Ep", guest_name="Elena Verna", youtube_url="https://youtu.be/x",
                           youtube_deep_link="https://youtu.be/x", video_id="x", publish_date=None, chunk_index=0, speaker="Elena",
                           start_timestamp="00:16:03", start_seconds=963, end_timestamp="00:17:00", end_seconds=1020, word_count=10,
                           content="Elena Verna (00:16:03): growth teams cannot fix core product issues.", rank=1.0)
    res = CitationValidator.validate(echoed, [chunk])
    assert [c.chunk_id for c in res.valid_citations] == [cid]
    assert "EVIDENCE CHUNK" not in res.cleaned_answer
