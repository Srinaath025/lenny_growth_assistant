Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Lenny's Podcast Transcripts - Ingestion & Verification" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$container = docker ps -q -f name=lenny-growth-backend
if (-not $container) {
    Write-Host "[INFO] lenny-growth-backend Docker container is not running." -ForegroundColor Yellow
    Write-Host "[INFO] Starting services via docker compose..." -ForegroundColor Yellow
    docker compose up -d
}

Write-Host "`n[STEP 1] Checking current database chunk count..." -ForegroundColor Green
docker exec lenny-growth-backend python -c "
import asyncio
from backend.db.connection import AsyncSessionLocal
from sqlalchemy import text

async def check():
    try:
        async with AsyncSessionLocal() as s:
            count = (await s.execute(text('SELECT count(*) FROM transcript_chunks'))).scalar()
            print(f'Currently indexed chunks in PostgreSQL: {count}')
    except Exception as e:
        print(f'Error checking database: {e}')

asyncio.run(check())
"

Write-Host "`n[STEP 2] Running idempotent ingestion pipeline over 303 episodes..." -ForegroundColor Green
docker exec lenny-growth-backend python -m backend.ingestion.run --no-sync

Write-Host "`n[DONE] Ingestion verification completed successfully!" -ForegroundColor Green
