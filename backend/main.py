"""
The Lenny Growth Assistant - FastAPI backend.

Endpoints: /api/health, /api/sessions[...], /api/chat (SSE or JSON), /api/essay, /api/artifacts/{id}[/raw].
See architecture.md for the full contract, routing rules and failure behaviour.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import hashlib
import json
import logging
import sys
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
import uuid

if sys.platform == "win32":  # Pi RPC needs subprocess support on Windows
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.agent.artifact_skill import ArtifactSkill
from backend.agent.citation_validator import Citation
from backend.agent.conversation import ChatTurn, trim_history
from backend.agent.essay_skill import EssayEvidenceError, GeneratedEssay, Ship30EssayEngine
from backend.agent.orchestrator import GroundedAnswer, GrowthAssistantAgent
from backend.agent.prompt import ABSTENTION_MESSAGE
from backend.agent.router import ARTIFACT_HTML, ARTIFACT_MARKDOWN, CHAT, ESSAY, route_intent
from backend.config import get_settings
from backend.db.connection import AsyncSessionLocal, engine
from backend.db.models import Artifact, CitationRecord, Message, Session as DBSession, TranscriptChunk
from backend.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from backend.logging_config import configure_logging, request_id_ctx

logger = logging.getLogger("backend.main")

APP_VERSION = "1.1.0"
PROVIDERS = ("ollama", "anthropic", "claude", "gemini", "google")
INGEST_STATE: Dict[str, str] = {"state": "idle", "detail": ""}


# --------------------------------------------------------------------------- schemas
class OllamaHealth(BaseModel):
    available: bool
    url: str
    model: str
    model_installed: bool = False
    error: Optional[str] = None


class CloudHealth(BaseModel):
    available: bool
    provider: str = "anthropic"
    key_configured: bool
    model: str = ""


class DatabaseHealth(BaseModel):
    connected: bool
    total_chunks: int
    error: Optional[str] = None


class IngestionHealth(BaseModel):
    state: str
    detail: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str = APP_VERSION
    default_provider: str = "ollama"
    ollama: OllamaHealth
    cloud: CloudHealth
    database: DatabaseHealth
    ingestion: IngestionHealth = IngestionHealth(state="idle")


class SessionCreate(BaseModel):
    title: Optional[str] = Field("New Growth Session", max_length=255)
    model_provider: Optional[str] = "ollama"
    model_name: Optional[str] = None

    @field_validator("model_provider")
    @classmethod
    def _provider(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.lower().strip() not in PROVIDERS:
            raise ValueError(f"model_provider must be one of {PROVIDERS}")
        return v


class SessionUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    model_provider: Optional[str] = None
    model_name: Optional[str] = None


class SessionSummary(BaseModel):
    id: str
    title: str
    model_provider: str
    model_name: str
    created_at: str
    updated_at: str
    message_count: int


class CitationItem(BaseModel):
    id: Optional[str] = None
    episode_title: str
    guest_name: str
    youtube_url: str
    timestamp_seconds: Optional[int] = None
    quote_text: str


class MessageItem(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    is_abstention: bool
    created_at: str
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    citations: List[CitationItem] = []


class ArtifactSummary(BaseModel):
    id: str
    session_id: Optional[str] = None
    message_id: Optional[str] = None
    title: str
    artifact_type: str
    word_count: int
    created_at: str


class SessionDetailResponse(BaseModel):
    id: str
    title: str
    model_provider: str
    model_name: str
    created_at: str
    updated_at: str
    messages: List[MessageItem]
    artifacts: List[ArtifactSummary]


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=4000)
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    stream: Optional[bool] = True

    @field_validator("message")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


class ChatResponse(BaseModel):
    message_id: str
    session_id: str
    role: str = "assistant"
    content: str
    is_abstention: bool
    citations: List[CitationItem] = []
    duration_seconds: float
    intent: str = CHAT
    artifact_id: Optional[str] = None


class EssayRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    session_id: Optional[str] = None
    guest_filter: Optional[str] = Field(None, max_length=150)
    model_provider: Optional[str] = None
    provider: Optional[str] = None


class EssayResponse(BaseModel):
    artifact_id: str
    markdown_artifact_id: Optional[str] = None
    session_id: Optional[str] = None
    title: str
    subtitle: str
    topic: str
    word_count: int
    is_valid_word_count: bool
    has_all_4a_sections: bool
    guest_attributions: List[str]
    citations: List[CitationItem]
    markdown_content: str
    html_content: str
    created_at: str


class ArtifactDetailResponse(BaseModel):
    id: str
    session_id: Optional[str] = None
    message_id: Optional[str] = None
    title: str
    artifact_type: str
    content: str
    word_count: int
    created_at: str


# --------------------------------------------------------------------------- dependencies
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_agent() -> GrowthAssistantAgent:
    """Overridable in tests."""
    return GrowthAssistantAgent()


def get_essay_engine() -> Ship30EssayEngine:
    """Overridable in tests."""
    return Ship30EssayEngine()


_OLLAMA_CACHE: Dict[str, Any] = {"at": 0.0, "value": None}


async def probe_ollama(force: bool = False) -> Dict[str, Any]:
    """Queries Ollama /api/tags (cached 5s). Returns {available, model_installed, error, models}."""
    now = time.time()
    if not force and _OLLAMA_CACHE["value"] is not None and now - _OLLAMA_CACHE["at"] < 5:
        return _OLLAMA_CACHE["value"]
    cfg = get_settings()
    result: Dict[str, Any] = {"available": False, "model_installed": False, "error": None, "models": []}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{cfg.ollama_base_url}/api/tags")
        if resp.status_code == 200:
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            result.update(available=True, models=models)
            wanted = cfg.ollama_model
            result["model_installed"] = any(m == wanted or m.split(":")[0] == wanted or wanted in m for m in models)
            if not result["model_installed"]:
                result["error"] = f"Model '{wanted}' not found in Ollama ({len(models)} installed)."
        else:
            result["error"] = f"Ollama HTTP status {resp.status_code}"
    except Exception as exc:
        result["error"] = f"Connection failed to {cfg.ollama_base_url}: {type(exc).__name__}"
    _OLLAMA_CACHE.update(at=now, value=result)
    return result


async def preflight_checks(provider: str, db: AsyncSession) -> None:
    """
    Fails fast with a structured error BEFORE any message is persisted or any model is called.
    (Module-level so tests can monkeypatch it.)
    """
    cfg = get_settings()
    if provider in ("anthropic", "claude") and not cfg.cloud_configured:
        raise AppError(400, "CLOUD_CREDENTIALS_MISSING",
                       "ANTHROPIC_API_KEY is not configured in the backend environment. Use local Ollama mode.",
                       "Set ANTHROPIC_API_KEY in .env and restart the backend.")
    try:
        total = (await db.execute(select(func.count(TranscriptChunk.id)))).scalar_one() or 0
    except Exception as exc:
        raise AppError(503, "DATABASE_UNAVAILABLE", "The database is not reachable.",
                       "Check that PostgreSQL is running (docker compose up -d db) and DATABASE_URL is correct.") from exc
    if total == 0:
        state = INGEST_STATE["state"]
        raise AppError(503, "KNOWLEDGE_BASE_EMPTY",
                       "The transcript knowledge base is empty" + (" (indexing is still running)." if state == "running" else "."),
                       "Wait for indexing to finish, or run: python -m backend.ingestion.run --no-sync")
    if provider in ("anthropic", "claude"):
        return
    probe = await probe_ollama()
    if not probe["available"]:
        raise AppError(503, "OLLAMA_OFFLINE",
                       f"Ollama is not reachable at {cfg.ollama_base_url}.",
                       "Start it with `ollama serve` (in Docker the backend reaches the host via host.docker.internal).")
    if not probe["model_installed"]:
        raise AppError(422, "MODEL_MISSING", f"Model '{cfg.ollama_model}' is not installed in Ollama.",
                       f"Run: ollama pull {cfg.ollama_model}")


# --------------------------------------------------------------------------- helpers
def _client_meta(request: Request) -> Dict[str, Optional[str]]:
    ip = request.client.host if request.client else ""
    return {
        "client_id": (request.headers.get("x-client-id") or "")[:64] or None,
        "user_agent": (request.headers.get("user-agent") or "")[:255] or None,
        "client_ip_hash": hashlib.sha256(ip.encode()).hexdigest()[:16] if ip else None,
    }


def _resolve_provider(requested: Optional[str], sess: Optional[DBSession] = None) -> str:
    provider = (requested or (sess.model_provider if sess else None) or get_settings().default_provider or "ollama").lower().strip()
    if provider not in PROVIDERS:
        raise AppError(422, "UNKNOWN_PROVIDER", f"Unknown model provider '{provider}'.", f"Use one of: {', '.join(PROVIDERS)}")
    if provider in ("claude", "anthropic"):
        return "anthropic"
    if provider in ("gemini", "google"):
        return "gemini"
    return provider


def _model_name_for(provider: str) -> str:
    cfg = get_settings()
    if provider == "anthropic":
        return cfg.anthropic_model
    elif provider == "gemini":
        return cfg.gemini_model
    return cfg.ollama_model


def _apply_provider(agent: GrowthAssistantAgent, provider: str) -> None:
    if provider == "anthropic":
        from backend.agent.cloud_client import AnthropicClaudeClient

        agent.model_provider = "anthropic"
        agent.llm_client = AnthropicClaudeClient()
        agent.pi_client = agent.llm_client
    elif provider == "gemini":
        from backend.agent.cloud_client import GoogleGeminiClient

        agent.model_provider = "gemini"
        agent.llm_client = GoogleGeminiClient()
        agent.pi_client = agent.llm_client


def _citation_fields(c: Any) -> Dict[str, Any]:
    return {
        "episode_title": c.episode_title,
        "guest_name": c.guest_name,
        "youtube_url": getattr(c, "source_url", None) or getattr(c, "youtube_deep_link", None) or getattr(c, "youtube_url", "") or "",
        "timestamp_seconds": getattr(c, "start_seconds", None) if hasattr(c, "start_seconds") else getattr(c, "timestamp_seconds", None),
        "quote_text": getattr(c, "snippet", None) or getattr(c, "quote_text", "") or "",
    }


async def load_history(db: AsyncSession, session_id: str) -> List[ChatTurn]:
    """Messages of THIS session only (sessions never share context)."""
    cfg = get_settings()
    rows = (
        await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(cfg.history_turns * 2)
        )
    ).scalars().all()
    turns = [ChatTurn(role=m.role, content=m.content) for m in reversed(rows) if not m.is_abstention or m.role == "user"]
    return trim_history(turns, cfg.history_turns, cfg.history_char_budget)


# --------------------------------------------------------------------------- lifespan
async def _auto_ingest() -> None:
    from backend.ingestion.ingest import run_ingestion_pipeline
    from backend.retrieval.retriever import clear_corpus_stats

    cfg = get_settings()
    try:
        async with AsyncSessionLocal() as s:
            existing = (await s.execute(select(func.count(TranscriptChunk.id)))).scalar_one() or 0
        if existing > 0:
            INGEST_STATE.update(state="skipped", detail=f"{existing} chunks already indexed")
            return
        if not cfg.data_dir.exists():
            INGEST_STATE.update(state="failed", detail=f"data directory not found: {cfg.data_dir}")
            logger.error("auto_ingest_no_data", extra={"data_dir": str(cfg.data_dir)})
            return
        INGEST_STATE.update(state="running", detail="indexing transcripts")
        logger.info("auto_ingest_started", extra={"data_dir": str(cfg.data_dir)})
        stats = await run_ingestion_pipeline(data_dir=cfg.data_dir, sync_online=False)
        clear_corpus_stats()
        INGEST_STATE.update(state="done", detail=f"{stats.get('episodes_ingested', 0)} episodes, {stats.get('total_chunks_in_db', 0)} chunks")
        logger.info("auto_ingest_done", extra=stats)
    except Exception as exc:
        INGEST_STATE.update(state="failed", detail=str(exc)[:200])
        logger.error("auto_ingest_failed", exc_info=exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    configure_logging(cfg.log_format, cfg.log_level)
    logger.info("startup", extra={"version": APP_VERSION, "ollama_url": cfg.ollama_base_url, "ollama_model": cfg.ollama_model,
                                  "cloud_configured": cfg.cloud_configured, "cors_origins": cfg.cors_origins})
    task: Optional[asyncio.Task] = None
    try:
        from backend.db.schema import create_schema

        await create_schema()
        if cfg.auto_ingest:
            task = asyncio.create_task(_auto_ingest())
    except Exception as exc:  # the API still starts; /api/health reports the database as down
        logger.error("schema_init_failed", exc_info=exc)
    yield
    if task and not task.done():
        task.cancel()
    await engine.dispose()
    logger.info("shutdown_complete")


app = FastAPI(
    title="The Lenny Growth Assistant API",
    version=APP_VERSION,
    description="Retrieval-grounded Q&A, Ship 30 for 30 essays and sandboxed artifacts over Lenny's Podcast transcripts.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = request_id_ctx.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.error("request_crashed", extra={"method": request.method, "path": request.url.path}, exc_info=True)
        raise
    finally:
        request_id_ctx.reset(token)
    response.headers["X-Request-ID"] = rid
    if request.url.path != "/api/health":
        logger.info("http_request", extra={"method": request.method, "path": request.url.path,
                                           "status": response.status_code, "ms": round((time.perf_counter() - start) * 1000, 1),
                                           "request_id": rid})
    return response


# --------------------------------------------------------------------------- health
@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """Operational health of PostgreSQL, Ollama, the cloud key and background ingestion."""
    cfg = get_settings()
    db_connected, total_chunks, db_error = False, 0, None
    try:
        total_chunks = (await db.execute(select(func.count(TranscriptChunk.id)))).scalar_one() or 0
        db_connected = True
    except Exception as exc:
        db_error = type(exc).__name__
        logger.warning("health_db_failed", extra={"error": str(exc)[:200]})

    probe = await probe_ollama(force=True)
    cloud_ok = cfg.cloud_configured

    if not db_connected:
        status_str = "unhealthy"
    elif (not probe["available"] and not cloud_ok) or total_chunks == 0:
        status_str = "degraded"
    else:
        status_str = "healthy"

    cloud_provider = "gemini" if cfg.gemini_api_key else "anthropic"
    cloud_model = cfg.gemini_model if cfg.gemini_api_key else cfg.anthropic_model

    return HealthResponse(
        status=status_str,
        default_provider=cfg.default_provider,
        ollama=OllamaHealth(available=probe["available"], url=cfg.ollama_base_url, model=cfg.ollama_model,
                            model_installed=probe["model_installed"], error=probe["error"]),
        cloud=CloudHealth(available=cloud_ok, provider=cloud_provider, key_configured=cloud_ok, model=cloud_model),
        database=DatabaseHealth(connected=db_connected, total_chunks=total_chunks, error=db_error),
        ingestion=IngestionHealth(**INGEST_STATE),
    )


# --------------------------------------------------------------------------- sessions
def _summary(s: DBSession, count: int) -> SessionSummary:
    return SessionSummary(id=s.id, title=s.title, model_provider=s.model_provider, model_name=s.model_name,
                          created_at=s.created_at.isoformat(), updated_at=s.updated_at.isoformat(), message_count=count)


async def _get_session_or_404(db: AsyncSession, session_id: str) -> DBSession:
    sess = (await db.execute(select(DBSession).where(DBSession.id == session_id))).scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return sess


@app.get("/api/sessions", response_model=List[SessionSummary], tags=["Sessions"])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    sessions = (await db.execute(select(DBSession).order_by(DBSession.updated_at.desc()))).scalars().all()
    counts = dict((await db.execute(select(Message.session_id, func.count(Message.id)).group_by(Message.session_id))).all())
    return [_summary(s, counts.get(s.id, 0)) for s in sessions]


@app.post("/api/sessions", response_model=SessionSummary, status_code=status.HTTP_201_CREATED, tags=["Sessions"])
async def create_session(req: SessionCreate, request: Request, db: AsyncSession = Depends(get_db)):
    provider = _resolve_provider(req.model_provider)
    now = datetime.utcnow()
    meta = _client_meta(request)
    new_sess = DBSession(
        id=str(uuid.uuid4()), title=(req.title or "New Growth Session").strip() or "New Growth Session",
        model_provider=provider, model_name=req.model_name or _model_name_for(provider),
        created_at=now, updated_at=now, **meta,
    )
    db.add(new_sess)
    await db.commit()
    await db.refresh(new_sess)
    logger.info("session_created", extra={"session_id": new_sess.id, "provider": provider})
    return _summary(new_sess, 0)


@app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse, tags=["Sessions"])
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    sess = await _get_session_or_404(db, session_id)
    messages = (await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc()))).scalars().all()
    by_msg: Dict[str, List[CitationItem]] = {m.id: [] for m in messages}
    if messages:
        cites = (await db.execute(select(CitationRecord).where(CitationRecord.message_id.in_(list(by_msg))).order_by(CitationRecord.created_at.asc()))).scalars().all()
        for c in cites:
            by_msg[c.message_id].append(CitationItem(id=c.id, episode_title=c.episode_title, guest_name=c.guest_name,
                                                     youtube_url=c.youtube_url, timestamp_seconds=c.timestamp_seconds, quote_text=c.quote_text))
    arts = (await db.execute(select(Artifact).where(Artifact.session_id == session_id).order_by(Artifact.created_at.asc()))).scalars().all()
    return SessionDetailResponse(
        id=sess.id, title=sess.title, model_provider=sess.model_provider, model_name=sess.model_name,
        created_at=sess.created_at.isoformat(), updated_at=sess.updated_at.isoformat(),
        messages=[MessageItem(id=m.id, session_id=m.session_id, role=m.role, content=m.content, is_abstention=m.is_abstention,
                              created_at=m.created_at.isoformat(), model_provider=m.model_provider, model_name=m.model_name,
                              citations=by_msg.get(m.id, [])) for m in messages],
        artifacts=[ArtifactSummary(id=a.id, session_id=a.session_id, message_id=a.message_id, title=a.title, artifact_type=a.artifact_type,
                                   word_count=a.word_count or 0, created_at=a.created_at.isoformat() if a.created_at else "") for a in arts],
    )


@app.patch("/api/sessions/{session_id}", response_model=SessionSummary, tags=["Sessions"])
async def update_session(session_id: str, req: SessionUpdate, db: AsyncSession = Depends(get_db)):
    sess = await _get_session_or_404(db, session_id)
    if req.title is not None:
        sess.title = req.title.strip() or "Untitled Session"
    if req.model_provider is not None:
        p = req.model_provider.lower().strip()
        if p not in PROVIDERS:
            raise AppError(422, "UNKNOWN_PROVIDER", f"Unknown model provider '{p}'.")
        sess.model_provider = "anthropic" if p == "claude" else p
    if req.model_name is not None:
        sess.model_name = req.model_name
    sess.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(sess)
    count = (await db.execute(select(func.count(Message.id)).where(Message.session_id == session_id))).scalar_one() or 0
    return _summary(sess, count)


@app.delete("/api/sessions/{session_id}", tags=["Sessions"])
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    sess = await _get_session_or_404(db, session_id)
    await db.delete(sess)
    await db.commit()
    return {"deleted": True, "id": session_id}


# --------------------------------------------------------------------------- chat
async def _persist_assistant(
    session_id: str, content: str, is_abstention: bool, provider: str, duration_s: float,
    citations: List[Dict[str, Any]],
) -> str:
    msg_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as save_db:
        save_db.add(Message(id=msg_id, session_id=session_id, role="assistant", content=content, is_abstention=is_abstention,
                            model_provider=provider, model_name=_model_name_for(provider),
                            duration_ms=int(duration_s * 1000), created_at=datetime.utcnow()))
        await save_db.flush()
        for c in citations:
            save_db.add(CitationRecord(id=str(uuid.uuid4()), message_id=msg_id, created_at=datetime.utcnow(), **c))
        sess = (await save_db.execute(select(DBSession).where(DBSession.id == session_id))).scalar_one_or_none()
        if sess:
            sess.updated_at = datetime.utcnow()
        await save_db.commit()
    return msg_id


async def _run_chat(
    agent: GrowthAssistantAgent, session_id: str, message: str, provider: str, history: List[ChatTurn],
    emit,
) -> Dict[str, Any]:
    """Routes the message to a skill, persists the result and returns the final payload."""
    started = time.time()
    intent = route_intent(message, history)
    logger.info("intent_routed", extra={"intent": intent.kind, "reason": intent.reason, "provider": provider})

    # ---- Ship 30 for 30 essay
    if intent.kind == ESSAY:
        await emit({"type": "status", "text": "Retrieving transcripts and drafting your Ship 30 for 30 essay…"})
        engine_ = Ship30EssayEngine(llm_client=agent.llm_client, model_provider=provider)
        try:
            essay = await engine_.generate_essay(
                topic=intent.topic or message,
                session_id=session_id,
                on_delta=lambda d: emit({"type": "token", "text": d}),
            )
        except EssayEvidenceError as exc:
            msg_id = await _persist_assistant(session_id, ABSTENTION_MESSAGE + " " + str(exc), True, provider, time.time() - started, [])
            return {"message_id": msg_id, "content": ABSTENTION_MESSAGE + " " + str(exc), "is_abstention": True,
                    "citations": [], "intent": ESSAY, "artifact_id": None, "duration_seconds": round(time.time() - started, 2)}
        note = "" if essay.is_valid_word_count else f" (note: the model produced {essay.word_count} words, outside the 1,100–1,400 target)"
        content = (f"I wrote a Ship 30 for 30 essay, **{essay.title}** (~{essay.word_count} words){note}. "
                   "It follows the 4A framework and the Two-Year Test and is grounded in "
                   f"{', '.join(essay.guest_attributions[:4]) or 'the transcripts'}. Open it in the Artifact Viewer →")
        cites = [_citation_fields(c) for c in essay.citations]
        msg_id = await _persist_assistant(session_id, content, False, provider, time.time() - started, cites)
        return {"message_id": msg_id, "content": content, "is_abstention": False, "citations": cites, "intent": ESSAY,
                "artifact_id": essay.artifact_id, "duration_seconds": round(time.time() - started, 2), "streamed": True}

    # ---- Markdown / HTML artifact from the conversation
    if intent.kind in (ARTIFACT_MARKDOWN, ARTIFACT_HTML):
        label = "HTML/CSS" if intent.kind == ARTIFACT_HTML else "Markdown"
        await emit({"type": "status", "text": f"Building your {label} artifact from the transcripts…"})
        skill = ArtifactSkill(agent.llm_client)
        art = await skill.generate(intent.kind, message, history)
        if art.is_abstention:
            content = ABSTENTION_MESSAGE + " I could not find transcript evidence to build that artifact — try asking a question about the topic first."
            msg_id = await _persist_assistant(session_id, content, True, provider, time.time() - started, [])
            return {"message_id": msg_id, "content": content, "is_abstention": True, "citations": [], "intent": intent.kind,
                    "artifact_id": None, "duration_seconds": round(time.time() - started, 2)}
        cites = [_citation_fields(c) for c in art.citations]
        content = f"I created a {label} artifact: **{art.title}**. It is open in the Artifact Viewer →"
        msg_id = await _persist_assistant(session_id, content, False, provider, time.time() - started, cites)
        artifact_id = await skill.save(art, session_id=session_id, message_id=msg_id)
        return {"message_id": msg_id, "content": content, "is_abstention": False, "citations": cites, "intent": intent.kind,
                "artifact_id": artifact_id, "duration_seconds": round(time.time() - started, 2)}

    # ---- Grounded Q&A (default)
    answer: GroundedAnswer = await agent.ask(query=message, session=None, history=history,
                                             on_delta=lambda d: emit({"type": "token", "text": d}))
    if answer.error:
        raise AppError(502, "MODEL_ERROR", answer.answer,
                       "Check the model provider (is Ollama running? is the key valid?). The request_id is in the logs.")
    cites = [_citation_fields(c) for c in answer.citations]
    msg_id = await _persist_assistant(session_id, answer.answer, answer.is_abstention, provider, answer.duration_seconds, cites)
    return {"message_id": msg_id, "content": answer.answer, "is_abstention": answer.is_abstention, "citations": cites,
            "intent": CHAT, "artifact_id": None, "duration_seconds": answer.duration_seconds, "streamed": True}


@app.post("/api/chat", tags=["Chat"])
async def chat(req: ChatRequest, request: Request, db: AsyncSession = Depends(get_db),
               agent: GrowthAssistantAgent = Depends(get_agent)):
    """Grounded chat (SSE by default, JSON when stream=false). Routes essay/artifact requests to skills."""
    sess = await _get_session_or_404(db, req.session_id)
    provider = _resolve_provider(req.model_provider, sess)
    await preflight_checks(provider, db)  # structured 4xx/5xx before anything is stored

    history = await load_history(db, req.session_id)  # BEFORE adding the new user message
    db.add(Message(id=str(uuid.uuid4()), session_id=req.session_id, role="user", content=req.message,
                   is_abstention=False, created_at=datetime.utcnow()))
    if sess.title == "New Growth Session":
        cleaned = req.message.replace("\n", " ")
        sess.title = cleaned[:45] + ("..." if len(cleaned) > 45 else "")
    sess.model_provider = provider
    sess.updated_at = datetime.utcnow()
    await db.commit()

    _apply_provider(agent, provider)
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(evt: Dict[str, Any]) -> None:
        await queue.put(evt)

    async def producer() -> None:
        try:
            result = await _run_chat(agent, req.session_id, req.message, provider, history, emit)
            await queue.put({"type": "complete", "result": result})
        except AppError as exc:
            await queue.put({"type": "error", "code": exc.code, "error": exc.message, "hint": exc.hint})
        except Exception as exc:
            logger.error("chat_failed", exc_info=exc)
            await queue.put({"type": "error", "code": "INTERNAL_ERROR", "error": "The assistant hit an unexpected error."})

    task = asyncio.create_task(producer())  # keeps running (and persisting) even if the client disconnects

    def _payload(result: Dict[str, Any]) -> Dict[str, Any]:
        return {"message_id": result["message_id"], "session_id": req.session_id, "role": "assistant",
                "content": result["content"], "is_abstention": result["is_abstention"],
                "citations": result["citations"], "duration_seconds": result["duration_seconds"],
                "intent": result["intent"], "artifact_id": result["artifact_id"]}

    if not req.stream:
        while True:
            evt = await queue.get()
            if evt["type"] == "complete":
                return ChatResponse(**_payload(evt["result"]))
            if evt["type"] == "error":
                raise AppError(502, evt["code"], evt["error"], evt.get("hint"))

    async def sse() -> AsyncGenerator[str, None]:
        rid = request_id_ctx.get()
        while True:
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=1.5)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            t = evt["type"]
            if t == "token":
                yield f"event: token\ndata: {json.dumps({'text': evt['text']})}\n\n"
            elif t == "status":
                yield f"event: status\ndata: {json.dumps({'text': evt['text']})}\n\n"
            elif t == "complete":
                res = evt["result"]
                if not res.get("streamed"):  # essay / artifact / abstention-without-tokens: send the text now
                    yield f"event: token\ndata: {json.dumps({'text': res['content']})}\n\n"
                elif res["is_abstention"]:
                    pass
                if res.get("artifact_id"):
                    yield f"event: artifact\ndata: {json.dumps({'artifact_id': res['artifact_id'], 'intent': res['intent']})}\n\n"
                yield f"event: complete\ndata: {json.dumps(_payload(res))}\n\n"
                yield "event: done\ndata: [DONE]\n\n"
                return
            elif t == "error":
                yield f"event: error\ndata: {json.dumps({'error': evt['error'], 'code': evt.get('code'), 'hint': evt.get('hint'), 'request_id': rid})}\n\n"
                yield "event: done\ndata: [DONE]\n\n"
                return

    return StreamingResponse(sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- essay endpoint
@app.post("/api/essay", response_model=EssayResponse, tags=["Essay"])
async def generate_essay(req: EssayRequest, db: AsyncSession = Depends(get_db),
                         engine_: Ship30EssayEngine = Depends(get_essay_engine)):
    """Dedicated Ship 30 for 30 skill endpoint (also reachable through chat routing)."""
    provider = _resolve_provider(req.model_provider or req.provider)
    if provider not in PROVIDERS:
        raise AppError(422, "UNKNOWN_PROVIDER", f"Unknown model provider '{provider}'.")
    if provider == "anthropic":
        from backend.agent.cloud_client import AnthropicClaudeClient

        cloud = AnthropicClaudeClient()
        if not cloud.is_configured():
            raise AppError(400, "CLOUD_CREDENTIALS_MISSING",
                           "ANTHROPIC_API_KEY is not configured in the backend environment. Use local Ollama mode.")
        engine_.model_provider, engine_.llm_client = "anthropic", cloud
    elif provider == "gemini":
        from backend.agent.cloud_client import GoogleGeminiClient

        gemini = GoogleGeminiClient()
        if not gemini.is_configured():
            raise AppError(400, "CLOUD_CREDENTIALS_MISSING",
                           "GEMINI_API_KEY is not configured in the backend environment. Get a free key at https://aistudio.google.com/app/apikey")
        engine_.model_provider, engine_.llm_client = "gemini", gemini
    if req.session_id:
        await _get_session_or_404(db, req.session_id)

    try:
        essay: GeneratedEssay = await engine_.generate_essay(topic=req.topic.strip(), session_id=req.session_id,
                                                             guest_filter=req.guest_filter, session=db)
    except EssayEvidenceError as exc:
        raise AppError(422, "NO_EVIDENCE", str(exc), "Try a topic that Lenny's guests actually discussed.") from exc

    if req.session_id:
        db.add(Message(id=str(uuid.uuid4()), session_id=req.session_id, role="user",
                       content=f"Generate a Ship 30 for 30 essay on: {req.topic}", is_abstention=False, created_at=datetime.utcnow()))
        db.add(Message(id=str(uuid.uuid4()), session_id=req.session_id, role="assistant",
                       content=(f"I have generated a Ship 30 for 30 growth essay on **{essay.title}** (~{essay.word_count} words). "
                                "It adheres to the 4A framework and passes the Two-Year Test.\n\nThe artifact is available in the viewer."),
                       is_abstention=False, model_provider=provider, model_name=_model_name_for(provider), created_at=datetime.utcnow()))
        await db.commit()

    return EssayResponse(
        artifact_id=essay.artifact_id or "", markdown_artifact_id=essay.markdown_artifact_id, session_id=req.session_id,
        title=essay.title, subtitle=essay.subtitle, topic=essay.topic, word_count=essay.word_count,
        is_valid_word_count=essay.is_valid_word_count, has_all_4a_sections=essay.has_all_4a_sections,
        guest_attributions=essay.guest_attributions,
        citations=[CitationItem(id=getattr(c, "chunk_id", None), **_citation_fields(c)) for c in essay.citations],
        markdown_content=essay.markdown_content, html_content=essay.html_content, created_at=essay.created_at,
    )


# --------------------------------------------------------------------------- artifacts
@app.get("/api/artifacts/{artifact_id}", response_model=ArtifactDetailResponse, tags=["Artifacts"])
async def get_artifact(artifact_id: str, db: AsyncSession = Depends(get_db)):
    art = (await db.execute(select(Artifact).where(Artifact.id == artifact_id))).scalar_one_or_none()
    if not art:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found")
    return ArtifactDetailResponse(id=art.id, session_id=art.session_id, message_id=art.message_id, title=art.title,
                                  artifact_type=art.artifact_type, content=art.content, word_count=art.word_count or 0,
                                  created_at=art.created_at.isoformat() if art.created_at else "")


RAW_ARTIFACT_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'"


@app.get("/api/artifacts/{artifact_id}/raw", response_class=HTMLResponse, tags=["Artifacts"])
async def get_raw_artifact(artifact_id: str, db: AsyncSession = Depends(get_db)):
    """Raw HTML artifact for direct opening; the CSP `sandbox` directive applies the same isolation as the in-app viewer."""
    art = (await db.execute(select(Artifact).where(Artifact.id == artifact_id))).scalar_one_or_none()
    if not art:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found")
    if art.artifact_type != "html":
        raise AppError(400, "NOT_HTML", "Only HTML artifacts can be served raw.", "Use GET /api/artifacts/{id} for Markdown.")
    return HTMLResponse(content=art.content, headers={"Content-Security-Policy": RAW_ARTIFACT_CSP,
                                                      "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN",
                                                      "Referrer-Policy": "no-referrer"})
