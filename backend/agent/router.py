"""
Deterministic intent router (the "agent routing" layer).

Small local models (llama3.2:3b) are unreliable at tool-selection, so routing is done with
explicit, unit-tested rules BEFORE any LLM call. Skills:

  chat              -> grounded Q&A over the transcripts (retrieval + citations + abstention)
  essay             -> Ship 30 for 30 essay skill (4A framework, ~1,250 words)
  artifact_markdown -> Markdown document generated from the conversation / transcripts
  artifact_html     -> complete HTML/CSS snippet generated from the conversation / transcripts

A message is only routed to a generation skill when it is a *request* (imperative or
"can you ..."), so questions ABOUT essays or HTML ("how do I write a good essay?") stay in chat.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Sequence

from backend.agent.conversation import ChatTurn

CHAT = "chat"
ESSAY = "essay"
ARTIFACT_MARKDOWN = "artifact_markdown"
ARTIFACT_HTML = "artifact_html"

_VERBS = (
    r"(?:create|make|build|write|draft|generate|design|turn|convert|produce|give\s+me|put|prepare|compose|"
    r"render|show\s+me|craft|summari[sz]e)"
)
_REQUEST = re.compile(
    rf"^\s*(?:please\s+)?(?:{_VERBS}\b|(?:can|could|would|will)\s+you\s+(?:please\s+)?{_VERBS}\b|"
    rf"i\s+(?:want|need|would\s+like)\s+(?:you\s+to\s+)?(?:a|an|the|some|to)?\s*{_VERBS}?)",
    re.IGNORECASE,
)
_REQUEST_ANYWHERE = re.compile(rf"\b(?:can|could|would|will)\s+you\s+(?:please\s+)?{_VERBS}\b", re.IGNORECASE)

_ESSAY = re.compile(r"\b(ship\s*-?\s*30(?:\s+for\s+30)?|atomic\s+essay|essay)\b", re.IGNORECASE)
_HTML_EXPLICIT = re.compile(r"\b(html|css|web\s*page|landing\s+page|webpage)\b", re.IGNORECASE)
_MD_EXPLICIT = re.compile(r"(\bmarkdown\b|\.md\b)", re.IGNORECASE)
_HTML_NOUNS = re.compile(
    r"\b(one[\s-]?pager|infographic|poster|dashboard|card|slide|slides|snippet|widget|banner|timeline|"
    r"comparison\s+table|visual)\b",
    re.IGNORECASE,
)
_MD_NOUNS = re.compile(
    r"\b(document|doc|brief|memo|cheat[\s-]?sheet|checklist|template|outline|notes|playbook|summary|"
    r"report|guide|plan|one[\s-]?pager)\b",
    re.IGNORECASE,
)

_TOPIC_PREFIX = re.compile(
    r"^.*?\b(?:ship\s*-?\s*30(?:\s+for\s+30)?(?:\s+style)?\s+(?:atomic\s+)?essay|(?:atomic\s+)?essay|"
    r"ship\s*-?\s*30(?:\s+for\s+30)?)\b\s*(?:on|about|covering|regarding|for|:)?\s*",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class Intent:
    kind: str
    topic: Optional[str] = None
    reason: str = ""


def _is_request(message: str) -> bool:
    return bool(_REQUEST.match(message) or _REQUEST_ANYWHERE.search(message))


def extract_essay_topic(message: str, history: Sequence[ChatTurn] = ()) -> str:
    """Pulls the essay topic out of the request; falls back to the previous user question."""
    cleaned = _TOPIC_PREFIX.sub("", message, count=1).strip(" .?!:-")
    cleaned = re.sub(r"^(?:based\s+on\s+)", "", cleaned, flags=re.IGNORECASE).strip()
    generic = {"", "this", "that", "it", "this conversation", "our conversation", "the above", "above"}
    if cleaned.lower() in generic:
        prior = next((t.content for t in reversed(history) if t.role == "user"), "")
        return prior or cleaned or message
    return cleaned


def route_intent(message: str, history: Sequence[ChatTurn] = ()) -> Intent:
    text = (message or "").strip()
    if not text:
        return Intent(CHAT, reason="empty")

    if not _is_request(text):
        return Intent(CHAT, reason="not_a_generation_request")

    if _ESSAY.search(text):
        return Intent(ESSAY, topic=extract_essay_topic(text, history), reason="essay_keyword")

    if _HTML_EXPLICIT.search(text):
        return Intent(ARTIFACT_HTML, reason="explicit_html")
    if _MD_EXPLICIT.search(text):
        return Intent(ARTIFACT_MARKDOWN, reason="explicit_markdown")
    if _HTML_NOUNS.search(text):
        return Intent(ARTIFACT_HTML, reason="html_noun")
    if _MD_NOUNS.search(text):
        return Intent(ARTIFACT_MARKDOWN, reason="markdown_noun")

    return Intent(CHAT, reason="no_artifact_keyword")
