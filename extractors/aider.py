from __future__ import annotations

import re
from pathlib import Path

from . import common

DISPLAY_NAME = "Aider"
SOURCE_ID = "aider"

# Common project root names to scan under home directory
PROJECT_HINTS = ["projects", "code", "dev", "repos", "workspace", "src", "Documents", "work"]

# Skip these directories during traversal
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}

# Parse lines like: #### 2024-01-15 14:30:22 - user: message text
HISTORY_PATTERN = re.compile(r"^####\s+(.+?)\s+-\s+(\w+):\s*(.*)$")


def find_installations(extra_paths: list[Path] | None = None) -> list[Path]:
    """Return project directories that contain .aider.chat.history.md files."""
    roots = [Path.home()]
    
    # Add common project root locations
    for hint in PROJECT_HINTS:
        candidate = Path.home() / hint
        if candidate.exists():
            roots.append(candidate)
    
    if extra_paths:
        roots.extend(extra_paths)
    
    # Deduplicate
    roots = list(dict.fromkeys(roots))
    
    history_files = []
    for root in roots:
        if not root.exists():
            continue
        
        # First check if root itself has the file
        direct = root / ".aider.chat.history.md"
        if direct.exists():
            history_files.append(direct)
        
        # Then scan subdirectories (up to 5 levels deep)
        try:
            for path in root.rglob(".aider.chat.history.md"):
                # Skip if too deep
                relative = path.relative_to(root)
                if len(relative.parts) > 5:
                    continue
                # Skip if in skip dirs
                if any(part in SKIP_DIRS for part in relative.parts):
                    continue
                if path not in history_files:
                    history_files.append(path)
        except (OSError, PermissionError):
            continue
    
    return history_files


def _parse_timestamp(ts_str: str) -> str | None:
    """Parse various timestamp formats into ISO 8601."""
    ts_str = ts_str.strip()
    
    # Try common formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            import datetime
            dt = datetime.datetime.strptime(ts_str, fmt)
            return dt.isoformat()
        except ValueError:
            continue
    
    # If all fails, return as-is if it looks like a timestamp
    if re.match(r"\d{4}-\d{2}-\d{2}", ts_str):
        return ts_str
    return None


def _extract_history_file(path: Path) -> dict | None:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, PermissionError):
        return None
    
    messages = []
    session_id = path.parent.name
    
    for line in content.splitlines():
        match = HISTORY_PATTERN.match(line)
        if not match:
            continue
        
        ts_str, role, message = match.groups()
        role = role.lower()
        
        # Map roles to user/assistant
        if role in ("user", "human", "you"):
            role = "user"
        elif role in ("assistant", "ai", "model", "aider"):
            role = "assistant"
        else:
            continue
        
        timestamp = _parse_timestamp(ts_str)
        
        messages.append({
            "role": role,
            "content": message,
            "timestamp": timestamp,
        })
    
    if not messages:
        return None
    
    return {
        "messages": messages,
        "source": "aider",
        "session_id": session_id,
        "name": session_id,
        "project_path": str(path.parent),
        "created_at": messages[0].get("timestamp"),
    }


def extract(installations: list[Path]) -> list[dict]:
    conversations = []
    for history_file in installations:
        convo = _extract_history_file(history_file)
        if convo:
            conversations.append(convo)
    return conversations


if __name__ == "__main__":
    installs = find_installations()
    convos = extract(installs)
    out = common.write_jsonl(convos, Path("extracted_data"), "aider_conversations")
    print(f"Found {len(convos)} conversations across {len(installs)} installation(s).")
    if out:
        print(f"Wrote {out}")