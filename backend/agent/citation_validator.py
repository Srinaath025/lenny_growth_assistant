"""
Citation validation and verification layer for Lenny Growth Assistant.
Ensures that all citations emitted by the LLM strictly correspond to retrieved chunk IDs,
preserves verified source metadata (never trusting LLM for metadata), and detects abstentions.
"""

from dataclasses import dataclass
import logging
import re
from typing import Dict, Any, List, Set, Optional, Tuple
from backend.retrieval.retriever import RetrievedChunk, build_youtube_deep_link
from backend.agent.prompt import ABSTENTION_MESSAGE


@dataclass
class Citation:
    """A verified source citation pointing to an authentic transcript chunk."""
    chunk_id: str
    episode_title: str
    guest_name: str
    timestamp: Optional[str]
    start_seconds: int
    source_url: Optional[str]
    snippet: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "episode_title": self.episode_title,
            "guest_name": self.guest_name,
            "timestamp": self.timestamp,
            "start_seconds": self.start_seconds,
            "source_url": self.source_url,
            "snippet": self.snippet,
        }


@dataclass
class ValidationResult:
    """Outcome of validating model response against retrieved evidence."""
    is_abstention: bool
    valid_citations: List[Citation]
    invalid_chunk_ids: List[str]
    cleaned_answer: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_abstention": self.is_abstention,
            "valid_citations": [c.to_dict() for c in self.valid_citations],
            "invalid_chunk_ids": self.invalid_chunk_ids,
            "cleaned_answer": self.cleaned_answer,
        }


# Regex to detect bracketed citation tokens: e.g. [citation:12345...] or [12345...]
# Small models sometimes copy the prompt's evidence block header instead of citing. The header
# carries the real chunk id, so it is converted into a normal citation token and the header text removed.
_ECHO_OPEN = re.compile(r'\[EVIDENCE CHUNK[^\]]*?id="([a-f0-9]{16,64})"[^\]]*\]', re.IGNORECASE)
_ECHO_ANY = re.compile(r'\[/?EVIDENCE CHUNK[^\]]*\]', re.IGNORECASE)


def normalise_echoed_evidence(text: str) -> str:
    text = _ECHO_OPEN.sub(lambda m: f"[citation:{m.group(1)}] ", text)
    return _ECHO_ANY.sub("", text)


logger = logging.getLogger("agent.citation_validator")

CITATION_PATTERN = re.compile(r"\[(?:citation:\s*)?([a-f0-9]{16,64})\]", re.IGNORECASE)

# When the model forgets the [citation:ID] syntax we may still attach the best-matching retrieved
# chunk, but ONLY if the answer shares at least this many distinctive words with it. Below that the
# answer is treated as ungrounded (it would otherwise receive a "verified" source it never used).
MIN_INFERRED_OVERLAP = 3

# Phrases indicating model abstention
ABSTENTION_PHRASES = [
    "do not have sufficient evidence",
    "insufficient evidence",
    "no evidence in lenny's podcast",
    "not enough evidence",
    "the provided transcripts do not contain",
    "transcripts provided do not contain",
    "provided evidence does not contain",
    "cannot answer based on the provided",
]


