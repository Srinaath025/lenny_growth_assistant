"""
Shared test bootstrap: makes the suite self-contained for a fresh evaluator.

* Creates the schema and ingests the bundled transcripts if the database is empty
  (previously the tests silently depended on a manually pre-populated database).
* Stubs the Ollama probe so API tests do not need a running Ollama daemon.
"""

import pytest
import pytest_asyncio
from sqlalchemy import func, select


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _bootstrap_database():
    from backend.config import get_settings
    from backend.db.connection import AsyncSessionLocal
    from backend.db.models import TranscriptChunk
    from backend.db.schema import create_schema
    from backend.ingestion.ingest import run_ingestion_pipeline

    await create_schema()
    async with AsyncSessionLocal() as s:
        total = (await s.execute(select(func.count(TranscriptChunk.id)))).scalar_one()
    if total == 0:
        await run_ingestion_pipeline(data_dir=get_settings().data_dir, sync_online=False)
    yield


@pytest.fixture(autouse=True)
def _stub_ollama_probe(monkeypatch):
    import backend.main as main

    async def fake_probe(force: bool = False):
        return {"available": True, "model_installed": True, "error": None, "models": ["llama3.2:3b"]}

    monkeypatch.setattr(main, "probe_ollama", fake_probe)
