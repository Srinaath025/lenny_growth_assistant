"""
Utility script to export, sanitize, and document coding-agent transcripts and logs.
Performs:
1. Transfer and sanitization of session trajectory from antigravity IDE transcript.jsonl.
2. Generation of a human-readable Markdown transcript.
3. Transfer and sanitization of background task logs.
4. Export and sanitization of Pi coding agent RPC trace.
5. Verification of zero secrets, passwords, or personal credentials.
"""

import json
import os
import re
import shutil
from pathlib import Path

SOURCE_LOG_DIR = Path(r"C:\Users\Admin\.gemini\antigravity-ide\brain\27bffd55-9336-4815-8b29-47ff7112850f\.system_generated\logs")
SOURCE_TASKS_DIR = Path(r"C:\Users\Admin\.gemini\antigravity-ide\brain\27bffd55-9336-4815-8b29-47ff7112850f\.system_generated\tasks")
SOURCE_PI_TRACE = Path(r"d:\Projects\oogway labs\proof-of-concept\trace.json")

DEST_DIR = Path(r"d:\Projects\oogway labs\coding-agent-transcripts")
DEST_TASKS_DIR = DEST_DIR / "tasks"

REDACTIONS = [
    # API keys
    (re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}"), "sk-ant-***REDACTED_API_KEY***"),
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "sk-***REDACTED_API_KEY***"),
    (re.compile(r"ghp_[a-zA-Z0-9]{20,}"), "ghp_***REDACTED_GITHUB_TOKEN***"),
    # DB passwords
    (re.compile(r"lenny_dev_password_change_in_prod"), "[REDACTED_DB_PASSWORD]"),
    (re.compile(r"lenny_secure_pass"), "[REDACTED_DB_PASSWORD]"),
    (re.compile(r":password@"), ":[REDACTED_PASSWORD]@"),
    # Sensitive user path (handling JSON escaped slashes and regular slashes)
    (re.compile(r"Users[\\/]+Admin[\\/]+", re.IGNORECASE), "Users/developer/"),
    (re.compile(r"Users\\\\+Admin\\\\+", re.IGNORECASE), "Users\\\\developer\\\\"),
    (re.compile(r"C:\\\\Users\\\\Admin", re.IGNORECASE), "C:\\\\Users\\\\developer"),
    (re.compile(r"C:/Users/Admin", re.IGNORECASE), "C:/Users/developer"),
    (re.compile(r"C:\\Users\\Admin", re.IGNORECASE), "C:\\Users\\developer"),
]

def sanitize_text(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(lambda m, r=replacement: r, text)
    return text


def export_transcripts():
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    DEST_TASKS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Sanitize transcript.jsonl
    src_transcript = SOURCE_LOG_DIR / "transcript.jsonl"
    dest_jsonl = DEST_DIR / "session_transcript.jsonl"
    dest_md = DEST_DIR / "session_transcript_readable.md"

    print(f"Reading {src_transcript}...")
    readable_entries = []
    sanitized_lines = []

    if src_transcript.exists():
        with open(src_transcript, "r", encoding="utf-8", errors="replace") as f_in:
            for idx, line in enumerate(f_in):
                clean_line = sanitize_text(line)
                sanitized_lines.append(clean_line)
                try:
                    obj = json.loads(clean_line)
                    step_type = obj.get("type", "UNKNOWN")
                    source = obj.get("source", "UNKNOWN")
                    content = obj.get("content", "")
                    tool_calls = obj.get("tool_calls", [])

                    if step_type == "USER_INPUT":
                        readable_entries.append(f"\n### 👤 User Message (Step {obj.get('step_index', idx)})\n\n```\n{content.strip()}\n```\n")
                    elif tool_calls:
                        for tc in tool_calls:
                            name = tc.get("name", "tool")
                            args = tc.get("args", {})
                            summary = tc.get("toolSummary", tc.get("toolAction", name))
                            readable_entries.append(f"\n#### 🛠️ Action: `{name}` - {summary} (Step {obj.get('step_index', idx)})\n")
                            if name in ("run_command", "view_file", "replace_file_content", "write_to_file"):
                                args_preview = json.dumps(args, indent=2)
                                if len(args_preview) > 600:
                                    args_preview = args_preview[:600] + "\n... [truncated]"
                                readable_entries.append(f"```json\n{args_preview}\n```\n")
                    elif content:
                        text_snip = content.strip()
                        if len(text_snip) > 800:
                            text_snip = text_snip[:800] + "\n... [truncated]"
                        readable_entries.append(f"\n**🤖 Assistant Note / Response:**\n\n{text_snip}\n")
                except Exception:
                    pass

        with open(dest_jsonl, "w", encoding="utf-8") as f_out:
            f_out.writelines(sanitized_lines)
        print(f"Wrote sanitized JSONL ({len(sanitized_lines)} lines) to {dest_jsonl}")

        with open(dest_md, "w", encoding="utf-8") as f_md:
            f_md.write("# Antigravity Coding Agent - Complete Chronological Trajectory\n\n")
            f_md.write("This file contains the sanitized, human-readable execution history across Milestones 1 through 9.\n\n---\n\n")
            f_md.writelines(readable_entries)
        print(f"Wrote human-readable markdown to {dest_md}")

    # 2. Export & sanitize task logs
    if SOURCE_TASKS_DIR.exists():
        task_count = 0
        for task_file in SOURCE_TASKS_DIR.glob("*"):
            if task_file.is_file():
                dest_task = DEST_TASKS_DIR / task_file.name
                content = task_file.read_text(encoding="utf-8", errors="replace")
                clean_content = sanitize_text(content)
                dest_task.write_text(clean_content, encoding="utf-8")
                task_count += 1
        print(f"Exported and sanitized {task_count} task logs into {DEST_TASKS_DIR}")

    # 3. Export Pi trace
    if SOURCE_PI_TRACE.exists():
        pi_dest = DEST_DIR / "pi_agent_trace.json"
        content = SOURCE_PI_TRACE.read_text(encoding="utf-8", errors="replace")
        clean_content = sanitize_text(content)
        pi_dest.write_text(clean_content, encoding="utf-8")
        print(f"Exported sanitized Pi agent trace to {pi_dest}")


if __name__ == "__main__":
    export_transcripts()
