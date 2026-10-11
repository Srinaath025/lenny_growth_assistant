"""
Integration tests for PostgreSQL schema, idempotent ingestion, and Full-Text Search.
Runs against the real local PostgreSQL container on port 5433.
Covers:
1. Database schema verification (columns, types, GIN full-text index).
2. Repeatable / idempotent ingestion without duplicating chunks.
3. Full-text search (tsvector + GIN) accuracy and ranking (ts_rank_cd).
4. YouTube deep link generation.
5. Empty corpus and malformed file handling.
6. Database error handling and transaction rollback.
"""

import tempfile
from pathlib import Path
import pytest
from sqlalchemy import text, select, func, delete

from backend.db.connection import AsyncSessionLocal, engine
from backend.db.models import Base, TranscriptChunk
from backend.ingestion.ingest import ingest_single_file, run_ingestion_pipeline

FIXTURE_EPISODE_CONTENT = """---
guest: Elena Verna
title: 10 growth tactics that never work | Elena Verna
youtube_url: https://www.youtube.com/watch?v=IHwS2By9UKM
video_id: IHwS2By9UKM
publish_date: 2025-01-19
description: Comprehensive discussion on product-led growth and B2B SaaS strategies.
---

Elena Verna (00:00:00):
Growth is a fairly new field. Many people focus on growth hacks that do not work.

Lenny Rachitsky (00:00:21):
We are going to start with growth tactics that never work. What is number one?

Elena Verna (00:00:26):
Number one is hiring a growth team before you have product market fit.
You cannot outsource finding product market fit to a growth team.
It is an existential trap for early stage SaaS startups.

(00:01:15):
Number two is doing a cosmetic marketing website redesign hoping it fixes core activation churn.
Retention is the foundation of growth. If your leaky bucket loses users, top-of-funnel acquisition is futile.
"""


@pytest.mark.asyncio
async def test_schema_and_gin_index_exist():
    """Verify that transcript_chunks table, columns, and GIN index exist in PostgreSQL."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Check column existence
        result = await session.execute(
            text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'transcript_chunks'
                ORDER BY ordinal_position;
            """)
        )
        columns = {row[0]: row[1] for row in result.fetchall()}

        expected_columns = [
            "id", "episode_slug", "episode_title", "guest_name",
            "youtube_url", "video_id", "publish_date", "chunk_index",
            "speaker", "start_timestamp", "start_seconds", "end_timestamp",
            "end_seconds", "word_count", "content", "search_vector"
        ]
        for col in expected_columns:
            assert col in columns, f"Column '{col}' missing from transcript_chunks"

        # Check GIN index
        index_res = await session.execute(
            text("""
                SELECT indexname, indexdef 
                FROM pg_indexes 
                WHERE tablename = 'transcript_chunks';
            """)
        )
        indices = {row[0]: row[1] for row in index_res.fetchall()}
        assert "ix_transcript_chunks_search_vector" in indices
        assert "using gin" in indices["ix_transcript_chunks_search_vector"].lower()


