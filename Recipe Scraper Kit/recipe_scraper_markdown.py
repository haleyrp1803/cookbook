#!/usr/bin/env python3
"""Cookbook-aware recipe scraper.

Extracts Schema.org Recipe JSON-LD from direct recipe-page URLs and writes:

    <cookbook root>/recipes/<recipe-slug>.md
    <cookbook root>/assets/<recipe-slug>.<image extension>
    <cookbook root>/recipes/recipe-index.json

The Markdown structure matches Haley's GitHub Pages cookbook:
YAML frontmatter, description, Ingredients, Preparation, and Personal Notes.

The script does not bypass logins, paywalls, CAPTCHAs, robots.txt, or
anti-bot systems. Always review scraped recipes before cooking or publishing.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import mimetypes
import re
import sys
import time
import subprocess
from datetime import date
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "PersonalCookbookRecipeScraper/2.0 "
    "(personal-use recipe organizer; replace-contact@example.com)"
)
MAX_IMAGE_BYTES = 25 * 1024 * 1024
LOGGER = logging.getLogger("cookbook_recipe_scraper")


@dataclass
class Recipe:
    source_url: str
    title: str
    description: str
    author: str
    image_url: str
    prep_time: str
    cook_time: str
    total_time: str
    servings: str
    source_category: str
    cuisine: str
    keywords: list[str]
    ingredients: list[str]
    instructions: list[str]
    rating: str
    rating_count: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape recipe pages into the Markdown format used by Haley's cookbook."
    )
    parser.add_argument("url_file", type=Path, help="Text file with one direct recipe URL per line.")
    parser.add_argument(
        "--cookbook-root",
        type=Path,
        default=Path("scraped_cookbook_import"),
        help=(
            "Cookbook root containing recipes/ and assets/. "
            "Default: ./scraped_cookbook_import"
        ),
    )
    parser.add_argument(
        "--category",
        default="",
        help="Override the cookbook category for every URL in this run.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Add a tag to every recipe. Repeat --tag for multiple tags.",
    )
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between page requests.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Read timeout in seconds.")
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="Skip robots.txt checking. Use only when you have permission.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing Markdown file and image with the same slug.",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Do not update recipes/recipe-index.json.",
    )
    return parser.parse_args()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    text = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = clean_text(item)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def slugify(text: str) -> str:
    value = clean_text(text).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:90] or "recipe"


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def load_urls(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"URL file not found: {path}")
    values = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        if not url.startswith(("http://", "https://")):
            LOGGER.warning("Skipping non-URL line: %s", url)
            continue
        values.append(url)
    return unique(values)


def robots_allows(url: str, timeout: float) -> tuple[bool, str]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = requests.get(
            robots_url,
            headers={"User-Agent": USER_AGENT},
            timeout=(10, timeout),
        )
        if response.status_code >= 400:
            return True, f"robots.txt returned HTTP {response.status_code}"
        parser.parse(response.text.splitlines())
        return parser.can_fetch(USER_AGENT, url), robots_url
    except requests.RequestException as exc:
        return True, f"robots.txt check failed: {exc}"


def fetch_html(session: requests.Session, url: str, timeout: float) -> tuple[str, str]:
    response = session.get(url, timeout=(10, timeout), allow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if "html" not in content_type.lower() and not response.text.lstrip().startswith("<"):
        raise ValueError(f"Expected HTML, received {content_type or 'unknown content type'}")
    return response.text, response.url


def iter_jsonld(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, dict):
        yield data
        if isinstance(data.get("@graph"), list):
            for item in data["@graph"]:
                yield from iter_jsonld(item)
    elif isinstance(data, list):
        for item in data:
            yield from iter_jsonld(item)


def is_recipe_type(value: Any) -> bool:
    if isinstance(value, str):
        return value.casefold() == "recipe"
    if isinstance(value, list):
        return any(is_recipe_type(item) for item in value)
    return False


def extract_candidates(soup: BeautifulSoup) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for node in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = (node.string or node.get_text() or "").strip()
        if not raw:
            continue
        raw = re.sub(r"^\s*<!--|-->\s*$", "", raw)
        raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for obj in iter_jsonld(parsed):
            if is_recipe_type(obj.get("@type")):
                candidates.append(obj)
    return candidates


def candidate_score(candidate: dict[str, Any]) -> int:
    score = 0
    for key, weight in {
        "name": 2,
        "recipeIngredient": 8,
        "recipeInstructions": 8,
        "image": 2,
        "recipeYield": 1,
        "totalTime": 1,
    }.items():
        if candidate.get(key):
            score += weight
    ingredients = candidate.get("recipeIngredient")
    if isinstance(ingredients, list):
        score += min(len(ingredients), 15)
    return score


def extract_author(value: Any) -> str:
    if isinstance(value, dict):
        return clean_text(value.get("name"))
    if isinstance(value, list):
        return ", ".join(filter(None, (extract_author(item) for item in value)))
    return clean_text(value)


def extract_image_url(value: Any, base_url: str) -> str:
    urls: list[str] = []
    def walk(item: Any) -> None:
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict):
            for key in ("url", "contentUrl", "thumbnailUrl"):
                if item.get(key):
                    walk(item[key])
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return urljoin(base_url, clean_text(urls[0])) if urls else ""


def fallback_image(soup: BeautifulSoup, base_url: str) -> str:
    for selector, attr in [
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
        ('link[rel="image_src"]', "href"),
    ]:
        node = soup.select_one(selector)
        if node and node.get(attr):
            return urljoin(base_url, clean_text(node.get(attr)))
    return ""


def flatten_instructions(value: Any) -> list[str]:
    steps: list[str] = []
    def walk(item: Any) -> None:
        if isinstance(item, str):
            steps.extend(x.strip() for x in re.split(r"(?:\r?\n)+", clean_text(item)) if x.strip())
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, dict):
            item_type = item.get("@type")
            if item_type == "HowToSection":
                name = clean_text(item.get("name"))
                if name:
                    steps.append(f"[{name}]")
                walk(item.get("itemListElement"))
            else:
                text = clean_text(item.get("text") or item.get("name"))
                if text:
                    steps.append(text)
                if item.get("itemListElement"):
                    walk(item.get("itemListElement"))
    walk(value)
    return unique(steps)


def parse_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        return unique(value)
    text = clean_text(value)
    return unique(re.split(r"[,;|]", text)) if text else []


def first_or_joined(value: Any) -> str:
    if isinstance(value, list):
        parts = unique(clean_text(item) for item in value)
        if len(parts) >= 2 and parts[1].casefold().startswith(parts[0].casefold()):
            return parts[1]
        return ", ".join(parts)
    return clean_text(value)


def parse_rating(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return "", ""
    return (
        clean_text(value.get("ratingValue")),
        clean_text(value.get("ratingCount") or value.get("reviewCount")),
    )


def parse_recipe(data: dict[str, Any], source_url: str, soup: BeautifulSoup) -> Recipe:
    ingredients_raw = data.get("recipeIngredient") or data.get("ingredients") or []
    if isinstance(ingredients_raw, str):
        ingredients = [x.strip() for x in ingredients_raw.splitlines() if x.strip()]
    else:
        ingredients = unique(clean_text(x) for x in ingredients_raw)
    rating, rating_count = parse_rating(data.get("aggregateRating"))
    image_url = extract_image_url(data.get("image"), source_url) or fallback_image(soup, source_url)
    return Recipe(
        source_url=source_url,
        title=clean_text(data.get("name")) or clean_text(soup.title.string if soup.title else ""),
        description=clean_text(data.get("description")),
        author=extract_author(data.get("author")),
        image_url=image_url,
        prep_time=clean_text(data.get("prepTime")),
        cook_time=clean_text(data.get("cookTime")),
        total_time=clean_text(data.get("totalTime")),
        servings=first_or_joined(data.get("recipeYield")),
        source_category=clean_text(data.get("recipeCategory")),
        cuisine=first_or_joined(data.get("recipeCuisine")),
        keywords=parse_keywords(data.get("keywords")),
        ingredients=ingredients,
        instructions=flatten_instructions(data.get("recipeInstructions")),
        rating=rating,
        rating_count=rating_count,
    )


def infer_cookbook_category(recipe: Recipe) -> str:
    haystack = " ".join([
        recipe.title,
        recipe.source_category,
        recipe.description,
        " ".join(recipe.keywords),
    ]).casefold()
    rules = [
        ("Breakfast and Smoothie Bowls", ["breakfast", "smoothie bowl", "shakshuka"]),
        ("Cookies and Other Desserts", ["cookie", "tiramisu", "dessert", "brownie", "bar recipe"]),
        ("Cakes, Quick Breads, and Muffins", ["cake", "muffin", "banana bread", "quick bread", "pound cake", "bundt"]),
        ("Soups, Stews, and Chili", ["soup", "stew", "chili"]),
        ("Curries", ["curry", "tikka masala"]),
        ("Salads", ["salad", "coleslaw"]),
        ("Pasta, Noodles, Gnocchi, and Orzo", ["pasta", "noodle", "gnocchi", "orzo", "mac and cheese", "cacio e pepe"]),
        ("Rice, Grain Dishes, and Bowls", ["rice", "risotto", "paella", "bibimbap", "sushi bowl", "grain bowl", "katsu bowl"]),
        ("Pies, Casseroles, and Bakes", ["pie", "casserole", "lasagna", "bake"]),
        ("Sandwiches, Quesadillas, and Sliders", ["sandwich", "quesadilla", "slider", "taco", "wrap"]),
        ("Chicken and Meat Mains", ["chicken", "beef", "pork", "sausage", "meatball"]),
        ("Vegetables and Side Dishes", ["vegetable", "broccoli", "cauliflower", "potato", "brussels", "side dish"]),
    ]
    for category, terms in rules:
        if any(term in haystack for term in terms):
            return category
    return "Uncategorized"


def infer_tags(recipe: Recipe, category: str, extra_tags: list[str]) -> list[str]:
    raw = [*recipe.keywords]
    if recipe.cuisine:
        raw.extend(re.split(r"[,;|]", recipe.cuisine))
    raw.append(category.casefold())
    raw.extend(extra_tags)

    haystack = " ".join([
        recipe.title,
        recipe.description,
        recipe.source_category,
        recipe.cuisine,
        " ".join(recipe.keywords),
        " ".join(recipe.ingredients),
    ]).casefold()
    for label, terms in [
        ("vegan", ["vegan"]),
        ("vegetarian", ["vegetarian"]),
        ("gluten-free", ["gluten-free", "gluten free"]),
        ("contains chicken", ["chicken"]),
        ("contains beef", ["beef", "steak"]),
        ("contains pork", ["pork", "ham", "bacon", "sausage"]),
        ("contains seafood", ["salmon", "shrimp", "tuna", "seafood", "fish"]),
        ("eggs", [" egg", "eggs"]),
        ("tomatoes", ["tomato"]),
        ("beans", ["bean"]),
        ("chickpeas", ["chickpea"]),
        ("lentils", ["lentil"]),
        ("potatoes", ["potato"]),
        ("sweet potatoes", ["sweet potato"]),
        ("broccoli", ["broccoli"]),
        ("cauliflower", ["cauliflower"]),
        ("squash", ["squash", "pumpkin"]),
        ("mushrooms", ["mushroom"]),
    ]:
        if any(term in haystack for term in terms):
            raw.append(label)
    return [x.casefold() for x in unique(raw)]


def infer_extension(response: requests.Response, image_url: str) -> str:
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    known = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if content_type in known:
        return known[content_type]
    suffix = Path(urlparse(image_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return mimetypes.guess_extension(content_type) or ".jpg"


def download_image(
    session: requests.Session,
    image_url: str,
    destination_stem: Path,
    referer: str,
    timeout: float,
) -> Path | None:
    if not image_url:
        return None
    with session.get(
        image_url,
        headers={"Referer": referer},
        timeout=(10, timeout),
        stream=True,
        allow_redirects=True,
    ) as response:
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if not content_type.lower().startswith("image/"):
            raise ValueError(f"Image URL returned {content_type or 'non-image content'}")
        suffix = infer_extension(response, image_url)
        destination = destination_stem.with_suffix(suffix)
        total = 0
        with destination.open("wb") as handle:
            for chunk in response.iter_content(64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise ValueError("Image exceeded 25 MB")
                handle.write(chunk)
    return destination


def write_markdown(
    recipe: Recipe,
    category: str,
    tags: list[str],
    image_path: Path | None,
    destination: Path,
) -> None:
    image_reference = f"assets/{image_path.name}" if image_path else ""
    lines = [
        "---",
        f"title: {yaml_quote(recipe.title)}",
        f"category: {yaml_quote(category)}",
        "tags:",
    ]
    if tags:
        lines.extend(f"  - {yaml_quote(tag)}" for tag in tags)
    else:
        lines.append('  - "review tags"')
    lines.extend([
        f"source: {yaml_quote(recipe.source_url)}",
        f"servings: {yaml_quote(recipe.servings)}",
        f"prep_time: {yaml_quote(recipe.prep_time)}",
        f"cook_time: {yaml_quote(recipe.cook_time)}",
        f"total_time: {yaml_quote(recipe.total_time)}",
        f"rating: {yaml_quote(recipe.rating)}",
        f"image: {yaml_quote(image_reference)}",
        f"added_date: {yaml_quote(date.today().isoformat())}",
        "---",
    ])
    if recipe.description:
        lines.extend([recipe.description, ""])
    lines.extend(["## Ingredients", ""])
    lines.extend(f"- {item}" for item in recipe.ingredients) if recipe.ingredients else lines.append("- [No ingredient list extracted]")
    lines.extend(["", "## Preparation", ""])
    if recipe.instructions:
        number = 0
        for instruction in recipe.instructions:
            if instruction.startswith("[") and instruction.endswith("]"):
                lines.extend([f"### {instruction[1:-1]}", ""])
            else:
                number += 1
                lines.append(f"{number}. {instruction}")
    else:
        lines.append("1. [No preparation steps extracted]")
    lines.extend([
        "",
        "## Personal Notes",
        "",
        "- Date tried:",
        "- Rating:",
        "- Make again:",
        "- Changes for next time:",
        "",
    ])
    destination.write_text("\n".join(lines), encoding="utf-8")


def update_index(cookbook_root: Path) -> None:
    script = cookbook_root / "scripts" / "build_recipe_index.py"
    if not script.exists():
        raise FileNotFoundError(
            "Missing scripts/build_recipe_index.py; the cookbook index could not be updated."
        )
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=cookbook_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout.strip():
        LOGGER.info(result.stdout.strip())
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Recipe index generation failed")


def append_csv(path: Path, headers: list[str], row: dict[str, Any]) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def next_available_slug(base: str, recipes_dir: Path, overwrite: bool) -> str:
    if overwrite or not (recipes_dir / f"{base}.md").exists():
        return base
    number = 2
    while (recipes_dir / f"{base}-{number}.md").exists():
        number += 1
    return f"{base}-{number}"


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        urls = load_urls(args.url_file)
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 2
    if not urls:
        LOGGER.error("No valid URLs found.")
        return 2

    root = args.cookbook_root.resolve()
    recipes_dir = root / "recipes"
    assets_dir = root / "assets"
    recipes_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    failures = root / "scrape_failures.csv"
    log = root / "scrape_log.csv"

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
    })

    successful = 0
    for position, url in enumerate(urls, 1):
        LOGGER.info("[%d/%d] %s", position, len(urls), url)
        if not args.ignore_robots:
            allowed, note = robots_allows(url, args.timeout)
            if not allowed:
                reason = f"Disallowed by robots.txt ({note})"
                append_csv(failures, ["url", "reason"], {"url": url, "reason": reason})
                LOGGER.warning("%s", reason)
                continue
        try:
            page_html, final_url = fetch_html(session, url, args.timeout)
            soup = BeautifulSoup(page_html, "html.parser")
            candidates = extract_candidates(soup)
            if not candidates:
                raise ValueError("No Schema.org Recipe JSON-LD found")
            recipe = parse_recipe(max(candidates, key=candidate_score), final_url, soup)
            if not recipe.title:
                raise ValueError("No recipe title extracted")
            base_slug = slugify(recipe.title)
            slug = next_available_slug(base_slug, recipes_dir, args.overwrite)
            markdown_path = recipes_dir / f"{slug}.md"
            if args.overwrite and markdown_path.exists():
                markdown_path.unlink()
                for old in assets_dir.glob(f"{slug}.*"):
                    old.unlink()

            image_path = None
            image_error = ""
            try:
                image_path = download_image(
                    session, recipe.image_url, assets_dir / slug, final_url, args.timeout
                )
            except Exception as exc:
                image_error = str(exc)
                LOGGER.warning("Image download failed: %s", exc)

            category = args.category.strip() or infer_cookbook_category(recipe)
            tags = infer_tags(recipe, category, args.tag)
            write_markdown(recipe, category, tags, image_path, markdown_path)
            append_csv(log, [
                "title", "source_url", "markdown_file", "image_file", "category",
                "ingredient_count", "instruction_count", "image_error"
            ], {
                "title": recipe.title,
                "source_url": final_url,
                "markdown_file": str(markdown_path.relative_to(root)),
                "image_file": str(image_path.relative_to(root)) if image_path else "",
                "category": category,
                "ingredient_count": len(recipe.ingredients),
                "instruction_count": len(recipe.instructions),
                "image_error": image_error,
            })
            successful += 1
            LOGGER.info("Saved recipes/%s.md", slug)
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            append_csv(failures, ["url", "reason"], {"url": url, "reason": reason})
            LOGGER.error("Failed: %s", reason)
        if position < len(urls):
            time.sleep(max(args.delay, 0))

    if successful and not args.no_index:
        update_index(root)
        LOGGER.info("Updated recipes/recipe-index.json")
    LOGGER.info("Finished: %d succeeded, %d failed", successful, len(urls) - successful)
    LOGGER.info("Output root: %s", root)
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