def resolve_turn_timestamp(
    content: str,
    answer_text: str,
    default_ts: Optional[str],
    default_seconds: int,
) -> Tuple[Optional[str], int, str]:
    """
    Finds the specific dialogue turn within a chunk that best matches the cited answer.
    Returns (timestamp_str, seconds, turn_snippet) for accurate deep linking.
    """
    turn_matches = list(re.finditer(
        r"([A-Za-z0-9\s\.\'\-–—]+?)\s*\((?:(\d{1,2}):)?(\d{1,2}):(\d{2})\)\s*:\s*(.*?)(?=\n\n[A-Za-z0-9\s\.\'\-–—]+?\s*\(|\Z)",
        content,
        re.DOTALL
    ))
    if not turn_matches:
        default_snippet = content[:200].strip() + ("..." if len(content) > 200 else "")
        return default_ts, default_seconds, default_snippet

    answer_words = set(re.findall(r"[a-zA-Z]{4,}", answer_text.lower()))
    if not answer_words:
        default_snippet = content[:200].strip() + ("..." if len(content) > 200 else "")
        return default_ts, default_seconds, default_snippet

    best_ts = default_ts
    best_secs = default_seconds
    best_snippet = content[:200].strip() + ("..." if len(content) > 200 else "")
    best_overlap = 0

    for m in turn_matches:
        speaker = m.group(1).strip()
        h_str, m_str, s_str = m.group(2), m.group(3), m.group(4)
        h = int(h_str) if h_str else 0
        secs = h * 3600 + int(m_str) * 60 + int(s_str)
        ts_str = f"{h:02d}:{int(m_str):02d}:{int(s_str):02d}"
        text_turn = m.group(5).strip()

        turn_words = set(re.findall(r"[a-zA-Z]{4,}", text_turn.lower()))
        overlap = len(answer_words.intersection(turn_words))
        if overlap > best_overlap:
            best_overlap = overlap
            best_ts = ts_str
            best_secs = secs
            best_snippet = f"{speaker} ({ts_str}): {text_turn[:180].strip()}" + ("..." if len(text_turn) > 180 else "")

    if best_overlap >= 3:
        return best_ts, best_secs, best_snippet
    return default_ts, default_seconds, content[:200].strip() + ("..." if len(content) > 200 else "")


