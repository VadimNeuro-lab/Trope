// Set A - recipe app "Simmer". Five screens, two variants (improved / weak).
(function () {
  const { icon, statusBar, homeIndicator, tabbar } = K;
  const TIME = '18:30';
  const img = (k) => `food/${k}.svg`;

  const R = {
    salmon: { name: 'Lemon Herb Salmon', img: 'lemon-herb-salmon', time: '25 min', level: 'Easy', serves: '2 servings' },
    tomato: { name: 'Creamy Tomato Pasta', img: 'creamy-tomato-pasta', time: '20 min', level: 'Easy', note: 'Penne, tomato, cream' },
    pesto: { name: 'Basil Pesto Pasta', img: 'basil-pesto-pasta', time: '15 min', level: 'Easy', note: 'Spaghetti, basil, pine nuts' },
    shrimp: { name: 'Garlic Shrimp Linguine', img: 'garlic-shrimp-linguine', time: '25 min', level: 'Medium', note: 'Linguine, shrimp, chili' },
    mac: { name: 'Baked Mac & Cheese', img: 'baked-mac-and-cheese', time: '45 min', level: 'Medium', note: 'Macaroni, cheddar, crumbs' },
    shakshuka: { name: 'Shakshuka', img: 'shakshuka', time: '30 min', level: 'Easy' },
    buddha: { name: 'Green Buddha Bowl', img: 'green-buddha-bowl', time: '15 min', level: 'Easy' },
    risotto: { name: 'Mushroom Risotto', img: 'mushroom-risotto', time: '40 min', level: 'Medium' },
    pancakes: { name: 'Berry Pancakes', img: 'berry-pancakes', time: '20 min', level: 'Easy' },
  };

  const TABS = [
    { key: 'home', label: 'Home', icon: 'house' },
    { key: 'search', label: 'Search', icon: 'search' },
    { key: 'saved', label: 'Saved', icon: 'bookmark' },
    { key: 'profile', label: 'Profile', icon: 'user' },
  ];
  const nav = (active) => tabbar(TABS, active);
  const meta = (r, opt = {}) => `<div class="meta"${opt.style ? ` style="${opt.style}"` : ''}><span>${icon('clock', { size: opt.s || 16 })}${r.time}</span><span>${icon('chef-hat', { size: opt.s || 16 })}${r.level}</span>${opt.serves ? `<span>${icon('users', { size: opt.s || 16 })}${r.serves}</span>` : ''}</div>`;
  const shell = (body, active) => `<div class="screen">${statusBar(TIME)}${body}${active ? nav(active) : ''}${homeIndicator()}</div>`;

  // ---------------- HOME ----------------
  const home = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        <div class="w-greet">Hi, Emma</div>
        <div class="w-label">Today's recipe</div>
        <div class="w-hero">
          <img src="${img(R.salmon.img)}" style="object-position:50% 50%">
          <div class="ov">
            <div><h2>${R.salmon.name}</h2><p>${R.salmon.time} · ${R.salmon.level}</p></div>
            <span class="mini">View</span>
          </div>
        </div>
        <div class="w-label" style="margin-top:22px">More recipes</div>
        <div class="w-recs">
          ${[R.buddha, R.shakshuka, R.risotto].map((r) => `<div><img src="${img(r.img)}"><h4>${r.name}</h4><p>${r.time}</p></div>`).join('')}
        </div>
      </div>`, 'home');
    }
    return shell(`
    <div class="content">
      <header class="greet">
        <p class="hello">Good evening, Emma</p>
        <h1 class="display">What's cooking tonight?</h1>
      </header>
      <article class="card hero-card">
        <div class="hero-img">
          <img src="${img(R.salmon.img)}">
          <span class="badge-today">${icon('sparkles', { size: 16, sw: 2.2 })}Today's recipe</span>
        </div>
        <div class="hero-body">
          <h2>${R.salmon.name}</h2>
          ${meta(R.salmon, { serves: true })}
          <button class="btn-primary">Open recipe ${icon('arrow-right', { size: 20, sw: 2.4 })}</button>
        </div>
      </article>
      <section style="margin-top:24px">
        <div class="sec-head"><h3>Recommended for you</h3><span class="link">See all</span></div>
        <div class="recs">
          ${[R.buddha, R.shakshuka].map((r) => `
          <div class="card rec"><img src="${img(r.img)}"><div class="rb"><h4>${r.name}</h4>${meta(r, { s: 14 })}</div></div>`).join('')}
        </div>
      </section>
    </div>`, 'home');
  };

  // ---------------- SEARCH ----------------
  const results = [R.tomato, R.pesto, R.shrimp, R.mac];
  const search = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        <div class="w-navtitle">Search</div>
        <div class="w-search">${icon('search', { size: 18 })}<span>pasta</span></div>
        <div class="w-chips"><span class="on">All</span><span>Quick</span><span>Vegetarian</span><span>Dinner</span></div>
        <div style="margin-top:8px">
          ${results.map((r) => `<div class="w-row"><img src="${img(r.img)}"><div><h4>${r.name}</h4><p>${r.level}</p></div></div>`).join('')}
        </div>
      </div>`, 'search');
    }
    return shell(`
    <div class="content">
      <div class="page-head"><h1 class="title-xl">Search</h1></div>
      <div class="searchbar focus">${icon('search', { size: 21, sw: 2.2, style: 'color:var(--ink-2)' })}<span class="q">pasta</span><span class="clear">${icon('x', { size: 15, sw: 2.6 })}</span></div>
      <div class="chips">
        <span class="chip on">All</span><span class="chip">Quick</span><span class="chip">Vegetarian</span><span class="chip">Dinner</span>
      </div>
      <p class="results-label"><b>4 recipes</b> for “pasta”</p>
      ${results.map((r) => `
      <div class="card result">
        <img class="thumb" src="${img(r.img)}">
        <div class="rbody"><h4>${r.name}</h4><p class="note">${r.note}</p>${meta(r, { s: 15 })}</div>
        <span class="go">${icon('chevron-right', { size: 20, sw: 2.4 })}</span>
      </div>`).join('')}
    </div>`, 'search');
  };

  // ---------------- RECIPE ----------------
  const INGR = [
    ['Salmon fillets', '2'], ['Asparagus', '200 g'],
    ['Baby potatoes', '300 g'], ['Lemon', '1'],
    ['Butter', '2 tbsp'], ['Fresh dill', '1 bunch'],
  ];
  const DESC = 'Pan-seared salmon with a bright lemon-butter glaze, roasted asparagus and crispy baby potatoes.';
  const recipe = (v) => {
    if (v === 'weak') {
      return `<div class="screen">
        <div class="detail-img" data-bleed style="height:280px"><img src="${img(R.salmon.img)}"></div>
        ${statusBar(TIME)}
        <div class="round-btn" style="left:16px;top:54px;width:36px;height:36px">${icon('chevron-left', { size: 20, sw: 2.4 })}</div>
        <div style="position:absolute;right:20px;top:60px;color:#fff;z-index:20;filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))">${icon('bookmark', { size: 22, sw: 2 })}</div>
        <div class="sheet" style="top:260px;padding-top:20px">
          <h1 style="font-size:24px">${R.salmon.name}</h1>
          <p style="font-size:13px;color:#A69C90;margin-top:6px">${R.salmon.time} • ${R.salmon.serves} • ${R.salmon.level}</p>
          <p class="desc" style="font-size:14px">${DESC} Season the fillets, sear skin-side down until crisp, then baste with butter, garlic and lemon.</p>
          <h3 style="font-size:16px;font-weight:700;margin:16px 0 6px">Ingredients</h3>
          <ul style="list-style:none;font-size:14px;color:var(--ink-2);line-height:1.9">
            ${INGR.slice(0, 5).map(([n, q]) => `<li>• ${q} ${n.toLowerCase()}</li>`).join('')}
          </ul>
          <button class="btn-secondary" style="height:40px;width:150px;font-size:14px;border-radius:12px;margin-top:14px;color:var(--primary);border-color:var(--primary)">Start cooking</button>
        </div>
        ${homeIndicator()}
      </div>`;
    }
    return `<div class="screen">
      <div class="detail-img" data-bleed><img src="${img(R.salmon.img)}"></div>
      ${statusBar(TIME)}
      <div class="round-btn" style="left:16px;top:54px">${icon('arrow-left', { size: 22, sw: 2.2 })}</div>
      <div class="sheet">
        <h1>${R.salmon.name}</h1>
        <p class="desc">${DESC}</p>
        <div class="stats">
          <div class="stat"><b>${icon('clock', { size: 18, sw: 2.2 })}25 min</b><small>Total time</small></div>
          <div class="stat"><b>${icon('users', { size: 18, sw: 2.2 })}2</b><small>Servings</small></div>
          <div class="stat"><b>${icon('chef-hat', { size: 18, sw: 2.2 })}Easy</b><small>Difficulty</small></div>
        </div>
        <div class="ing-head"><h3>Main ingredients</h3><span>6 items</span></div>
        <ul class="card ing">
          ${INGR.map(([n, q]) => `<li>${n}<span>${q}</span></li>`).join('')}
        </ul>
      </div>
      <div class="bottom-bar">
        <button class="btn-secondary">${icon('bookmark', { size: 20, sw: 2.2 })}Save</button>
        <button class="btn-primary">${icon('play', { size: 18, sw: 2.4, fill: 'currentColor' })}Start cooking</button>
      </div>
      ${homeIndicator()}
    </div>`;
  };

  // ---------------- SAVED ----------------
  const savedList = [R.tomato, R.shakshuka, R.buddha, R.risotto, R.pancakes];
  const saved = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        <div class="w-navtitle">Saved</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 12px;margin-top:16px">
          ${savedList.slice(0, 4).map((r) => `<div><img src="${img(r.img)}" style="width:100%;height:150px;border-radius:14px;object-fit:cover"><h4 style="font-size:14px;font-weight:600;margin-top:8px">${r.name}</h4></div>`).join('')}
        </div>
      </div>`, 'saved');
    }
    return shell(`
    <div class="content">
      <div class="page-head"><h1 class="title-xl">Saved</h1><p class="count">5 recipes</p></div>
      <div class="saved-list">
        ${savedList.map((r) => `
        <div class="card saved">
          <div class="tw"><img class="thumb" src="${img(r.img)}"><span class="bm">${icon('bookmark', { size: 13, sw: 2.4, fill: 'currentColor' })}</span></div>
          <div class="sb"><h4>${r.name}</h4>${meta(r, { s: 15 })}</div>
          <span class="go">${icon('chevron-right', { size: 20, sw: 2.4 })}</span>
        </div>`).join('')}
      </div>
    </div>`, 'saved');
  };

  // ---------------- PROFILE ----------------
  const profile = (v) => {
    const chev = icon('chevron-right', { size: 18, sw: 2.2 });
    if (v === 'weak') {
      const row = (l, val) => `<div class="row" style="min-height:44px;font-size:14.5px;font-weight:500"><span class="rl">${l}</span><span class="rv" style="font-size:14px">${val}${chev}</span></div>`;
      return shell(`
      <div class="content">
        <div class="w-navtitle">Profile</div>
        <div style="display:flex;flex-direction:column;align-items:center;margin-top:18px">
          <div class="avatar" style="width:84px;height:84px;font-size:27px;background:var(--accent-soft);color:var(--accent)">EW</div>
          <div style="font-size:19px;font-weight:700;margin-top:12px">Emma Wilson</div><div style="font-size:13px;color:var(--ink-3);margin-top:2px">emma.wilson@mail.com</div>
        </div>
        <div class="card rows" style="margin-top:20px;border-radius:16px">
          ${row('Diet', 'Pescatarian')}
          ${row('Allergies', 'Peanuts')}
          ${row('Favorite categories', 'Seafood, Pasta…')}
          ${row('Default servings', '2')}
          ${row('Units', 'Metric')}
        </div>
      </div>`, 'profile');
    }
    const row = (ic, l, val, sub) => `<div class="row"><span class="ri">${icon(ic, { size: 17, sw: 2.2 })}</span><span class="rl">${l}${sub ? `<small>${sub}</small>` : ''}</span><span class="rv">${val}${chev}</span></div>`;
    const tog = (ic, l, sub, on) => `<div class="row"><span class="ri">${icon(ic, { size: 17, sw: 2.2 })}</span><span class="rl">${l}<small>${sub}</small></span><span class="switch ${on ? 'on' : ''}"></span></div>`;
    return shell(`
    <div class="content">
      <div class="page-head"><h1 class="title-xl">Profile</h1></div>
      <div class="card user">
        <div class="avatar" style="background:var(--accent-soft);color:var(--accent)">EW</div>
        <div style="flex:1"><h2>Emma Wilson</h2><p>Home cook · 2 people</p></div>
        <span style="color:var(--ink-3)">${chev}</span>
      </div>
      <p class="group-label">Dietary preferences</p>
      <div class="card rows">
        ${row('leaf', 'Diet', 'Pescatarian')}
        ${row('shield', 'Allergies', 'Peanuts')}
      </div>
      <p class="group-label">Favorite categories</p>
      <div class="cat-chips">
        <span class="cat">${icon('check', { size: 15, sw: 2.6 })}Quick dinners</span>
        <span class="cat">${icon('check', { size: 15, sw: 2.6 })}Seafood</span>
        <span class="cat">${icon('check', { size: 15, sw: 2.6 })}Pasta</span>
        <span class="cat off">${icon('plus', { size: 15, sw: 2.4 })}Add</span>
      </div>
      <p class="group-label">Saved settings</p>
      <div class="card rows">
        ${row('users', 'Default servings', '2')}
        ${row('scale', 'Units', 'Metric')}
      </div>
      <p class="group-label">Notifications</p>
      <div class="card rows">
        ${tog('bell', "Today's recipe", 'Every day at 17:30', true)}
      </div>
    </div>`, 'profile');
  };

  window.SCREENS = { home, search, recipe, saved, profile };
})();
