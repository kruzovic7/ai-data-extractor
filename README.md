# AI Coding Assistant Data Extraction

Extract your **own local chat history** from AI coding assistants into a single,
normalized JSONL format - for fine-tuning, personal analytics, or just backing
up years of conversations before an app's local database gets cleared.


## Features

Auto-discovers and extracts complete conversation history, including:

- User messages & assistant responses
- Code context (file paths, selections, snippets)
- Code diffs / suggested edits, where the tool records them
- Tool calls and their results
- Timestamps, session IDs, project paths, model names - whatever each
  tool's storage actually contains

## Supported sources

| # | Tool | Storage | Search location |
|---|------|---------|------------------|
| 1 | **Claude Code** | JSONL, one file per session | `~/.claude/projects/**/*.jsonl` |
| 2 | **Codex CLI** | JSONL "rollout" files | `~/.codex/sessions/**/rollout-*.jsonl` |
| 3 | **Cursor** | SQLite (`state.vscdb`) | `~/…/Cursor/User/{global,workspace}Storage` |
| 4 | **Windsurf** | SQLite, undocumented schema (heuristic) | `~/…/Windsurf/User/{global,workspace}Storage` |
| 5 | **Trae** | SQLite + JSONL, undocumented (heuristic) | `~/…/Trae` |
| 6 | **Continue** | JSON, one file per session | `~/.continue/sessions/*.json` |
| 7 | **Gemini CLI** | JSON, one file per chat | `~/.gemini/tmp/<hash>/chats/*.json` |
| 8 | **OpenCode** | JSON (session/message/part trees) | `~/.local/share/opencode/storage/` |
| 9 | **Cline / Roo Code** *(new)* | JSON, one folder per task | `<editor>/User/globalStorage/<ext-id>/tasks/` |
| 10 | **Aider** *(new)* | Markdown transcript per project | `<project>/.aider.chat.history.md` |

Every script searches macOS, Linux, and Windows conventions
(`~/Library/Application Support`, `~/.config`, `~/.local/share`, `%APPDATA%`,
`%LOCALAPPDATA%`) automatically - you don't need to tell it which OS you're on.

### Why Cline and Aider

They're two of the most-used AI coding tools that the original list left out,
and both have a genuinely different (and instructive) storage shape:

- **Cline** (and its fork **Roo Code**) is the most popular open-source
  autonomous coding *agent* extension. It stores raw Anthropic-format
  message arrays per task, so its extractor doubles as the simplest example
  of parsing that format if you want to add your own tool later.
- **Aider** is the most popular *terminal-only* pair-programming tool, and
  it's structured completely differently from everything else here: no
  central database, just a markdown transcript sitting in every project
  directory. It's included specifically to prove the toolkit generalizes
  beyond "SQLite or JSONL in one app-data folder."

## Quick start

```bash
# No dependencies -- standard library only
python --version   # 3.9+ required, 3.10+ recommended

# Interactive: pick which sources to extract from a numbered menu
python extract.py

# Or drive it directly
python extract.py --all
python extract.py --sources cursor,claude_code,aider
python extract.py --list                    # just show what's installed, don't extract
python extract.py --all --merge             # also write all_conversations.jsonl

# Shorthand for "extract everything"
./extract_all.sh
```

### CLI reference

```
python extract.py [--all] [--sources ids] [--list] [--output-dir DIR]
                    [--search-path PATH ...] [--merge]

--all                 Extract every supported source, no prompts.
--sources ids         Comma-separated source ids (see table above for names,
                       or run with --list to see them). Skips the menu.
--list                Report what was found for each source without
                       extracting anything -- a fast, safe preview.
--output-dir DIR      Where to write JSONL (default: ./extracted_data)
--search-path PATH    Extra directory to search, on top of the normal OS
                       locations. Repeatable. Mainly useful for:
                         - Aider, which has no fixed app-data folder and
                           needs to know where your projects live
                         - nonstandard install locations for anything else
--merge               After extracting, also concatenate everything into
                       all_conversations.jsonl
```

Each extractor can also still be run standalone, same as the original
toolkit (`python -m extractors.cursor` from the project root, or
`python extractors/cursor.py`), which is handy while debugging one source.

## Output format

Every run creates timestamped files under `extracted_data/`:

```
extracted_data/
├── claude_code_conversations_20260816_143022.jsonl
├── cursor_conversations_20260816_143022.jsonl
├── aider_conversations_20260816_143022.jsonl
├── cline_conversations_20260816_143022.jsonl
└── ... one file per source you extracted, plus all_conversations.jsonl if --merge
```

