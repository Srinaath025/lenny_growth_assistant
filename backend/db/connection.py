"""
Database connection and session factory for PostgreSQL (Docker Port 5433).
Reads connection settings strictly from environment variables without exposing secrets.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Load root .env
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

DEFAULT_DATABASE_URL = "postgresql+asyncpg://lenny_user:lenny_dev_password_change_in_prod@127.0.0.1:5433/lenny_growth_db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncSession:
    """Dependency / context provider for async database sessions."""
    async with AsyncSessionLocal() as session:
        yield session
