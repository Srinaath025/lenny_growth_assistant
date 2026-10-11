"""
Dedicated retrieval module for Lenny's Podcast transcripts.
Searches transcript_chunks using PostgreSQL Full-Text Search (tsvector + GIN index).
Returns a configurable set of relevant chunks preserving source traceability,
exact timestamps, and verified YouTube deep links.
"""

from dataclasses import dataclass
import logging
import re
from typing import Dict, Any, List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.connection import AsyncSessionLocal

logger = logging.getLogger("retrieval.retriever")

# Words that carry no retrieval signal. Postgres' English dictionary drops most of these
# too, but we need to know the *significant* term count in Python to compute coverage.
STOPWORDS = frozenset(
    """a about above after again all also am an and any are as at be because been before being below
    between both but by can could did do does doing down during each few for from further had has have
    having he her here hers him his how i if in into is it its just me more most my no nor not of off on
    once only or other our out over own same she should so some such than that the their theirs them then
    there these they this those through to too under until up very was we were what when where which while
    who whom why will with would you your yours tell say said says think thought lenny lennys please give
    explain explains talk talks discuss discusses want know like make get got guests guest podcast episode
    cite cited cites citation citations transcript transcripts evidence source sources quote quotes quoted reference
    references describe describes share shares mention mentions according provide include answer find show list
    verbatim exact exactly directly example examples please""".split()
)


