"""
Live integration test for GrowthAssistantAgent with real PostgreSQL and local Ollama (llama3.2:3b).
Skips gracefully if Ollama is offline.
"""

import urllib.request
import pytest
from backend.agent.orchestrator import GrowthAssistantAgent
from backend.agent.prompt import ABSTENTION_MESSAGE


def is_ollama_available() -> bool:
    """Checks whether local Ollama server is responding at localhost:11434."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False


@pytest.mark.asyncio
async def test_live_agent_grounded_answer_and_abstention():
    """Verify live end-to-end grounded retrieval, citation verification, and abstention."""
    if not is_ollama_available():
        pytest.skip("Ollama is offline or unreachable at http://localhost:11434")

    agent = GrowthAssistantAgent(retriever_limit=3)

    # 1. Grounded Question: Elena Verna on hiring a growth team before PMF
    grounded_query = "What does Elena Verna say about hiring a growth team before product-market fit?"
    ans1 = await agent.ask(grounded_query)

    assert not ans1.is_abstention
    assert "growth team" in ans1.answer.lower()
    assert len(ans1.citations) >= 1

    top_citation = ans1.citations[0]
    assert "Elena Verna" in top_citation.guest_name
    assert "youtube.com" in top_citation.source_url
    assert top_citation.timestamp is not None
    assert top_citation.start_seconds >= 0

    # 2. Unsupported Question: Completely unrelated to podcast
    unsupported_query = "What is the recommended carburetor tuning for a 1968 Chevrolet Camaro?"
    ans2 = await agent.ask(unsupported_query)

    assert ans2.is_abstention
    assert len(ans2.citations) == 0
    assert ABSTENTION_MESSAGE in ans2.answer
