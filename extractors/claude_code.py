from __future__ import annotations

from pathlib import Path

from . import common

DISPLAY_NAME = "Claude Code"
SOURCE_ID = "claude_code"

SEARCH_DIRS = [".claude", ".claude-code", ".claude-local", ".claude-m2", ".claude-zai"]


def find_installations(extra_paths: list[Path] | None = None) -> list[Path]:
    roots = common.candidate_paths(SEARCH_DIRS)
    if extra_paths:
        roots += [p for p in extra_paths if p.exists() and p not in roots]
    projects_dirs = []
    for r in roots:
        p = r / "projects"
        if p.exists():
            projects_dirs.append(p)
    return projects_dirs


def _flatten_content(content) -> tuple[str, list[dict], list[dict]]:
    """Split Anthropic-style content into (text, tool_use[], tool_result[])."""
    if isinstance(content, str):
        return content, [], []

    text_parts: list[str] = []
    tool_use: list[dict] = []
    tool_result: list[dict] = []

    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tool_use.append({
                    "name": block.get("name"), "input": block.get("input"), "id": block.get("id"),
                })
            elif btype == "tool_result":
                tool_result.append({
                    "tool_use_id": block.get("tool_use_id"),
                    "content": block.get("content"),
                    "is_error": block.get("is_error", False),
                })
    return "\n".join(t for t in text_parts if t), tool_use, tool_result


def _extract_session(path: Path) -> dict | None:
    messages = []
    project_path = None
    session_id = path.stem

    for event in common.safe_read_jsonl(path):
        etype = event.get("type")
        project_path = project_path or event.get("cwd")
        session_id = event.get("sessionId", session_id)

        if etype not in ("user", "assistant"):
            continue

        msg = event.get("message") or {}
        role = msg.get("role", etype)
        text, tool_use, tool_result = _flatten_content(msg.get("content"))

        entry = {"role": role, "content": text, "timestamp": event.get("timestamp")}
        if tool_use:
            entry["tool_use"] = tool_use
        if tool_result:
            entry["tool_results"] = tool_result
        messages.append(entry)

    if not messages:
        return None

    return {
        "messages": messages,
        "source": "claude-code",
        "session_id": session_id,
        "project_path": project_path,
        "name": path.parent.name,
        "created_at": messages[0].get("timestamp"),
    }


def extract(installations: list[Path]) -> list[dict]:
    conversations = []
    for projects_dir in installations:
        try:
            project_dirs = list(projects_dir.iterdir())
        except (OSError, PermissionError):
            continue
        for project_dir in project_dirs:
            if not project_dir.is_dir():
                continue
            for session_file in project_dir.glob("*.jsonl"):
                convo = _extract_session(session_file)
                if convo:
                    conversations.append(convo)
    return conversations


if __name__ == "__main__":
    installs = find_installations()
    convos = extract(installs)
    out = common.write_jsonl(convos, Path("extracted_data"), "claude_code_conversations")
    print(f"Found {len(convos)} conversations across {len(installs)} installation(s).")
    if out:
        print(f"Wrote {out}")