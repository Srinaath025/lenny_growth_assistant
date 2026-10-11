"""
Unit tests for Milestone 5: Ship 30 for 30 Essay Generation Engine.
Verifies:
1. 4A Framework structure validation (Actionable, Analytical, Aspirational, Anthropological).
2. The "2-Year Test" and word count boundaries (1,100 to 1,400 words).
3. Skimmable layout formatting and HTML artifact generation with CSP headers.
4. Database persistence into the PostgreSQL artifacts table.
"""

from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import select

from backend.db.connection import AsyncSessionLocal
from backend.db.models import Artifact
from backend.retrieval.retriever import RetrievedChunk
from backend.agent.essay_skill import (
    Ship30EssayEngine,
    GeneratedEssay,
    count_words,
    validate_essay_structure,
    build_ship30_essay_prompt,
    generate_html_artifact,
    MIN_ESSAY_WORDS,
    MAX_ESSAY_WORDS,
    TARGET_ESSAY_WORDS,
)


def make_dummy_essay_text(word_count: int, include_all_sections: bool = True) -> str:
    """Generates synthetic markdown matching the 4A framework structure with target word count."""
    hook = (
        "# Why Most Founders Hire Growth Teams 2 Years Too Early\n\n"
        "## The 2-Year Test Playbook\n\n"
        "Two years ago, I believed that hiring a growth lead would magically fix product distribution. "
        "It was the most expensive misconception of my career. "
        "If you are an early-stage operator wondering why your growth experiments keep stalling, this is for you.\n\n"
    )

    actionable_header = "# 1. Actionable: The Step-by-Step Playbook\n\n"
    actionable_body = (
        "First, stop hiring external growth agencies before you have product-market fit. "
        "Founder-led growth must precede specialized hiring. "
        "Here are three non-negotiable execution steps:\n\n"
        "1. Map your customer activation funnel manually.\n"
        "2. Identify your primary aha-moment within the first 48 hours.\n"
        "3. Automate self-serve onboarding before introducing enterprise sales reps.\n\n"
    )

    analytical_header = "# 2. Analytical: Metrics, Benchmarks & Hard Data\n\n"
    analytical_body = (
        "Let us examine the concrete numbers that separate scalable growth from noise. "
        "A healthy product-led business demonstrates a 30-day retention curve flattening above 40 percent. "
        "Furthermore, your natural pull from word-of-mouth should account for at least 50 percent of top-of-funnel acquisition. "
        "If your net revenue retention is below 110 percent, adding more headcount to growth merely accelerates churn.\n\n"
    )

    aspirational_header = "# 3. Aspirational: Mindset Shift & Product Philosophy\n\n"
    aspirational_body = (
        "High-agency leaders treat growth not as an isolated marketing department, but as a company-wide cultural ethos. "
        "When every engineer, designer, and support representative takes ownership of user value, compounding kicks in. "
        "True growth is the byproduct of relentless craft and customer obsession.\n\n"
    )

    anthropological_header = "# 4. Anthropological: Human Friction & Organizational Behavior\n\n"
    anthropological_body = (
        "Why do teams resist this obvious playbook? "
        "Human psychology defaults to hiring as a status symbol rather than a capability builder. "
        "Founders want to delegate the messy, uncomfortable work of customer discovery. "
        "Overcoming this organizational inertia requires creating psychological safety for honest failure.\n\n"
    )

    if not include_all_sections:
        anthropological_header = ""
        anthropological_body = ""

    base_text = (
        hook
        + actionable_header + actionable_body
        + analytical_header + analytical_body
        + aspirational_header + aspirational_body
        + anthropological_header + anthropological_body
    )

    current_words = count_words(base_text)
    if current_words >= word_count:
        return base_text

    # Pad with substantive sentences to hit exact target word count
    padding_sentence = "Compounding product value requires disciplined experimentation and deep user empathy. "
    pad_words = len(padding_sentence.split())
    needed = (word_count - current_words) // pad_words + 1
    padded_actionable = actionable_body + (padding_sentence * needed)

    full_text = (
        hook
        + actionable_header + padded_actionable
        + analytical_header + analytical_body
        + aspirational_header + aspirational_body
        + anthropological_header + anthropological_body
    )
    return full_text


def test_count_words():
    """Verify word counter accurately counts words and strips markdown punctuation."""
    text = "# Header 1\n\nThis is a **test** of the [link](http://example.com) counter."
    assert count_words(text) == 11
    assert count_words("") == 0
    assert count_words("   \n\n  ") == 0


def test_validate_essay_structure_detects_all_4a_sections():
    """Verify validation passes when all four 4A sections are present."""
    text = make_dummy_essay_text(1250, include_all_sections=True)
    has_all, section_map, words = validate_essay_structure(text)

    assert has_all is True
    assert section_map["actionable"] is True
    assert section_map["analytical"] is True
    assert section_map["aspirational"] is True
    assert section_map["anthropological"] is True
    assert words >= 1100


