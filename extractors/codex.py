from __future__ import annotations

from pathlib import Path

from . import common

DISPLAY_NAME = "Codex CLI"
SOURCE_ID = "codex"

SEARCH_DIRS = [".codex", ".codex-local"]


def find_installations(extra_paths: list[Path] | None = None) -> list[Path]:
    roots = common.candidate_paths(SEARCH_DIRS)
    if extra_paths:
        roots += [p for p in extra_paths if p.exists() and p not in roots]
    session_dirs = []
    for r in roots:
        sessions = r / "sessions"
        session_dirs.append(sessions if sessions.exists() else r)
    return session_dirs


def _get_role_content(obj: dict) -> tuple[str, str] | None:
    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else None
    for cand in (payload, obj):
        if not cand:
            continue
        role = cand.get("role")
        content = cand.get("content")
        if role and content is not None:
            if isinstance(content, str):
                return role, content
            if isinstance(content, list):
                text = "\n".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") in ("text", "input_text", "output_text")
                )
                if text:
                    return role, text
    return None


def _extract_session(path: Path) -> dict | None:
    messages = []
    session_id = path.stem
    cwd = None

    for event in common.safe_read_jsonl(path):
        etype = event.get("type")
        if etype == "session_meta":
            meta = event.get("payload", event)
            cwd = meta.get("cwd", cwd)
            session_id = meta.get("id", session_id)
            continue

        pair = _get_role_content(event)
        if not pair:
            continue
        role, text = pair
        if role not in ("user", "assistant"):
            continue
        messages.append({"role": role, "content": text, "timestamp": event.get("timestamp")})

    if not messages:
        return None

    return {
        "messages": messages,
        "source": "codex",
        "session_id": session_id,
        "project_path": cwd,
        "name": path.stem,
        "created_at": messages[0].get("timestamp"),
    }


def extract(installations: list[Path]) -> list[dict]:
    conversations = []
    for session_dir in installations:
        if not session_dir.exists():
            continue
        rollout_files = list(session_dir.rglob("rollout-*.jsonl"))
        files = rollout_files if rollout_files else list(session_dir.rglob("*.jsonl"))
        for f in files:
            convo = _extract_session(f)
            if convo:
                conversations.append(convo)
    return conversations


if __name__ == "__main__":
    installs = find_installations()
    convos = extract(installs)
    out = common.write_jsonl(convos, Path("extracted_data"), "codex_conversations")
    print(f"Found {len(convos)} conversations across {len(installs)} installation(s).")
    if out:
        print(f"Wrote {out}")