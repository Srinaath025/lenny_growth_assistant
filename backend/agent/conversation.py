"""
Conversation memory helpers (assignment 4.1: follow-ups + independent per-session context).

Each chat request loads ONLY the messages of its own session from PostgreSQL, so sessions can
never leak context into each other. The recent turns are injected into the prompt as
*context for resolving references* ("that", "it", "tell me more") -- they are explicitly NOT
evidence and may never be cited. Retrieval for short/ambiguous follow-ups is augmented with
the previous user question so "Can you give an example?" still finds the right transcripts.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Sequence

from backend.retrieval.retriever import significant_terms

_ANAPHORA = re.compile(
    r"\b(that|this|it|they|them|those|these|he|she|his|her|their|more|elaborate|expand|example|"
    r"examples|why|how so|what about|and then|go deeper|summari[sz]e|above|earlier|previous)\b",
    re.IGNORECASE,
)

MAX_TURN_CHARS = 700


@dataclass
class ChatTurn:
    role: str
    content: str


def trim_history(turns: Iterable[Dict[str, str] | ChatTurn], max_turns: int, char_budget: int) -> List[ChatTurn]:
    """Keep the most recent `max_turns` user/assistant turns within `char_budget` characters."""
    cleaned: List[ChatTurn] = []
    for t in turns:
        role = t.role if isinstance(t, ChatTurn) else t.get("role", "")
        content = t.content if isinstance(t, ChatTurn) else t.get("content", "")
        if role not in ("user", "assistant") or not (content or "").strip():
            continue
        text = " ".join(content.split())
        if len(text) > MAX_TURN_CHARS:
            text = text[:MAX_TURN_CHARS].rstrip() + " …"
        cleaned.append(ChatTurn(role=role, content=text))

    cleaned = cleaned[-max_turns:] if max_turns > 0 else []
    kept: List[ChatTurn] = []
    used = 0
    for turn in reversed(cleaned):  # newest first so recent context wins the budget
        if used + len(turn.content) > char_budget and kept:
            break
        kept.append(turn)
        used += len(turn.content)
    return list(reversed(kept))


def format_history(turns: Sequence[ChatTurn]) -> str:
    if not turns:
        return ""
    lines = []
    for t in turns:
        who = "User" if t.role == "user" else "Assistant"
        lines.append(f"{who}: {t.content}")
    return "\n".join(lines)


def needs_context(message: str) -> bool:
    """True when the message is too short or too pronoun-heavy to retrieve on its own."""
    if len(significant_terms(message)) <= 2:
        return True
    return bool(_ANAPHORA.search(message)) and len(significant_terms(message)) <= 4


def build_retrieval_query(message: str, history: Sequence[ChatTurn]) -> str:
    """Augment ambiguous follow-ups with the previous user question; leave standalone ones alone."""
    if not history or not needs_context(message):
        return message
    prior_user = next((t.content for t in reversed(history) if t.role == "user"), "")
    return f"{prior_user} {message}".strip() if prior_user else message
