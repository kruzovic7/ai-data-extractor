from __future__ import annotations

from pathlib import Path

from . import common

DISPLAY_NAME = "Trae"
SOURCE_ID = "trae"

APP_DIR_NAMES = ["Trae", "Trae CN", ".trae"]
KEY_HINTS = ("trae", "chat", "aichat", "conversation", "marscode")


def find_installations(extra_paths: list[Path] | None = None) -> list[Path]:
    found = common.candidate_paths(APP_DIR_NAMES)
    if extra_paths:
        found += [p for p in extra_paths if p.exists() and p not in found]
    return found


def extract(installations: list[Path]) -> list[dict]:
    conversations = []
    for app_dir in installations:
        for db_path in app_dir.rglob("state.vscdb"):
            conversations += common.heuristic_extract_chat_from_kv(db_path, "trae", KEY_HINTS)
        for jsonl_path in app_dir.rglob("*.jsonl"):
            convo = common.heuristic_extract_chat_from_jsonl(jsonl_path, "trae")
            if convo:
                conversations.append(convo)
    return conversations


if __name__ == "__main__":
    installs = find_installations()
    convos = extract(installs)
    out = common.write_jsonl(convos, Path("extracted_data"), "trae_conversations")
    print(f"Found {len(convos)} conversations across {len(installs)} installation(s).")
    if out:
        print(f"Wrote {out}")