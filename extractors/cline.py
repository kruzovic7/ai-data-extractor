from __future__ import annotations

import json
from pathlib import Path

from . import common

DISPLAY_NAME = "Cline / Roo Code"
SOURCE_ID = "cline"

# Common editor app dir names and extension IDs
EDITOR_DIRS = ["Code", "VSCodium", "Cursor", "Windsurf", "code-oss"]
EXTENSION_IDS = [
    "saoudrizwan.claude-dev",  # Cline
    "rooveterinaryinc.roo-cline",  # Roo Code
]


def find_installations(extra_paths: list[Path] | None = None) -> list[Path]:
    found = []
    
    # Search in common app data roots
    for root in common.app_data_roots():
        for editor in EDITOR_DIRS:
            editor_dir = root / editor
            if not editor_dir.exists():
                continue
            
            for ext_id in EXTENSION_IDS:
                tasks_dir = editor_dir / "User" / "globalStorage" / ext_id / "tasks"
                if tasks_dir.exists():
                    found.append(tasks_dir)
    
    if extra_paths:
        found += [p for p in extra_paths if p.exists() and p not in found]
    
    return found


def _extract_task_folder(tasks_dir: Path) -> list[dict]:
    conversations = []
    
    for task_dir in tasks_dir.iterdir():
        if not task_dir.is_dir():
            continue
        
        history_file = task_dir / "api_conversation_history.json"
        if not history_file.exists():
            continue
        
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, PermissionError):
            continue
        
        messages = []
        for msg in history:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            
            content = msg.get("content", "")
            if isinstance(content, list):
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
                "timestamp": msg.get("timestamp") or msg.get("created_at"),
            })
        
        if messages:
            conversations.append({
                "messages": messages,
                "source": "cline",
                "session_id": task_dir.name,
                "name": task_dir.name,
                "created_at": messages[0].get("timestamp"),
            })
    
    return conversations


def extract(installations: list[Path]) -> list[dict]:
    conversations = []
    for tasks_dir in installations:
        if tasks_dir.exists():
            conversations.extend(_extract_task_folder(tasks_dir))
    return conversations


if __name__ == "__main__":
    installs = find_installations()
    convos = extract(installs)
    out = common.write_jsonl(convos, Path("extracted_data"), "cline_conversations")
    print(f"Found {len(convos)} conversations across {len(installs)} installation(s).")
    if out:
        print(f"Wrote {out}")