class CitationValidator:
    """Validates citations against the exact set of retrieved transcript chunks."""

    @staticmethod
    def is_abstention_text(text: str) -> bool:
        """Determines whether text represents an evidence-based abstention."""
        if not text or not text.strip():
            return True
        lower = text.lower()
        if ABSTENTION_MESSAGE.lower() in lower:
            return True
        for phrase in ABSTENTION_PHRASES:
            if phrase in lower:
                return True
        return False

    @classmethod
    def validate(
        cls,
        model_response: str,
        retrieved_chunks: List[RetrievedChunk],
        allow_inferred: bool = True,
        min_inferred_overlap: int = MIN_INFERRED_OVERLAP,
    ) -> ValidationResult:
        """
        Validates model response against retrieved chunks.
        
        Args:
            model_response: Raw text returned by Pi Coding Agent.
            retrieved_chunks: The chunks actually provided to the agent for this prompt.
            
        Returns:
            ValidationResult with verified citations and abstention status.
        """
        model_response = normalise_echoed_evidence(model_response)

        # If no chunks were provided, response must be treated as abstention
        if not retrieved_chunks:
            return ValidationResult(
                is_abstention=True,
                valid_citations=[],
                invalid_chunk_ids=[],
                cleaned_answer=ABSTENTION_MESSAGE,
            )

        # Check if the model explicitly abstained
        if cls.is_abstention_text(model_response):
            logger.warning("abstention_model_refused", extra={"response_head": model_response[:300]})
            return ValidationResult(
                is_abstention=True,
                valid_citations=[],
                invalid_chunk_ids=[],
                cleaned_answer=ABSTENTION_MESSAGE,
            )

        # Build lookup table of allowed chunks
        allowed_map: Dict[str, RetrievedChunk] = {c.id.lower(): c for c in retrieved_chunks}

        # Extract cited chunk IDs
        raw_matches = CITATION_PATTERN.findall(model_response)
        seen_cited_ids: Set[str] = set()
        valid_citations: List[Citation] = []
        invalid_ids: List[str] = []

        for match_id in raw_matches:
            norm_id = match_id.lower()
            if norm_id in seen_cited_ids:
                continue
            seen_cited_ids.add(norm_id)

            if norm_id in allowed_map:
                chunk = allowed_map[norm_id]
                ts, secs, snippet = resolve_turn_timestamp(
                    chunk.content,
                    model_response,
                    chunk.start_timestamp,
                    chunk.start_seconds,
                )
                deep_link = build_youtube_deep_link(chunk.youtube_url, chunk.video_id, secs)
                valid_citations.append(
                    Citation(
                        chunk_id=chunk.id,
                        episode_title=chunk.episode_title,
                        guest_name=chunk.guest_name,
                        timestamp=ts,
                        start_seconds=secs,
                        source_url=deep_link or chunk.youtube_deep_link or chunk.youtube_url,
                        snippet=snippet,
                    )
                )
            else:
                invalid_ids.append(match_id)

        # If the model answered without valid citations (or garbled the ID), fall back to textual overlap --
        # but only when the overlap is substantial; otherwise the answer is not demonstrably grounded.
        if not valid_citations and retrieved_chunks:
            answer_words = set(re.findall(r"[a-zA-Z]{4,}", model_response.lower()))
            best_chunk = retrieved_chunks[0]
            best_overlap = -1
            for ch in retrieved_chunks:
                chunk_words = set(re.findall(r"[a-zA-Z]{4,}", ch.content.lower()))
                overlap = len(answer_words.intersection(chunk_words))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_chunk = ch

            if not allow_inferred or best_overlap < min_inferred_overlap:
                logger.warning("abstention_ungrounded_answer", extra={"best_overlap": best_overlap, "needed": min_inferred_overlap,
                                                                     "response_head": model_response[:300]})
                return ValidationResult(
                    is_abstention=True,
                    valid_citations=[],
                    invalid_chunk_ids=invalid_ids,
                    cleaned_answer=ABSTENTION_MESSAGE,
                )

            ts, secs, snippet = resolve_turn_timestamp(
                best_chunk.content,
                model_response,
                best_chunk.start_timestamp,
                best_chunk.start_seconds,
            )
            deep_link = build_youtube_deep_link(best_chunk.youtube_url, best_chunk.video_id, secs)
            valid_citations.append(
                Citation(
                    chunk_id=best_chunk.id,
                    episode_title=best_chunk.episode_title,
                    guest_name=best_chunk.guest_name,
                    timestamp=ts,
                    start_seconds=secs,
                    source_url=deep_link or best_chunk.youtube_deep_link or best_chunk.youtube_url,
                    snippet=snippet,
                )
            )

        # Format cleaned answer (optionally strip broken fabricated citations)
        cleaned_text = model_response.strip()
        for bad_id in invalid_ids:
            cleaned_text = re.sub(rf"\[(?:citation:\s*)?{re.escape(bad_id)}\]", "", cleaned_text)

        # Enforce quotation integrity: strip quotes from non-verbatim paraphrases
        cleaned_text = sanitize_unquoted_paraphrases(cleaned_text, retrieved_chunks)

        return ValidationResult(
            is_abstention=False,
            valid_citations=valid_citations,
            invalid_chunk_ids=invalid_ids,
            cleaned_answer=cleaned_text.strip(),
        )


def sanitize_unquoted_paraphrases(text: str, retrieved_chunks: List[RetrievedChunk]) -> str:
    """
    Ensures that paraphrases are not formatted as direct quotations.
    If text inside quotation marks does not appear verbatim in any chunk,
    the quotation marks are removed so synthesized wording is not falsely attributed as verbatim.
    """
    if not text or not retrieved_chunks:
        return text

    combined_corpus = " ".join(c.content for c in retrieved_chunks).lower()

    def _check_double_quote(match):
        quoted_text = match.group(1).strip()
        if len(quoted_text.split()) < 3:
            return match.group(0)
        norm_quoted = " ".join(re.sub(r"[^\w\s]", "", quoted_text.lower()).split())
        norm_corpus = " ".join(re.sub(r"[^\w\s]", "", combined_corpus).split())
        if norm_quoted in norm_corpus:
            return match.group(0)
        return quoted_text

    return re.sub(r'"([^"\n]+)"', _check_double_quote, text)
