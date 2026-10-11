"""
Repeatable, Idempotent Ingestion Pipeline for Lenny's Podcast Transcripts.
Parses Markdown transcripts, chunks them, and upserts them into PostgreSQL with
PostgreSQL Full-Text Search indexing.
Safe to execute multiple times without duplicating chunks.
"""

import argparse
import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, func

from backend.db.connection import engine, AsyncSessionLocal
from backend.db.models import Base, TranscriptChunk
from backend.ingestion.parser import parse_transcript_markdown
from backend.ingestion.chunker import chunk_dialogue_turns
from backend.ingestion.downloader import sync_transcripts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ingestion.pipeline")


async def ingest_single_file(file_path: Path, session) -> Dict[str, Any]:
    """
    Parses and upserts a single transcript file into PostgreSQL.
    Returns stats dict for the file.
    """
    episode_slug = file_path.parent.name
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        if not content.strip():
            logger.warning(f"File {file_path} is empty, skipping.")
            return {"status": "skipped", "reason": "empty_file", "chunks": 0}

        metadata, turns = parse_transcript_markdown(content, fallback_slug=episode_slug)
        if not turns:
            logger.warning(f"No dialogue turns extracted from {episode_slug}, skipping.")
            return {"status": "skipped", "reason": "no_turns", "chunks": 0}

        chunks = chunk_dialogue_turns(episode_slug, metadata, turns)
        if not chunks:
            return {"status": "skipped", "reason": "no_chunks", "chunks": 0}

        # Idempotent batch upsert via PostgreSQL ON CONFLICT (id) DO UPDATE
        stmt = insert(TranscriptChunk).values(chunks)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "episode_title": stmt.excluded.episode_title,
                "guest_name": stmt.excluded.guest_name,
                "youtube_url": stmt.excluded.youtube_url,
                "video_id": stmt.excluded.video_id,
                "publish_date": stmt.excluded.publish_date,
                "speaker": stmt.excluded.speaker,
                "start_timestamp": stmt.excluded.start_timestamp,
                "start_seconds": stmt.excluded.start_seconds,
                "end_timestamp": stmt.excluded.end_timestamp,
                "end_seconds": stmt.excluded.end_seconds,
                "word_count": stmt.excluded.word_count,
                "content": stmt.excluded.content,
                "updated_at": datetime.utcnow(),
            },
        )

        await session.execute(upsert_stmt)
        await session.commit()

        return {
            "status": "success",
            "episode_slug": episode_slug,
            "guest": metadata.get("guest"),
            "chunks": len(chunks),
        }

    except Exception as exc:
        logger.error(f"Error ingesting {file_path}: {exc}")
        await session.rollback()
        return {"status": "error", "reason": str(exc), "chunks": 0}


async def run_ingestion_pipeline(
    data_dir: Path,
    limit: Optional[int] = None,
    sync_online: bool = True,
    episode_slug: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Orchestrates the complete ingestion workflow:
    1. Ensures database tables exist.
    2. Downloads transcripts if missing or requested.
    3. Iterates over transcript files and upserts chunks into PostgreSQL.
    4. Computes and returns comprehensive statistics.
    """
    start_time = time.time()
    logger.info(f"Starting ingestion pipeline from {data_dir} (limit={limit}, sync_online={sync_online}, episode_slug={episode_slug})")

    # Step 1: Ensure database tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Step 2: Download / Sync transcripts if requested
    if episode_slug:
        target_file = data_dir / episode_slug / "transcript.md"
        if not target_file.exists() and sync_online:
            from backend.ingestion.downloader import download_episode
            download_episode(episode_slug, data_dir)
        transcript_files = [target_file] if target_file.exists() else []
    else:
        transcript_files = list(data_dir.glob("*/transcript.md"))
        if sync_online and (len(transcript_files) == 0 or (limit and len(transcript_files) < limit)):
            logger.info("Syncing transcripts from official repository mirror...")
            transcript_files = sync_transcripts(data_dir, limit=limit)

        transcript_files = list(data_dir.glob("*/transcript.md"))
        if limit is not None:
            transcript_files = transcript_files[:limit]

    logger.info(f"Found {len(transcript_files)} transcript files to process.")

    stats = {
        "files_inspected": len(transcript_files),
        "episodes_ingested": 0,
        "chunks_upserted": 0,
        "files_skipped": 0,
        "errors": 0,
        "duration_seconds": 0.0,
    }

    if not transcript_files:
        logger.warning("No transcript files found to ingest.")
        stats["duration_seconds"] = round(time.time() - start_time, 2)
        return stats

    # Step 3: Ingest files
    async with AsyncSessionLocal() as session:
        for f in transcript_files:
            result = await ingest_single_file(f, session)
            if result["status"] == "success":
                stats["episodes_ingested"] += 1
                stats["chunks_upserted"] += result["chunks"]
            elif result["status"] == "skipped":
                stats["files_skipped"] += 1
            else:
                stats["errors"] += 1

        # Check total chunk count in DB
        total_chunks = await session.scalar(select(func.count(TranscriptChunk.id)))
        stats["total_chunks_in_db"] = total_chunks

    stats["duration_seconds"] = round(time.time() - start_time, 2)
    logger.info(
        f"Ingestion completed in {stats['duration_seconds']}s: "
        f"{stats['episodes_ingested']} episodes ingested, "
        f"{stats['chunks_upserted']} chunks upserted. "
        f"Total chunks in database: {stats.get('total_chunks_in_db', 0)}"
    )

    return stats


def main():
    parser = argparse.ArgumentParser(description="Lenny's Podcast Transcript Ingestion Pipeline")
    parser.add_argument("--data-dir", type=str, default="data/transcripts", help="Path to transcript data directory")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of episodes to ingest")
    parser.add_argument("--episode-slug", type=str, default=None, help="Ingest a single specific episode slug")
    parser.add_argument("--no-sync", action="store_true", help="Do not sync from online CDN mirror")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent
    data_path = project_root / args.data_dir

    stats = asyncio.run(run_ingestion_pipeline(
        data_dir=data_path,
        limit=args.limit,
        sync_online=not args.no_sync,
        episode_slug=args.episode_slug,
    ))
    print("\n--- Ingestion Summary ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
