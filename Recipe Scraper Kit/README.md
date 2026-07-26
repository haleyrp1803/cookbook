# Cookbook Markdown Recipe Scraper

This scraper writes recipes directly into Haley's GitHub Pages cookbook format.

For each successful URL it creates:

```text
Cookbook/
├── recipes/
│   ├── recipe-name.md
│   └── recipe-index.json
├── assets/
│   └── recipe-name.jpg
├── scrape_log.csv
└── scrape_failures.csv
```

Each Markdown file contains YAML frontmatter, description, ingredients, preparation, and personal notes. New recipes receive an `added_date` using the calendar date on which the scraper runs. After a successful batch, the scraper calls the cookbook's `scripts/build_recipe_index.py`, so the new recipes and their searchable metadata appear on the website.

## Setup on Windows

```powershell
Set-Location "C:\Users\haley\OneDrive\Desktop\Cookbook\Recipe Scraper Kit"

py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The virtual environment does not need to be activated.

## Add URLs

Put one direct recipe-page URL per line in `urls.txt`.

## Scrape directly into the cookbook

```powershell
.\.venv\Scripts\python.exe .\recipe_scraper_markdown.py .\urls.txt `
  --cookbook-root "C:\Users\haley\OneDrive\Desktop\Cookbook"
```

## Override the inferred category

```powershell
.\.venv\Scripts\python.exe .\recipe_scraper_markdown.py .\urls.txt `
  --cookbook-root "C:\Users\haley\OneDrive\Desktop\Cookbook" `
  --category "Soups, Stews, and Chili"
```

## Add tags to the batch

```powershell
.\.venv\Scripts\python.exe .\recipe_scraper_markdown.py .\urls.txt `
  --cookbook-root "C:\Users\haley\OneDrive\Desktop\Cookbook" `
  --tag "weeknight" `
  --tag "good leftovers"
```

## Existing filenames

By default, a duplicate slug receives `-2`, `-3`, and so forth. Use `--overwrite` only when intentionally replacing the recipe with the same slug.

## After scraping

Review the new Markdown files, especially category, tags, ingredients, instructions, image, and source. The index has already been regenerated unless `--no-index` was supplied.

```powershell
Set-Location "C:\Users\haley\OneDrive\Desktop\Cookbook"

git status
git add recipes assets "Recipe Scraper Kit" scrape_log.csv scrape_failures.csv
git commit -m "Add scraped recipes"
git push
```

## Limits

- Works best with pages publishing Schema.org `Recipe` JSON-LD.
- Does not bypass logins, paywalls, CAPTCHAs, robots.txt restrictions, or anti-bot systems.
- JavaScript-only sites may not expose recipe data in initial HTML.
- Category and tags are inferred and should be reviewed.
- Always verify ingredients and instructions before cooking.
