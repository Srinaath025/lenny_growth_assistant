"""
Database initialisation and lightweight, idempotent migrations.

`create_schema()` is called from the FastAPI lifespan, from the ingestion CLI and from the
test-suite bootstrap. It (1) creates any missing tables/indexes and (2) adds columns that
were introduced after the first release, so an existing database volume keeps working
after an upgrade (`CREATE TABLE IF NOT EXISTS` alone never alters existing tables).
"""

import asyncio
import logging

from sqlalchemy import text

from backend.db.connection import engine
from backend.db.models import Base

logger = logging.getLogger("db.schema")

# Each statement is idempotent.
MIGRATIONS = [
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS client_id VARCHAR(64)",
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_agent VARCHAR(255)",
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS client_ip_hash VARCHAR(16)",
    "CREATE INDEX IF NOT EXISTS ix_sessions_client_id ON sessions (client_id)",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS model_provider VARCHAR(50)",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS model_name VARCHAR(100)",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS duration_ms INTEGER",
]


async def create_schema() -> None:
    """Create all tables and indexes, then apply additive migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for statement in MIGRATIONS:
            await conn.execute(text(statement))
    logger.info("schema_ready")


# Backwards-compatible alias (the original module exposed `init_db`).
init_db = create_schema


if __name__ == "__main__":
    asyncio.run(create_schema())
    print("Database tables initialized successfully.")
