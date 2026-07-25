# Haley's Recipe Book

This is a static GitHub Pages cookbook whose recipe files are editable Markdown.

## Authoritative recipe source

Each recipe lives in `recipes/<recipe-name>.md`. The browser fetches and renders those Markdown files directly from GitHub Pages. Recipe content is no longer compiled into a large JavaScript bundle.

## Ordinary recipe edits

Edit an existing Markdown file, then commit and push:

```powershell
Set-Location "C:\Users\haley\OneDrive\Desktop\Cookbook"

git add recipes
git commit -m "Update recipe"
git push
```

No build command is needed when changing ingredients, instructions, notes, title, category, tags, timing, rating, source, or image metadata inside an existing recipe file.

## Adding, deleting, or renaming recipe files

The browser needs a filename manifest because GitHub Pages does not expose directory listings. After adding, deleting, or renaming a `.md` file, regenerate the manifest:

```powershell
py .\scripts\build_recipe_index.py
```

Validate it with:

```powershell
py .\scripts\build_recipe_index.py --check
```

Then commit both the recipe-file change and `recipes/recipe-index.json`.

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
```

## Deployment

GitHub Pages should publish from the `main` branch and repository root.
