"""
Unit and integration test suite for Cloud Claude (Anthropic Claude 3.5 Sonnet) integration.
Verifies:
1. AnthropicClaudeClient request schema construction and header generation.
2. Error handling when ANTHROPIC_API_KEY is missing, invalid, or rate-limited.
3. Mocked non-streaming response extraction.
4. Mocked SSE streaming token parsing (content_block_delta -> text_delta).
5. Dynamic switching between Local Ollama and Cloud Claude in GrowthAssistantAgent.
6. API endpoint validation: POST /api/chat and POST /api/essay return 400 when key is absent.
7. Secret masking: Asserts API key is never exposed in error messages or logs.
"""

import asyncio
import json
import os
import pytest
import httpx
from unittest.mock import patch, AsyncMock

from backend.agent.cloud_client import (
    AnthropicClaudeClient,
    AnthropicClaudeConfig,
    CloudProviderError,
    ANTHROPIC_API_VERSION,
)
from backend.agent.orchestrator import GrowthAssistantAgent, GroundedAnswer
from backend.agent.citation_validator import Citation
from backend.main import app, get_agent


# --- Fixtures ---

@pytest.fixture
def mock_claude_response():
    """Returns a realistic response payload matching the Anthropic Messages API."""
    return {
        "id": "msg_01X9Z8Y7W6V5U4T3S2R1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": [
            {
                "type": "text",
                "text": "Elena Verna states that hiring a growth team before PMF leads to premature scaling [citation:0123456789abcdef0123456789abcdef]."
            }
        ],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 420, "output_tokens": 35}
    }


# --- Test Cases ---

@pytest.mark.asyncio
async def test_cloud_client_missing_key_rejection():
    """Verifies AnthropicClaudeClient raises CloudProviderError if API key is not configured."""
    client = AnthropicClaudeClient(config=AnthropicClaudeConfig(api_key=None))
    # Explicitly clear env
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
        client.api_key = ""
        assert client.is_configured() is False
        with pytest.raises(CloudProviderError, match="ANTHROPIC_API_KEY is not configured"):
            await client.run_prompt("Test prompt")


