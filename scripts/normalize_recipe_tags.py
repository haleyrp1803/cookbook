#!/usr/bin/env python3
"""Normalize recipe frontmatter tags conservatively and consistently."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "recipes"

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


def parse_frontmatter(frontmatter):
    metadata = {}
    current = None
    for line in frontmatter.splitlines():
        if line.startswith("  - ") and current:
            metadata[current].append(line[4:].strip().strip('"'))
        elif ":" in line:
            key, value = line.split(":", 1)
            current = key.strip() if not value.strip() else None
            metadata[key.strip()] = [] if current else value.strip().strip('"')
    return metadata

def yaml_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'

def normalize_file(path):
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"{path.name}: invalid frontmatter")
    closing = text.index("\n---\n", 4)
    front = text[4:closing]
    body = text[closing + 5:]
    metadata = parse_frontmatter(front)
    tags = metadata.get("tags", [])
    if isinstance(tags, str): tags = [tags]
    normalized = normalize_tags(tags, title=metadata.get("title", ""), category=metadata.get("category", ""))
    lines = front.splitlines()
    start = next((i for i,l in enumerate(lines) if l.startswith("tags:")), None)
    if start is None: return False
    end = start + 1
    while end < len(lines) and lines[end].startswith("  - "): end += 1
    replacement = ["tags:"] + [f"  - {yaml_quote(tag)}" for tag in normalized]
    updated = "---\n" + "\n".join(lines[:start] + replacement + lines[end:]) + "\n---\n" + body.lstrip("\n")
    changed = updated != text
    if changed: path.write_text(updated, encoding="utf-8")
    return changed

def main():
    changed = 0
    for path in sorted(RECIPES.glob("*.md")):
        changed += int(normalize_file(path))
    print(f"Normalized tags in {changed} recipe files.")

if __name__ == "__main__": main()
