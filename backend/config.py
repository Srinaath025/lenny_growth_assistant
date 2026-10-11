"""
Central runtime configuration for the Lenny Growth Assistant.

Every tunable (model, endpoints, thresholds, CORS, logging) is read from environment
variables so an evaluator can switch models or behaviour by editing `.env` only --
no application code changes are required (assignment requirement 3.2).

Settings are read lazily on every `get_settings()` call (cheap) so tests and operators
can override environment variables at runtime without re-importing modules.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
# Cloud default is overridable with ANTHROPIC_MODEL. (claude-3-5-sonnet-20241022 was retired.)
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or not value.strip() else value.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env_str(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env_str(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env_str(name, "true" if default else "false").lower()
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # --- Local LLM (Ollama) ---
    ollama_base_url: str
    ollama_model: str
    ollama_num_ctx: int
    ollama_timeout_seconds: float

    # --- Cloud LLM (Anthropic & Google Gemini) ---
    anthropic_api_key: str
    anthropic_model: str
    gemini_api_key: str
    gemini_model: str
    cloud_timeout_seconds: float

    # --- Behaviour ---
    default_provider: str
    min_term_coverage: float
    retriever_limit: int
    history_turns: int
    history_char_budget: int
    essay_max_attempts: int
    essay_timeout_seconds: float

    # --- Platform ---
    cors_origins: List[str]
    log_format: str
    log_level: str
    auto_ingest: bool
    data_dir: Path

    @property
    def cloud_configured(self) -> bool:
        anthropic_ok = bool(self.anthropic_api_key) and not self.anthropic_api_key.startswith("your_") and len(self.anthropic_api_key) > 10
        gemini_ok = bool(self.gemini_api_key) and not self.gemini_api_key.startswith("your_") and len(self.gemini_api_key) > 10
        return anthropic_ok or gemini_ok


def get_settings() -> Settings:
    origins_raw = _env_str(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
    )
    data_dir_raw = _env_str("DATA_DIR", "data/transcripts")
    data_dir = Path(data_dir_raw)
    if not data_dir.is_absolute():
        data_dir = ROOT_DIR / data_dir

    return Settings(
        ollama_base_url=_env_str("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=_env_str("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        ollama_num_ctx=_env_int("OLLAMA_NUM_CTX", 8192),
        ollama_timeout_seconds=_env_float("OLLAMA_TIMEOUT_SECONDS", 180.0),
        anthropic_api_key=_env_str("ANTHROPIC_API_KEY", ""),
        anthropic_model=_env_str("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL),
        gemini_api_key=_env_str("GEMINI_API_KEY", _env_str("GOOGLE_API_KEY", "")),
        gemini_model=_env_str("GEMINI_MODEL", "gemini-3.8-flash"),
        cloud_timeout_seconds=_env_float("CLOUD_TIMEOUT_SECONDS", 120.0),
        default_provider=_env_str("LLM_PROVIDER", "ollama").lower(),
        min_term_coverage=_env_float("MIN_TERM_COVERAGE", 0.65),
        retriever_limit=_env_int("RETRIEVER_LIMIT", 2),
        history_turns=_env_int("HISTORY_TURNS", 6),
        history_char_budget=_env_int("HISTORY_CHAR_BUDGET", 3000),
        essay_max_attempts=_env_int("ESSAY_MAX_ATTEMPTS", 0),
        essay_timeout_seconds=_env_float("ESSAY_TIMEOUT_SECONDS", 900.0),
        cors_origins=[o.strip() for o in origins_raw.split(",") if o.strip()],
        log_format=_env_str("LOG_FORMAT", "json").lower(),
        log_level=_env_str("LOG_LEVEL", "INFO").upper(),
        auto_ingest=_env_bool("AUTO_INGEST", True),
        data_dir=data_dir,
    )
