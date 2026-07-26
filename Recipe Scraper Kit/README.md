# Cookbook Markdown Recipe Scraper

This version writes recipes directly in the format used by Haley's GitHub Pages cookbook.

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

Each Markdown file contains:

- YAML frontmatter matching the current cookbook fields;
- a description when supplied by the source;
- `## Ingredients`;
- `## Preparation`;
- `## Personal Notes`.

The script also updates `recipes/recipe-index.json`, so newly scraped recipes appear on the website after committing and pushing.

## Setup on Windows

Open PowerShell in this scraper-kit folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Using the virtual environment's Python directly avoids PowerShell execution-policy problems.

## Add URLs

Put one direct recipe-page URL per line in `urls.txt`.

## Scrape directly into the cookbook repository

```powershell
Set-Location "C:\Users\haley\OneDrive\Desktop\Cookbook\Recipe Scraper Kit"

.\.venv\Scripts\python.exe .\recipe_scraper_markdown.py .\urls.txt `
  --cookbook-root "C:\Users\haley\OneDrive\Desktop\Cookbook"
```

This creates the Markdown files in `Cookbook\recipes`, saves images in `Cookbook\assets`, and updates the recipe index.

## Override the inferred category

The automatic category is a best-effort classification. For a batch that belongs to one known category:

```powershell
.\.venv\Scripts\python.exe .\recipe_scraper_markdown.py .\urls.txt `
  --cookbook-root "C:\Users\haley\OneDrive\Desktop\Cookbook" `
  --category "Soups, Stews, and Chili"
```

## Add tags to the whole batch

```powershell
.\.venv\Scripts\python.exe .\recipe_scraper_markdown.py .\urls.txt `
  --cookbook-root "C:\Users\haley\OneDrive\Desktop\Cookbook" `
  --tag "weeknight" `
  --tag "good leftovers"
```

## Existing filenames

By default, a duplicate slug receives `-2`, `-3`, and so on rather than overwriting an existing recipe. Use `--overwrite` only when intentionally replacing the file with the same slug.

## After scraping

Review the new Markdown files, especially:

- category;
- tags;
- ingredient completeness;
- preparation steps;
- image;
- source URL.

Then commit and push:

```powershell
git status
git add recipes assets scrape_log.csv scrape_failures.csv
git commit -m "Add scraped recipes"
git push
```

## Limits

- Works best on sites publishing Schema.org `Recipe` JSON-LD.
- Does not bypass logins, paywalls, CAPTCHAs, robots.txt restrictions, or anti-bot systems.
- JavaScript-only sites may not expose recipe data in the initial HTML.
- Category and tags are inferred and should be reviewed.
- Always verify ingredients and instructions before cooking.
