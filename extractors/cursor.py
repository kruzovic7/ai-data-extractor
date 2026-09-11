from __future__ import annotations

import json
from pathlib import Path

from . import common

DISPLAY_NAME = "Cursor"
SOURCE_ID = "cursor"

APP_DIR_NAMES = ["Cursor"]
CHAT_ITEM_KEY = "workbench.panel.aichat.view.aichat.chatdata"


def find_installations(extra_paths: list[Path] | None = None) -> list[Path]:
    found = common.candidate_paths(APP_DIR_NAMES)
    if extra_paths:
        found += [p for p in extra_paths if p.exists() and p not in found]
    return found


def _iter_state_dbs(app_dir: Path) -> list[Path]:
    dbs = []
    global_db = app_dir / "User" / "globalStorage" / "state.vscdb"
    if global_db.exists():
        dbs.append(global_db)
    ws_root = app_dir / "User" / "workspaceStorage"
    if ws_root.exists():
        try:
            for ws in ws_root.iterdir():
                db = ws / "state.vscdb"
                if db.exists():
                    dbs.append(db)
        except (OSError, PermissionError):
            pass
    return dbs


def _extract_bubble_text(bubble: dict) -> str:
    for key in ("text", "content"):
        val = bubble.get(key)
        if isinstance(val, str) and val.strip():
            return val
    rich = bubble.get("richText")
    if isinstance(rich, str) and rich.strip():
        return rich
    return ""


def _bubble_role(bubble: dict) -> str:
    role = bubble.get("role")
    if role in ("user", "assistant"):
        return role
    return "user" if bubble.get("type") == 1 else "assistant"


def _code_context_from_bubble(bubble: dict) -> list[dict]:
    ctx = []
    for block in bubble.get("codeBlocks") or []:
        if isinstance(block, dict):
            uri = block.get("uri")
            ctx.append({
                "file": uri.get("path") if isinstance(uri, dict) else block.get("file"),
                "code": block.get("content") or block.get("code"),
            })
    for sel in bubble.get("selections") or []:
        if isinstance(sel, dict):
            uri = sel.get("uri")
            ctx.append({
                "file": uri.get("path") if isinstance(uri, dict) else sel.get("file"),
                "code": sel.get("text"),
                "range": sel.get("range"),
            })
    return ctx


def _extract_old_chat(db_path: Path) -> list[dict]:
    conversations = []
    if not common.table_exists(db_path, "ItemTable"):
        return conversations
    rows = common.safe_sqlite_query(db_path, "SELECT value FROM ItemTable WHERE key = ?", (CHAT_ITEM_KEY,))
    for (raw,) in rows:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for tab in data.get("tabs", []):
            messages = []
            for bubble in tab.get("bubbles", []):
                text = _extract_bubble_text(bubble)
                if not text:
                    continue
                messages.append({
                    "role": _bubble_role(bubble),
                    "content": text,
                    "code_context": _code_context_from_bubble(bubble) or None,
                })
            if messages:
                conversations.append({
                    "messages": messages,
                    "source": "cursor-chat",
                    "session_id": tab.get("tabId"),
                    "name": tab.get("chatTitle") or tab.get("title"),
                    "created_at": tab.get("lastSendTime"),
                })
    return conversations


def _extract_composer(db_path: Path) -> list[dict]:
    conversations = []
    if not common.table_exists(db_path, "cursorDiskKV"):
        return conversations

    composer_rows = common.safe_sqlite_query(
        db_path, "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
    )
    bubble_rows = common.safe_sqlite_query(
        db_path, "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'bubbleId:%'"
    )

    bubbles_by_composer: dict[str, dict[str, dict]] = {}
    for key, raw in bubble_rows:
        parts = key.split(":")
        if len(parts) != 3:
            continue
        _, composer_id, bubble_id = parts
        try:
            bubble = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        bubbles_by_composer.setdefault(composer_id, {})[bubble_id] = bubble

    for key, raw in composer_rows:
        composer_id = key.split(":", 1)[1]
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        messages = []

        inline_conv = data.get("conversation")
        if isinstance(inline_conv, list) and inline_conv:
            for bubble in inline_conv:
                text = _extract_bubble_text(bubble)
                if not text:
                    continue
                messages.append({
                    "role": _bubble_role(bubble),
                    "content": text,
                    "code_context": _code_context_from_bubble(bubble) or None,
                })

        if not messages:
            headers = data.get("fullConversationHeadersOnly") or data.get("conversationHeaders") or []
            local_bubbles = bubbles_by_composer.get(composer_id, {})
            ordered_ids = [h.get("bubbleId") for h in headers if isinstance(h, dict) and h.get("bubbleId")]
            if not ordered_ids:
                ordered_ids = list(local_bubbles.keys())
            for bubble_id in ordered_ids:
                bubble = local_bubbles.get(bubble_id)
                if not bubble:
                    continue
                text = _extract_bubble_text(bubble)
                if not text:
                    continue
                messages.append({
                    "role": _bubble_role(bubble),
                    "content": text,
                    "code_context": _code_context_from_bubble(bubble) or None,
                })

        if messages:
            conversations.append({
                "messages": messages,
                "source": "cursor-composer",
                "session_id": composer_id,
                "name": data.get("name") or data.get("title"),
                "created_at": data.get("createdAt") or data.get("lastUpdatedAt"),
            })

    return conversations


def extract(installations: list[Path]) -> list[dict]:
    conversations = []
    for app_dir in installations:
        for db_path in _iter_state_dbs(app_dir):
            conversations += _extract_old_chat(db_path)
            conversations += _extract_composer(db_path)
    return conversations


if __name__ == "__main__":
    installs = find_installations()
    convos = extract(installs)
    out = common.write_jsonl(convos, Path("extracted_data"), "cursor_complete")
    print(f"Found {len(convos)} conversations across {len(installs)} installation(s).")
    if out:
        print(f"Wrote {out}")