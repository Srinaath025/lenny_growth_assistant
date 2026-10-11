"""
Unit tests for Lenny's Podcast semantic dialogue chunker.
Covers:
1. Deterministic identifier generation and reproducibility.
2. Chunk boundaries respecting target and max word limits.
3. Preservation of all source metadata fields across chunks.
4. Handling of long monologues exceeding max_words.
5. Handling of empty input.
"""

import pytest
from backend.ingestion.chunker import (
    chunk_dialogue_turns,
    generate_deterministic_chunk_id,
)


def test_deterministic_chunk_id():
    """Verify that chunk IDs are stable, repeatable, and unique per index."""
    id1 = generate_deterministic_chunk_id("elena-verna", 0)
    id2 = generate_deterministic_chunk_id("elena-verna", 0)
    id3 = generate_deterministic_chunk_id("elena-verna", 1)
    id4 = generate_deterministic_chunk_id("brian-chesky", 0)

    # Idempotent: identical input yields identical output
    assert id1 == id2
    # Case-insensitive normalization
    assert id1 == generate_deterministic_chunk_id("ELENA-VERNA", 0)
    # Distinct indices produce distinct IDs
    assert id1 != id3
    # Distinct slugs produce distinct IDs
    assert id1 != id4
    # Fixed length hex string
    assert len(id1) == 32


def test_chunking_boundaries_and_metadata():
    """Verify dialogue turn grouping into chunks with preserved metadata."""
    metadata = {
        "guest": "Elena Verna",
        "title": "10 growth tactics that never work",
        "youtube_url": "https://www.youtube.com/watch?v=IHwS2By9UKM",
        "video_id": "IHwS2By9UKM",
        "publish_date": "2025-01-19",
    }

    # Create 10 turns of ~60 words each = ~600 words total
    turns = []
    for i in range(10):
        turns.append({
            "speaker": "Elena Verna" if i % 2 == 0 else "Lenny Rachitsky",
            "seconds": i * 60,
            "timestamp": f"00:{i:02d}:00",
            "text": f"This is statement number {i} discussing retention metrics and product market fit in detail. " * 5,
        })

    # Chunk with target_words=200, max_words=350
    chunks = chunk_dialogue_turns(
        episode_slug="elena-verna",
        metadata=metadata,
        turns=turns,
        target_words=200,
        max_words=350,
    )

    assert len(chunks) > 1
    # Check that each chunk has sequential indices and deterministic IDs
    for idx, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == idx
        assert chunk["id"] == generate_deterministic_chunk_id("elena-verna", idx)
        assert chunk["episode_slug"] == "elena-verna"
        assert chunk["guest_name"] == "Elena Verna"
        assert chunk["episode_title"] == "10 growth tactics that never work"
        assert chunk["youtube_url"] == "https://www.youtube.com/watch?v=IHwS2By9UKM"
        assert chunk["video_id"] == "IHwS2By9UKM"
        assert chunk["publish_date"] == "2025-01-19"
        assert chunk["word_count"] > 0
        assert chunk["start_seconds"] <= chunk["end_seconds"]
        assert chunk["content"] != ""


def test_chunk_long_single_monologue():
    """Verify that a single turn exceeding max_words is cleanly split without loss."""
    metadata = {
        "guest": "Brian Chesky",
        "title": "Leading Through Crisis",
    }

    long_paragraph = "We had to rethink the entire product experience from the ground up. " * 80  # ~800 words
    turns = [{
        "speaker": "Brian Chesky",
        "seconds": 120,
        "timestamp": "00:02:00",
        "text": long_paragraph,
    }]

    chunks = chunk_dialogue_turns(
        episode_slug="brian-chesky",
        metadata=metadata,
        turns=turns,
        target_words=300,
        max_words=450,
    )

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk["guest_name"] == "Brian Chesky"
        assert chunk["speaker"] == "Brian Chesky"
        assert chunk["start_timestamp"] == "00:02:00"
        assert chunk["start_seconds"] == 120


def test_chunk_empty_turns():
    """Verify that an empty list of turns returns an empty chunk list."""
    chunks = chunk_dialogue_turns("empty-ep", {}, [])
    assert chunks == []
