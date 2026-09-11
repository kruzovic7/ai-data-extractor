from __future__ import annotations

from pathlib import Path

from . import common

DISPLAY_NAME = "Windsurf"
SOURCE_ID = "windsurf"

APP_DIR_NAMES = ["Windsurf"]
KEY_HINTS = ("cascade", "windsurf", "chat", "aichat", "conversation")


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


def extract(installations: list[Path]) -> list[dict]:
    conversations = []
    for app_dir in installations:
        for db_path in _iter_state_dbs(app_dir):
            conversations += common.heuristic_extract_chat_from_kv(db_path, "windsurf", KEY_HINTS)
    return conversations


if __name__ == "__main__":
    installs = find_installations()
    convos = extract(installs)
    out = common.write_jsonl(convos, Path("extracted_data"), "windsurf_conversations")
    print(f"Found {len(convos)} conversations across {len(installs)} installation(s).")
    if out:
        print(f"Wrote {out}")