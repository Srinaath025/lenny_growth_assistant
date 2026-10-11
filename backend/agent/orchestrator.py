"""
Orchestration layer for the Lenny Growth Assistant.
Coordinates:
1. Full-text search retrieval from PostgreSQL.
2. Injection-defended prompt construction.
3. Invocation of genuine Pi Coding Agent RPC subprocess.
4. Citation validation and strict evidence-based abstention enforcement.
"""

import asyncio
from dataclasses import dataclass
import logging
import time
from typing import Dict, Any, List, Optional, Callable

from backend.config import get_settings
from backend.agent.conversation import ChatTurn, build_retrieval_query
from backend.retrieval.retriever import (
    RetrievedChunk,
    retrieve_relevant_chunks,
)
from backend.agent.prompt import (
    build_grounded_prompt,
    ABSTENTION_MESSAGE,
)
from backend.agent.citation_validator import (
    Citation,
    CitationValidator,
    ValidationResult,
)
from backend.agent.pi_client import PiAgentClient, PiAgentConfig, PiRPCError
from backend.agent.cloud_client import (
    AnthropicClaudeClient,
    AnthropicClaudeConfig,
    CloudProviderError,
)

logger = logging.getLogger("agent.orchestrator")


@dataclass
class GroundedAnswer:
    """Complete answer package returned to callers."""
    query: str
    answer: str
    is_abstention: bool
    retrieved_chunks: List[RetrievedChunk]
    citations: List[Citation]
    raw_model_response: str
    invalid_citations: List[str]
    duration_seconds: float
    error: Optional[str] = None  # set when the LLM call failed (NOT an abstention)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "is_abstention": self.is_abstention,
            "duration_seconds": round(self.duration_seconds, 2),
            "retrieved_chunks_count": len(self.retrieved_chunks),
            "citations": [c.to_dict() for c in self.citations],
            "invalid_citations": self.invalid_citations,
            "raw_model_response": self.raw_model_response,
            "error": self.error,
        }


class GrowthAssistantAgent:
    """
    Main agent interface for answering growth questions grounded in Lenny's Podcast transcripts.
    Supports both Local Ollama (via genuine Pi Coding Agent RPC) and Cloud Claude.
    """

    def __init__(
        self,
        retriever_limit: Optional[int] = None,
        model_provider: str = "ollama",
        pi_client: Optional[PiAgentClient] = None,
        pi_config: Optional[PiAgentConfig] = None,
        cloud_client: Optional[AnthropicClaudeClient] = None,
        cloud_config: Optional[AnthropicClaudeConfig] = None,
        llm_client: Optional[Any] = None,
    ):
        self.retriever_limit = retriever_limit or get_settings().retriever_limit
        self.model_provider = model_provider.lower().strip()
        if llm_client:
            self.llm_client = llm_client
        elif self.model_provider in ("anthropic", "claude"):
            self.llm_client = cloud_client or AnthropicClaudeClient(config=cloud_config)
        elif self.model_provider in ("gemini", "google"):
            from backend.agent.cloud_client import GoogleGeminiClient
            self.llm_client = cloud_client or GoogleGeminiClient()
        else:
            self.llm_client = pi_client or PiAgentClient(config=pi_config)
        self.pi_client = self.llm_client  # backwards compatibility

    async def ask(
        self,
        query: str,
        session=None,
        on_delta: Optional[Callable[[str], Any]] = None,
        history: Optional[List[ChatTurn]] = None,
    ) -> GroundedAnswer:
        """
        Processes a user question end-to-end:
        1. Retrieves relevant passages from PostgreSQL.
        2. Enforces immediate abstention if no relevant evidence is found.
        3. Prompts the selected LLM (Ollama or Cloud Claude) with bounded, untrusted evidence.
        4. Validates all citations against the retrieved set.
        """
        start_time = time.time()
        logger.info("chat_query", extra={"query": query[:160], "provider": self.model_provider, "history_turns": len(history or [])})

        # Step 1: Retrieval
        history = history or []
        retrieval_query = build_retrieval_query(query, history)
        raw_chunks = await retrieve_relevant_chunks(
            query=retrieval_query,
            limit=self.retriever_limit * 3,
            session=session,
        )

        # Deduplicate identical chunks / duplicate mirror episodes while allowing
        # up to 3 relevant chunks per episode so comprehensive discussions are preserved
        seen_chunk_ids = set()
        seen_texts = set()
        episode_counts: Dict[str, int] = {}
        chunks: List[RetrievedChunk] = []
        for c in raw_chunks:
            text_snippet = c.content[:100].strip()
            if c.id in seen_chunk_ids or text_snippet in seen_texts:
                continue
            seen_chunk_ids.add(c.id)
            seen_texts.add(text_snippet)

            ep_key = c.video_id or c.episode_slug or "default"
            max_per_ep = max(self.retriever_limit, 6)
            if episode_counts.get(ep_key, 0) >= max_per_ep:
                continue
            episode_counts[ep_key] = episode_counts.get(ep_key, 0) + 1
            chunks.append(c)
            if len(chunks) >= self.retriever_limit:
                break

        # Step 2: Immediate abstention if no supporting chunks exist
        if not chunks:
            logger.info("No supporting chunks retrieved. Returning immediate abstention.")
            return GroundedAnswer(
                query=query,
                answer=ABSTENTION_MESSAGE,
                is_abstention=True,
                retrieved_chunks=[],
                citations=[],
                raw_model_response="",
                invalid_citations=[],
                duration_seconds=round(time.time() - start_time, 2),
            )

        # Step 3: Build grounded prompt
        prompt = build_grounded_prompt(query=query, retrieved_chunks=chunks, history=history)

        # Step 4: Execute through active LLM client (Ollama via Pi RPC, or Cloud Claude)
        try:
            raw_response = await self.llm_client.run_prompt(prompt, on_delta=on_delta)
        except Exception as llm_err:
            logger.error(f"LLM execution failure ({self.model_provider}): {llm_err}", exc_info=True)
            err_msg = str(llm_err).strip() or f"{type(llm_err).__name__}: Local model execution interrupted or unavailable"
            err_target = "local agent" if (isinstance(llm_err, PiRPCError) or self.model_provider == "ollama") else f"{self.model_provider} model"
            return GroundedAnswer(
                query=query,
                answer=f"Error communicating with {err_target}: {err_msg}",
                is_abstention=False,
                retrieved_chunks=chunks,
                citations=[],
                raw_model_response=err_msg,
                invalid_citations=[],
                duration_seconds=round(time.time() - start_time, 2),
                error=err_msg,
            )

        # Step 5: Citation validation & Abstention verification
        val_result: ValidationResult = CitationValidator.validate(
            model_response=raw_response,
            retrieved_chunks=chunks,
        )

        duration = round(time.time() - start_time, 2)
        logger.info(
            f"Answer generated in {duration}s: abstention={val_result.is_abstention}, "
            f"citations={len(val_result.valid_citations)}, invalid_citations={len(val_result.invalid_chunk_ids)}"
        )

        return GroundedAnswer(
            query=query,
            answer=val_result.cleaned_answer,
            is_abstention=val_result.is_abstention,
            retrieved_chunks=chunks,
            citations=val_result.valid_citations,
            raw_model_response=raw_response,
            invalid_citations=val_result.invalid_chunk_ids,
            duration_seconds=duration,
        )
