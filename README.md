# Haley's Recipe Book

A focused personal cookbook published through GitHub Pages. Each recipe remains an editable Markdown source file; the browser loads a lightweight metadata/search index for the library and fetches a full recipe only when it is opened.

## Authoritative recipe source

Each recipe lives in `recipes/<recipe-name>.md`. The Markdown file remains authoritative for the recipe's metadata, ingredients, preparation, source, and personal notes.

The generated file `recipes/recipe-index.json` contains only the information needed to build and search the library efficiently:

- filename and stable ID;
- title, category, tags, and image path;
- normalized servings and timing values;
- source rating;
- date added;
- normalized searchable text.

It does **not** contain rendered recipe HTML. Full recipe Markdown is fetched only when a recipe is opened.

## Editing an existing recipe

Edit the corresponding Markdown file. Run the index builder when the change should affect library cards, filters, sorting, or search—for example, changes to:

- title, category, tags, image, servings, timing, rating, or date added;
- ingredients, preparation, or descriptive text that should be found through full-text search.

```powershell
Set-Location "C:\Users\haley\OneDrive\Desktop\Cookbook"
py .\scripts\build_recipe_index.py
```

A personal-note change that does not need to affect search can be committed without rebuilding the index.

## Adding, deleting, or renaming recipes

Always rebuild the index after adding, deleting, or renaming a recipe Markdown file:

```powershell
py .\scripts\build_recipe_index.py
```

Validate that the current index matches the recipe sources:

```powershell
py .\scripts\build_recipe_index.py --check
```

## Date-added policy

Recipes present during the Pass 1 migration use:

```text
2026-07-25
```

The scraper assigns the actual local calendar date when it creates a new recipe.

## File structure

```text
index.html
styles.css
app.js
assets/
recipes/
  recipe-index.json
  banana-bread.md
  ...
scripts/
  build_recipe_index.py
Recipe Scraper Kit/
  recipe_scraper_markdown.py
  ...
```

## Deployment

GitHub Pages publishes from the `main` branch and repository root. The root-level `.nojekyll` file ensures recipe Markdown is served without Jekyll transformation.


## Recipe URLs and navigation

Each recipe has a stable hash URL such as `#banana-bread`. Direct links and browser refreshes reopen that recipe. Browser Back and Forward move through recipe and library history, and returning to the library restores the previous grid scroll position. Previous/Next controls follow the currently filtered recipe set.
