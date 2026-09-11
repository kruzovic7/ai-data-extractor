from __future__ import annotations

import json
from pathlib import Path

from . import common

DISPLAY_NAME = "Continue"
SOURCE_ID = "continue"

SEARCH_DIRS = [".continue", ".continue-local"]


def find_installations(extra_paths: list[Path] | None = None) -> list[Path]:
    roots = common.candidate_paths(SEARCH_DIRS)
    if extra_paths:
        roots += [p for p in extra_paths if p.exists() and p not in roots]
    session_dirs = []
    for r in roots:
        sessions = r / "sessions"
        session_dirs.append(sessions if sessions.exists() else r)
    return session_dirs


def _extract_session(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, PermissionError):
        return None

    history = data.get("history", [])
    if not history:
        return None

    messages = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        
        message = item.get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            # Extract text from Continue's content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)
        
        messages.append({
            "role": role,
            "content": content,
            "timestamp": item.get("time"),
        })

    if not messages:
        return None

    return {
        "messages": messages,
        "source": "continue",
        "session_id": data.get("session_id") or path.stem,
        "name": data.get("title"),
        "project_path": data.get("workspace_directory"),
        "created_at": data.get("time_created") or messages[0].get("timestamp"),
    }


def extract(installations: list[Path]) -> list[dict]:
    conversations = []
    for session_dir in installations:
        if not session_dir.exists():
            continue
        for json_file in session_dir.glob("*.json"):
            convo = _extract_session(json_file)
            if convo:
                conversations.append(convo)
    return conversations


if __name__ == "__main__":
    installs = find_installations()
    convos = extract(installs)
    out = common.write_jsonl(convos, Path("extracted_data"), "continue_conversations")
    print(f"Found {len(convos)} conversations across {len(installs)} installation(s).")
    if out:
        print(f"Wrote {out}")