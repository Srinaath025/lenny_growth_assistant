"""
Comprehensive test suite for the Lenny Growth Assistant FastAPI backend API.
Verifies:
1. GET /api/health diagnostics (DB, Ollama, Cloud key).
2. Chat Session CRUD lifecycle (Create, List, Retrieve, Update title, Delete cascade).
3. POST /api/chat non-streaming contract and PostgreSQL persistence.
4. POST /api/chat streaming SSE contract (events: token, complete, done).
5. POST /api/chat abstention enforcement and citation isolation.
6. POST /api/essay Ship 30 for 30 essay generation and artifact persistence.
7. GET /api/artifacts/{id} and GET /api/artifacts/{id}/raw with CSP security headers.
8. Error handling and 404/400 validation boundaries.
"""

import asyncio
import json
import uuid
import pytest
import httpx
from sqlalchemy import select, delete

from backend.main import app, get_agent, get_essay_engine
from backend.db.connection import AsyncSessionLocal
from backend.db.models import Session as DBSession, Message, CitationRecord, Artifact
from backend.agent.orchestrator import GroundedAnswer, GrowthAssistantAgent
from backend.agent.essay_skill import GeneratedEssay, Ship30EssayEngine
from backend.agent.citation_validator import Citation


# --- Mock Implementations for Controlled Testing ---

class MockGrowthAssistantAgent:
    """Mock agent returning controlled GroundedAnswer with streaming simulation."""

    def __init__(
        self,
        answer: str = "Elena Verna explains that hiring a growth team before PMF leads to premature scaling.",
        is_abstention: bool = False,
        citations=None,
    ):
        self.answer = answer
        self.is_abstention = is_abstention
        if citations is not None:
            self.citations = citations
        elif is_abstention:
            self.citations = []
        else:
            self.citations = [
                Citation(
                    chunk_id="chunk-test-1",
                    episode_title="Elena Verna on PLG",
                    guest_name="Elena Verna",
                    timestamp="00:00:26",
                    start_seconds=26,
                    source_url="https://www.youtube.com/watch?v=mockvideo&t=26s",
                    snippet="Hiring a growth team before product-market fit is a mistake.",
                )
            ]

    async def ask(self, query: str, session=None, on_delta=None, history=None) -> GroundedAnswer:
        if on_delta and not self.is_abstention:
            tokens = self.answer.split(" ")
            for t in tokens:
                res = on_delta(t + " ")
                if asyncio.iscoroutine(res):
                    await res

        return GroundedAnswer(
            query=query,
            answer=self.answer,
            is_abstention=self.is_abstention,
            retrieved_chunks=[],
            citations=[] if self.is_abstention else self.citations,
            raw_model_response=self.answer,
            invalid_citations=[],
            duration_seconds=0.12,
        )


class MockShip30EssayEngine:
    """Mock essay engine returning realistic GeneratedEssay and saving artifact."""

    async def generate_essay(
        self,
        topic: str,
        session_id=None,
        guest_filter=None,
        session=None,
    ) -> GeneratedEssay:
        art_id = f"art-{uuid.uuid4().hex[:12]}"
        title = f"The Product-Led Growth Playbook: {topic}"
        subtitle = "A Tactical Guide Built on Lenny's Podcast Transcripts"
        html_content = (
            f"<!DOCTYPE html><html><head><title>{title}</title></head>"
            f"<body><article><h1>{title}</h1><p>Ship 30 for 30</p></article></body></html>"
        )
        markdown_content = f"# {title}\n\n## {subtitle}\n\n### 1. Actionable Playbook\n..."

        essay = GeneratedEssay(
            title=title,
            subtitle=subtitle,
            topic=topic,
            word_count=1245,
            is_valid_word_count=True,
            has_all_4a_sections=True,
            markdown_content=markdown_content,
            html_content=html_content,
            guest_attributions=["Elena Verna"],
            citations=[],
            artifact_id=art_id,
        )

        # Persist artifact
        art_record = Artifact(
            id=art_id,
            session_id=session_id,
            title=essay.title,
            artifact_type="html",
            content=essay.html_content,
            word_count=essay.word_count,
        )
        if session is not None:
            session.add(art_record)
            await session.commit()
        else:
            async with AsyncSessionLocal() as s:
                s.add(art_record)
                await s.commit()

        return essay


# --- Fixtures ---

@pytest.fixture
def test_client():
    """Provides an ASGI test client bound to the FastAPI application."""
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
async def created_session_id():
    """Creates a temporary chat session in PostgreSQL and cleans it up after test."""
    sess_id = f"test-sess-{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as s:
        db_sess = DBSession(
            id=sess_id,
            title="Automated Test Session",
            model_provider="ollama",
            model_name="llama3.2:3b",
        )
        s.add(db_sess)
        await s.commit()

    yield sess_id

    # Cleanup session and cascaded rows
    async with AsyncSessionLocal() as s:
        stmt = delete(DBSession).where(DBSession.id == sess_id)
        await s.execute(stmt)
        await s.commit()


