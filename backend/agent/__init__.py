"""
Agent package for Lenny Growth Assistant.
Contains Pi Coding Agent RPC client, prompt engineering, citation validation,
and evidence-based retrieval-grounded orchestration.
"""

from backend.agent.pi_client import PiAgentClient, PiAgentConfig
from backend.agent.citation_validator import Citation, CitationValidator
from backend.agent.prompt import build_grounded_prompt, ABSTENTION_MESSAGE
from backend.agent.orchestrator import GroundedAnswer, GrowthAssistantAgent
from backend.agent.essay_skill import (
    Ship30EssayEngine,
    GeneratedEssay,
    count_words,
    validate_essay_structure,
)

from backend.agent.cloud_client import (
    AnthropicClaudeClient,
    AnthropicClaudeConfig,
    CloudProviderError,
)

__all__ = [
    "PiAgentClient",
    "PiAgentConfig",
    "AnthropicClaudeClient",
    "AnthropicClaudeConfig",
    "CloudProviderError",
    "Citation",
    "CitationValidator",
    "build_grounded_prompt",
    "ABSTENTION_MESSAGE",
    "GroundedAnswer",
    "GrowthAssistantAgent",
    "Ship30EssayEngine",
    "GeneratedEssay",
    "count_words",
    "validate_essay_structure",
]
