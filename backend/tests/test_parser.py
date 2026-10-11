"""
Unit tests for Lenny's Podcast transcript parser.
Covers:
1. Parsing representative transcript formats (frontmatter + speaker timestamps).
2. Handling various timestamp formats (HH:MM:SS, MM:SS, H:MM:SS).
3. Continuation turns with timestamp only (inheriting active speaker).
4. Multi-paragraph turns.
5. Missing or incomplete metadata fields.
6. Malformed YAML frontmatter without throwing fatal exceptions.
7. YouTube URL parsing and video ID extraction.
"""

import pytest
from backend.ingestion.parser import (
    parse_transcript_markdown,
    parse_timestamp_to_seconds,
    extract_video_id,
)

SAMPLE_STANDARD_TRANSCRIPT = """---
guest: Elena Verna
title: 10 growth tactics that never work | Elena Verna
youtube_url: https://www.youtube.com/watch?v=IHwS2By9UKM
video_id: IHwS2By9UKM
publish_date: 2025-01-19
description: Elena Verna is a renowned growth advisor and operator.
---

# 10 growth tactics that never work

## Transcript

Elena Verna (00:00:00):
Growth is a fairly new field. Many people focus on growth hacks that do not work.

Lenny Rachitsky (00:00:21):
We are going to start with growth tactics that never work. What is number one?

Elena Verna (00:00:26):
Number one is hiring a growth team before you have product market fit.
You cannot outsource finding product market fit to a growth team.

(00:01:15):
And furthermore, redesigning your marketing website almost never improves conversion.
"""

SAMPLE_MM_SS_TRANSCRIPT = """---
guest: Shreyas Doshi
title: The Art of Product Management
youtube_url: https://youtu.be/abc123XYZ99
publish_date: 2024-06-10
---

Shreyas Doshi (05:12):
Most product managers spend too much time on low-leverage tasks.

Lenny Rachitsky (06:05):
How should they prioritize their high-leverage work?
"""

SAMPLE_MALFORMED_YAML = """---
guest: Broken YAML: [unclosed list
title: This YAML is broken: {invalid
youtube_url: https://www.youtube.com/watch?v=testVid1234
---

Guest Name (00:01:00):
Even though the frontmatter was malformed, the transcript body should still be parsed safely.
"""

SAMPLE_NO_FRONTMATTER = """
Guest Speaker (00:00:10):
This transcript has no frontmatter whatsoever.

Lenny Rachitsky (00:00:30):
It should use fallback metadata derived from slug.
"""


def test_parse_timestamp_to_seconds():
    """Verify timestamp conversion for various valid time combinations."""
    assert parse_timestamp_to_seconds("01", "30", "15") == 5415
    assert parse_timestamp_to_seconds(None, "05", "30") == 330
    assert parse_timestamp_to_seconds("00", "00", "00") == 0
    assert parse_timestamp_to_seconds(None, "00", "45") == 45
    assert parse_timestamp_to_seconds("2", "00", "00") == 7200


def test_extract_video_id():
    """Verify video ID extraction from diverse YouTube URL formats."""
    assert extract_video_id("https://www.youtube.com/watch?v=IHwS2By9UKM") == "IHwS2By9UKM"
    assert extract_video_id("https://www.youtube.com/watch?v=IHwS2By9UKM&t=120s") == "IHwS2By9UKM"
    assert extract_video_id("https://youtu.be/IHwS2By9UKM") == "IHwS2By9UKM"
    assert extract_video_id("https://youtu.be/IHwS2By9UKM?si=abcdef") == "IHwS2By9UKM"
    assert extract_video_id(None) is None
    assert extract_video_id("") is None
    assert extract_video_id("not-a-youtube-url") is None


def test_parse_standard_transcript():
    """Verify parsing a standard episode with full frontmatter and turns."""
    meta, turns = parse_transcript_markdown(SAMPLE_STANDARD_TRANSCRIPT, fallback_slug="elena-verna")

    assert meta["guest"] == "Elena Verna"
    assert meta["title"] == "10 growth tactics that never work | Elena Verna"
    assert meta["youtube_url"] == "https://www.youtube.com/watch?v=IHwS2By9UKM"
    assert meta["video_id"] == "IHwS2By9UKM"
    assert meta["publish_date"] == "2025-01-19"
    assert "Elena Verna is a renowned" in meta["description"]

    assert len(turns) == 4
    assert turns[0]["speaker"] == "Elena Verna"
    assert turns[0]["seconds"] == 0
    assert turns[0]["timestamp"] == "00:00:00"
    assert "Growth is a fairly new field" in turns[0]["text"]

    assert turns[1]["speaker"] == "Lenny Rachitsky"
    assert turns[1]["seconds"] == 21
    assert turns[1]["timestamp"] == "00:00:21"

    assert turns[2]["speaker"] == "Elena Verna"
    assert turns[2]["seconds"] == 26
    assert "product market fit" in turns[2]["text"]

    # Continuation turn without explicit speaker inherits previous speaker (Elena Verna)
    assert turns[3]["speaker"] == "Elena Verna"
    assert turns[3]["seconds"] == 75  # 1 min 15 sec = 75 sec
    assert turns[3]["timestamp"] == "00:01:15"
    assert "redesigning your marketing website" in turns[3]["text"]


def test_parse_mm_ss_format():
    """Verify transcripts that omit hours in timestamps (MM:SS)."""
    meta, turns = parse_transcript_markdown(SAMPLE_MM_SS_TRANSCRIPT, fallback_slug="shreyas-doshi")

    assert meta["guest"] == "Shreyas Doshi"
    assert meta["video_id"] == "abc123XYZ99"
    assert len(turns) == 2

    assert turns[0]["speaker"] == "Shreyas Doshi"
    assert turns[0]["seconds"] == 312  # 5 * 60 + 12 = 312
    assert turns[0]["timestamp"] == "00:05:12"

    assert turns[1]["speaker"] == "Lenny Rachitsky"
    assert turns[1]["seconds"] == 365  # 6 * 60 + 5 = 365
    assert turns[1]["timestamp"] == "00:06:05"


def test_parse_malformed_yaml():
    """Verify graceful handling when frontmatter is corrupt YAML."""
    meta, turns = parse_transcript_markdown(SAMPLE_MALFORMED_YAML, fallback_slug="corrupted-ep")

    # Should fall back gracefully without raising an exception
    assert meta["guest"] == "Lenny's Guest"
    assert meta["title"] == "Corrupted Ep"
    assert len(turns) == 1
    assert turns[0]["speaker"] == "Guest Name"
    assert turns[0]["seconds"] == 60


def test_parse_no_frontmatter():
    """Verify handling when markdown has no YAML frontmatter delimiters."""
    meta, turns = parse_transcript_markdown(SAMPLE_NO_FRONTMATTER, fallback_slug="brian-chesky")

    assert meta["guest"] == "Lenny's Guest"
    assert meta["title"] == "Brian Chesky"
    assert len(turns) == 2
    assert turns[0]["speaker"] == "Guest Speaker"
    assert turns[0]["seconds"] == 10
    assert turns[1]["speaker"] == "Lenny Rachitsky"
    assert turns[1]["seconds"] == 30


def test_parse_empty_content():
    """Verify handling when content is completely empty."""
    meta, turns = parse_transcript_markdown("", fallback_slug="empty-ep")
    assert meta["title"] == "Empty Ep"
    assert len(turns) == 0
