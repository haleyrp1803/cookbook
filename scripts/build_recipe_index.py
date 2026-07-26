#!/usr/bin/env python3
"""Build the cookbook's lightweight searchable recipe index.

The browser uses recipes/recipe-index.json to render and search the library
without downloading every complete Markdown recipe at startup. Full Markdown
is fetched only when a recipe is opened.

Run this after changing indexed frontmatter/body search content, or after
adding, deleting, or renaming a recipe file. Ordinary edits that do not need to
appear in library search can be pushed without rebuilding the index.
"""
from __future__ import annotations

import argparse
import ast
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"
OUTPUT = RECIPES / "recipe-index.json"
REQUIRED_FIELDS = ("title", "category")
INDEX_VERSION = 2

TAG_ALIASES = {
    "gluten free": "gluten-free", "make ahead": "make-ahead", "main-dish": "main dish",
    "one pan": "one-pan", "one pot": "one-pot", "slow cooker": "slow-cooker",
    "low carb": "low-carb", "low sodium": "low-sodium", "dairy free": "dairy-free",
    "dairy free main course": "dairy-free", "dairy-free latte": "dairy-free",
    "dariy-free latte": "dairy-free", "contains chicken": "chicken",
    "contains beef": "beef", "contains pork": "pork", "contains sausage": "sausage",
    "contains seafood": "seafood", "american cuisine": "american",
    "american (us) cuisine": "american", "cajun cuisine": "cajun",
    "mediterranean cuisine": "mediterranean", "southern cuisine": "southern",
    "soul food cuisine": "southern", "italian cuisine": "italian",
    "european cuisine": "european", "chinese american": "chinese-american",
    "weeknight meals": "weeknight", "fall": "autumn", "drink": "beverage",
    "drinks": "beverage", "easy mockail": "mocktail", "easy mocktail": "mocktail",
}
TAG_DROP_PREFIXES = (
    "contentid:", "displaytype:", "issyndicated:", "locale:", "shorttitle:",
    "sponsored:", "subsection:", "totaltime:", "updated:", "filtertime:",
    "collection:", "content-type:", "category:", "nutrition:", "occasion:",
)
TAG_DROP_EXACT = {
    "uncategorized", "worldwide", "web", "general", "ingredient", "best",
    "publisher-tested", "receta", "easy recipe", "international",
}

def normalize_tags(values, *, title="", category=""):
    category_key = str(category or "").strip().casefold()
    title_key = str(title or "").strip().casefold()
    output = []
    for raw in values or []:
        raw_text = str(raw or "").strip().strip("[]'\\\"")
        raw_key = re.sub(r"\\s+", " ", raw_text).strip(" ,;|").casefold()
        if not raw_key or raw_key.startswith(TAG_DROP_PREFIXES) or raw_key == category_key:
            continue
        pieces = re.split(r"[,;|]", raw_text) if re.search(r"[,;|]", raw_text) else [raw_text]
        for piece in pieces:
            tag = re.sub(r"\\s+", " ", piece).strip(" []'\\\",;|").casefold()
            if not tag or tag.startswith(TAG_DROP_PREFIXES):
                continue
            tag = TAG_ALIASES.get(tag, tag)
            if tag in TAG_DROP_EXACT or tag == category_key or tag == title_key:
                continue
            if "recipe" in tag or tag.startswith(("how to ", "what is ")):
                continue
            if len(tag) > 40 or len(tag.split()) > 5:
                continue
            if tag not in output:
                output.append(tag)
    return output



def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        if value[0] == '"':
            try:
                return str(json.loads(value))
            except json.JSONDecodeError:
                pass
        return value[1:-1]
    return value


def split_frontmatter(text: str, filename: str) -> tuple[str, str]:
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise ValueError(f"{filename}: missing opening frontmatter delimiter")
    closing = normalized.find("\n---\n", 4)
    if closing == -1:
        raise ValueError(f"{filename}: missing closing frontmatter delimiter")
    return normalized[4:closing], normalized[closing + 5 :].strip()


def parse_frontmatter(frontmatter: str, filename: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    current_list: str | None = None
    for raw_line in frontmatter.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith("  - ") and current_list:
            metadata[current_list].append(unquote(raw_line[4:]))
            continue
        if ":" not in raw_line:
            raise ValueError(f"{filename}: invalid metadata line: {raw_line}")
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            metadata[key] = []
            current_list = key
        else:
            metadata[key] = unquote(value)
            current_list = None
    return metadata



def parse_listish(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple)):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (ValueError, SyntaxError):
            pass
    return [text] if text else []

