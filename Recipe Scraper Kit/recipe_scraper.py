#!/usr/bin/env python3
"""
recipe_scraper.py

Scrape recipe-card data and a principal image from a list of recipe URLs.

Primary extraction method:
    Schema.org Recipe data embedded as JSON-LD.

Outputs:
    output/
      index.csv
      failures.csv
      recipe-slug/
        recipe.json
        recipe.md
        image.jpg   (or png/webp, when available)

Usage:
    python recipe_scraper.py urls.txt
    python recipe_scraper.py urls.txt --output my_recipes
    python recipe_scraper.py urls.txt --delay 3 --ignore-robots

The script deliberately does not attempt to bypass logins, paywalls, CAPTCHAs,
or anti-bot systems. Some JavaScript-only sites will require manual entry or a
browser-automation version.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import logging
import mimetypes
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "PersonalRecipeOrganizer/1.0 "
    "(local personal-use recipe scraper; contact: replace-with-your-email@example.com)"
)
DEFAULT_TIMEOUT = (10, 30)
MAX_IMAGE_BYTES = 25 * 1024 * 1024

LOGGER = logging.getLogger("recipe_scraper")


@dataclass
class Recipe:
    source_url: str
    name: str
    description: str
    author: str
    image_url: str
    prep_time: str
    cook_time: str
    total_time: str
    yield_text: str
    category: str
    cuisine: str
    keywords: list[str]
    ingredients: list[str]
    instructions: list[str]
    rating_value: str
    rating_count: str
    nutrition: dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract recipe-card data and images from recipe URLs."
    )
    parser.add_argument(
        "url_file",
        type=Path,
        help="UTF-8 text file containing one recipe URL per line.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("scraped_recipes"),
        help="Output directory (default: scraped_recipes).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between page requests (default: 2.0).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Read timeout in seconds (default: 30).",
    )
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="Skip robots.txt checking. Use only when you have permission.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing recipe folders.",
    )
    return parser.parse_args()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    text = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def unique_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        cleaned = clean_text(item)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def slugify(text: str, fallback_url: str) -> str:
    text = clean_text(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text:
        text = "recipe"
    digest = hashlib.sha1(fallback_url.encode("utf-8")).hexdigest()[:8]
    return f"{text[:70]}-{digest}"


def load_urls(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"URL file not found: {path}")
    urls: list[str] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith(("http://", "https://")):
            LOGGER.warning("Skipping non-URL line: %s", line)
            continue
        urls.append(line)
    return unique_preserving_order(urls)


def robots_allows(url: str, user_agent: str, timeout: float) -> tuple[bool, str]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)

    try:
        response = requests.get(
            robots_url,
            headers={"User-Agent": user_agent},
            timeout=(10, timeout),
        )
        if response.status_code >= 400:
            # Missing/inaccessible robots.txt is treated as no explicit prohibition.
            return True, f"robots.txt returned HTTP {response.status_code}"
        parser.parse(response.text.splitlines())
        return parser.can_fetch(user_agent, url), robots_url
    except requests.RequestException as exc:
        return True, f"robots.txt check failed: {exc}"


def fetch_html(
    session: requests.Session,
    url: str,
    timeout: float,
) -> tuple[str, str]:
    response = session.get(
        url,
        timeout=(10, timeout),
        allow_redirects=True,
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "html" not in content_type.lower() and not response.text.lstrip().startswith("<"):
        raise ValueError(f"Expected HTML but received Content-Type: {content_type}")

    return response.text, response.url


def iter_jsonld_objects(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, dict):
        yield data
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from iter_jsonld_objects(item)
    elif isinstance(data, list):
        for item in data:
            yield from iter_jsonld_objects(item)


def is_recipe_type(value: Any) -> bool:
    if isinstance(value, str):
        return value.casefold() == "recipe"
    if isinstance(value, list):
        return any(is_recipe_type(item) for item in value)
    return False


def extract_jsonld_recipes(soup: BeautifulSoup) -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []

    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue

        raw = raw.strip()
        raw = re.sub(r"^\s*<!--|-->\s*$", "", raw)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Some pages contain several JSON objects or illegal control chars.
            repaired = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError:
                continue

        for obj in iter_jsonld_objects(parsed):
            if is_recipe_type(obj.get("@type")):
                recipes.append(obj)

    return recipes


def score_recipe_candidate(candidate: dict[str, Any]) -> int:
    score = 0
    for key, points in {
        "name": 2,
        "recipeIngredient": 5,
        "recipeInstructions": 5,
        "image": 2,
        "recipeYield": 1,
        "totalTime": 1,
    }.items():
        if candidate.get(key):
            score += points
    ingredients = candidate.get("recipeIngredient")
    if isinstance(ingredients, list):
        score += min(len(ingredients), 10)
    return score


def choose_recipe(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise ValueError("No Schema.org Recipe JSON-LD was found.")
    return max(candidates, key=score_recipe_candidate)


def extract_author(value: Any) -> str:
    if isinstance(value, dict):
        return clean_text(value.get("name"))
    if isinstance(value, list):
        return ", ".join(filter(None, (extract_author(item) for item in value)))
    return clean_text(value)


def extract_image_url(value: Any, base_url: str) -> str:
    candidates: list[str] = []

    def collect(item: Any) -> None:
        if isinstance(item, str):
            candidates.append(item)
        elif isinstance(item, dict):
            for key in ("url", "contentUrl", "thumbnailUrl"):
                if item.get(key):
                    collect(item[key])
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    candidates = [urljoin(base_url, clean_text(x)) for x in candidates if clean_text(x)]
    return candidates[0] if candidates else ""


def flatten_instructions(value: Any) -> list[str]:
    steps: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, str):
            text = clean_text(item)
            if text:
                # Preserve a paragraph as one step unless numbered separators exist.
                pieces = re.split(r"(?:\r?\n)+", text)
                steps.extend(piece.strip() for piece in pieces if piece.strip())
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, dict):
            item_type = item.get("@type")
            if item_type == "HowToSection":
                section_name = clean_text(item.get("name"))
                if section_name:
                    steps.append(f"[{section_name}]")
                walk(item.get("itemListElement"))
            else:
                text = item.get("text") or item.get("name")
                if text:
                    steps.append(clean_text(text))
                nested = item.get("itemListElement")
                if nested:
                    walk(nested)

    walk(value)
    return unique_preserving_order(steps)


def parse_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        return unique_preserving_order(clean_text(x) for x in value)
    text = clean_text(value)
    if not text:
        return []
    return unique_preserving_order(re.split(r"[,;|]", text))


def parse_rating(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return "", ""
    rating = clean_text(value.get("ratingValue"))
    count = clean_text(
        value.get("ratingCount")
        or value.get("reviewCount")
        or value.get("userInteractionCount")
    )
    return rating, count


def parse_nutrition(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, item in value.items():
        if key.startswith("@"):
            continue
        cleaned = clean_text(item)
        if cleaned:
            result[key] = cleaned
    return result


def fallback_meta_image(soup: BeautifulSoup, base_url: str) -> str:
    selectors = [
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
        ('link[rel="image_src"]', "href"),
    ]
    for selector, attr in selectors:
        node = soup.select_one(selector)
        if node and node.get(attr):
            return urljoin(base_url, clean_text(node.get(attr)))
    return ""


def recipe_from_jsonld(data: dict[str, Any], source_url: str, soup: BeautifulSoup) -> Recipe:
    rating_value, rating_count = parse_rating(data.get("aggregateRating"))
    image_url = extract_image_url(data.get("image"), source_url)
    if not image_url:
        image_url = fallback_meta_image(soup, source_url)

    ingredients_raw = data.get("recipeIngredient") or data.get("ingredients") or []
    if isinstance(ingredients_raw, str):
        ingredients = [line.strip() for line in ingredients_raw.splitlines() if line.strip()]
    else:
        ingredients = unique_preserving_order(clean_text(x) for x in ingredients_raw)

    return Recipe(
        source_url=source_url,
        name=clean_text(data.get("name")) or clean_text(soup.title.string if soup.title else ""),
        description=clean_text(data.get("description")),
        author=extract_author(data.get("author")),
        image_url=image_url,
        prep_time=clean_text(data.get("prepTime")),
        cook_time=clean_text(data.get("cookTime")),
        total_time=clean_text(data.get("totalTime")),
        yield_text=clean_text(data.get("recipeYield")),
        category=clean_text(data.get("recipeCategory")),
        cuisine=clean_text(data.get("recipeCuisine")),
        keywords=parse_keywords(data.get("keywords")),
        ingredients=ingredients,
        instructions=flatten_instructions(data.get("recipeInstructions")),
        rating_value=rating_value,
        rating_count=rating_count,
        nutrition=parse_nutrition(data.get("nutrition")),
    )


def infer_extension(response: requests.Response, image_url: str) -> str:
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    preferred = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type)
    if preferred:
        return preferred

    suffix = Path(urlparse(image_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if suffix == ".jpeg" else suffix

    guessed = mimetypes.guess_extension(content_type)
    return guessed or ".jpg"


def download_image(
    session: requests.Session,
    image_url: str,
    destination_without_suffix: Path,
    referer: str,
    timeout: float,
) -> Path | None:
    if not image_url:
        return None

    headers = {"Referer": referer}
    with session.get(
        image_url,
        headers=headers,
        timeout=(10, timeout),
        stream=True,
        allow_redirects=True,
    ) as response:
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if not content_type.lower().startswith("image/"):
            raise ValueError(f"Image URL returned non-image Content-Type: {content_type}")

        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_IMAGE_BYTES:
            raise ValueError("Image exceeds the 25 MB safety limit.")

        extension = infer_extension(response, image_url)
        destination = destination_without_suffix.with_suffix(extension)

        total = 0
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise ValueError("Image exceeded the 25 MB safety limit.")
                handle.write(chunk)

    return destination


def markdown_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|")


def write_markdown(recipe: Recipe, image_path: Path | None, destination: Path) -> None:
    lines: list[str] = [f"# {recipe.name}", ""]

    if image_path:
        lines.extend([f"![{markdown_escape(recipe.name)}]({image_path.name})", ""])

    facts = [
        ("Source", recipe.source_url),
        ("Author", recipe.author),
        ("Yield", recipe.yield_text),
        ("Prep time", recipe.prep_time),
        ("Cook time", recipe.cook_time),
        ("Total time", recipe.total_time),
        ("Category", recipe.category),
        ("Cuisine", recipe.cuisine),
        (
            "Rating",
            (
                f"{recipe.rating_value}"
                + (f" ({recipe.rating_count} ratings/reviews)" if recipe.rating_count else "")
            )
            if recipe.rating_value
            else "",
        ),
    ]

    for label, value in facts:
        if value:
            lines.append(f"**{label}:** {value}")
    lines.append("")

    if recipe.description:
        lines.extend([recipe.description, ""])

    lines.extend(["## Ingredients", ""])
    if recipe.ingredients:
        lines.extend(f"- {item}" for item in recipe.ingredients)
    else:
        lines.append("- [No ingredient list extracted]")
    lines.append("")

    lines.extend(["## Preparation", ""])
    if recipe.instructions:
        step_number = 0
        for instruction in recipe.instructions:
            if instruction.startswith("[") and instruction.endswith("]"):
                lines.extend([f"### {instruction[1:-1]}", ""])
            else:
                step_number += 1
                lines.append(f"{step_number}. {instruction}")
    else:
        lines.append("1. [No instructions extracted]")
    lines.append("")

    if recipe.nutrition:
        lines.extend(["## Nutrition supplied by source", ""])
        for key, value in recipe.nutrition.items():
            label = re.sub(r"(?<!^)(?=[A-Z])", " ", key).replace("Content", "").title()
            lines.append(f"- **{label}:** {value}")
        lines.append("")

    tags = unique_preserving_order(
        [recipe.category, recipe.cuisine, *recipe.keywords]
    )
    lines.extend(["## Tags", ""])
    lines.append("; ".join(tags) if tags else "[Add personal tags]")
    lines.append("")

    destination.write_text("\n".join(lines), encoding="utf-8")


def write_json(recipe: Recipe, image_path: Path | None, destination: Path) -> None:
    payload = asdict(recipe)
    payload["downloaded_image"] = image_path.name if image_path else ""
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_csv(path: Path, headers: list[str], row: dict[str, Any]) -> None:
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def process_url(
    session: requests.Session,
    url: str,
    output_dir: Path,
    timeout: float,
    overwrite: bool,
) -> dict[str, str]:
    page_html, final_url = fetch_html(session, url, timeout)
    soup = BeautifulSoup(page_html, "html.parser")

    candidates = extract_jsonld_recipes(soup)
    selected = choose_recipe(candidates)
    recipe = recipe_from_jsonld(selected, final_url, soup)

    folder = output_dir / slugify(recipe.name, final_url)
    if folder.exists() and not overwrite:
        raise FileExistsError(
            f"Output folder already exists: {folder}. Use --overwrite to replace it."
        )
    folder.mkdir(parents=True, exist_ok=True)

    image_path: Path | None = None
    image_error = ""
    if recipe.image_url:
        try:
            image_path = download_image(
                session,
                recipe.image_url,
                folder / "image",
                referer=final_url,
                timeout=timeout,
            )
        except Exception as exc:  # image failure should not discard recipe text
            image_error = str(exc)
            LOGGER.warning("Image download failed for %s: %s", final_url, exc)

    write_json(recipe, image_path, folder / "recipe.json")
    write_markdown(recipe, image_path, folder / "recipe.md")

    return {
        "name": recipe.name,
        "source_url": final_url,
        "folder": str(folder),
        "image_file": str(image_path) if image_path else "",
        "ingredient_count": str(len(recipe.ingredients)),
        "instruction_count": str(len(recipe.instructions)),
        "rating_value": recipe.rating_value,
        "rating_count": recipe.rating_count,
        "image_error": image_error,
    }


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        urls = load_urls(args.url_file)
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 2

    if not urls:
        LOGGER.error("No valid URLs found in %s", args.url_file)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    index_path = args.output / "index.csv"
    failures_path = args.output / "failures.csv"

    if args.overwrite:
        index_path.unlink(missing_ok=True)
        failures_path.unlink(missing_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
        }
    )

    index_headers = [
        "name",
        "source_url",
        "folder",
        "image_file",
        "ingredient_count",
        "instruction_count",
        "rating_value",
        "rating_count",
        "image_error",
    ]
    failure_headers = ["url", "reason"]

    for position, url in enumerate(urls, start=1):
        LOGGER.info("[%d/%d] %s", position, len(urls), url)

        if not args.ignore_robots:
            allowed, robots_note = robots_allows(url, USER_AGENT, args.timeout)
            if not allowed:
                reason = f"Disallowed by robots.txt ({robots_note})"
                LOGGER.warning("%s", reason)
                append_csv(failures_path, failure_headers, {"url": url, "reason": reason})
                continue

        try:
            result = process_url(
                session=session,
                url=url,
                output_dir=args.output,
                timeout=args.timeout,
                overwrite=args.overwrite,
            )
            append_csv(index_path, index_headers, result)
            LOGGER.info(
                "Saved %s (%s ingredients, %s instructions)",
                result["name"],
                result["ingredient_count"],
                result["instruction_count"],
            )
        except Exception as exc:
            LOGGER.error("Failed: %s", exc)
            append_csv(
                failures_path,
                failure_headers,
                {"url": url, "reason": f"{type(exc).__name__}: {exc}"},
            )

        if position < len(urls):
            time.sleep(max(args.delay, 0))

    LOGGER.info("Finished. Output: %s", args.output.resolve())
    if failures_path.exists():
        LOGGER.info("Review failures: %s", failures_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
