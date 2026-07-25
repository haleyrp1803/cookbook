const libraryView = document.getElementById('libraryView');
const readerView = document.getElementById('readerView');
const libraryGrid = document.getElementById('libraryGrid');
const cards = document.getElementById('cards');
const reader = document.getElementById('reader');
const search = document.getElementById('search');
const category = document.getElementById('category');
const tag = document.getElementById('tag');
const libraryCount = document.getElementById('libraryCount');
const railCount = document.getElementById('railCount');
const homeButton = document.getElementById('homeButton');
const backButton = document.getElementById('backButton');

let recipes = [];
let currentRecipeId = null;
let currentView = 'library';

function unquote(value) {
  const trimmed = String(value || '').trim();
  if (!trimmed) return '';
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed.slice(1, -1);
    }
  }
  return trimmed;
}

function parseRecipeMarkdown(text, filename) {
  const normalized = text.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
  if (!normalized.startsWith('---\n')) {
    throw new Error(`${filename}: missing opening frontmatter delimiter`);
  }

  const closing = normalized.indexOf('\n---\n', 4);
  if (closing === -1) {
    throw new Error(`${filename}: missing closing frontmatter delimiter`);
  }

  const frontmatter = normalized.slice(4, closing);
  const body = normalized.slice(closing + 5).trim();
  const metadata = {};
  let currentList = null;

  frontmatter.split('\n').forEach(rawLine => {
    if (!rawLine.trim() || rawLine.trimStart().startsWith('#')) return;

    if (rawLine.startsWith('  - ') && currentList) {
      metadata[currentList].push(unquote(rawLine.slice(4)));
      return;
    }

    const colon = rawLine.indexOf(':');
    if (colon === -1) {
      throw new Error(`${filename}: invalid metadata line: ${rawLine}`);
    }

    const key = rawLine.slice(0, colon).trim();
    const value = rawLine.slice(colon + 1).trim();
    if (!value) {
      metadata[key] = [];
      currentList = key;
    } else {
      metadata[key] = unquote(value);
      currentList = null;
    }
  });

  const title = String(metadata.title || '').trim();
  const recipeCategory = String(metadata.category || '').trim();
  if (!title) throw new Error(`${filename}: missing title`);
  if (!recipeCategory) throw new Error(`${filename}: missing category`);

  let tags = metadata.tags || [];
  if (typeof tags === 'string') {
    tags = tags.split(';').map(value => value.trim()).filter(Boolean);
  }

  const renderedHtml = markdownToHtml(body);
  const plainBody = stripHtml(renderedHtml);
  const stem = filename.replace(/\.md$/i, '');

  return {
    id: stem,
    filename,
    title,
    category: recipeCategory,
    tags,
    source: String(metadata.source || ''),
    servings: String(metadata.servings || ''),
    prep_time: String(metadata.prep_time || ''),
    cook_time: String(metadata.cook_time || ''),
    total_time: String(metadata.total_time || ''),
    rating: String(metadata.rating || ''),
    image: String(metadata.image || ''),
    html: renderedHtml,
    search: [title, recipeCategory, tags.join(' '), plainBody].join(' ').toLowerCase()
  };
}

function markdownToHtml(markdown) {
  const output = [];
  let paragraph = [];
  let listType = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    output.push(`<p>${inlineMarkdown(paragraph.map(line => line.trim()).join(' '))}</p>`);
    paragraph = [];
  };

  const closeList = () => {
    if (!listType) return;
    output.push(`</${listType}>`);
    listType = null;
  };

  markdown.split('\n').forEach(rawLine => {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      closeList();
      return;
    }

    if (line.startsWith('### ')) {
      flushParagraph();
      closeList();
      output.push(`<h3>${inlineMarkdown(line.slice(4))}</h3>`);
      return;
    }

    if (line.startsWith('## ')) {
      flushParagraph();
      closeList();
      output.push(`<h2>${inlineMarkdown(line.slice(3))}</h2>`);
      return;
    }

    const unordered = line.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      if (listType !== 'ul') {
        closeList();
        output.push('<ul>');
        listType = 'ul';
      }
      output.push(`<li>${inlineMarkdown(unordered[1])}</li>`);
      return;
    }

    const ordered = line.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      if (listType !== 'ol') {
        closeList();
        output.push('<ol>');
        listType = 'ol';
      }
      output.push(`<li>${inlineMarkdown(ordered[1])}</li>`);
      return;
    }

    paragraph.push(line);
  });

  flushParagraph();
  closeList();
  return output.join('\n');
}

