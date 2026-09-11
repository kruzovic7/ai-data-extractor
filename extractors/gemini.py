from __future__ import annotations

import json
from pathlib import Path

from . import common

DISPLAY_NAME = "Gemini CLI"
SOURCE_ID = "gemini"

SEARCH_DIRS = [".gemini"]

def find_installations(extra_paths: list[Path] | None = None) -> list[Path]:
    roots = common.candidate_paths(SEARCH_DIRS)
    if extra_paths:
        roots += [p for p in extra_paths if p.exists() and p not in roots]
    return roots


def _extract_chat_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, PermissionError):
        return None

    # Try multiple known message container formats
    messages_raw = None
    for key in ("messages", "history", "turns"):
        if isinstance(data.get(key), list):
            messages_raw = data[key]
            break
    
    if not messages_raw:
        # Maybe the file itself is a list of messages
        if isinstance(data, list) and data and isinstance(data[0], dict):
            messages_raw = data

    if not messages_raw:
        return None

    messages = []
    for item in messages_raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role") or item.get("author")
        if role in ("model", "bot"):
            role = "assistant"
        elif role in ("human",):
            role = "user"
        
        if role not in ("user", "assistant"):
            continue

        content = item.get("content") or item.get("text") or ""
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    text_parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    text_parts.append(part)
            content = "\n".join(text_parts)

        messages.append({
            "role": role,
            "content": content,
            "timestamp": item.get("timestamp") or item.get("time"),
        })

    if not messages:
        return None

    return {
        "messages": messages,
        "source": "gemini",
        "session_id": data.get("session_id") or data.get("id") or path.stem,
        "name": data.get("title"),
        "project_path": data.get("workspace") or data.get("cwd"),
        "created_at": data.get("created_at") or messages[0].get("timestamp"),
    }


def extract(installations: list[Path]) -> list[dict]:
    conversations = []
    for root in installations:
        if not root.exists():
            continue
        chats_dirs = root.rglob("chats")
        for chats_dir in chats_dirs:
            if not chats_dir.exists():
                continue
            for json_file in chats_dir.glob("*.json"):
                convo = _extract_chat_file(json_file)
                if convo:
                    conversations.append(convo)
    
    # If no chats directories found, try scanning all JSON files
    if not conversations:
        for root in installations:
            for json_file in root.rglob("*.json"):
                convo = _extract_chat_file(json_file)
                if convo:
                    conversations.append(convo)
    
    return conversations


if __name__ == "__main__":
    installs = find_installations()
    convos = extract(installs)
    out = common.write_jsonl(convos, Path("extracted_data"), "gemini_conversations")
    print(f"Found {len(convos)} conversations across {len(installs)} installation(s).")
    if out:
        print(f"Wrote {out}")