@dataclass
class RetrievedChunk:
    """Represents a retrieved transcript chunk with full source traceability."""
    id: str
    episode_slug: str
    episode_title: str
    guest_name: str
    youtube_url: Optional[str]
    youtube_deep_link: Optional[str]
    video_id: Optional[str]
    publish_date: Optional[str]
    chunk_index: int
    speaker: Optional[str]
    start_timestamp: Optional[str]
    start_seconds: int
    end_timestamp: Optional[str]
    end_seconds: Optional[int]
    word_count: int
    content: str
    rank: float
    # Relevance gating metadata: how many of the query's significant terms this chunk matched.
    matched_terms: int = 0
    total_terms: int = 0
    weighted_coverage: float = 0.0

    @property
    def coverage(self) -> float:
        return self.weighted_coverage

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk into a dictionary representation."""
        return {
            "id": self.id,
            "episode_slug": self.episode_slug,
            "episode_title": self.episode_title,
            "guest_name": self.guest_name,
            "youtube_url": self.youtube_url,
            "youtube_deep_link": self.youtube_deep_link,
            "video_id": self.video_id,
            "publish_date": self.publish_date,
            "chunk_index": self.chunk_index,
            "speaker": self.speaker,
            "start_timestamp": self.start_timestamp,
            "start_seconds": self.start_seconds,
            "end_timestamp": self.end_timestamp,
            "end_seconds": self.end_seconds,
            "word_count": self.word_count,
            "content": self.content,
            "rank": round(self.rank, 5),
            "matched_terms": self.matched_terms,
            "total_terms": self.total_terms,
            "coverage": round(self.weighted_coverage, 3),
        }


def build_youtube_deep_link(
    youtube_url: Optional[str],
    video_id: Optional[str],
    start_seconds: int = 0,
) -> Optional[str]:
    """
    Constructs a verified YouTube deep link with timestamp.
    Returns None if neither video_id nor youtube_url is provided.
    """
    seconds = max(0, start_seconds)
    if video_id and video_id.strip():
        clean_vid = video_id.strip()
        return f"https://www.youtube.com/watch?v={clean_vid}&t={seconds}s"

    if youtube_url and youtube_url.strip():
        url = youtube_url.strip()
        # Clean any preexisting timestamp parameter to avoid duplicates
        url_without_t = re.sub(r"[?&]t=\d+s?", "", url)
        sep = "&" if "?" in url_without_t else "?"
        return f"{url_without_t}{sep}t={seconds}s"

    return None


def sanitize_fts_query(query: str) -> str:
    """
    Validates and sanitizes a user query for PostgreSQL full-text search.
    Normalizes punctuation, removes conversational question filler, and cleans control characters.
    """
    if not query:
        return ""
    # Normalize hyphens and control characters
    cleaned = query.replace("-", " ")
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", cleaned)
    cleaned = cleaned.replace("\\", " ").replace(";", " ")

    # Strip common conversational question prefixes and non-stopword filler verbs
    filler_patterns = [
        r"\bwhat (?:does|did|is|are|do)\b",
        r"\bhow (?:does|did|to|can|do)\b",
        r"\btell (?:me|us) about\b",
        r"\bcan you explain\b",
        r"\b(?:say|said|think|thought|recommend|recommends|discuss|discusses|talk|talks)\s+about\b",
        r"\b(?:say|said|think|thought)\b",
        r"\baccording to\b",
        r"\b(?:about\s+)?(?:hiring|having|starting|building)\s+(?:a|an)?\b",
    ]
    for pat in filler_patterns:
        cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)

    # Clean trailing or punctuation tokens like ? or !
    cleaned = re.sub(r"[?!.,]", " ", cleaned)
    return " ".join(cleaned.split()).strip()


# Document-frequency cache (term -> number of chunks containing it). The corpus is static between
# ingestions, so this is computed once per term; call `clear_corpus_stats()` after re-ingesting.
_DF_CACHE: Dict[str, int] = {}
_TOTAL_CHUNKS: Dict[str, int] = {}


def clear_corpus_stats() -> None:
    _DF_CACHE.clear()
    _TOTAL_CHUNKS.clear()


async def _term_weights(terms: List[str], s: AsyncSession) -> List[float]:
    """
    IDF-style weight per term: rare terms (names, jargon) count for more than common ones.
    This is what lets "weather in Paris tomorrow" fail the gate while "retention loops" passes.
    """
    import math

    if "n" not in _TOTAL_CHUNKS:
        _TOTAL_CHUNKS["n"] = int((await s.execute(text("SELECT count(*) FROM transcript_chunks"))).scalar_one() or 1)
    total = max(_TOTAL_CHUNKS["n"], 1)
    for term in terms:
        if term not in _DF_CACHE:
            df = (
                await s.execute(
                    text("SELECT count(*) FROM transcript_chunks WHERE search_vector @@ to_tsquery('english', :t)"),
                    {"t": term},
                )
            ).scalar_one()
            _DF_CACHE[term] = int(df or 0)
    return [math.log(1.0 + total / (1.0 + _DF_CACHE[t])) for t in terms]


def significant_terms(query: str, max_terms: int = 10) -> List[str]:
    """
    Extracts the distinct, meaningful search terms of a question (lower-cased, de-possessived,
    stop-words removed). Used both to build the OR query and to compute per-chunk coverage.
    """
    cleaned = sanitize_fts_query(query).lower().replace("\u2019", "'")
    terms: List[str] = []
    for raw in re.findall(r"[a-z0-9]+(?:'[a-z]+)?", cleaned):
        tok = re.sub(r"'s$", "", raw)
        if len(tok) < 3 and not tok.isdigit():
            continue
        if tok in STOPWORDS or tok in terms:
            continue
        terms.append(tok)
        if len(terms) >= max_terms:
            break
    return terms


async def retrieve_relevant_chunks(
    query: str,
    limit: int = 5,
    session: Optional[AsyncSession] = None,
    min_coverage: Optional[float] = None,
) -> List[RetrievedChunk]:
    """
    Searches transcript_chunks using PostgreSQL Full-Text Search with an evidence gate.

    Ranking: chunks are ordered by (IDF-weighted significant terms matched, ts_rank_cd).
    Gate: a chunk is returned only if it matches at least `min_coverage` (default from
    MIN_TERM_COVERAGE, 0.8) of the question's significant terms. Off-topic questions
    ("sourdough recipe", "capital of Mongolia") therefore return an EMPTY list, which the
    orchestrator turns into an immediate abstention -- retrieval, not the LLM, is the first
    line of defence against hallucination.

    NOTE: ts_rank_cd scores are not comparable across different queries, so a fixed absolute
    rank threshold (as in the original PRD) cannot separate on-topic from off-topic questions;
    term coverage is scale-free and is what we gate on.
    """
    terms = significant_terms(query)
    if not terms:
        logger.debug("query_rejected_no_significant_terms", extra={"query": query[:120]})
        return []

    coverage_floor = get_settings().min_term_coverage if min_coverage is None else min_coverage
    clamped_limit = max(1, min(limit, 20))
    candidate_pool = max(clamped_limit * 6, 40)

    async def _execute_search(s: AsyncSession) -> List[RetrievedChunk]:
        weights = await _term_weights(terms, s)
        total_weight = sum(weights) or 1.0

        params: Dict[str, Any] = {"orq": " | ".join(terms), "pool": candidate_pool}
        count_exprs, weight_exprs = [], []
        for i, term in enumerate(terms):
            params[f"t{i}"] = term
            params[f"w{i}"] = float(weights[i])
            flag = f"(CASE WHEN search_vector @@ to_tsquery('english', :t{i}) THEN 1 ELSE 0 END)"
            count_exprs.append(flag)
            weight_exprs.append(f"(CAST(:w{i} AS float8) * {flag})")

        sql = text(f"""
            SELECT id, episode_slug, episode_title, guest_name, youtube_url, video_id, publish_date,
                   chunk_index, speaker, start_timestamp, start_seconds, end_timestamp, end_seconds,
                   word_count, content,
                   ts_rank_cd(search_vector, to_tsquery('english', :orq)) AS rank,
                   ({" + ".join(count_exprs)}) AS matched,
                   ({" + ".join(weight_exprs)}) AS matched_w
            FROM transcript_chunks
            WHERE search_vector @@ to_tsquery('english', :orq)
            ORDER BY matched_w DESC, rank DESC, chunk_index ASC
            LIMIT :pool
        """)
        res = await s.execute(sql, params)
        rows = res.fetchall()

        results: List[RetrievedChunk] = []
        for r in rows:
            if float(r.matched_w) / total_weight < coverage_floor:
                continue
            results.append(
                RetrievedChunk(
                    id=r.id,
                    episode_slug=r.episode_slug,
                    episode_title=r.episode_title,
                    guest_name=r.guest_name,
                    youtube_url=r.youtube_url,
                    youtube_deep_link=build_youtube_deep_link(r.youtube_url, r.video_id, r.start_seconds),
                    video_id=r.video_id,
                    publish_date=r.publish_date,
                    chunk_index=r.chunk_index,
                    speaker=r.speaker,
                    start_timestamp=r.start_timestamp,
                    start_seconds=r.start_seconds,
                    end_timestamp=r.end_timestamp,
                    end_seconds=r.end_seconds,
                    word_count=r.word_count,
                    content=r.content,
                    rank=float(r.rank),
                    matched_terms=int(r.matched),
                    total_terms=len(terms),
                    weighted_coverage=float(r.matched_w) / total_weight,
                )
            )
            if len(results) >= clamped_limit:
                break

        best = max((float(r.matched_w) / total_weight for r in rows), default=0.0)
        logger.info(
            "retrieval",
            extra={
                "query": query[:160],
                "terms": terms,
                "coverage_floor": coverage_floor,
                "best_weighted_coverage": round(best, 3),
                "candidates": len(rows),
                "returned": len(results),
                "top_rank": round(results[0].rank, 4) if results else None,
            },
        )
        return results

    if session is not None:
        return await _execute_search(session)
    async with AsyncSessionLocal() as new_session:
        return await _execute_search(new_session)
