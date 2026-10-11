"""
SQLAlchemy models for Lenny Growth Assistant database schema.
Milestone 2: Transcript Chunks with PostgreSQL Full-Text Search indexing.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    Index,
    UniqueConstraint,
    Computed,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TranscriptChunk(Base):
    """
    Represents an indexed semantic chunk of an episode transcript.
    Maintains full source traceability back to guest, episode, timestamp, and YouTube deep link.
    """
    __tablename__ = "transcript_chunks"

    # Deterministic identifier: e.g. sha256(episode_slug + ":" + chunk_index)[:32]
    id = Column(String(64), primary_key=True)

    # Episode Source Metadata
    episode_slug = Column(String(150), nullable=False, index=True)
    episode_title = Column(String(300), nullable=False)
    guest_name = Column(String(150), nullable=False, index=True)
    youtube_url = Column(String(500), nullable=True)
    video_id = Column(String(50), nullable=True)
    publish_date = Column(String(50), nullable=True)

    # Chunking & Alignment Details
    chunk_index = Column(Integer, nullable=False)
    speaker = Column(String(150), nullable=True)
    start_timestamp = Column(String(20), nullable=True)  # e.g. "00:04:36"
    start_seconds = Column(Integer, nullable=False, default=0)
    end_timestamp = Column(String(20), nullable=True)
    end_seconds = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=False, default=0)

    # Untrusted transcript content
    content = Column(Text, nullable=False)

    # PostgreSQL Full-Text Search Vector: automatically generated and stored
    search_vector = Column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(guest_name, '') || ' ' || coalesce(episode_title, '') || ' ' || coalesce(content, ''))",
            persisted=True,
        ),
        nullable=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("episode_slug", "chunk_index", name="uq_transcript_chunk_episode_index"),
        Index("ix_transcript_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    def to_dict(self) -> dict:
        """Serializes chunk to dictionary representation."""
        youtube_deep_link = None
        if self.video_id:
            youtube_deep_link = f"https://www.youtube.com/watch?v={self.video_id}&t={self.start_seconds}s"
        elif self.youtube_url:
            sep = "&" if "?" in self.youtube_url else "?"
            youtube_deep_link = f"{self.youtube_url}{sep}t={self.start_seconds}s"

        return {
            "id": self.id,
            "episode_slug": self.episode_slug,
            "episode_title": self.episode_title,
            "guest_name": self.guest_name,
            "youtube_url": self.youtube_url,
            "youtube_deep_link": youtube_deep_link,
            "video_id": self.video_id,
            "publish_date": self.publish_date,
            "chunk_index": self.chunk_index,
            "speaker": self.speaker,
            "start_timestamp": self.start_timestamp,
            "start_seconds": self.start_seconds,
            "word_count": self.word_count,
            "content": self.content,
        }


class Session(Base):
    """Chat session for conversation history and model configuration."""
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False, default="New Growth Session")
    model_provider = Column(String(50), nullable=False, default="ollama")
    model_name = Column(String(100), nullable=False, default="llama3.2:3b")

    # User metadata (assignment 3.1): anonymous, no authentication in scope.
    client_id = Column(String(64), nullable=True, index=True)      # random UUID kept in the browser
    user_agent = Column(String(255), nullable=True)
    client_ip_hash = Column(String(16), nullable=True)             # truncated SHA-256, never the raw IP

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Message(Base):
    """Individual conversation message within a chat session."""
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    is_abstention = Column(Boolean, nullable=False, default=False)

    # Observability: which model produced this answer and how long it took.
    model_provider = Column(String(50), nullable=True)
    model_name = Column(String(100), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CitationRecord(Base):
    """Database record for verified citations attached to an assistant message."""
    __tablename__ = "citations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_title = Column(String(255), nullable=False)
    guest_name = Column(String(150), nullable=False)
    youtube_url = Column(String(500), nullable=False)
    timestamp_seconds = Column(Integer, nullable=True)
    quote_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Artifact(Base):
    """Generated artifact (e.g. Ship 30 for 30 essay) stored for isolated viewing."""
    __tablename__ = "artifacts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    artifact_type = Column(String(50), nullable=False)  # 'markdown', 'html'
    content = Column(Text, nullable=False)
    word_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "title": self.title,
            "artifact_type": self.artifact_type,
            "content": self.content,
            "word_count": self.word_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
