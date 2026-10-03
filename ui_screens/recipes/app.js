// Set A - recipe app "Simmer". Five screens, two variants:
//   improved - complete, clear hierarchy, large primary actions
//   weak     - same content and data, plainer layout, weaker hierarchy and smaller actions
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
  const HERO_NOTE = 'Lemon-butter glaze, roasted asparagus';
  const RECS = [R.buddha, R.shakshuka, R.risotto];
  const RESULTS = [R.tomato, R.pesto, R.shrimp, R.mac];
  const SAVED = [R.tomato, R.shakshuka, R.buddha, R.risotto, R.pancakes, R.pesto];
  const INGR = [
    ['Salmon fillets', '2'], ['Asparagus', '200 g'],
    ['Baby potatoes', '300 g'], ['Lemon', '1'],
    ['Butter', '2 tbsp'], ['Fresh dill', '1 bunch'],
  ];
  const DESC = 'Pan-seared salmon with a bright lemon-butter glaze, roasted asparagus and crispy baby potatoes.';

  const TABS = [
    { key: 'home', label: 'Home', icon: 'house' },
    { key: 'search', label: 'Search', icon: 'search' },
    { key: 'saved', label: 'Saved', icon: 'bookmark' },
    { key: 'profile', label: 'Profile', icon: 'user' },
  ];
  const shell = (body, active) => `<div class="screen">${statusBar(TIME)}${body}${active ? tabbar(TABS, active) : ''}${homeIndicator()}</div>`;
  const meta = (r, opt = {}) => `<div class="meta"><span>${icon('clock', { size: opt.s || 16 })}${r.time}</span><span>${icon('chef-hat', { size: opt.s || 16 })}${r.level}</span>${opt.serves ? `<span>${icon('users', { size: opt.s || 16 })}${r.serves}</span>` : ''}</div>`;
  const plainMeta = (r) => `${r.time} · ${r.level}`;
  const chev = (s = 18) => icon('chevron-right', { size: s, sw: 2.2 });
  const navTitle = (t) => `<div class="w-navtitle">${t}</div>`;

  // ---------------- HOME ----------------
  const home = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        <div class="w-greet">Hi, Emma</div>
        <div class="w-label">Today's recipe</div>
        <div class="card w-card">
          <img src="${img(R.salmon.img)}" style="width:100%;height:188px;object-fit:cover">
          <div style="padding:12px 14px 14px">
            <h2 style="font-size:18px;font-weight:700">${R.salmon.name}</h2>
            <p class="w-sub" style="margin-top:3px">${plainMeta(R.salmon)}</p>
            <div class="w-btn-outline" style="margin-top:12px">View recipe</div>
          </div>
        </div>
        <div class="w-label" style="margin-top:20px">Recommended</div>
        ${RECS.map((r) => `<div class="w-row"><img src="${img(r.img)}"><div style="flex:1"><h4>${r.name}</h4><p>${plainMeta(r)}</p></div></div>`).join('')}
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
          <p class="hero-note">${HERO_NOTE}</p>
          ${meta(R.salmon, { serves: true })}
          <button class="btn-primary">Open recipe ${icon('arrow-right', { size: 20, sw: 2.4 })}</button>
        </div>
      </article>
      <section style="margin-top:22px">
        <div class="sec-head"><h3>Recommended for you</h3><span class="link">See all</span></div>
        <div class="recs">
          ${[R.buddha, R.shakshuka].map((r) => `
          <div class="card rec"><img src="${img(r.img)}"><div class="rb"><h4>${r.name}</h4>${meta(r, { s: 14 })}</div></div>`).join('')}
        </div>
      </section>
    </div>`, 'home');
  };

  // ---------------- SEARCH ----------------
  const search = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        ${navTitle('Search')}
        <div class="w-search">${icon('search', { size: 18 })}<span style="flex:1;color:var(--ink)">pasta</span>${icon('x', { size: 16, sw: 2.2 })}</div>
        <div class="w-chips"><span class="on">All</span><span>Quick</span><span>Vegetarian</span><span>Dinner</span></div>
        <p class="w-sub" style="margin:14px 0 10px">4 results</p>
        <div class="w-grid">
          ${RESULTS.map((r) => `<div class="card w-card"><img src="${img(r.img)}" style="width:100%;height:118px;object-fit:cover"><div style="padding:9px 11px 11px"><h4>${r.name}</h4><p class="w-sub" style="margin-top:3px">${plainMeta(r)}</p></div></div>`).join('')}
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
      ${RESULTS.map((r) => `
      <div class="card result">
        <img class="thumb" src="${img(r.img)}">
        <div class="rbody"><h4>${r.name}</h4><p class="note">${r.note}</p>${meta(r, { s: 15 })}</div>
        <span class="go">${chev(20)}</span>
      </div>`).join('')}
    </div>`, 'search');
  };

  // ---------------- RECIPE ----------------
  const recipe = (v) => {
    if (v === 'weak') {
      return `<div class="screen">
        <div class="detail-img" data-bleed style="height:276px"><img src="${img(R.salmon.img)}"></div>
        ${statusBar(TIME)}
        <div class="round-btn" style="left:16px;top:54px;width:36px;height:36px">${icon('chevron-left', { size: 20, sw: 2.4 })}</div>
        <div class="round-btn" style="right:16px;top:54px;width:36px;height:36px">${icon('bookmark', { size: 18, sw: 2.2 })}</div>
        <div class="sheet" style="top:252px;padding-top:20px">
          <h1 style="font-size:25px">${R.salmon.name}</h1>
          <div class="meta" style="font-size:13.5px;margin-top:8px;gap:12px"><span>${icon('clock', { size: 14 })}25 min</span><span>${icon('users', { size: 14 })}2 servings</span><span>${icon('chef-hat', { size: 14 })}Easy</span></div>
          <p class="desc" style="font-size:14px;margin-top:10px">${DESC}</p>
          <h3 style="font-size:16px;font-weight:700;margin:16px 0 4px">Ingredients</h3>
          ${INGR.map(([n, q]) => `<div class="w-ing"><span>${n}</span><span>${q}</span></div>`).join('')}
          <button class="btn-primary" style="height:46px;font-size:15px;margin-top:16px;box-shadow:none;border-radius:12px">Start cooking</button>
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
  const saved = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        ${navTitle('Saved')}
        <p class="w-sub" style="margin:10px 0 2px">6 recipes</p>
        ${SAVED.map((r) => `<div class="w-row"><img src="${img(r.img)}"><div style="flex:1"><h4>${r.name}</h4><p>${plainMeta(r)}</p></div><span style="color:var(--primary)">${icon('bookmark', { size: 18, sw: 2, fill: 'currentColor' })}</span></div>`).join('')}
      </div>`, 'saved');
    }
    return shell(`
    <div class="content">
      <div class="page-head"><h1 class="title-xl">Saved</h1><p class="count">6 recipes</p></div>
      <div class="saved-grid">
        ${SAVED.map((r) => `
        <div class="card sv">
          <div class="sv-img"><img src="${img(r.img)}"><span class="bm">${icon('bookmark', { size: 14, sw: 2.4, fill: 'currentColor' })}</span></div>
          <div class="sv-b"><h4>${r.name}</h4>${meta(r, { s: 14 })}</div>
        </div>`).join('')}
      </div>
    </div>`, 'saved');
  };

  // ---------------- PROFILE ----------------
  const profile = (v) => {
    if (v === 'weak') {
      const row = (l, val) => `<div class="row w-prow"><span class="rl">${l}</span><span class="rv">${val}${chev(16)}</span></div>`;
      const tog = (l, on) => `<div class="row w-prow"><span class="rl">${l}</span><span class="switch sm ${on ? 'on' : ''}"></span></div>`;
      return shell(`
      <div class="content">
        ${navTitle('Profile')}
        <div style="display:flex;flex-direction:column;align-items:center;margin-top:12px">
          <div class="avatar" style="width:72px;height:72px;font-size:24px;background:var(--accent-soft);color:var(--accent)">EW</div>
          <div style="font-size:18px;font-weight:700;margin-top:10px">Emma Wilson</div><div class="w-sub" style="margin-top:2px">emma.wilson@mail.com</div>
        </div>
        <p class="w-cap">Preferences</p>
        <div class="card rows" style="border-radius:14px">
          ${row('Diet', 'Pescatarian')}
          ${row('Allergies', 'Peanuts')}
          ${row('Favorite categories', 'Seafood, Pasta…')}
          ${row('Default servings', '2')}
          ${row('Units', 'Metric')}
        </div>
        <p class="w-cap">Notifications</p>
        <div class="card rows" style="border-radius:14px">
          ${tog("Today's recipe", true)}
          ${tog('Weekly picks', false)}
        </div>
      </div>`, 'profile');
    }
    const row = (ic, l, val, sub) => `<div class="row"><span class="ri">${icon(ic, { size: 17, sw: 2.2 })}</span><span class="rl">${l}${sub ? `<small>${sub}</small>` : ''}</span><span class="rv">${val}${chev()}</span></div>`;
    const tog = (ic, l, sub, on) => `<div class="row"><span class="ri">${icon(ic, { size: 17, sw: 2.2 })}</span><span class="rl">${l}<small>${sub}</small></span><span class="switch ${on ? 'on' : ''}"></span></div>`;
    return shell(`
    <div class="content">
      <div class="page-head"><h1 class="title-xl">Profile</h1></div>
      <div class="card user">
        <div class="avatar" style="background:var(--accent-soft);color:var(--accent)">EW</div>
        <div style="flex:1"><h2>Emma Wilson</h2><p>emma.wilson@mail.com</p></div>
        <span style="color:var(--ink-3)">${chev()}</span>
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
      <p class="group-label">Cooking settings</p>
      <div class="card rows">
        ${row('users', 'Default servings', '2')}
        ${row('scale', 'Units', 'Metric')}
      </div>
      <p class="group-label">Notifications</p>
      <div class="card rows">
        ${tog('bell', "Today's recipe", 'Every day at 17:30', true)}
        ${tog('sparkles', 'Weekly picks', 'Sundays at 10:00', false)}
      </div>
    </div>`, 'profile');
  };

  window.SCREENS = { home, search, recipe, saved, profile };
})();
