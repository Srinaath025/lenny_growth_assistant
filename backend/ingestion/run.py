"""
Convenience CLI entry point for transcript ingestion.
Forwards to backend.ingestion.ingest.
"""
from backend.ingestion.ingest import main

if __name__ == "__main__":
    main()