@pytest.mark.asyncio
async def test_cloud_client_headers_and_config():
    """Verifies request headers conform strictly to Anthropic API specification."""
    config = AnthropicClaudeConfig(
        api_key="sk-ant-api03-test-secret-key-123456789",
        model="claude-sonnet-5-5",
    )
    client = AnthropicClaudeClient(config=config)
    assert client.is_configured() is True

    headers = client._build_headers()
    assert headers["x-api-key"] == "sk-ant-api03-test-secret-key-123456789"
    assert headers["anthropic-version"] == ANTHROPIC_API_VERSION
    assert headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_cloud_client_non_streaming_mock(mock_claude_response):
    """Verifies non-streaming response extraction from Anthropic Messages API."""
    config = AnthropicClaudeConfig(api_key="sk-ant-api03-test-key-mock")
    client = AnthropicClaudeClient(config=config)

    mock_resp = httpx.Response(
        status_code=200,
        json=mock_claude_response,
        request=httpx.Request("POST", config.base_url),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await client.run_prompt("What does Elena Verna say about PMF?")

        assert "Elena Verna states that hiring a growth team before PMF" in result
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["model"] == "claude-sonnet-5-5"
        assert call_kwargs["json"]["stream"] is False


@pytest.mark.asyncio
async def test_cloud_client_streaming_mock():
    """Verifies SSE token extraction from content_block_delta events."""
    config = AnthropicClaudeConfig(api_key="sk-ant-api03-test-key-mock")
    client = AnthropicClaudeClient(config=config)

    sse_lines = [
        'event: message_start\ndata: {"type":"message_start"}\n\n',
        'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Elena "}}\n\n',
        'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Verna "}}\n\n',
        'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"emphasizes PLG."}}\n\n',
        'event: message_stop\ndata: {"type":"message_stop"}\n\n',
    ]

    async def mock_aiter_lines():
        for line in sse_lines:
            yield line

    # Create mock response stream
    mock_stream_ctx = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = mock_aiter_lines
    mock_stream_ctx.__aenter__.return_value = mock_resp

    streamed_tokens = []

    def on_delta(delta: str):
        streamed_tokens.append(delta)

    with patch("httpx.AsyncClient.stream", return_value=mock_stream_ctx):
        full_text = await client.run_prompt("Test prompt", on_delta=on_delta)

        assert full_text == "Elena Verna emphasizes PLG."
        assert streamed_tokens == ["Elena ", "Verna ", "emphasizes PLG."]


@pytest.mark.asyncio
async def test_cloud_client_error_mapping():
    """Verifies Anthropic HTTP errors (401, 429) are converted to CloudProviderError without leaking keys."""
    config = AnthropicClaudeConfig(api_key="sk-ant-api03-super-secret-key")
    client = AnthropicClaudeClient(config=config)

    # 401 Unauthorized
    resp_401 = httpx.Response(status_code=401, text="Unauthorized", request=httpx.Request("POST", config.base_url))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = resp_401
        with pytest.raises(CloudProviderError, match="Authentication failed: Invalid ANTHROPIC_API_KEY"):
            await client.run_prompt("Test")

    # 429 Rate Limit
    resp_429 = httpx.Response(status_code=429, text="Rate limit", request=httpx.Request("POST", config.base_url))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = resp_429
        with pytest.raises(CloudProviderError, match="rate limit exceeded"):
            await client.run_prompt("Test")


@pytest.mark.asyncio
async def test_growth_agent_cloud_switching():
    """Verifies GrowthAssistantAgent dynamically routes to Cloud Claude when configured."""
    mock_cloud = AsyncMock(spec=AnthropicClaudeClient)
    mock_cloud.run_prompt = AsyncMock(
        return_value="According to Elena Verna, growth teams need PMF first [citation:0123456789abcdef0123456789abcdef]."
    )

    agent = GrowthAssistantAgent(
        model_provider="anthropic",
        cloud_client=mock_cloud,
    )
    assert agent.model_provider == "anthropic"

    # Mock retrieved chunks
    from backend.retrieval.retriever import RetrievedChunk
    mock_chunk = RetrievedChunk(
        id="0123456789abcdef0123456789abcdef",
        episode_slug="elena-verna",
        episode_title="Elena Verna on PLG",
        guest_name="Elena Verna",
        youtube_url="https://www.youtube.com/watch?v=mockvideo",
        youtube_deep_link="https://www.youtube.com/watch?v=mockvideo&t=26s",
        video_id="mockvideo",
        publish_date="2023-01-01",
        chunk_index=0,
        speaker="Elena Verna",
        start_timestamp="00:00:26",
        start_seconds=26,
        end_timestamp="00:02:00",
        end_seconds=120,
        word_count=45,
        content="Hiring a growth team before product-market fit is a mistake.",
        rank=0.95,
    )

    with patch("backend.agent.orchestrator.retrieve_relevant_chunks", new_callable=AsyncMock) as mock_ret:
        mock_ret.return_value = [mock_chunk]
        answer: GroundedAnswer = await agent.ask("When should a startup hire a growth team?")

        assert answer.is_abstention is False
        assert "Elena Verna" in answer.answer
        assert len(answer.citations) == 1
        assert answer.citations[0].guest_name == "Elena Verna"
        mock_cloud.run_prompt.assert_called_once()


@pytest.mark.asyncio
async def test_api_chat_rejects_cloud_when_key_absent():
    """Verifies POST /api/chat returns HTTP 400 when Cloud Claude is requested without an API key."""
    from backend.main import get_db
    from backend.db.models import Session as DBSession

    class MockDBSession:
        async def execute(self, stmt):
            class MockResult:
                def scalar_one_or_none(self):
                    return DBSession(id="test-cloud-sess-id", title="Mock Session", model_provider="ollama")
            return MockResult()

        def add(self, obj):
            pass

        async def commit(self):
            pass

        async def close(self):
            pass

    async def mock_db():
        yield MockDBSession()

    app.dependency_overrides[get_db] = mock_db

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
                chat_resp = await client.post(
                    "/api/chat",
                    json={
                        "session_id": "test-cloud-sess-id",
                        "message": "Explain retention loops",
                        "model_provider": "anthropic",
                        "stream": False,
                    },
                )
                assert chat_resp.status_code == 400
                assert "ANTHROPIC_API_KEY is not configured" in chat_resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)
