const recipes = window.RECIPE_DATA || [];
    const cards = document.getElementById('cards');
    const reader = document.getElementById('reader');
    const search = document.getElementById('search');
    const category = document.getElementById('category');
    const tag = document.getElementById('tag');
    const count = document.getElementById('count');

    [...new Set(recipes.map(r => r.category))].sort().forEach(v => {
      const o=document.createElement('option'); o.value=v; o.textContent=v; category.appendChild(o);
    });
    [...new Set(recipes.flatMap(r => r.tags))].sort().forEach(v => {
      const o=document.createElement('option'); o.value=v; o.textContent=v; tag.appendChild(o);
    });

    function glanceRow(label, value) {
      return value ? `<div class="glance-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>` : '';
    }

    function openRecipe(r) {
      document.querySelectorAll('.card').forEach(c => c.classList.toggle('active', Number(c.dataset.id)===r.id));
      reader.innerHTML = `
        <div class="recipe-header">
          <div class="category">${escapeHtml(r.category)}</div>
          <h1 class="recipe-title">${escapeHtml(r.title)}</h1>
        </div>
        <div class="recipe-layout">
          <aside class="recipe-sidebar">
            ${r.image ? `<img class="recipe-image" src="${r.image}" alt="${escapeHtml(r.title)}">` : ''}
            <section class="glance-card" aria-label="Recipe at a glance">
              <h2>At a Glance</h2>
              <dl class="glance-list">
                ${glanceRow('Servings', r.servings)}
                ${glanceRow('Prep', r.prep_time)}
                ${glanceRow('Cook', r.cook_time)}
                ${glanceRow('Total', r.total_time)}
                ${glanceRow('Rating', r.rating)}
                ${glanceRow('Category', r.category)}
              </dl>
            </section>
            ${r.tags.length ? `<div class="tag-wrap">${r.tags.map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join('')}</div>` : ''}
          </aside>
          <div>
            <article class="recipe-body">${r.html}</article>
            ${r.source ? `<div class="source"><strong>Original recipe:</strong> <a href="${escapeAttr(r.source)}" target="_blank" rel="noopener">${escapeHtml(r.source)}</a></div>` : ''}
          </div>
        </div>
      `;
      if (window.innerWidth < 850) reader.scrollIntoView({behavior:'smooth'});
    }

    function escapeHtml(s='') {
      return String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
    }
    function escapeAttr(s='') { return escapeHtml(s); }

    function render() {
      const q = search.value.trim().toLowerCase();
      const cat = category.value;
      const tg = tag.value;
      const filtered = recipes.filter(r =>
        (!q || r.search.includes(q)) &&
        (!cat || r.category === cat) &&
        (!tg || r.tags.includes(tg))
      );
      count.textContent = `${filtered.length} of ${recipes.length} recipes`;
      cards.innerHTML = '';
      filtered.forEach(r => {
        const b=document.createElement('button');
        b.className='card'; b.type='button'; b.dataset.id=r.id;
        b.innerHTML=`
          ${r.image ? `<img src="${r.image}" alt="">` : ''}
          <div class="card-body">
            <h3>${escapeHtml(r.title)}</h3>
            <div class="meta">${escapeHtml(r.category)}${r.total_time ? ` · ${escapeHtml(r.total_time)}` : ''}</div>
          </div>`;
        b.addEventListener('click',()=>openRecipe(r));
        cards.appendChild(b);
      });
      if (filtered.length === 1) openRecipe(filtered[0]);
    }

    [search,category,tag].forEach(el=>el.addEventListener('input',render));
    render();
    if (recipes.length) openRecipe(recipes[0]);
