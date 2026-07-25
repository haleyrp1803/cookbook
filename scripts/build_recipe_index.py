#!/usr/bin/env python3
"""Generate recipes/recipe-index.json from Markdown filenames.

Run this only after adding, deleting, or renaming recipe Markdown files.
Ordinary edits inside an existing recipe file do not require rebuilding.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
OUTPUT = RECIPES / "recipe-index.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the cookbook recipe filename index.")
    parser.add_argument("--check", action="store_true", help="Validate the existing index without rewriting it.")
    args = parser.parse_args()

    filenames = sorted(path.name for path in RECIPES.glob("*.md"))
    if not filenames:
        print("No recipe Markdown files found.", file=sys.stderr)
        return 1

    if args.check:
        if not OUTPUT.exists():
            print(f"Missing {OUTPUT.relative_to(ROOT)}", file=sys.stderr)
            return 1
        try:
            existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Invalid {OUTPUT.relative_to(ROOT)}: {exc}", file=sys.stderr)
            return 1
        if existing != filenames:
            print("Recipe index is out of date.", file=sys.stderr)
            print("Run: py .\\scripts\\build_recipe_index.py", file=sys.stderr)
            return 1
        print(f"Recipe index is current ({len(filenames)} files).")
        return 0

    OUTPUT.write_text(json.dumps(filenames, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(filenames)} recipe files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
