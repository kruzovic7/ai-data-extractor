from __future__ import annotations

import json
from pathlib import Path

from . import common

DISPLAY_NAME = "OpenCode"
SOURCE_ID = "opencode"

SEARCH_DIRS = ["opencode"]


def find_installations(extra_paths: list[Path] | None = None) -> list[Path]:
    roots = common.candidate_paths(SEARCH_DIRS)
    if extra_paths:
        roots += [p for p in extra_paths if p.exists() and p not in roots]
    
    storage_dirs = []
    for r in roots:
        storage = r / "storage" if r.name == "opencode" else r
        storage_dirs.append(storage if storage.exists() else r)
    return storage_dirs


def _extract_session_structure(storage: Path) -> list[dict]:
    """Walk the session/message/part tree structure."""
    conversations = []
    
    sessions_dir = storage / "session"
    if not sessions_dir.exists():
        return conversations
    
    for session_file in sessions_dir.rglob("*.json"):
        try:
            session_data = json.loads(session_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, PermissionError):
            continue
        
        messages = []
        session_id = session_data.get("id") or session_file.stem
        
        # Get messages for this session
        messages_dir = storage / "message" / session_id
        if messages_dir.exists():
            for message_file in messages_dir.glob("*.json"):
                try:
                    message_data = json.loads(message_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, PermissionError):
                    continue
                
                role = message_data.get("role", "")
                content = ""
                
                # Get parts for this message
                message_id = message_data.get("id") or message_file.stem
                parts_dir = storage / "part" / message_id
                if parts_dir.exists():
                    text_parts = []
                    for part_file in parts_dir.glob("*.json"):
                        try:
                            part_data = json.loads(part_file.read_text(encoding="utf-8"))
                        except (json.JSONDecodeError, OSError, PermissionError):
                            continue
                        if part_data.get("type") == "text":
                            text_parts.append(part_data.get("text", ""))
                    content = "\n".join(text_parts)
                
                if role and content:
                    messages.append({
                        "role": role,
                        "content": content,
                        "timestamp": message_data.get("time") or message_data.get("created_at"),
                    })
        
        if messages:
            conversations.append({
                "messages": messages,
                "source": "opencode",
                "session_id": session_id,
                "name": session_data.get("title"),
                "project_path": session_data.get("workspace") or session_data.get("cwd"),
                "created_at": session_data.get("time_created"),
            })
    
    return conversations


def extract(installations: list[Path]) -> list[dict]:
    conversations = []
    for storage in installations:
        if not storage.exists():
            continue
        conversations.extend(_extract_session_structure(storage))
    return conversations


if __name__ == "__main__":
    installs = find_installations()
    convos = extract(installs)
    out = common.write_jsonl(convos, Path("extracted_data"), "opencode_conversations")
    print(f"Found {len(convos)} conversations across {len(installs)} installation(s).")
    if out:
        print(f"Wrote {out}")