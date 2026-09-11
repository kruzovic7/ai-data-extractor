from __future__ import annotations

import argparse
import sys
from pathlib import Path

from extractors import extract
from extractors import common
from extractors import (
    claude_code, codex, cursor, windsurf, trae,
    continue_ext, gemini, opencode, cline, aider,
)

REGISTRY = [
    claude_code, codex, cursor, windsurf, trae,
    continue_ext, gemini, opencode, cline, aider,
]
BY_ID = {m.SOURCE_ID: m for m in REGISTRY}


extract.run_sync()

def interactive_select() -> list[str]:
    common.heading("Select data sources to extract")
    for i, m in enumerate(REGISTRY, 1):
        print(f"  [{i:>2}] {m.DISPLAY_NAME}")
    print()
    print("Enter numbers separated by commas (e.g. 1,3,5), 'a' for all, or 'q' to quit.")
    try:
        raw = input("> ").strip().lower()
    except EOFError:
        return []

    if raw in ("q", "quit", "exit"):
        sys.exit(0)
    if raw in ("a", "all"):
        return [m.SOURCE_ID for m in REGISTRY]

    chosen = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if not tok.isdigit() or not (1 <= int(tok) <= len(REGISTRY)):
            common.warn(f"Ignoring invalid selection: {tok!r}")
            continue
        chosen.append(REGISTRY[int(tok) - 1].SOURCE_ID)
    return chosen


def run_source(source_id: str, output_dir: Path, extra_paths: list[Path],
                dry_run: bool = False) -> common.ExtractorResult:
    module = BY_ID[source_id]
    result = common.ExtractorResult(source_id=source_id, display_name=module.DISPLAY_NAME)

    try:
        installations = module.find_installations(extra_paths=extra_paths or None)
    except Exception as exc:  # never let one bad tool kill the whole run
        result.error = f"discovery failed: {exc}"
        return result

    result.installations_found = len(installations)
    if not installations or dry_run:
        return result

    try:
        conversations = module.extract(installations)
    except Exception as exc:
        result.error = f"extraction failed: {exc}"
        return result

    result.conversations = conversations
    if conversations:
        result.output_path = common.write_jsonl(conversations, output_dir, f"{source_id}_conversations")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract local chat history from AI coding assistants into JSONL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--all", action="store_true", help="Extract every supported source.")
    parser.add_argument(
        "--sources", type=str, default=None,
        help="Comma-separated source ids, e.g. cursor,claude_code. "
             f"Available: {', '.join(m.SOURCE_ID for m in REGISTRY)}",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Only report what installations were found for each selected source; don't extract.",
    )
    parser.add_argument(
        "--output-dir", type=str, default="extracted_data",
        help="Directory to write JSONL output into (default: ./extracted_data)",
    )
    parser.add_argument(
        "--search-path", action="append", default=[],
        help="Extra directory to search, in addition to the usual OS locations. "
             "Most useful for Aider (project roots) and nonstandard install locations. "
             "Can be passed multiple times.",
    )
    parser.add_argument(
        "--merge", action="store_true",
        help="After extracting, also write a combined all_conversations.jsonl",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    extra_paths = [Path(p).expanduser() for p in args.search_path]

    if args.all:
        source_ids = [m.SOURCE_ID for m in REGISTRY]
    elif args.sources:
        source_ids = []
        for s in args.sources.split(","):
            s = s.strip()
            if s not in BY_ID:
                common.error(f"Unknown source: {s!r}. Available: {', '.join(BY_ID)}")
                sys.exit(1)
            source_ids.append(s)
    else:
        source_ids = interactive_select()

    if not source_ids:
        common.warn("Nothing selected, exiting.")
        return

    common.heading("Scanning" if args.list else "Extracting")
    results = []
    for source_id in source_ids:
        module = BY_ID[source_id]
        print(f"\n{module.DISPLAY_NAME}:")
        result = run_source(source_id, output_dir, extra_paths, dry_run=args.list)
        results.append(result)

        if result.error:
            common.error(result.error)
            continue
        if result.installations_found == 0:
            common.warn("No installation found.")
            continue
        common.success(f"{result.installations_found} installation location(s) found.")
        if args.list:
            continue
        if result.output_path:
            common.success(f"{len(result.conversations)} conversation(s) -> {result.output_path}")
        else:
            common.warn("Installation found, but no conversations could be parsed.")

    if args.list:
        return

    common.heading("Summary")
    total = 0
    for r in results:
        if r.output_path:
            n = len(r.conversations)
            total += n
            print(f"  {r.display_name:<20} {n:>5} conversations  ->  {r.output_path.name}")
    print(f"\nTotal: {total} conversations written to {output_dir}/")

    if args.merge and total > 0:
        merged_path = output_dir / "all_conversations.jsonl"
        with open(merged_path, "w", encoding="utf-8") as out_f:
            for r in results:
                if not r.output_path:
                    continue
                with open(r.output_path, "r", encoding="utf-8") as in_f:
                    out_f.write(in_f.read())
        common.success(f"Merged into {merged_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        common.warn("Interrupted.")
        sys.exit(130)
