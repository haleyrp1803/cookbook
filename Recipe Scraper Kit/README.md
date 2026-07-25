# Personal Recipe Scraper

## What it does

For each direct recipe-page URL, the script:

1. checks `robots.txt` unless you use `--ignore-robots`;
2. downloads the HTML;
3. extracts the page's Schema.org `Recipe` JSON-LD;
4. downloads the principal recipe image when accessible;
5. saves:
   - `recipe.json`
   - `recipe.md`
   - the downloaded image
6. creates `index.csv` and `failures.csv`.

The Markdown file is intended to be easy to copy into the Word cookbook template.

## Windows setup

Open PowerShell in this folder.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Add recipe URLs

Edit `urls.txt` and put one **direct recipe-post URL** on each line.

Pinterest pin URLs are usually less useful than the destination recipe URLs. Open the pin and copy the recipe site's URL.

## Run

```powershell
py recipe_scraper.py urls.txt
```

Custom output directory:

```powershell
py recipe_scraper.py urls.txt --output my_recipes
```

Overwrite existing recipe folders:

```powershell
py recipe_scraper.py urls.txt --overwrite
```

Slow the requests further:

```powershell
py recipe_scraper.py urls.txt --delay 4
```

## Limits

- It works best on sites publishing Schema.org `Recipe` JSON-LD.
- It does not bypass logins, paywalls, CAPTCHAs, or anti-bot systems.
- JavaScript-only pages may fail because the recipe data are not present in the initial HTML.
- Some image servers reject automated downloads even when the recipe text is available.
- Always inspect the extracted ingredient list and instructions before cooking.
- Replace the placeholder contact address in `USER_AGENT` with your own email if you plan to use the script regularly.

## Output example

```text
scraped_recipes/
├── index.csv
├── failures.csv
└── creamy-mushroom-orzo-a1b2c3d4/
    ├── recipe.json
    ├── recipe.md
    └── image.jpg
```
