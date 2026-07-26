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
const recipeDetailCache = new Map();

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

  let tags = metadata.tags || [];
  if (typeof tags === 'string') {
    tags = tags.split(';').map(value => value.trim()).filter(Boolean);
  }

  return {
    ...metadata,
    filename,
    tags,
    html: markdownToHtml(body)
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

async function loadRecipes() {
  try {
    const response = await fetch('recipes/recipe-index.json', { cache: 'no-cache' });
    if (!response.ok) {
      throw new Error(`Could not load recipe index (${response.status})`);
    }

    const payload = await response.json();
    if (!payload || !Array.isArray(payload.recipes)) {
      throw new Error('Recipe index is missing its recipes array.');
    }

    recipes = payload.recipes.map(recipe => ({
      ...recipe,
      tags: Array.isArray(recipe.tags) ? recipe.tags : [],
      search_text: String(recipe.search_text || '').toLowerCase()
    }));

    if (!recipes.length) {
      throw new Error('The recipe index contains no recipes.');
    }

    populateFilters();
    search.disabled = false;
    category.disabled = false;
    tag.disabled = false;
    renderLists();
    showLibrary(false);
  } catch (error) {
    console.error(error);
    libraryCount.textContent = 'Recipe collection unavailable';
    libraryGrid.innerHTML = `
      <div class="load-error">
        <h2>The recipes could not be loaded.</h2>
        <p>${escapeHtml(error.message)}</p>
        <p>Confirm that <code>recipes/recipe-index.json</code> was generated and pushed to GitHub Pages.</p>
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
    (!query || recipe.search_text.includes(query)) &&
    (!selectedCategory || recipe.category === selectedCategory) &&
    (!selectedTag || recipe.tags.includes(selectedTag))
  );
}

function cardMarkup(recipe) {
  return `
    ${recipe.image ? `<img src="${escapeAttr(recipe.image)}" alt="" loading="lazy" decoding="async">` : ''}
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

function pinRecipeSidebar() {
  const sidebar = reader.querySelector('.recipe-sidebar');
  if (!sidebar || window.innerWidth <= 850) return;

  sidebar.classList.remove('is-pinned');
  sidebar.style.removeProperty('--pinned-top');
  sidebar.style.removeProperty('--pinned-left');
  sidebar.style.removeProperty('--pinned-width');

  const rect = sidebar.getBoundingClientRect();
  sidebar.style.setProperty('--pinned-top', `${rect.top}px`);
  sidebar.style.setProperty('--pinned-left', `${rect.left}px`);
  sidebar.style.setProperty('--pinned-width', `${rect.width}px`);
  sidebar.classList.add('is-pinned');
}

function refreshPinnedSidebar() {
  if (currentView !== 'reader') return;
  requestAnimationFrame(pinRecipeSidebar);
}

async function fetchRecipeDetails(recipe) {
  if (recipeDetailCache.has(recipe.id)) {
    return recipeDetailCache.get(recipe.id);
  }
  const response = await fetch(`recipes/${encodeURIComponent(recipe.filename)}`, { cache: 'no-cache' });
  if (!response.ok) {
    throw new Error(`${recipe.filename}: HTTP ${response.status}`);
  }
  const parsed = parseRecipeMarkdown(await response.text(), recipe.filename);
  const details = {
    ...recipe,
    ...parsed,
    id: recipe.id,
    filename: recipe.filename,
    title: parsed.title || recipe.title,
    category: parsed.category || recipe.category,
    tags: parsed.tags.length ? parsed.tags : recipe.tags,
    image: parsed.image || recipe.image,
    servings: recipe.servings || String(parsed.servings || ''),
    prep_time: recipe.prep_time || String(parsed.prep_time || ''),
    cook_time: recipe.cook_time || String(parsed.cook_time || ''),
    total_time: recipe.total_time || String(parsed.total_time || ''),
    rating: recipe.rating || String(parsed.rating || ''),
    source: String(parsed.source || '')
  };
  recipeDetailCache.set(recipe.id, details);
  return details;
}

function renderRecipe(details) {
  reader.innerHTML = `
    <div class="recipe-header">
      <div class="category">${escapeHtml(details.category)}</div>
      <h1 class="recipe-title">${escapeHtml(details.title)}</h1>
    </div>
    <div class="recipe-layout">
      <aside class="recipe-sidebar">
        ${details.image ? `<img class="recipe-image" src="${escapeAttr(details.image)}" alt="${escapeHtml(details.title)}" decoding="async">` : ''}
        <section class="glance-card" aria-label="Recipe at a glance">
          <h2>At a Glance</h2>
          <dl class="glance-list">
            ${glanceRow('Servings', details.servings)}
            ${glanceRow('Prep', details.prep_time)}
            ${glanceRow('Cook', details.cook_time)}
            ${glanceRow('Total', details.total_time)}
            ${glanceRow('Source rating', details.rating)}
            ${glanceRow('Category', details.category)}
          </dl>
        </section>
        ${details.tags.length ? `<div class="tag-wrap">${details.tags.map(value => `<span class="tag">${escapeHtml(value)}</span>`).join('')}</div>` : ''}
      </aside>
      <div>
        <article class="recipe-body">${details.html}</article>
        ${details.source ? `<div class="source"><strong>Original recipe:</strong> <a href="${escapeAttr(details.source)}" target="_blank" rel="noopener">${escapeHtml(details.source)}</a></div>` : ''}
      </div>
    </div>`;

  requestAnimationFrame(() => requestAnimationFrame(pinRecipeSidebar));
}

async function openRecipe(recipe) {
  currentView = 'reader';
  currentRecipeId = recipe.id;
  libraryView.hidden = true;
  readerView.hidden = false;
  reader.innerHTML = `
    <div class="recipe-loading" role="status" aria-live="polite">
      <p>Loading ${escapeHtml(recipe.title)}…</p>
    </div>`;
  renderLists();
  window.scrollTo({ top: 0, behavior: 'auto' });

  try {
    const details = await fetchRecipeDetails(recipe);
    if (currentRecipeId !== recipe.id || currentView !== 'reader') return;
    renderRecipe(details);
  } catch (error) {
    console.error(error);
    if (currentRecipeId !== recipe.id || currentView !== 'reader') return;
    reader.innerHTML = `
      <div class="load-error" role="alert">
        <h1>${escapeHtml(recipe.title)}</h1>
        <p>This recipe could not be loaded.</p>
        <p>${escapeHtml(error.message)}</p>
      </div>`;
  }
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
window.addEventListener('resize', refreshPinnedSidebar);

loadRecipes();
