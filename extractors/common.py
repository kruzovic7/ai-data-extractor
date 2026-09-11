from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class ExtractorResult:
    """Result of running a single extractor."""
    source_id: str
    display_name: str
    installations_found: int = 0
    conversations: list[dict] = field(default_factory=list)
    output_path: Path | None = None
    error: str | None = None


def app_data_roots() -> list[Path]:
    """Return the top-level application data directories for the current OS."""
    home = Path.home()
    roots = []
    
    if sys.platform == "darwin":
        roots.append(home / "Library" / "Application Support")
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        localappdata = os.environ.get("LOCALAPPDATA")
        if appdata:
            roots.append(Path(appdata))
        if localappdata:
            roots.append(Path(localappdata))
    else:  # Linux and others
        xdg_config = os.environ.get("XDG_CONFIG_HOME", home / ".config")
        xdg_data = os.environ.get("XDG_DATA_HOME", home / ".local" / "share")
        roots.append(Path(xdg_config))
        roots.append(Path(xdg_data))
    
    # Always include home directory for tools that store in ~/.toolname
    roots.append(home)
    
    return [r for r in roots if r.exists()]


def candidate_paths(dir_names: list[str]) -> list[Path]:
    """Find candidate directories by searching common app data roots."""
    found = []
    for root in app_data_roots():
        for name in dir_names:
            candidate = root / name
            if candidate.exists():
                found.append(candidate)
    
    # Deduplicate preserving order
    return list(dict.fromkeys(found))


def safe_read_jsonl(path: Path) -> Iterator[dict]:
    """Read a JSONL file line by line, skipping malformed lines."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except (OSError, PermissionError):
        return


def safe_read_json(path: Path) -> dict | None:
    """Read and parse a JSON file, returning None on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, OSError, PermissionError, TypeError):
        return None


def safe_sqlite_query(db_path: Path, query: str, params: tuple = ()) -> list[tuple]:
    """Run a read-only SQLite query on a temporary copy, returning rows or empty list on error."""
    import shutil
    tmp_path = None
    try:
        # Создаём временный файл
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        
        # Копируем оригинальную базу во временный файл
        shutil.copy2(db_path, tmp_path)
        
        # Подключаемся к копии
        conn = sqlite3.connect(str(tmp_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = [tuple(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except (sqlite3.Error, OSError, PermissionError):
        return []
    finally:
        # Удаляем временный файл в любом случае
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def table_exists(db_path: Path, table_name: str) -> bool:
    """Check if a table exists in a SQLite database."""
    rows = safe_sqlite_query(
        db_path,
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return len(rows) > 0


def heuristic_extract_chat_from_kv(db_path: Path, source_id: str, key_hints: tuple[str, ...]) -> list[dict]:
    """
    Generic heuristic: scan a SQLite KV store for chat-related keys and
    try to extract role/text pairs from the JSON values.
    """
    conversations = []
    
    # Try common table names
    for table_name in ("ItemTable", "cursorDiskKV", "key_value_store", "kv_store"):
        if not table_exists(db_path, table_name):
            continue
        
        # Get all rows
        rows = safe_sqlite_query(db_path, f"SELECT key, value FROM {table_name}")
        
        for key, raw_value in rows:
            if not any(hint.lower() in key.lower() for hint in key_hints):
                continue
            
            # Try to parse the value as JSON
            try:
                data = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
            except (json.JSONDecodeError, TypeError):
                continue
            
            # Recursively search for role/text pairs
            messages = _extract_messages_from_structure(data)
            if messages:
                conversations.append({
                    "messages": messages,
                    "source": source_id,
                    "session_id": key,
                    "name": f"KV: {key}",
                    "created_at": messages[0].get("timestamp"),
                })
    
    return conversations


def heuristic_extract_chat_from_jsonl(path: Path, source_id: str) -> dict | None:
    """Generic heuristic: extract chat messages from a JSONL file."""
    messages = []
    
    for event in safe_read_jsonl(path):
        role = event.get("role")
        content = event.get("content")
        
        # Try nested payload
        if not role and "payload" in event and isinstance(event["payload"], dict):
            role = event["payload"].get("role")
            content = event["payload"].get("content")
        
        # Try message wrapper
        if not role and "message" in event and isinstance(event["message"], dict):
            role = event["message"].get("role")
            content = event["message"].get("content")
        
        if role not in ("user", "assistant", "system"):
            continue
        
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)
        
        if content:
            messages.append({
                "role": role,
                "content": content,
                "timestamp": event.get("timestamp"),
            })
    
    if not messages:
        return None
    
    return {
        "messages": messages,
        "source": source_id,
        "session_id": path.stem,
        "name": path.stem,
        "created_at": messages[0].get("timestamp"),
    }


def _extract_messages_from_structure(data: Any, depth: int = 0) -> list[dict]:
    """Recursively search a data structure for objects with role/text pairs."""
    if depth > 5:
        return []
    
    messages = []
    
    if isinstance(data, dict):
        # Check if this dict itself is a message
        role = data.get("role") or data.get("type")
        content = data.get("content") or data.get("text") or data.get("message")
        
        if role in ("user", "assistant") and content:
            if isinstance(content, str) and content.strip():
                messages.append({
                    "role": role,
                    "content": content,
                    "timestamp": data.get("timestamp") or data.get("time"),
                })
        
        # Recurse into values
        for value in data.values():
            messages.extend(_extract_messages_from_structure(value, depth + 1))
    
    elif isinstance(data, list):
        for item in data:
            messages.extend(_extract_messages_from_structure(item, depth + 1))
    
    return messages


def write_jsonl(conversations: list[dict], output_dir: Path, prefix: str) -> Path | None:
    """Write conversations to a JSONL file and return the path."""
    if not conversations:
        return None
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{prefix}_{timestamp}.jsonl"
    
    with open(output_path, "w", encoding="utf-8") as f:
        for convo in conversations:
            f.write(json.dumps(convo, ensure_ascii=False) + "\n")
    
    return output_path


def heading(text: str) -> None:
    """Print a formatted heading."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def success(text: str) -> None:
    """Print a success message."""
    print(f"  ✓ {text}")


def warn(text: str) -> None:
    """Print a warning message."""
    print(f"  ⚠ {text}")


def error(text: str) -> None:
    """Print an error message."""
    print(f"  ✗ {text}")