Each line is one JSON conversation:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "How do I fix this TypeScript error?",
      "code_context": [
        {"file": "/Users/you/project/src/index.ts", "code": "const x: string = 123;"}
      ],
      "timestamp": "2026-01-16T14:30:22Z"
    },
    {
      "role": "assistant",
      "content": "The error occurs because you're assigning a number to a string type...",
      "tool_use": [{"name": "edit_file", "input": {"path": "src/index.ts"}}],
      "timestamp": "2026-01-16T14:30:25Z"
    }
  ],
  "source": "cursor-composer",
  "session_id": "c1a2b3...",
  "project_path": "/Users/you/project",
  "name": "TypeScript Type Error Fix",
  "created_at": 1705414222000
}
```

Fields vary a bit by source (not every tool records `code_context`, token
usage, or `project_path`) - `messages`, `source`, and `session_id` are the
only ones you can always rely on.

## How it works

1. **Detect the OS** and build a list of plausible data roots
   (`Application Support`, `.config`, `.local/share`, `%APPDATA%`, etc).
2. **Search each root** for the tool's known folder name(s).
3. **Read the storage** - JSONL line-by-line, SQLite via a read-only
   connection (so a running app never blocks us), or JSON trees, depending
   on the tool.
4. **Normalize** whatever's found into the `messages[]` schema above.
5. **Write JSONL**, one conversation per line, into `extracted_data/`.

Nothing here ever opens a database for writing, and every reader is wrapped
so that one corrupt or locked file can't take down the whole run - you'll
get a partial result and move on, not a stack trace.

### A note on Cursor, Windsurf, and Trae

None of these publish their storage schema, and it has changed multiple
times (Cursor alone has gone through at least three shapes: workspace
`ItemTable` chat, inline composer, and split `bubbleId` composer). The
`cursor.py` extractor implements all three known shapes explicitly.
`windsurf.py` and `trae.py` instead use a **generic heuristic**
(`extractors/common.py::heuristic_extract_chat_from_kv`) that scans
chat-related keys and walks the parsed JSON looking for objects shaped like
a role + text pair. It's honest best-effort, not a documented format - if
a future version changes shape and stops matching, that's expected; adjust
`KEY_HINTS` in the relevant file or send a PR.

### A note on Aider

Aider has no central session store - every project directory gets its own
`.aider.chat.history.md`. By default this toolkit scans your home directory
plus a handful of common project-root names (`projects`, `code`, `dev`,
`repos`, `workspace`, `src`, `Documents`) up to 5 directories deep, skipping
`node_modules`, `.git`, and similar. If your projects live somewhere else,
point at them directly:

```bash
python extract.py --sources aider --search-path ~/client-work --search-path /mnt/data/repos
```

## Extending it: adding a new source

Every extractor is a small module with the same two-function interface -
copy the simplest one (`continue_ext.py` is a good template) and fill in:

```python
DISPLAY_NAME = "My Tool"
SOURCE_ID = "my_tool"

def find_installations(extra_paths: list[Path] | None = None) -> list[Path]:
    """Return the directories/files worth scanning."""

def extract(installations: list[Path]) -> list[dict]:
    """Return a list of conversation dicts matching the schema above."""
```

Then register it in `extract.py`'s `REGISTRY` list. `extractors/common.py`
has the SQLite/JSON/JSONL readers and the two generic heuristics you'll
probably want.

## Privacy & security

This extracts data from tools running under your own user account. Before
sharing or training on it:

1. **Scan for secrets**:
   ```bash
   pip install detect-secrets --break-system-packages
   detect-secrets scan extracted_data/*.jsonl
   ```
2. **Review for proprietary code, API keys, and personal file paths** -
   `code_context` and `tool_use` fields are the most likely places to find them.
3. **Don't commit `extracted_data/` to a public repo** (it's already in
   `.gitignore`). Keep it on encrypted storage if it contains client or
   proprietary work.

## Training use cases

```python
from datasets import load_dataset

dataset = load_dataset("json", data_files="extracted_data/*.jsonl", split="train")
dataset = dataset.filter(lambda x: any(m["role"] == "assistant" for m in x["messages"]))

def format_chat(example):
    return {"text": tokenizer.apply_chat_template(example["messages"], tokenize=False)}

dataset = dataset.map(format_chat)
```

## Troubleshooting

**"No installation found"** - the tool either isn't installed, has no chat
history yet, or lives somewhere nonstandard. Pass `--search-path` to point
at it directly, or check `extractors/<tool>.py`'s `SEARCH_DIRS` /
`APP_DIR_NAMES` constant and add your path there.

**Cursor/Windsurf database locked** - reads are opened `mode=ro` specifically
so a running editor won't block extraction, but if you still see errors,
close the app and re-run.

**Windsurf/Trae found an installation but 0 conversations** - the heuristic
key-matching in `common.heuristic_extract_chat_from_kv` didn't recognize the
current storage keys. Run `--list` to confirm the app dir was found, then
inspect `state.vscdb`'s `ItemTable`/`cursorDiskKV` keys directly
(`sqlite3 state.vscdb "SELECT key FROM ItemTable"`) and add matches to
`KEY_HINTS`.

## Disclaimer

This toolkit extracts **your own** data from AI tools installed on your own
machine. You're responsible for:

- having the rights to the extracted data,
- handling any sensitive/proprietary information appropriately,
- complying with each tool's Terms of Service,
- scanning for secrets before sharing or training on the output.

## License

MIT - use freely, including for training ML models.
