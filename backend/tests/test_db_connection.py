"""
Milestone 1 Database Connection & Environment Verification Tests.
Verifies:
1. All core dependencies (SQLAlchemy, asyncpg, PyYAML, dotenv) import cleanly.
2. Direct connection to Docker PostgreSQL on 127.0.0.1:5433 using asyncpg.
3. Asynchronous SQLAlchemy engine connection and query execution.
4. Verifies database name is 'lenny_growth_db' and engine is PostgreSQL 16.
"""

import os
from pathlib import Path
import pytest
from dotenv import load_dotenv

# Load environment from root .env
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")


def test_dependency_imports():
    """Verify that all Milestone 1 required dependencies can be imported cleanly."""
    import asyncpg
    import sqlalchemy
    import yaml
    import greenlet

    assert asyncpg.__version__ is not None
    assert sqlalchemy.__version__ is not None
    assert yaml.__version__ is not None
    assert greenlet.__version__ is not None


@pytest.mark.asyncio
async def test_asyncpg_direct_connection():
    """Verify real database connectivity over port 5433 using asyncpg."""
    import asyncpg

    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = int(os.getenv("POSTGRES_PORT", "5433"))
    user = os.getenv("POSTGRES_USER", "lenny_user")
    password = os.getenv("POSTGRES_PASSWORD", "lenny_dev_password_change_in_prod")
    database = os.getenv("POSTGRES_DB", "lenny_growth_db")

    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        timeout=5.0,
    )
    try:
        db_name = await conn.fetchval("SELECT current_database();")
        version_str = await conn.fetchval("SELECT version();")

        assert db_name == "lenny_growth_db"
        assert "PostgreSQL 16" in version_str
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_sqlalchemy_async_engine():
    """Verify SQLAlchemy 2.0 AsyncEngine connectivity over port 5433."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://lenny_user:lenny_dev_password_change_in_prod@127.0.0.1:5433/lenny_growth_db"
    )

    engine = create_async_engine(database_url, echo=False)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1 AS alive, current_database() AS db_name;"))
        row = result.mappings().one()

        assert row["alive"] == 1
        assert row["db_name"] == "lenny_growth_db"

    await engine.dispose()
