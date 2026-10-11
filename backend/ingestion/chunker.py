"""
Semantic Dialogue Chunker for Lenny's Podcast Transcripts.
Groups speaker turns into coherent, context-rich chunks (~350-700 words) while preserving
source timestamps, speaker attribution, and deterministic IDs.
"""

import hashlib
import re
from typing import Dict, Any, List


def generate_deterministic_chunk_id(episode_slug: str, chunk_index: int) -> str:
    """Generates a stable, reproducible SHA-256 hash identifier for each chunk."""
    seed = f"{episode_slug.lower().strip()}:{chunk_index}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def chunk_dialogue_turns(
    episode_slug: str,
    metadata: Dict[str, Any],
    turns: List[Dict[str, Any]],
    target_words: int = 450,
    max_words: int = 700,
) -> List[Dict[str, Any]]:
    """
    Groups consecutive dialogue turns into semantically coherent chunks.
    Ensures that every chunk retains exact start timestamp, primary speaker attribution,
    and a deterministic identifier for repeatable upserts.
    """
    if not turns:
        return []

    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    current_turns: List[Dict[str, Any]] = []
    current_word_count = 0

    for turn in turns:
        turn_text = turn.get("text", "").strip()
        turn_words = len(turn_text.split())

        # If a single turn is massive (> max_words), flush current accumulator and split
        if turn_words > max_words:
            if current_turns:
                # Flush existing buffer
                chunk = _build_chunk(episode_slug, metadata, chunk_index, current_turns)
                chunks.append(chunk)
                chunk_index += 1
                current_turns = []
                current_word_count = 0

            # Split large turn by sentence / word blocks
            raw_sentences = re.split(r"(?<=[.!?])\s+", turn_text)
            sentences: List[str] = []
            for s in raw_sentences:
                s_words = s.split()
                if len(s_words) > target_words:
                    for k in range(0, len(s_words), target_words):
                        sentences.append(" ".join(s_words[k : k + target_words]))
                elif s.strip():
                    sentences.append(s.strip())

            sub_accum: List[str] = []
            sub_count = 0
            for s in sentences:
                s_words = len(s.split())
                if sub_count + s_words > max_words and sub_accum:
                    chunk = {
                        "id": generate_deterministic_chunk_id(episode_slug, chunk_index),
                        "episode_slug": episode_slug,
                        "episode_title": metadata.get("title", episode_slug),
                        "guest_name": metadata.get("guest", "Lenny's Guest"),
                        "youtube_url": metadata.get("youtube_url"),
                        "video_id": metadata.get("video_id"),
                        "publish_date": metadata.get("publish_date"),
                        "chunk_index": chunk_index,
                        "speaker": turn.get("speaker"),
                        "start_timestamp": turn.get("timestamp", "00:00:00"),
                        "start_seconds": turn.get("seconds", 0),
                        "end_timestamp": turn.get("timestamp", "00:00:00"),
                        "end_seconds": turn.get("seconds", 0),
                        "word_count": sub_count,
                        "content": f"{turn.get('speaker', '')} ({turn.get('timestamp', '00:00:00')}): " + " ".join(sub_accum),
                    }
                    chunks.append(chunk)
                    chunk_index += 1
                    sub_accum = []
                    sub_count = 0
                sub_accum.append(s)
                sub_count += s_words

            if sub_accum:
                chunk = {
                    "id": generate_deterministic_chunk_id(episode_slug, chunk_index),
                    "episode_slug": episode_slug,
                    "episode_title": metadata.get("title", episode_slug),
                    "guest_name": metadata.get("guest", "Lenny's Guest"),
                    "youtube_url": metadata.get("youtube_url"),
                    "video_id": metadata.get("video_id"),
                    "publish_date": metadata.get("publish_date"),
                    "chunk_index": chunk_index,
                    "speaker": turn.get("speaker"),
                    "start_timestamp": turn.get("timestamp", "00:00:00"),
                    "start_seconds": turn.get("seconds", 0),
                    "end_timestamp": turn.get("timestamp", "00:00:00"),
                    "end_seconds": turn.get("seconds", 0),
                    "word_count": sub_count,
                    "content": f"{turn.get('speaker', '')} ({turn.get('timestamp', '00:00:00')}): " + " ".join(sub_accum),
                }
                chunks.append(chunk)
                chunk_index += 1
            continue

        # Normal accumulation
        if current_word_count + turn_words > max_words and current_turns:
            chunk = _build_chunk(episode_slug, metadata, chunk_index, current_turns)
            chunks.append(chunk)
            chunk_index += 1
            current_turns = [turn]
            current_word_count = turn_words
        else:
            current_turns.append(turn)
            current_word_count += turn_words
            if current_word_count >= target_words:
                chunk = _build_chunk(episode_slug, metadata, chunk_index, current_turns)
                chunks.append(chunk)
                chunk_index += 1
                current_turns = []
                current_word_count = 0

    # Flush any remaining turns
    if current_turns:
        chunk = _build_chunk(episode_slug, metadata, chunk_index, current_turns)
        chunks.append(chunk)

    return chunks


def _build_chunk(
    episode_slug: str,
    metadata: Dict[str, Any],
    chunk_index: int,
    turns: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Helper to format accumulated turns into a structured chunk record."""
    first_turn = turns[0]
    last_turn = turns[-1]

    # Format content with clear speaker attribution and turn timestamp
    formatted_dialogue: List[str] = []
    for t in turns:
        speaker = t.get("speaker", "Speaker")
        ts = t.get("timestamp", "00:00:00")
        text = t.get("text", "")
        formatted_dialogue.append(f"{speaker} ({ts}): {text}")

    full_text = "\n\n".join(formatted_dialogue)
    word_count = len(full_text.split())

    return {
        "id": generate_deterministic_chunk_id(episode_slug, chunk_index),
        "episode_slug": episode_slug,
        "episode_title": metadata.get("title", episode_slug),
        "guest_name": metadata.get("guest", "Lenny's Guest"),
        "youtube_url": metadata.get("youtube_url"),
        "video_id": metadata.get("video_id"),
        "publish_date": metadata.get("publish_date"),
        "chunk_index": chunk_index,
        "speaker": first_turn.get("speaker"),
        "start_timestamp": first_turn.get("timestamp", "00:00:00"),
        "start_seconds": first_turn.get("seconds", 0),
        "end_timestamp": last_turn.get("timestamp", first_turn.get("timestamp")),
        "end_seconds": last_turn.get("seconds", first_turn.get("seconds")),
        "word_count": word_count,
        "content": full_text,
    }
