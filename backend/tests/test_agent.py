"""
Unit tests for agent prompt construction, citation validation, and orchestration.
Uses mocked Pi client for deterministic, fast verification of grounding and abstention.
"""

from unittest.mock import AsyncMock, patch
import pytest

from backend.retrieval.retriever import RetrievedChunk
from backend.agent.prompt import build_grounded_prompt, ABSTENTION_MESSAGE
from backend.agent.citation_validator import (
    Citation,
    CitationValidator,
    ValidationResult,
)
from backend.agent.pi_client import PiAgentClient, PiRPCError, PiAgentConfig
from backend.agent.orchestrator import GrowthAssistantAgent, GroundedAnswer


def make_sample_chunk(
    chunk_id: str,
    guest: str = "Elena Verna",
    title: str = "10 growth tactics that never work",
    content: str = "Never hire a growth team before product market fit.",
    start_seconds: int = 26,
    start_timestamp: str = "00:00:26",
) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        episode_slug="elena-verna",
        episode_title=title,
        guest_name=guest,
        youtube_url="https://www.youtube.com/watch?v=IHwS2By9UKM",
        youtube_deep_link=f"https://www.youtube.com/watch?v=IHwS2By9UKM&t={start_seconds}s",
        video_id="IHwS2By9UKM",
        publish_date="2025-01-19",
        chunk_index=0,
        speaker=guest,
        start_timestamp=start_timestamp,
        start_seconds=start_seconds,
        end_timestamp=start_timestamp,
        end_seconds=start_seconds + 30,
        word_count=len(content.split()),
        content=content,
        rank=0.015,
    )


def test_prompt_construction_untrusted_delimiters():
    """Verify prompt isolates retrieved evidence in untrusted blocks and passes only selected chunks."""
    chunk1 = make_sample_chunk("chunk_aaa_111122223333444455556666", content="Text for chunk A")
    chunk2 = make_sample_chunk("chunk_bbb_111122223333444455556666", content="Text for chunk B")

    prompt = build_grounded_prompt(
        query="What is the growth advice?",
        retrieved_chunks=[chunk1, chunk2],
    )

    # Delimiters present
    assert "<<<UNTRUSTED_EVIDENCE_START>>>" in prompt
    assert "<<<UNTRUSTED_EVIDENCE_END>>>" in prompt
    assert "Text for chunk A" in prompt
    assert "Text for chunk B" in prompt
    # Chunks are individually tagged with IDs
    assert 'id="chunk_aaa_111122223333444455556666"' in prompt
    assert 'id="chunk_bbb_111122223333444455556666"' in prompt
    # Abstention instructions present
    assert ABSTENTION_MESSAGE in prompt


def test_citation_validator_accepts_valid_citations():
    """Verify valid citations referencing retrieved chunk IDs are verified and enriched with source metadata."""
    chunk_id = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    chunk = make_sample_chunk(chunk_id, guest="Elena Verna", start_seconds=120)

    model_output = f"Hiring a growth team too early is a major mistake [citation:{chunk_id}]."
    result = CitationValidator.validate(model_output, [chunk])

    assert not result.is_abstention
    assert len(result.valid_citations) == 1
    assert len(result.invalid_chunk_ids) == 0

    cit = result.valid_citations[0]
    assert cit.chunk_id == chunk_id
    assert cit.guest_name == "Elena Verna"
    assert cit.start_seconds == 120
    assert cit.source_url == f"https://www.youtube.com/watch?v=IHwS2By9UKM&t=120s"


def test_citation_validator_resolves_turn_level_timestamp():
    """Verify that citations resolve to the specific dialogue turn timestamp rather than chunk start."""
    chunk_id = "chunk_elena_verna_0011223344556677"
    content_with_turns = (
        "Elena Verna (00:00:00): Growth is a fairly new field. Many people focus on growth hacks.\n\n"
        "Lenny Rachitsky (00:00:21): What is number one on the list of mistakes?\n\n"
        "Elena Verna (00:00:26): Number one is hiring a growth team before you have product market fit. "
        "You cannot outsource finding product market fit to a growth team.\n\n"
        "Elena Verna (00:01:15): Number two is doing a cosmetic marketing redesign."
    )
    chunk = make_sample_chunk(
        chunk_id,
        guest="Elena Verna",
        content=content_with_turns,
        start_seconds=0,
        start_timestamp="00:00:00",
    )

    model_answer = (
        f"Elena Verna emphasizes that hiring a growth team before having product market fit "
        f"is an existential mistake [citation:{chunk_id}]."
    )

    result = CitationValidator.validate(model_answer, [chunk])

    assert not result.is_abstention
    assert len(result.valid_citations) == 1
    cit = result.valid_citations[0]
    # Timestamp must resolve to turn 2 (00:00:26 / 26s), NOT chunk start (0s)
    assert cit.timestamp == "00:00:26"
    assert cit.start_seconds == 26
    assert cit.source_url == "https://www.youtube.com/watch?v=IHwS2By9UKM&t=26s"
    assert "hiring a growth team" in cit.snippet.lower()