@pytest.mark.asyncio
async def test_repeatable_idempotent_ingestion():
    """Verify that ingesting an episode multiple times updates in-place without duplicating chunks."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        slug = "fixture-repeatable-test"
        ep_dir = Path(tmp_dir) / slug
        ep_dir.mkdir(parents=True, exist_ok=True)
        fixture_file = ep_dir / "transcript.md"
        fixture_file.write_text(FIXTURE_EPISODE_CONTENT, encoding="utf-8")

        async with AsyncSessionLocal() as session:
            try:
                # First ingestion
                res1 = await ingest_single_file(fixture_file, session)
                assert res1["status"] == "success"
                assert res1["chunks"] > 0
                chunks_count1 = res1["chunks"]

                # Verify chunk count in DB
                count_in_db1 = await session.scalar(
                    select(func.count(TranscriptChunk.id)).where(TranscriptChunk.episode_slug == slug)
                )
                assert count_in_db1 == chunks_count1

                # Second ingestion of the exact same file
                res2 = await ingest_single_file(fixture_file, session)
                assert res2["status"] == "success"
                assert res2["chunks"] == chunks_count1

                # Count in DB MUST remain strictly the same (idempotent upsert)
                count_in_db2 = await session.scalar(
                    select(func.count(TranscriptChunk.id)).where(TranscriptChunk.episode_slug == slug)
                )
                assert count_in_db2 == chunks_count1, "Chunks were duplicated upon re-ingestion!"
            finally:
                await session.execute(delete(TranscriptChunk).where(TranscriptChunk.episode_slug == slug))
                await session.commit()


@pytest.mark.asyncio
async def test_postgresql_fulltext_search_retrieval():
    """Verify that PostgreSQL full-text search matches and ranks relevant chunks."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        slug = "fixture-search-test"
        ep_dir = Path(tmp_dir) / slug
        ep_dir.mkdir(parents=True, exist_ok=True)
        fixture_file = ep_dir / "transcript.md"
        fixture_file.write_text(FIXTURE_EPISODE_CONTENT, encoding="utf-8")

        async with AsyncSessionLocal() as session:
            try:
                await ingest_single_file(fixture_file, session)

                # Query 1: Topic search for 'product market fit'
                search_sql = text("""
                    SELECT 
                        id, 
                        episode_title, 
                        guest_name, 
                        start_timestamp, 
                        start_seconds,
                        video_id,
                        content,
                        ts_rank_cd(search_vector, websearch_to_tsquery('english', :q)) AS rank
                    FROM transcript_chunks
                    WHERE episode_slug = :slug
                      AND search_vector @@ websearch_to_tsquery('english', :q)
                    ORDER BY rank DESC;
                """)

                res = await session.execute(search_sql, {"slug": slug, "q": "product market fit"})
                rows = res.fetchall()
                assert len(rows) >= 1
                top_match = rows[0]
                assert "product market fit" in top_match.content.lower()
                assert top_match.rank > 0

                # Query 2: Search for 'marketing website redesign'
                res2 = await session.execute(search_sql, {"slug": slug, "q": "marketing website redesign"})
                rows2 = res2.fetchall()
                assert len(rows2) >= 1
                assert "redesign" in rows2[0].content.lower()

                # Query 3: Search for guest name
                res3 = await session.execute(search_sql, {"slug": slug, "q": "Elena Verna"})
                rows3 = res3.fetchall()
                assert len(rows3) >= 1

                # Verify deep link formatting
                chunk_orm = await session.get(TranscriptChunk, top_match.id)
                data = chunk_orm.to_dict()
                assert data["youtube_deep_link"] is not None
                assert f"https://www.youtube.com/watch?v={top_match.video_id}&t=" in data["youtube_deep_link"]
            finally:
                await session.execute(delete(TranscriptChunk).where(TranscriptChunk.episode_slug == slug))
                await session.commit()


@pytest.mark.asyncio
async def test_empty_and_invalid_file_handling():
    """Verify graceful handling when files are empty or contain no turns."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Case 1: Empty 0-byte file
        slug_empty = "fixture-empty-file"
        dir_empty = Path(tmp_dir) / slug_empty
        dir_empty.mkdir(parents=True, exist_ok=True)
        empty_file = dir_empty / "transcript.md"
        empty_file.write_text("", encoding="utf-8")

        # Case 2: Headers only, no dialogue turns
        slug_no_turns = "fixture-no-turns"
        dir_no_turns = Path(tmp_dir) / slug_no_turns
        dir_no_turns.mkdir(parents=True, exist_ok=True)
        no_turns_file = dir_no_turns / "transcript.md"
        no_turns_file.write_text("# Title\n\n## Subheader\n\n", encoding="utf-8")

        async with AsyncSessionLocal() as session:
            res_empty = await ingest_single_file(empty_file, session)
            assert res_empty["status"] == "skipped"
            assert res_empty["reason"] == "empty_file"

            res_no_turns = await ingest_single_file(no_turns_file, session)
            assert res_no_turns["status"] == "skipped"
            assert res_no_turns["reason"] == "no_turns"


@pytest.mark.asyncio
async def test_database_error_handling_and_rollback():
    """Verify that errors trigger clean transaction rollback without breaking the session."""
    async with AsyncSessionLocal() as session:
        # Attempt to insert an invalid chunk violating non-nullable constraints
        broken_chunk = TranscriptChunk(
            id="bad-chunk-1",
            episode_slug="bad-slug",
            episode_title=None,  # NOT NULL constraint violation
            guest_name="Guest",
            chunk_index=0,
            content="Some text",
        )
        session.add(broken_chunk)
        with pytest.raises(Exception):
            await session.commit()

        # Session should be able to roll back cleanly
        await session.rollback()

        # Verify session is still alive and operational
        live_check = await session.scalar(select(1))
        assert live_check == 1