function inlineMarkdown(value) {
  let text = escapeHtml(value);
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/(^|[^*])\*([^*]+?)\*(?!\*)/g, '$1<em>$2</em>');
  return text;
}

function stripHtml(value) {
  const temporary = document.createElement('div');
  temporary.innerHTML = value;
  return temporary.textContent || temporary.innerText || '';
}

async function loadRecipes() {
  try {
    const manifestResponse = await fetch('recipes/recipe-index.json', { cache: 'no-cache' });
    if (!manifestResponse.ok) {
      throw new Error(`Could not load recipe index (${manifestResponse.status})`);
    }

    const filenames = await manifestResponse.json();
    if (!Array.isArray(filenames)) {
      throw new Error('Recipe index is not a JSON array.');
    }

    const results = await Promise.allSettled(
      filenames.map(async filename => {
        const response = await fetch(`recipes/${encodeURIComponent(filename)}`, { cache: 'no-cache' });
        if (!response.ok) {
          throw new Error(`${filename}: HTTP ${response.status}`);
        }
        return parseRecipeMarkdown(await response.text(), filename);
      })
    );

    const failures = results.filter(result => result.status === 'rejected');
    recipes = results
      .filter(result => result.status === 'fulfilled')
      .map(result => result.value)
      .sort((a, b) => a.category.localeCompare(b.category) || a.title.localeCompare(b.title));

    if (!recipes.length) {
      throw new Error('No recipes could be loaded.');
    }

    if (failures.length) {
      console.error('Some recipes failed to load:', failures.map(result => result.reason));
    }

    populateFilters();
    search.disabled = false;
    category.disabled = false;
    tag.disabled = false;
    renderLists();
    showLibrary(false);

    if (failures.length) {
      libraryCount.textContent += ` · ${failures.length} file${failures.length === 1 ? '' : 's'} failed to load`;
    }
  } catch (error) {
    console.error(error);
    libraryCount.textContent = 'Recipe collection unavailable';
    libraryGrid.innerHTML = `
      <div class="load-error">
        <h2>The recipes could not be loaded.</h2>
        <p>${escapeHtml(error.message)}</p>
        <p>Confirm that <code>recipes/recipe-index.json</code> and the Markdown files were pushed to GitHub Pages.</p>
      </div>`;
  }
}

function populateFilters() {
  category.innerHTML = '<option value="">All categories</option>';
  tag.innerHTML = '<option value="">All tags</option>';

  [...new Set(recipes.map(recipe => recipe.category))].sort().forEach(value => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    category.appendChild(option);
  });

  [...new Set(recipes.flatMap(recipe => recipe.tags))].sort().forEach(value => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    tag.appendChild(option);
  });
}

function glanceRow(label, value) {
  return value
    ? `<div class="glance-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`
    : '';
}

function filteredRecipes() {
  const query = search.value.trim().toLowerCase();
  const selectedCategory = category.value;
  const selectedTag = tag.value;

  return recipes.filter(recipe =>
    (!query || recipe.search.includes(query)) &&
    (!selectedCategory || recipe.category === selectedCategory) &&
    (!selectedTag || recipe.tags.includes(selectedTag))
  );
}