def test_validate_essay_structure_fails_when_section_missing():
    """Verify validation detects missing 4A sections."""
    text = make_dummy_essay_text(800, include_all_sections=False)
    has_all, section_map, _ = validate_essay_structure(text)

    assert has_all is False
    assert section_map["actionable"] is True
    assert section_map["analytical"] is True
    assert section_map["aspirational"] is True
    assert section_map["anthropological"] is False


def test_word_count_boundaries():
    """Verify the 1,100 to 1,400 word count guardrails."""
    assert MIN_ESSAY_WORDS == 1100
    assert MAX_ESSAY_WORDS == 1400
    assert TARGET_ESSAY_WORDS == 1250

    # Below boundary
    short_text = make_dummy_essay_text(1050)
    _, _, words_short = validate_essay_structure(short_text)
    # Target within boundary
    target_text = make_dummy_essay_text(1250)
    _, _, words_target = validate_essay_structure(target_text)
    assert MIN_ESSAY_WORDS <= words_target <= MAX_ESSAY_WORDS


def test_build_ship30_essay_prompt():
    """Verify prompt builder includes 4A instructions, 2-Year Test, and evidence delimiters."""
    chunk = RetrievedChunk(
        id="chunk_test_12345",
        episode_slug="elena-verna",
        episode_title="10 Growth Tactics",
        guest_name="Elena Verna",
        youtube_url="https://youtube.com/watch?v=123",
        youtube_deep_link="https://youtube.com/watch?v=123&t=0s",
        video_id="123",
        publish_date="2024-01-01",
        chunk_index=0,
        speaker="Elena Verna",
        start_timestamp="00:00:00",
        start_seconds=0,
        end_timestamp="00:02:00",
        end_seconds=120,
        word_count=50,
        content="Elena Verna: Growth teams before PMF never work.",
        rank=0.05,
    )

    prompt = build_ship30_essay_prompt(
        topic="Product-Led Sales",
        retrieved_chunks=[chunk],
        guest_name="Elena Verna",
    )

    assert "<<<UNTRUSTED_EVIDENCE_START>>>" in prompt
    assert "<<<UNTRUSTED_EVIDENCE_END>>>" in prompt
    assert "Two-Year Test" in prompt  # encoded via backend/skills/ship30/SKILL.md
    assert "4A Framework" in prompt
    for section in ("Actionable", "Analytical", "Aspirational", "Anthropological"):
        assert section in prompt
    assert "1,100 and 1,400 words" in prompt
    assert "chunk_test_12345" in prompt


def test_generate_html_artifact_renders_csp_and_obsidian_theme():
    """Verify HTML artifact includes strict CSP, responsive structure, and obsidian styles."""
    html_out = generate_html_artifact(
        title="Scaling Self-Serve",
        subtitle="A Playbook for Operators",
        markdown_content="# 1. Actionable\n\nDo not hire sales too early.\n\n> Bold takeaway",
        guest_attributions=["Elena Verna"],
        word_count=1250,
    )

    # Security check: CSP header exists and forbids unsafe origins
    assert "Content-Security-Policy" in html_out
    assert "default-src 'none'" in html_out
    assert "style-src 'unsafe-inline'" in html_out
    assert "fonts.googleapis.com" not in html_out  # no third-party requests: viewer CSP forbids them
    # Theme checks
    assert "#0b0f19" in html_out  # Dark background
    assert "Ship 30 for 30" in html_out
    assert "Elena Verna" in html_out
    assert "Scaling Self-Serve" in html_out
    assert "essay-takeaway" in html_out


@pytest.mark.asyncio
async def test_essay_engine_generate_and_database_persistence():
    """Verify Ship30EssayEngine generates essay, extracts metadata, and stores into artifacts table."""
    mock_pi = AsyncMock()
    simulated_essay_text = make_dummy_essay_text(1220, include_all_sections=True)
    mock_pi.run_prompt = AsyncMock(return_value=simulated_essay_text)

    engine = Ship30EssayEngine(retriever_limit=3, pi_client=mock_pi)

    essay = await engine.generate_essay(
        topic="Hiring a Growth Team",
        guest_filter="Elena Verna",
    )

    # Verification of returned GeneratedEssay
    assert essay.title != ""
    assert essay.has_all_4a_sections is True
    assert essay.is_valid_word_count is True
    assert 1100 <= essay.word_count <= 1400
    assert "Content-Security-Policy" in essay.html_content
    assert essay.artifact_id is not None
    assert essay.artifact_id.startswith("art-")

    # Verify database persistence into 'artifacts' table
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Artifact).where(Artifact.id == essay.artifact_id)
        )
        saved_art = result.scalar_one_or_none()

        assert saved_art is not None
        assert saved_art.title == essay.title
        assert saved_art.artifact_type == "html"
        assert saved_art.word_count == essay.word_count
        assert len(saved_art.content) > 500

        # Clean up test artifact
        await session.delete(saved_art)
        await session.commit()
