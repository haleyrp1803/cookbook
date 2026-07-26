const libraryView = document.getElementById('libraryView');
const readerView = document.getElementById('readerView');
const libraryGrid = document.getElementById('libraryGrid');
const cards = document.getElementById('cards');
const reader = document.getElementById('reader');
const search = document.getElementById('search');
const category = document.getElementById('category');
const tag = document.getElementById('tag');
const sort = document.getElementById('sort');
const clearFilters = document.getElementById('clearFilters');
const libraryCount = document.getElementById('libraryCount');
const railCount = document.getElementById('railCount');
const homeButton = document.getElementById('homeButton');
const backButton = document.getElementById('backButton');

let recipes = [];
let currentRecipeId = null;
let currentView = 'library';
let libraryScrollY = 0;
let routeChangeInProgress = false;
let recipeRailCollapsed = window.matchMedia('(min-width: 851px) and (max-width: 1150px)').matches;
let lastOpenedRecipeId = null;
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

function recipeIdFromFilename(filename = '') {
  return String(filename || '')
    .replace(/\\/g, '/')
    .split('/')
    .pop()
    .replace(/\.md$/i, '');
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
      id: String(recipe.id || recipe.slug || recipeIdFromFilename(recipe.filename)),
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
    sort.disabled = false;
    renderLists();
    initializeRoute();
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

function numericRating(value) {
  const match = String(value || '').match(/\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function sortedRecipes(items) {
  const result = [...items];
  const byTitle = (a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: 'base' });

  switch (sort.value) {
    case 'title-desc':
      return result.sort((a, b) => byTitle(b, a));
    case 'recent':
      return result.sort((a, b) => {
        const dateCompare = String(b.added_date || '').localeCompare(String(a.added_date || ''));
        return dateCompare || byTitle(a, b);
      });
    case 'time':
      return result.sort((a, b) => {
        const aTime = Number.isFinite(a.total_minutes) ? a.total_minutes : Number.POSITIVE_INFINITY;
        const bTime = Number.isFinite(b.total_minutes) ? b.total_minutes : Number.POSITIVE_INFINITY;
        return aTime - bTime || byTitle(a, b);
      });
    case 'rating':
      return result.sort((a, b) => {
        const aRating = numericRating(a.rating);
        const bRating = numericRating(b.rating);
        if (aRating === null && bRating === null) return byTitle(a, b);
        if (aRating === null) return 1;
        if (bRating === null) return -1;
        return bRating - aRating || byTitle(a, b);
      });
    default:
      return result.sort(byTitle);
  }
}

function filteredRecipes() {
  const query = search.value.trim().toLowerCase();
  const selectedCategory = category.value;
  const selectedTag = tag.value;

  const filtered = recipes.filter(recipe =>
    (!query || recipe.search_text.includes(query)) &&
    (!selectedCategory || recipe.category === selectedCategory) &&
    (!selectedTag || recipe.tags.includes(selectedTag))
  );

  return sortedRecipes(filtered);
}

function filtersAreActive() {
  return Boolean(search.value.trim() || category.value || tag.value);
}

function updateClearFiltersButton() {
  clearFilters.hidden = !filtersAreActive();
}

function clearAllFilters() {
  search.value = '';
  category.value = '';
  tag.value = '';
  renderLists();
  search.focus();
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
  button.addEventListener('click', () => navigateToRecipe(recipe));
  return button;
}

function renderLists() {
  const filtered = filteredRecipes();
  const countText = filtered.length === recipes.length
    ? `Showing ${recipes.length} recipes`
    : `Showing ${filtered.length} of ${recipes.length} recipes`;
  updateClearFiltersButton();
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

function focusLastOpenedRecipe() {
  if (!lastOpenedRecipeId) return;
  const card = libraryGrid.querySelector(`.card[data-id="${CSS.escape(lastOpenedRecipeId)}"]`);
  if (card) card.focus({ preventScroll: true });
}

function showLibrary(options = {}) {
  const { restoreScroll = true, scrollY = libraryScrollY, restoreFocus = true } = options;
  currentView = 'library';
  currentRecipeId = null;
  readerView.hidden = true;
  readerView.classList.remove('rail-collapsed');
  libraryView.hidden = false;
  document.title = "Haley's Recipe Book";
  renderLists();

  requestAnimationFrame(() => {
    window.scrollTo({ top: restoreScroll ? scrollY : 0, behavior: 'auto' });
    if (restoreFocus) focusLastOpenedRecipe();
  });
}

function recipeHash(recipe) {
  return `#${encodeURIComponent(recipe.id)}`;
}

function recipeFromHash() {
  const raw = window.location.hash.replace(/^#/, '');
  if (!raw) return null;
  let id = raw;
  try { id = decodeURIComponent(raw); } catch { /* use raw hash */ }
  return recipes.find(recipe => recipe.id === id) || null;
}

function rememberLibraryScroll() {
  if (currentView !== 'library') return;
  libraryScrollY = window.scrollY;
  const state = { ...(history.state || {}), view: 'library', scrollY: libraryScrollY };
  history.replaceState(state, '', window.location.href);
}

function navigateToRecipe(recipe, options = {}) {
  const { replace = false } = options;
  lastOpenedRecipeId = recipe.id;
  if (currentView === 'library') rememberLibraryScroll();

  const state = {
    view: 'recipe',
    recipeId: recipe.id,
    libraryScrollY
  };
  const method = replace ? 'replaceState' : 'pushState';
  history[method](state, '', recipeHash(recipe));
  openRecipe(recipe);
}

function navigateToLibrary(options = {}) {
  const { replace = false } = options;
  const state = { view: 'library', scrollY: libraryScrollY };
  const method = replace ? 'replaceState' : 'pushState';
  history[method](state, '', `${window.location.pathname}${window.location.search}`);
  showLibrary({ restoreScroll: true, scrollY: libraryScrollY });
}

function initializeRoute() {
  const recipe = recipeFromHash();
  if (recipe) {
    libraryScrollY = Number(history.state?.libraryScrollY || 0);
    history.replaceState(
      { view: 'recipe', recipeId: recipe.id, libraryScrollY },
      '',
      recipeHash(recipe)
    );
    openRecipe(recipe);
    return;
  }

  libraryScrollY = Number(history.state?.scrollY || 0);
  history.replaceState(
    { view: 'library', scrollY: libraryScrollY },
    '',
    `${window.location.pathname}${window.location.search}`
  );
  showLibrary({ restoreScroll: true, scrollY: libraryScrollY });
}

function handleRouteChange() {
  if (!recipes.length || routeChangeInProgress) return;
  routeChangeInProgress = true;

  const recipe = recipeFromHash();
  if (recipe) {
    libraryScrollY = Number(history.state?.libraryScrollY ?? libraryScrollY);
    openRecipe(recipe).finally(() => { routeChangeInProgress = false; });
    return;
  }

  libraryScrollY = Number(history.state?.scrollY ?? libraryScrollY);
  showLibrary({ restoreScroll: true, scrollY: libraryScrollY });
  routeChangeInProgress = false;
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

function updateRecipeRailState() {
  const isMobile = window.matchMedia('(max-width: 850px)').matches;
  readerView.classList.toggle('rail-collapsed', !isMobile && recipeRailCollapsed);

  const toggle = reader.querySelector('[data-rail-toggle]');
  if (!toggle) return;
  toggle.hidden = isMobile;
  toggle.setAttribute('aria-expanded', String(!recipeRailCollapsed));
  toggle.textContent = recipeRailCollapsed ? 'Show recipe list' : 'Hide recipe list';
}

function toggleRecipeRail() {
  recipeRailCollapsed = !recipeRailCollapsed;
  updateRecipeRailState();
  reader.querySelector('[data-rail-toggle]')?.focus();
}

function bindRecipeRailToggle() {
  const toggle = reader.querySelector('[data-rail-toggle]');
  if (toggle) toggle.addEventListener('click', toggleRecipeRail);
  updateRecipeRailState();
}

function recipeNavigationMarkup(recipe) {
  const filtered = filteredRecipes();
  const index = filtered.findIndex(item => item.id === recipe.id);
  const previous = index > 0 ? filtered[index - 1] : null;
  const next = index >= 0 && index < filtered.length - 1 ? filtered[index + 1] : null;

  return `
    <nav class="recipe-navigation" aria-label="Recipe navigation">
      <button class="recipe-nav-button" type="button" data-recipe-nav="previous" ${previous ? '' : 'disabled'}>
        <span aria-hidden="true">←</span>
        <span><small>Previous recipe</small>${previous ? escapeHtml(previous.title) : 'None'}</span>
      </button>
      <button class="recipe-nav-button recipe-nav-next" type="button" data-recipe-nav="next" ${next ? '' : 'disabled'}>
        <span><small>Next recipe</small>${next ? escapeHtml(next.title) : 'None'}</span>
        <span aria-hidden="true">→</span>
      </button>
    </nav>`;
}

function bindRecipeNavigation(recipe) {
  const filtered = filteredRecipes();
  const index = filtered.findIndex(item => item.id === recipe.id);
  const previous = index > 0 ? filtered[index - 1] : null;
  const next = index >= 0 && index < filtered.length - 1 ? filtered[index + 1] : null;

  const previousButton = reader.querySelector('[data-recipe-nav="previous"]');
  const nextButton = reader.querySelector('[data-recipe-nav="next"]');
  if (previous && previousButton) previousButton.addEventListener('click', () => navigateToRecipe(previous));
  if (next && nextButton) nextButton.addEventListener('click', () => navigateToRecipe(next));
}

function renderRecipe(details) {
  reader.innerHTML = `
    <div class="recipe-header">
      <button class="rail-toggle" type="button" data-rail-toggle aria-controls="recipeRail">Hide recipe list</button>
      <div class="category">${escapeHtml(details.category)}</div>
      <h1 class="recipe-title" tabindex="-1">${escapeHtml(details.title)}</h1>
      ${recipeNavigationMarkup(details)}
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

  document.title = `${details.title} · Haley's Recipe Book`;
  bindRecipeNavigation(details);
  bindRecipeRailToggle();
  requestAnimationFrame(() => reader.querySelector('.recipe-title')?.focus({ preventScroll: true }));
}

async function openRecipe(recipe) {
  lastOpenedRecipeId = recipe.id;
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
    if (!currentStillVisible) navigateToLibrary();
  }
}

[search, category, tag, sort].forEach(control => control.addEventListener('input', handleFilterChange));
clearFilters.addEventListener('click', clearAllFilters);
homeButton.addEventListener('click', () => navigateToLibrary());
backButton.addEventListener('click', () => navigateToLibrary());
window.addEventListener('resize', updateRecipeRailState);
window.addEventListener('popstate', handleRouteChange);
window.addEventListener('hashchange', handleRouteChange);
window.addEventListener('pagehide', rememberLibraryScroll);

loadRecipes();
