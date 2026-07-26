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


## Library sorting and tag maintenance

The library can be sorted by title, date added, total time, or source rating. Search, category, tag, and sort selections remain active while a recipe is open.

Recipe tags use a conservative normalized vocabulary. To normalize frontmatter tags after manual imports, run:

```powershell
py .\scripts\normalize_recipe_tags.py
py .\scripts\build_recipe_index.py
```

The scraper applies the same normalization rules to newly imported recipes. Review new tags as part of the normal import audit; dietary tags should not be inferred unless the source explicitly supports them.


## Reader layout and accessibility

The recipe image and At a Glance card are ordinary document content. They are neither fixed nor sticky, and they do not create a nested scrolling region; they move out of view naturally as the page scrolls.

On wide and intermediate desktop layouts, the recipe-list rail can be shown or hidden from the open recipe. On screens 850 pixels wide or narrower, the rail is omitted from reader view so the currently opened recipe appears immediately below the site header. The All recipes control returns to the full library.

Opening a recipe moves keyboard focus to its title. Returning to the library restores focus to the recipe card that was opened when that card remains in the current filtered result set. Loading states, errors, and result counts are exposed to assistive technology.