function cardMarkup(recipe) {
  return `
    ${recipe.image ? `<img src="${escapeAttr(recipe.image)}" alt="">` : ''}
    <div class="card-body">
      <h3>${escapeHtml(recipe.title)}</h3>
      <div class="meta">${escapeHtml(recipe.category)}${recipe.total_time ? ` · ${escapeHtml(recipe.total_time)}` : ''}</div>
    </div>`;
}

function makeCard(recipe) {
  const button = document.createElement('button');
  button.className = 'card';
  button.type = 'button';
  button.dataset.id = recipe.id;
  button.innerHTML = cardMarkup(recipe);
  button.addEventListener('click', () => openRecipe(recipe));
  return button;
}

function renderLists() {
  const filtered = filteredRecipes();
  const countText = `${filtered.length} of ${recipes.length} recipes`;
  libraryCount.textContent = countText;
  railCount.textContent = countText;
  libraryGrid.innerHTML = '';
  cards.innerHTML = '';

  if (!filtered.length) {
    libraryGrid.innerHTML = '<p class="no-results">No recipes match those filters.</p>';
    cards.innerHTML = '<p class="no-results">No recipes match those filters.</p>';
    return;
  }

  filtered.forEach(recipe => {
    libraryGrid.appendChild(makeCard(recipe));
    cards.appendChild(makeCard(recipe));
  });

  document.querySelectorAll('.card').forEach(card => {
    card.classList.toggle('active', card.dataset.id === currentRecipeId);
  });
}

function showLibrary(shouldScroll = true) {
  currentView = 'library';
  currentRecipeId = null;
  readerView.hidden = true;
  libraryView.hidden = false;
  renderLists();
  if (shouldScroll) window.scrollTo({ top: 0, behavior: 'smooth' });
}

function openRecipe(recipe) {
  currentView = 'reader';
  currentRecipeId = recipe.id;
  libraryView.hidden = true;
  readerView.hidden = false;

  reader.innerHTML = `
    <div class="recipe-header">
      <div class="category">${escapeHtml(recipe.category)}</div>
      <h1 class="recipe-title">${escapeHtml(recipe.title)}</h1>
    </div>
    <div class="recipe-layout">
      <aside class="recipe-sidebar">
        ${recipe.image ? `<img class="recipe-image" src="${escapeAttr(recipe.image)}" alt="${escapeHtml(recipe.title)}">` : ''}
        <section class="glance-card" aria-label="Recipe at a glance">
          <h2>At a Glance</h2>
          <dl class="glance-list">
            ${glanceRow('Servings', recipe.servings)}
            ${glanceRow('Prep', recipe.prep_time)}
            ${glanceRow('Cook', recipe.cook_time)}
            ${glanceRow('Total', recipe.total_time)}
            ${glanceRow('Rating', recipe.rating)}
            ${glanceRow('Category', recipe.category)}
          </dl>
        </section>
        ${recipe.tags.length ? `<div class="tag-wrap">${recipe.tags.map(value => `<span class="tag">${escapeHtml(value)}</span>`).join('')}</div>` : ''}
      </aside>
      <div>
        <article class="recipe-body">${recipe.html}</article>
        ${recipe.source ? `<div class="source"><strong>Original recipe:</strong> <a href="${escapeAttr(recipe.source)}" target="_blank" rel="noopener">${escapeHtml(recipe.source)}</a></div>` : ''}
      </div>
    </div>`;

  renderLists();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, character => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  }[character]));
}

function escapeAttr(value = '') {
  return escapeHtml(value);
}

function handleFilterChange() {
  renderLists();

  if (currentView === 'reader') {
    const filtered = filteredRecipes();
    const currentStillVisible = filtered.some(recipe => recipe.id === currentRecipeId);
    if (!currentStillVisible) showLibrary();
  }
}

[search, category, tag].forEach(control => control.addEventListener('input', handleFilterChange));
homeButton.addEventListener('click', () => showLibrary());
backButton.addEventListener('click', () => showLibrary());

loadRecipes();