# --- Test Cases ---

@pytest.mark.asyncio
async def test_health_endpoint(test_client):
    """Verifies GET /api/health reports database status, total chunks, and cloud key state."""
    async with test_client as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()

        assert "status" in data
        assert data["database"]["connected"] is True
        assert data["database"]["total_chunks"] >= 283  # Canonical chunks verified
        assert "ollama" in data
        assert "cloud" in data
        assert data["cloud"]["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_session_lifecycle(test_client):
    """Verifies complete session CRUD: create, list, retrieve, update title, delete."""
    async with test_client as client:
        # 1. Create Session
        create_resp = await client.post(
            "/api/sessions",
            json={"title": "Strategy Exploration", "model_provider": "ollama", "model_name": "llama3.2:3b"},
        )
        assert create_resp.status_code == 201
        new_sess = create_resp.json()
        session_id = new_sess["id"]
        assert new_sess["title"] == "Strategy Exploration"
        assert new_sess["message_count"] == 0

        try:
            # 2. List Sessions
            list_resp = await client.get("/api/sessions")
            assert list_resp.status_code == 200
            sessions = list_resp.json()
            assert any(s["id"] == session_id for s in sessions)

            # 3. Retrieve Session Details
            get_resp = await client.get(f"/api/sessions/{session_id}")
            assert get_resp.status_code == 200
            detail = get_resp.json()
            assert detail["id"] == session_id
            assert detail["title"] == "Strategy Exploration"
            assert detail["messages"] == []
            assert detail["artifacts"] == []

            # 4. Update Session Title
            patch_resp = await client.patch(
                f"/api/sessions/{session_id}",
                json={"title": "Renamed PLG Playbook"},
            )
            assert patch_resp.status_code == 200
            updated = patch_resp.json()
            assert updated["title"] == "Renamed PLG Playbook"

            # 5. Delete Session
            del_resp = await client.delete(f"/api/sessions/{session_id}")
            assert del_resp.status_code == 200
            assert del_resp.json() == {"deleted": True, "id": session_id}

            # 6. Verify 404 after deletion
            get_again = await client.get(f"/api/sessions/{session_id}")
            assert get_again.status_code == 404

        finally:
            # Defensive cleanup if deletion step failed
            async with AsyncSessionLocal() as s:
                await s.execute(delete(DBSession).where(DBSession.id == session_id))
                await s.commit()


@pytest.mark.asyncio
async def test_chat_non_streaming(test_client, created_session_id):
    """Verifies POST /api/chat with stream=false saves messages and citations in PostgreSQL."""
    mock_agent = MockGrowthAssistantAgent()
    app.dependency_overrides[get_agent] = lambda: mock_agent

    try:
        async with test_client as client:
            resp = await client.post(
                "/api/chat",
                json={
                    "session_id": created_session_id,
                    "message": "When should a startup hire a growth team?",
                    "stream": False,
                },
            )
            assert resp.status_code == 200
            data = resp.json()

            assert data["session_id"] == created_session_id
            assert data["role"] == "assistant"
            assert "Elena Verna" in data["content"]
            assert data["is_abstention"] is False
            assert len(data["citations"]) == 1
            citation = data["citations"][0]
            assert citation["guest_name"] == "Elena Verna"
            assert citation["timestamp_seconds"] == 26
            assert "mockvideo&t=26s" in citation["youtube_url"]

            # Verify Database State
            get_resp = await client.get(f"/api/sessions/{created_session_id}")
            assert get_resp.status_code == 200
            sess_data = get_resp.json()
            assert len(sess_data["messages"]) == 2
            assert sess_data["messages"][0]["role"] == "user"
            assert sess_data["messages"][1]["role"] == "assistant"
            assert len(sess_data["messages"][1]["citations"]) == 1

    finally:
        app.dependency_overrides.pop(get_agent, None)


@pytest.mark.asyncio
async def test_chat_streaming_sse(test_client, created_session_id):
    """Verifies POST /api/chat with stream=true emits SSE token events and complete payload."""
    mock_agent = MockGrowthAssistantAgent()
    app.dependency_overrides[get_agent] = lambda: mock_agent

    try:
        async with test_client as client:
            resp = await client.post(
                "/api/chat",
                json={
                    "session_id": created_session_id,
                    "message": "What is Elena Verna's advice on PLG?",
                    "stream": True,
                },
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

            # Read SSE stream text
            stream_text = resp.text
            lines = [line.strip() for line in stream_text.splitlines() if line.strip()]

            # Validate event types present
            event_types = [l.replace("event: ", "") for l in lines if l.startswith("event: ")]
            assert "token" in event_types
            assert "complete" in event_types
            assert "done" in event_types

            # Verify complete payload
            complete_data_lines = [
                lines[i + 1]
                for i, l in enumerate(lines)
                if l == "event: complete" and i + 1 < len(lines)
            ]
            assert len(complete_data_lines) >= 1
            complete_json = json.loads(complete_data_lines[0].replace("data: ", ""))
            assert complete_json["is_abstention"] is False
            assert len(complete_json["citations"]) == 1
            assert complete_json["citations"][0]["guest_name"] == "Elena Verna"

    finally:
        app.dependency_overrides.pop(get_agent, None)


@pytest.mark.asyncio
async def test_chat_abstention_handling(test_client, created_session_id):
    """Verifies out-of-domain queries return explicit abstention with 0 citations."""
    abstention_text = (
        "I cannot answer this question because it is outside the scope of Lenny's Podcast transcripts. "
        "My answers are strictly grounded in interview transcripts from Lenny's Podcast."
    )
    mock_agent = MockGrowthAssistantAgent(answer=abstention_text, is_abstention=True, citations=[])
    app.dependency_overrides[get_agent] = lambda: mock_agent

    try:
        async with test_client as client:
            resp = await client.post(
                "/api/chat",
                json={
                    "session_id": created_session_id,
                    "message": "What is the best sourdough bread recipe?",
                    "stream": False,
                },
            )
            assert resp.status_code == 200
            data = resp.json()

            assert data["is_abstention"] is True
            assert data["citations"] == []
            assert "outside the scope of Lenny's Podcast" in data["content"]

    finally:
        app.dependency_overrides.pop(get_agent, None)


@pytest.mark.asyncio
async def test_essay_generation_and_artifact_retrieval(test_client, created_session_id):
    """Verifies POST /api/essay generates Ship 30 for 30 essay, stores artifact, and serves raw HTML."""
    mock_engine = MockShip30EssayEngine()
    app.dependency_overrides[get_essay_engine] = lambda: mock_engine

    try:
        async with test_client as client:
            # 1. Generate Essay
            resp = await client.post(
                "/api/essay",
                json={
                    "topic": "Product-Led Growth Playbook",
                    "session_id": created_session_id,
                    "guest_filter": "Elena Verna",
                },
            )
            assert resp.status_code == 200
            data = resp.json()

            assert data["artifact_id"].startswith("art-")
            assert data["word_count"] == 1245
            assert data["is_valid_word_count"] is True
            assert data["has_all_4a_sections"] is True
            assert "Elena Verna" in data["guest_attributions"]
            artifact_id = data["artifact_id"]

            # 2. Retrieve Stored Artifact JSON
            art_resp = await client.get(f"/api/artifacts/{artifact_id}")
            assert art_resp.status_code == 200
            art_data = art_resp.json()
            assert art_data["id"] == artifact_id
            assert art_data["artifact_type"] == "html"
            assert art_data["word_count"] == 1245

            # 3. Retrieve Raw HTML with CSP Security Headers
            raw_resp = await client.get(f"/api/artifacts/{artifact_id}/raw")
            assert raw_resp.status_code == 200
            assert "text/html" in raw_resp.headers["content-type"]
            assert "default-src 'none'" in raw_resp.headers.get("content-security-policy", "")
            assert raw_resp.headers.get("x-content-type-options") == "nosniff"
            assert "<!DOCTYPE html>" in raw_resp.text

    finally:
        app.dependency_overrides.pop(get_essay_engine, None)


@pytest.mark.asyncio
async def test_api_error_validation(test_client):
    """Verifies 404 and 400 validation boundaries across endpoints."""
    async with test_client as client:
        # Invalid Session ID for Chat
        chat_resp = await client.post(
            "/api/chat",
            json={"session_id": "non-existent-uuid", "message": "Hello"},
        )
        assert chat_resp.status_code == 404

        # Empty Topic for Essay
        essay_resp = await client.post(
            "/api/essay",
            json={"topic": "   "},
        )
        assert essay_resp.status_code == 422  # pydantic min_length -> structured VALIDATION_ERROR

        # Non-existent Artifact
        art_resp = await client.get("/api/artifacts/art-doesnotexist")
        assert art_resp.status_code == 404

        # Non-existent Raw Artifact
        raw_resp = await client.get("/api/artifacts/art-doesnotexist/raw")
        assert raw_resp.status_code == 404

        # Non-existent Session Delete
        del_resp = await client.delete("/api/sessions/non-existent-session-id")
        assert del_resp.status_code == 404