def test_citation_validator_sanitizes_unquoted_paraphrases():
    """Verify that quotes around synthesized/paraphrased text are removed, while verbatim quotes remain."""
    chunk_id = "chunk_verbatim_test_1234567890ab"
    content = "Elena Verna (00:00:26): Number one is hiring a growth team before you have product market fit. It is an existential trap."
    chunk = make_sample_chunk(chunk_id, content=content)

    # Paraphrased quote (not verbatim) -> quotes stripped
    para_answer = f'Elena Verna states that "hiring a growth team too early is an existential trap for early stage startups" [citation:{chunk_id}].'
    res_para = CitationValidator.validate(para_answer, [chunk])
    assert '"' not in res_para.cleaned_answer
    assert "existential trap" in res_para.cleaned_answer

    # Verbatim quote -> quotes preserved
    verb_answer = f'Elena Verna states that "hiring a growth team before you have product market fit" is wrong [citation:{chunk_id}].'
    res_verb = CitationValidator.validate(verb_answer, [chunk])
    assert '"hiring a growth team before you have product market fit"' in res_verb.cleaned_answer


def test_citation_validator_rejects_unretrieved_chunk_ids():
    """Verify the agent cannot cite chunk IDs that were not part of the retrieved evidence."""
    retrieved_id = "11112222333344445555666677778888"
    fake_id = "99998888777766665555444433332222"

    chunk = make_sample_chunk(retrieved_id)

    # Model hallucinates fake_id
    model_output = f"According to advice [citation:{fake_id}], startups should iterate quickly."
    result = CitationValidator.validate(model_output, [chunk])

    # fake_id flagged as invalid
    assert fake_id in result.invalid_chunk_ids
    # fake_id is NOT in valid citations
    for cit in result.valid_citations:
        assert cit.chunk_id != fake_id


def test_citation_validator_detects_abstention():
    """Verify that abstention messages are classified as abstention."""
    chunk = make_sample_chunk("11112222333344445555666677778888")

    # Case 1: Exact message
    r1 = CitationValidator.validate(ABSTENTION_MESSAGE, [chunk])
    assert r1.is_abstention
    assert len(r1.valid_citations) == 0

    # Case 2: Semantic variant
    r2 = CitationValidator.validate(
        "I do not have sufficient evidence in Lenny's Podcast transcripts to answer this question about car engines.",
        [chunk],
    )
    assert r2.is_abstention


def test_citation_validator_empty_chunks_forces_abstention():
    """Verify that if no chunks are provided, result is strictly an abstention."""
    r = CitationValidator.validate("Here is an answer anyway.", [])
    assert r.is_abstention
    assert r.cleaned_answer == ABSTENTION_MESSAGE
    assert len(r.valid_citations) == 0


@pytest.mark.asyncio
async def test_orchestrator_abstains_immediately_on_empty_retrieval():
    """Verify that if search returns 0 chunks, agent abstains immediately without invoking Pi RPC."""
    mock_pi = AsyncMock(spec=PiAgentClient)

    agent = GrowthAssistantAgent(pi_client=mock_pi)

    with patch("backend.agent.orchestrator.retrieve_relevant_chunks", return_value=[]):
        answer = await agent.ask("completely nonexistent topic xyz123")

        assert answer.is_abstention
        assert answer.answer == ABSTENTION_MESSAGE
        assert answer.retrieved_chunks == []
        assert answer.citations == []
        # Pi client must NOT be called at all
        mock_pi.run_prompt.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_successful_grounded_answer():
    """Verify end-to-end flow with valid chunks and mocked Pi response."""
    chunk_id = "abcdef1234567890abcdef1234567890"
    chunk = make_sample_chunk(chunk_id, guest="Elena Verna", content="Never outsource PMF to a growth team.")

    mock_pi = AsyncMock(spec=PiAgentClient)
    mock_pi.run_prompt.return_value = (
        f"You should never hire a growth team before product market fit [citation:{chunk_id}]."
    )

    agent = GrowthAssistantAgent(pi_client=mock_pi)

    with patch("backend.agent.orchestrator.retrieve_relevant_chunks", return_value=[chunk]):
        answer = await agent.ask("Should I hire a growth team early?")

        assert not answer.is_abstention
        assert "growth team" in answer.answer
        assert len(answer.citations) == 1
        assert answer.citations[0].chunk_id == chunk_id
        assert answer.citations[0].guest_name == "Elena Verna"
        assert "youtube.com" in answer.citations[0].source_url
        mock_pi.run_prompt.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_handles_rpc_failure():
    """Verify that when Pi RPC raises an error (e.g. Ollama down), agent handles it gracefully."""
    chunk = make_sample_chunk("11112222333344445555666677778888")

    mock_pi = AsyncMock(spec=PiAgentClient)
    mock_pi.run_prompt.side_effect = PiRPCError("Ollama connection refused at localhost:11434")

    agent = GrowthAssistantAgent(pi_client=mock_pi)

    with patch("backend.agent.orchestrator.retrieve_relevant_chunks", return_value=[chunk]):
        answer = await agent.ask("Any query")

        # An infrastructure failure is an ERROR, never a (misleading) "topic not discussed" abstention.
        assert answer.error
        assert not answer.is_abstention
        assert "Error communicating with local agent" in answer.answer
        assert len(answer.citations) == 0
