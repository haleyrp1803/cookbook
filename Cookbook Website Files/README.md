# Haley's Cookbook Website

The **editable source of truth** is the `recipes/` folder. Each recipe is one Markdown file with a small metadata block at the top.

## Editing a recipe

1. Open the matching `.md` file in `recipes/` with Notepad, VS Code, or another text editor.
2. Edit the metadata, ingredients, preparation, or personal notes.
3. From PowerShell in this folder, run:

```powershell
py scripts\build_recipes.py
```

4. Open `index.html` to inspect the result.
5. Commit both the edited Markdown file and the regenerated `generated/recipes.js`.

## Adding a recipe

Copy an existing Markdown file, rename it with a short descriptive filename, and update its contents. Put the image in `assets/` and set the `image:` path accordingly. Then run the build command.

## Validating without changing output

```powershell
py scripts\build_recipes.py --check
```

The builder reports missing titles, categories, images, malformed metadata, and duplicate recipe titles.

## Folder roles

- `recipes/` — editable recipe source files
- `assets/` — local recipe images
- `scripts/build_recipes.py` — validates and builds the site data
- `generated/recipes.js` — generated website data; do not edit manually
- `index.html`, `styles.css`, `app.js` — site interface

Current collection: 96 recipes.
