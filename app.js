const recipes = window.RECIPE_DATA || [];
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

let currentRecipeId = null;
let currentView = 'library';

[...new Set(recipes.map(r => r.category))].sort().forEach(v => {
  const option = document.createElement('option');
  option.value = v;
  option.textContent = v;
  category.appendChild(option);
});

[...new Set(recipes.flatMap(r => r.tags))].sort().forEach(v => {
  const option = document.createElement('option');
  option.value = v;
  option.textContent = v;
  tag.appendChild(option);
});

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
    card.classList.toggle('active', Number(card.dataset.id) === currentRecipeId);
  });
}

function showLibrary() {
  currentView = 'library';
  currentRecipeId = null;
  readerView.hidden = true;
  libraryView.hidden = false;
  renderLists();
  window.scrollTo({ top:0, behavior:'smooth' });
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
  window.scrollTo({ top:0, behavior:'smooth' });
}

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, character => ({
    '&':'&amp;',
    '<':'&lt;',
    '>':'&gt;',
    '"':'&quot;',
    "'":'&#039;'
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
homeButton.addEventListener('click', showLibrary);
backButton.addEventListener('click', showLibrary);

renderLists();
showLibrary();
