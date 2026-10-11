"""
Parser for Lenny's Podcast transcripts.
Extracts YAML frontmatter and dialogue turns with timestamps and speaker attribution.
Handles missing, unexpected, or malformed metadata gracefully without throwing fatal exceptions.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
import yaml


# Regex patterns for dialogue lines with timestamps:
# Pattern 1: "Speaker Name (HH:MM:SS): text" or "Speaker Name (MM:SS): text"
SPEAKER_TIMESTAMP_PATTERN = re.compile(
    r"^([A-Za-z0-9\s\.\'\-–—]+?)\s*\((?:(\d{1,2}):)?(\d{1,2}):(\d{2})\)\s*:\s*(.*)$"
)

# Pattern 2: Continuation timestamp without speaker: "(HH:MM:SS): text" or "(MM:SS): text"
TIMESTAMP_ONLY_PATTERN = re.compile(
    r"^\((?:(\d{1,2}):)?(\d{1,2}):(\d{2})\)\s*:\s*(.*)$"
)

# Pattern 3: Extract YouTube video ID from URL
YOUTUBE_ID_PATTERN = re.compile(r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:[&?]|\b)")


def parse_timestamp_to_seconds(hours_str: Optional[str], minutes_str: str, seconds_str: str) -> int:
    """Converts (HH, MM, SS) or (None, MM, SS) strings to total integer seconds."""
    hours = int(hours_str) if hours_str is not None else 0
    minutes = int(minutes_str) if minutes_str is not None else 0
    seconds = int(seconds_str) if seconds_str is not None else 0
    return hours * 3600 + minutes * 60 + seconds


def extract_video_id(youtube_url: Optional[str]) -> Optional[str]:
    """Extracts 11-character YouTube video ID from a YouTube watch or short URL."""
    if not youtube_url:
        return None
    match = YOUTUBE_ID_PATTERN.search(youtube_url)
    return match.group(1) if match else None


def parse_transcript_markdown(content: str, fallback_slug: str = "unknown-episode") -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Parses a transcript Markdown document.
    Returns:
        (metadata_dict, dialogue_turns_list)
    """
    metadata: Dict[str, Any] = {
        "guest": "Lenny's Guest",
        "title": fallback_slug.replace("-", " ").title(),
        "youtube_url": None,
        "video_id": None,
        "publish_date": None,
        "description": None,
    }

    body = content

    # Check for YAML frontmatter between --- markers
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_frontmatter = parts[1].strip()
            body = parts[2].strip()
            try:
                parsed_yaml = yaml.safe_load(raw_frontmatter)
                if isinstance(parsed_yaml, dict):
                    if parsed_yaml.get("guest"):
                        metadata["guest"] = str(parsed_yaml["guest"]).strip()
                    if parsed_yaml.get("title"):
                        metadata["title"] = str(parsed_yaml["title"]).strip()
                    if parsed_yaml.get("youtube_url"):
                        metadata["youtube_url"] = str(parsed_yaml["youtube_url"]).strip()
                    if parsed_yaml.get("video_id"):
                        metadata["video_id"] = str(parsed_yaml["video_id"]).strip()
                    elif metadata["youtube_url"]:
                        metadata["video_id"] = extract_video_id(metadata["youtube_url"])
                    if parsed_yaml.get("publish_date"):
                        metadata["publish_date"] = str(parsed_yaml["publish_date"]).strip()
                    if parsed_yaml.get("description"):
                        metadata["description"] = str(parsed_yaml["description"]).strip()
            except Exception:
                # Malformed frontmatter: keep default fallback metadata
                pass

    # Ensure video_id is populated if youtube_url was extracted
    if not metadata.get("video_id") and metadata.get("youtube_url"):
        metadata["video_id"] = extract_video_id(metadata["youtube_url"])

    # Parse dialogue turns
    dialogue_turns: List[Dict[str, Any]] = []
    current_speaker = metadata["guest"]
    current_seconds = 0
    current_timestamp_str = "00:00:00"

    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            i += 1
            continue

        # Check speaker + timestamp pattern
        match_speaker = SPEAKER_TIMESTAMP_PATTERN.match(line)
        if match_speaker:
            speaker_name, h_str, m_str, s_str, text_rem = match_speaker.groups()
            current_speaker = speaker_name.strip()
            current_seconds = parse_timestamp_to_seconds(h_str, m_str, s_str)
            h_val = int(h_str) if h_str else 0
            current_timestamp_str = f"{h_val:02d}:{int(m_str):02d}:{int(s_str):02d}"

            # Accumulate subsequent lines for this turn
            text_lines = [text_rem.strip()] if text_rem.strip() else []
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if not next_line:
                    i += 1
                    continue
                if SPEAKER_TIMESTAMP_PATTERN.match(next_line) or TIMESTAMP_ONLY_PATTERN.match(next_line):
                    break
                text_lines.append(next_line)
                i += 1

            turn_content = " ".join(text_lines).strip()
            if turn_content:
                dialogue_turns.append({
                    "speaker": current_speaker,
                    "seconds": current_seconds,
                    "timestamp": current_timestamp_str,
                    "text": turn_content,
                })
            continue

        # Check timestamp-only pattern
        match_ts = TIMESTAMP_ONLY_PATTERN.match(line)
        if match_ts:
            h_str, m_str, s_str, text_rem = match_ts.groups()
            current_seconds = parse_timestamp_to_seconds(h_str, m_str, s_str)
            h_val = int(h_str) if h_str else 0
            current_timestamp_str = f"{h_val:02d}:{int(m_str):02d}:{int(s_str):02d}"

            text_lines = [text_rem.strip()] if text_rem.strip() else []
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if not next_line:
                    i += 1
                    continue
                if SPEAKER_TIMESTAMP_PATTERN.match(next_line) or TIMESTAMP_ONLY_PATTERN.match(next_line):
                    break
                text_lines.append(next_line)
                i += 1

            turn_content = " ".join(text_lines).strip()
            if turn_content:
                dialogue_turns.append({
                    "speaker": current_speaker,
                    "seconds": current_seconds,
                    "timestamp": current_timestamp_str,
                    "text": turn_content,
                })
            continue

        # Fallback paragraph without timestamp
        text_lines = [line]
        i += 1
        while i < len(lines):
            next_line = lines[i].strip()
            if not next_line:
                i += 1
                continue
            if SPEAKER_TIMESTAMP_PATTERN.match(next_line) or TIMESTAMP_ONLY_PATTERN.match(next_line):
                break
            text_lines.append(next_line)
            i += 1

        turn_content = " ".join(text_lines).strip()
        if turn_content:
            dialogue_turns.append({
                "speaker": current_speaker,
                "seconds": current_seconds,
                "timestamp": current_timestamp_str,
                "text": turn_content,
            })

    return metadata, dialogue_turns
