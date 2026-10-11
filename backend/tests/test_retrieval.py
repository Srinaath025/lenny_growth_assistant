"""
Tests for the dedicated transcript retrieval module.
Verifies:
1. YouTube deep link construction across URL variants.
2. Query sanitization and validation.
3. PostgreSQL full-text search returning real database chunks.
4. Source metadata preservation on RetrievedChunk objects.
5. Limit enforcement.
6. Safe handling of empty or non-matching queries.
"""

import pytest
from backend.retrieval.retriever import (
    RetrievedChunk,
    build_youtube_deep_link,
    sanitize_fts_query,
    retrieve_relevant_chunks,
)


def test_build_youtube_deep_link():
    """Verify deep link generation with exact timestamp seconds."""
    # Preferred: video_id
    link1 = build_youtube_deep_link(
        youtube_url="https://www.youtube.com/watch?v=IHwS2By9UKM",
        video_id="IHwS2By9UKM",
        start_seconds=125,
    )
    assert link1 == "https://www.youtube.com/watch?v=IHwS2By9UKM&t=125s"

    # Fallback: youtube_url with existing parameters
    link2 = build_youtube_deep_link(
        youtube_url="https://www.youtube.com/watch?v=abc&list=xyz",
        video_id=None,
        start_seconds=45,
    )
    assert link2 == "https://www.youtube.com/watch?v=abc&list=xyz&t=45s"

    # Fallback: simple URL without existing query params
    link3 = build_youtube_deep_link(
        youtube_url="https://youtu.be/abc",
        video_id=None,
        start_seconds=60,
    )
    assert link3 == "https://youtu.be/abc?t=60s"

    # Neither provided
    link4 = build_youtube_deep_link(youtube_url=None, video_id=None, start_seconds=10)
    assert link4 is None

    # Negative seconds clamped to 0
    link5 = build_youtube_deep_link(youtube_url=None, video_id="xyz123", start_seconds=-10)
    assert link5 == "https://www.youtube.com/watch?v=xyz123&t=0s"


def test_sanitize_fts_query():
    """Verify query sanitization removes unsafe characters while preserving search tokens."""
    assert sanitize_fts_query("  product led growth  ") == "product led growth"
    assert sanitize_fts_query("hello; DROP TABLE chunks;--") == "hello DROP TABLE chunks"
    assert sanitize_fts_query("\x00test\x1fquery") == "test query"
    assert sanitize_fts_query("") == ""
    assert sanitize_fts_query("   ") == ""


@pytest.mark.asyncio
async def test_retrieve_empty_and_short_queries():
    """Verify empty or 1-character queries return empty list immediately without hitting DB."""
    assert await retrieve_relevant_chunks("") == []
    assert await retrieve_relevant_chunks("   ") == []
    assert await retrieve_relevant_chunks("a") == []


@pytest.mark.asyncio
async def test_retrieve_relevant_chunks_real_db():
    """Verify retrieval against the real PostgreSQL database returns valid chunks."""
    # Query for Elena Verna (already ingested in Milestone 2)
    results = await retrieve_relevant_chunks("Elena Verna product led growth", limit=3)
    assert len(results) > 0
    assert len(results) <= 3

    top = results[0]
    assert isinstance(top, RetrievedChunk)
    assert "Elena Verna" in top.guest_name
    assert top.id is not None
    assert top.episode_title is not None
    assert top.start_timestamp is not None
    assert top.start_seconds >= 0
    assert top.youtube_deep_link is not None
    assert "youtube.com" in top.youtube_deep_link
    assert top.rank > 0
    assert len(top.content) > 0

    # Dictionary conversion
    d = top.to_dict()
    assert d["id"] == top.id
    assert d["youtube_deep_link"] == top.youtube_deep_link
    assert "rank" in d


@pytest.mark.asyncio
async def test_retrieve_nonexistent_query():
    """Verify query with no semantic matches returns empty list safely."""
    results = await retrieve_relevant_chunks("zyxwvutsrqponmlkjihgfedcba nonexistentkeywordxyz", limit=5)
    assert results == []
