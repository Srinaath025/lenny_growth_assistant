@echo off
echo ==========================================================
echo  Lenny's Podcast Transcripts - Ingestion ^& Verification
echo ==========================================================
echo.
docker exec lenny-growth-backend python -m backend.ingestion.run --no-sync
echo.
echo [DONE] Ingestion check completed.
pause