def markdown_to_search_text(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^[#>*+-]+\s*", " ", text, flags=re.MULTILINE)
    text = re.sub(r"^\d+\.\s*", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[*_`~]", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip().casefold()


def parse_minutes(value: str) -> int | None:
    value = str(value or "").strip().casefold()
    if not value:
        return None
    iso = re.fullmatch(r"p(?:\d+d)?t(?:(\d+)h)?(?:(\d+)m)?", value, flags=re.IGNORECASE)
    if iso:
        return int(iso.group(1) or 0) * 60 + int(iso.group(2) or 0)
    total = 0
    found = False
    hours = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr|h)\b", value)
    minutes = re.search(r"(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|min|m)\b", value)
    if hours:
        total += round(float(hours.group(1)) * 60)
        found = True
    if minutes:
        total += round(float(minutes.group(1)))
        found = True
    if not found and re.fullmatch(r"\d+", value):
        return int(value)
    return total if found else None


def format_minutes(minutes: int | None) -> str:
    if minutes is None:
        return ""
    if minutes < 60:
        return f"{minutes} min"
    hours, remainder = divmod(minutes, 60)
    if not remainder:
        return f"{hours} hr"
    return f"{hours} hr {remainder} min"


def normalize_servings(value: str) -> str:
    parts = parse_listish(value)
    if len(parts) > 1:
        first = parts[0]
        second = parts[1]
        duplicate = re.fullmatch(rf"{re.escape(first)}\s*(.*)", second, flags=re.IGNORECASE)
        if duplicate and duplicate.group(1).strip():
            return f"{first} {duplicate.group(1).strip()}"
        if second == first:
            return first
        return ", ".join(parts)
    value = re.sub(r"\s+", " ", (parts[0] if parts else "")).strip(" ,")
    duplicate = re.fullmatch(r"(\d+(?:\.\d+)?)\s*,\s*\1\s*(.*)", value, flags=re.IGNORECASE)
    if duplicate:
        return f"{duplicate.group(1)} {duplicate.group(2).strip()}".strip()
    return value


def build_entry(path: Path) -> dict[str, Any]:
    frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8-sig"), path.name)
    metadata = parse_frontmatter(frontmatter, path.name)
    missing = [field for field in REQUIRED_FIELDS if not str(metadata.get(field, "")).strip()]
    if missing:
        raise ValueError(f"{path.name}: missing required field(s): {', '.join(missing)}")

    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [part.strip() for part in re.split(r"[;,]", tags) if part.strip()]
    elif not isinstance(tags, list):
        tags = []
    normalized_tags: list[str] = []
    for tag in tags:
        normalized_tags.extend(parse_listish(tag))
    tags = normalize_tags(
        normalized_tags,
        title=str(metadata.get("title", "")),
        category=str(metadata.get("category", "")),
    )

    prep_minutes = parse_minutes(str(metadata.get("prep_time", "")))
    cook_minutes = parse_minutes(str(metadata.get("cook_time", "")))
    total_minutes = parse_minutes(str(metadata.get("total_time", "")))
    if total_minutes is None and prep_minutes is not None and cook_minutes is not None:
        total_minutes = prep_minutes + cook_minutes

    title = str(metadata.get("title", "")).strip()
    category = str(metadata.get("category", "")).strip()
    searchable = " ".join(
        [title, category, " ".join(str(tag) for tag in tags), markdown_to_search_text(body)]
    ).casefold()

    return {
        "id": path.stem,
        "filename": path.name,
        "title": title,
        "category": category,
        "tags": [str(tag) for tag in tags],
        "image": str(metadata.get("image", "")).strip(),
        "servings": normalize_servings(str(metadata.get("servings", ""))),
        "prep_time": format_minutes(prep_minutes) or str(metadata.get("prep_time", "")).strip(),
        "cook_time": format_minutes(cook_minutes) or str(metadata.get("cook_time", "")).strip(),
        "total_time": format_minutes(total_minutes) or str(metadata.get("total_time", "")).strip(),
        "total_minutes": total_minutes,
        "rating": re.sub(r"\s+", " ", str(metadata.get("rating", ""))).strip(),
        "added_date": str(metadata.get("added_date", "")).strip(),
        "search_text": searchable,
    }


def build_payload() -> dict[str, Any]:
    paths = sorted(RECIPES.glob("*.md"), key=lambda item: item.name.casefold())
    if not paths:
        raise ValueError("No recipe Markdown files found.")
    entries = [build_entry(path) for path in paths]
    entries.sort(key=lambda item: (item["category"].casefold(), item["title"].casefold(), item["filename"]))
    return {"version": INDEX_VERSION, "recipe_count": len(entries), "recipes": entries}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the cookbook recipe metadata/search index.")
    parser.add_argument("--check", action="store_true", help="Validate that the existing index matches current sources.")
    args = parser.parse_args()
    try:
        payload = build_payload()
    except Exception as exc:
        print(f"Index build failed: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not OUTPUT.exists():
            print(f"Missing {OUTPUT.relative_to(ROOT)}", file=sys.stderr)
            return 1
        if OUTPUT.read_text(encoding="utf-8") != rendered:
            print("Recipe index is out of date.", file=sys.stderr)
            print(r"Run: py .\scripts\build_recipe_index.py", file=sys.stderr)
            return 1
        print(f"Recipe index is current ({payload['recipe_count']} recipes).")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {payload['recipe_count']} recipes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
