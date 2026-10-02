/*
 * Doors: a five-screen event discovery app.
 * Screens: Discover, Search, Event, Saved, Account. Vanilla JS, no build step.
 * State the person changes (saved events, tickets, settings) is kept in localStorage.
 */
(function () {
  'use strict';

  const DATA = window.DOORS_DATA;
  const STORE_KEY = 'doors-demo-v1';
  const MAX_QTY = 8;

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ---------- Formatting ----------
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ESC[c]);
  const pad = (n) => String(n).padStart(2, '0');
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

  function startOfDay(d) {
    const x = new Date(d);
    x.setHours(0, 0, 0, 0);
    return x;
  }
  function addDays(d, n) {
    const x = new Date(d);
    x.setDate(x.getDate() + n);
    return x;
  }
  function isoDay(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  function fromIso(s) {
    const [y, m, d] = s.split('-').map(Number);
    return new Date(y, m - 1, d);
  }

  const TODAY = startOfDay(new Date());
  const TODAY_ISO = isoDay(TODAY);
  const daysFromToday = (iso) => Math.round((fromIso(iso) - TODAY) / 86400000);

  const fmt = {
    dow: (d) => d.toLocaleDateString('en-US', { weekday: 'short' }),
    dowLong: (d) => d.toLocaleDateString('en-US', { weekday: 'long' }),
    mon: (d) => d.toLocaleDateString('en-US', { month: 'short' }),
    short: (d) => d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }),
    long: (d) => d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }),
    monthDay: (d) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  };

  function dayName(iso) {
    const n = daysFromToday(iso);
    if (n === 0) return 'Today';
    if (n === 1) return 'Tomorrow';
    return fmt.dowLong(fromIso(iso));
  }
  function dayLabel(e) {
    const n = daysFromToday(e.day);
    if (n === 0) return 'Today';
    if (n === 1) return 'Tomorrow';
    return fmt.short(e.date);
  }
  function relDay(iso) {
    const n = daysFromToday(iso);
    if (n === 0) return 'Today';
    if (n === 1) return 'Tomorrow';
    if (n < 7) return `In ${n} days`;
    if (n < 14) return 'Next week';
    return `In ${Math.round(n / 7)} weeks`;
  }
  function fmtTime(hhmm) {
    if (!hhmm) return '';
    const [h, m] = hhmm.split(':').map(Number);
    if (store.prefs.clock === '24') return `${pad(h)}:${pad(m)}`;
    const suffix = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 === 0 ? 12 : h % 12;
    return m ? `${h12}:${pad(m)} ${suffix}` : `${h12} ${suffix}`;
  }

  const usd0 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  const usd2 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });
  const round2 = (n) => Math.round(n * 100) / 100;
  const money = (n) => (n === 0 ? 'Free' : Math.round(n * 100) % 100 === 0 ? usd0.format(n) : usd2.format(n));
  const moneyExact = (n) => usd2.format(n);
  // Service fee: 10% plus $1.50 per paid ticket. Free tickets carry no fee.
  const feeFor = (price) => (price === 0 ? 0 : round2(price * 0.1 + 1.5));

  // ---------- Events ----------
  const CATS = Object.fromEntries(DATA.categories.map((c) => [c.id, c]));

  function resolveDate(when) {
    if (typeof when.in === 'number') return addDays(TODAY, when.in);
    const diff = (when.weekday - TODAY.getDay() + 7) % 7;
    return addDays(TODAY, diff + 7 * (when.week || 0));
  }

  const EVENTS = DATA.events
    .map((e) => {
      const date = resolveDate(e.when);
      const prices = e.tiers.map((t) => t.price);
      return Object.assign({}, e, {
        date,
        day: isoDay(date),
        venue: DATA.venues[e.venue],
        category: CATS[e.cat],
        minPrice: Math.min.apply(null, prices),
        maxPrice: Math.max.apply(null, prices),
      });
    })
    .sort((a, b) => (a.day + a.start).localeCompare(b.day + b.start));
  const BY_ID = Object.fromEntries(EVENTS.map((e) => [e.id, e]));
  const byDate = (a, b) => (a.day + a.start).localeCompare(b.day + b.start);

  // ---------- Stored state ----------
  const clone = (o) => JSON.parse(JSON.stringify(o));

  function loadStore() {
    const base = clone(DATA.defaults);
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
    } catch (_) {
      saved = null;
    }
    if (!saved || typeof saved !== 'object') return base;
    const merged = Object.assign(base, saved, {
      profile: Object.assign(base.profile, saved.profile),
      prefs: Object.assign(base.prefs, saved.prefs),
      notify: Object.assign(base.notify, saved.notify),
    });
    merged.saved = (merged.saved || []).filter((id) => BY_ID[id]);
    merged.orders = (merged.orders || []).filter((o) => BY_ID[o.eventId]);
    merged.cards = merged.cards || [];
    return merged;
  }

  function persist() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(store));
    } catch (_) {
      /* Storage can be unavailable (private windows, blocked site data). The app keeps working in memory. */
    }
  }

  let store = loadStore();

  const ticketCount = () => store.orders.reduce((n, o) => n + o.qty, 0);
  const purchased = (eventId, tierId) =>
    store.orders.filter((o) => o.eventId === eventId && o.tierId === tierId).reduce((n, o) => n + o.qty, 0);
  const remaining = (e, t) => Math.max(0, t.left - purchased(e.id, t.id));
  const isSaved = (id) => store.saved.includes(id);
  const cardById = (id) => store.cards.find((c) => c.id === id);

  // ---------- UI state (this visit only) ----------
  const EMPTY_SEARCH = { q: '', date: 'any', day: null, cats: [], sort: 'date' };
  const ui = {
    route: { name: 'discover' },
    backStack: [],
    pushedDepth: 0,
    suppressHash: null,
    scroll: {},
    search: clone(EMPTY_SEARCH),
    savedSeg: 'saved',
    checkout: null,
    sheet: null,
    toastTimer: null,
    toastAction: null,
    afterCard: null,
  };

  const EMBEDDED = (() => {
    try {
      return window.self !== window.top;
    } catch (_) {
      return true;
    }
  })();

  // ---------- Date filters ----------
  const DATE_FILTERS = [
    { id: 'any', label: 'Any date' },
    { id: 'today', label: 'Today' },
    { id: 'tomorrow', label: 'Tomorrow' },
    { id: 'weekend', label: 'This weekend' },
    { id: 'week', label: 'Next 7 days' },
    { id: 'month', label: 'Next 30 days' },
  ];

  // Friday through Sunday. From Friday on, the weekend starts today.
  function weekendRange() {
    const dow = TODAY.getDay();
    const toSunday = (7 - dow) % 7;
    const toFriday = dow === 0 || dow >= 5 ? 0 : 5 - dow;
    return [isoDay(addDays(TODAY, toFriday)), isoDay(addDays(TODAY, toSunday))];
  }

  function rangeFor(date, day) {
    switch (date) {
      case 'today':
        return [TODAY_ISO, TODAY_ISO];
      case 'tomorrow': {
        const t = isoDay(addDays(TODAY, 1));
        return [t, t];
      }
      case 'weekend':
        return weekendRange();
      case 'week':
        return [TODAY_ISO, isoDay(addDays(TODAY, 6))];
      case 'month':
        return [TODAY_ISO, isoDay(addDays(TODAY, 29))];
      case 'day':
        return day ? [day, day] : null;
      default:
        return null;
    }
  }

  const inRange = (e, range) => !range || (e.day >= range[0] && e.day <= range[1]);

  function matchesQuery(e, q) {
    if (!q) return true;
    const hay = [e.title, e.subtitle, e.venue.name, e.venue.area, e.category.label, e.organizer]
      .concat((e.lineup || []).map((l) => l.name))
      .join(' ')
      .toLowerCase();
    return q
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean)
      .every((w) => hay.includes(w));
  }

  function searchResults() {
    const s = ui.search;
    const range = rangeFor(s.date, s.day);
    const q = s.q.trim();
    const list = EVENTS.filter(
      (e) => inRange(e, range) && (!s.cats.length || s.cats.includes(e.cat)) && matchesQuery(e, q)
    );
    if (s.sort === 'price') list.sort((a, b) => a.minPrice - b.minPrice || byDate(a, b));
    return list;
  }

  function dateSummary() {
    const s = ui.search;
    if (s.date === 'day' && s.day) return fmt.short(fromIso(s.day));
    const f = DATE_FILTERS.find((x) => x.id === s.date);
    return f ? f.label : 'Any date';
  }

  // ---------- Icons ----------
  const ICONS = {
    discover: '<circle cx="12" cy="12" r="8.5"/><path d="m15.4 8.6-2 4.8-4.8 2 2-4.8z"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    bookmark: '<path d="M6.5 3.75h11v16.5l-5.5-4-5.5 4z"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5"/>',
    back: '<path d="M15 5l-7 7 7 7"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    pin: '<path d="M12 21s-6.5-6.2-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 14.8 12 21 12 21z"/><circle cx="12" cy="9.8" r="2.3"/>',
    ticket:
      '<path d="M3.5 7.5a1 1 0 0 1 1-1h15a1 1 0 0 1 1 1V10a2 2 0 0 0 0 4v2.5a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1V14a2 2 0 0 0 0-4z"/><path d="M14.5 7v1.5M14.5 11.25v1.5M14.5 15.5V17"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    minus: '<path d="M5 12h14"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>',
    card: '<rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h4"/>',
    help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.5a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.4M12 16.6v.4"/>',
    mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="m4 7 8 6 8-6"/>',
    shield: '<path d="M12 3.5 19 6v5.5c0 4.3-3 7.6-7 9-4-1.4-7-4.7-7-9V6z"/>',
    logout: '<path d="M14 4.5H6.5a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1H14"/><path d="M10.5 12h10M17 8.5l3.5 3.5-3.5 3.5"/>',
    trash: '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/>',
    chevron: '<path d="m9 5 7 7-7 7"/>',
    users:
      '<circle cx="9" cy="8.5" r="3.5"/><path d="M2.5 19.5c.9-3 3.4-4.5 6.5-4.5s5.6 1.5 6.5 4.5M15.5 5.2a3.5 3.5 0 0 1 0 6.6M18 15.3c1.7.6 2.9 2 3.5 4.2"/>',
    info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.6v.4"/>',
    edit: '<path d="M4.5 19.5h4l10-10-4-4-10 10z"/><path d="m13 7 4 4"/>',
  };
  const icon = (name, cls = '') =>
    `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[name]}</svg>`;

  // ---------- Shared components ----------
  function posterHTML(e, variant = '') {
    const p = e.poster;
    const ink = DATA.inks;
    const style = `--p-bg:${ink[p.bg]};--p-fg:${ink[p.fg]};--p-ac:${ink[p.ac]};--len:${p.word.length}`;
    const tag = `${fmt.dow(e.date)} ${pad(e.date.getMonth() + 1)}.${pad(e.date.getDate())}`;
    return `<div class="poster pat-${p.pattern} ${variant}" style="${style}" aria-hidden="true">
      <span class="poster-tag">${esc(tag)}<br>${esc(e.venue.name)}</span>
      <span class="poster-word">${esc(p.word)}</span>
    </div>`;
  }

  const dotStyle = (inkName) => `--dot:${DATA.inks[inkName]}`;
  const catTag = (e) =>
    `<span class="cat"><span class="dot" style="${dotStyle(e.category.ink)}"></span>${esc(e.category.label)}</span>`;

  function priceLabel(e) {
    if (e.minPrice === 0) return e.maxPrice === 0 ? 'Free' : 'Free entry';
    const p = store.prefs.allIn ? e.minPrice + feeFor(e.minPrice) : e.minPrice;
    return `From ${money(p)}`;
  }

  function saveBtn(e, cls = '') {
    return `<button type="button" class="save-btn ${cls}" data-action="toggle-save" data-id="${e.id}" aria-pressed="${isSaved(
      e.id
    )}" aria-label="Save ${esc(e.title)}">${icon('bookmark')}</button>`;
  }

  const titleBtn = (e) =>
    `<button type="button" class="stretch" data-action="open-event" data-id="${e.id}">${esc(e.title)}</button>`;

  function featureCard(e) {
    return `<article class="feature" data-event="${e.id}" data-day="${e.day}">
      <div class="feature-art">${posterHTML(e)}${saveBtn(e, 'on-art')}</div>
      <div class="feature-info">
        ${catTag(e)}
        <h3 class="feature-title">${titleBtn(e)}</h3>
        <p class="meta num">${esc(dayLabel(e))} · ${esc(fmtTime(e.start))}</p>
        <p class="meta">${esc(e.venue.name)}, ${esc(e.venue.area)}</p>
        <p class="price">${esc(priceLabel(e))}</p>
      </div>
    </article>`;
  }

  function eventRow(e, opts = {}) {
    const showDate = opts.showDate !== false;
    const when = (showDate ? `${dayLabel(e)} · ` : '') + fmtTime(e.start);
    return `<article class="row" data-event="${e.id}" data-day="${e.day}" data-cat="${e.cat}">
      <div class="row-art">${posterHTML(e, 'poster--thumb')}</div>
      <div class="row-main">
        <p class="row-when">${esc(when)}</p>
        <h3 class="row-title">${titleBtn(e)}</h3>
        <p class="row-where">${icon('pin', 'ic-sm')}<span>${esc(e.venue.name)} · ${esc(e.venue.area)}</span></p>
        <p class="row-foot">${catTag(e)}<span class="price">${esc(priceLabel(e))}</span></p>
      </div>
      ${saveBtn(e)}
    </article>`;
  }

  function miniCard(e) {
    return `<article class="mini" data-event="${e.id}">
      ${posterHTML(e, 'poster--thumb')}
      <h3 class="mini-title">${titleBtn(e)}</h3>
      <p class="meta num">${esc(dayLabel(e))} · ${esc(fmtTime(e.start))}</p>
    </article>`;
  }

  function groupByDay(list) {
    const groups = [];
    list.forEach((e) => {
      const last = groups[groups.length - 1];
      if (last && last[0] === e.day) last[1].push(e);
      else groups.push([e.day, [e]]);
    });
    return groups;
  }

  function barcodeSVG(seed) {
    let h = 2166136261;
    for (let i = 0; i < seed.length; i++) {
      h ^= seed.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    const rand = () => {
      h ^= h << 13;
      h ^= h >>> 17;
      h ^= h << 5;
      return (h >>> 0) / 4294967296;
    };
    let x = 0;
    let rects = '';
    for (let i = 0; i < 54; i++) {
      const w = 1 + Math.floor(rand() * 3);
      rects += `<rect x="${x}" y="0" width="${w}" height="40"/>`;
      x += w + 1 + Math.floor(rand() * 2);
    }
    return `<svg class="barcode" viewBox="0 0 ${x} 40" preserveAspectRatio="none" aria-hidden="true">${rects}</svg>`;
  }

  function stubHTML(o, opts = {}) {
    const e = BY_ID[o.eventId];
    const title = opts.link
      ? `<button type="button" class="stretch" data-action="open-event" data-id="${e.id}">${esc(o.title)}</button>`
      : esc(o.title);
    return `<div class="stub-wrap"><article class="stub" data-order="${esc(o.id)}">
      <div class="stub-top">
        <div class="stub-head">
          ${posterHTML(e, 'poster--thumb')}
          <div>
            <p class="stub-kicker">Admit ${o.qty} · ${esc(o.tierName)}</p>
            <h3 class="stub-title">${title}</h3>
          </div>
        </div>
        <dl class="stub-grid">
          <div><dt>Date</dt><dd>${esc(fmt.short(fromIso(o.day)))}</dd></div>
          <div><dt>${o.doors ? 'Doors' : 'Starts'}</dt><dd>${esc(fmtTime(o.doors || o.start))}</dd></div>
          <div><dt>Venue</dt><dd>${esc(o.venue)}</dd></div>
          <div><dt>Paid</dt><dd>${o.total ? esc(moneyExact(o.total)) : 'Free'}</dd></div>
        </dl>
      </div>
      <div class="stub-tear" aria-hidden="true"></div>
      <div class="stub-bottom">
        ${barcodeSVG(o.id)}
        <p class="stub-code">ORDER ${esc(o.id)}</p>
      </div>
    </article></div>`;
  }

  function emptyState(title, text, action, word = 'None') {
    const ink = DATA.inks;
    const art = `<div class="poster pat-halftone poster--thumb" style="--p-bg:${ink.yellow};--p-fg:${ink.ink};--p-ac:${ink.pink};--len:${word.length}" aria-hidden="true"><span class="poster-word">${esc(word)}</span></div>`;
    return `<div class="empty">
      <div class="empty-art">${art}</div>
      <h2>${esc(title)}</h2>
      <p>${esc(text)}</p>
      ${action || ''}
    </div>`;
  }

  // ---------- Screen 1: Discover ----------
  function renderDiscover() {
    const hour = new Date().getHours();
    const greet = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
    const first = store.signedIn ? store.profile.name.split(' ')[0] : '';
    const featured = EVENTS.filter((e) => e.featured);
    const favs = store.prefs.favCats;
    const forYou = EVENTS.filter((e) => favs.includes(e.cat) && !e.featured).slice(0, 8);
    const upcoming = EVENTS.slice(0, 10);

    const quick = [
      ['today', 'Tonight'],
      ['tomorrow', 'Tomorrow'],
      ['weekend', 'This weekend'],
      ['week', 'Next 7 days'],
    ]
      .map(([id, label]) => {
        const n = EVENTS.filter((e) => inRange(e, rangeFor(id))).length;
        return `<button type="button" class="quick" data-action="go-search" data-date="${id}" aria-label="${label}: ${plural(
          n,
          'event'
        )}"><span class="quick-n">${n}</span><span class="quick-l">${label}</span></button>`;
      })
      .join('');

    const cats = DATA.categories
      .map((c) => {
        const n = EVENTS.filter((e) => e.cat === c.id).length;
        return `<button type="button" class="cat-tile" data-action="go-search" data-cat="${c.id}">
          <span class="cat-swatch" style="${dotStyle(c.ink)}"></span>
          <span class="cat-tile-label">${esc(c.label)}</span>
          <span class="cat-tile-count">${plural(n, 'event')}</span>
        </button>`;
      })
      .join('');

    const forYouHTML = forYou.length
      ? `<div class="scroll-x" data-keep-scroll="foryou">${forYou.map(miniCard).join('')}</div>`
      : `<div class="note-card"><p>Pick a few favorite categories and we'll suggest events here.</p>
          <button type="button" class="btn btn-small btn-ghost" data-action="tab" data-tab="account">Choose favorites</button></div>`;

    const upcomingHTML = groupByDay(upcoming)
      .map(
        ([day, list]) => `<div class="day-group">
          <h3 class="day-head"><span>${esc(dayName(day))}</span><span class="day-date">${esc(fmt.monthDay(fromIso(day)))}</span></h3>
          <div class="list">${list.map((e) => eventRow(e, { showDate: false })).join('')}</div>
        </div>`
      )
      .join('');

    return `
      <header class="disc-head">
        <div class="topline">
          <span class="wordmark"><i aria-hidden="true"></i>Doors</span>
          <span class="where">${icon('pin', 'ic-sm')}${esc(DATA.city)}</span>
        </div>
        <p class="greet">${esc(greet)}${first ? `, ${esc(first)}` : ''} · ${esc(fmt.short(TODAY))}</p>
        <h1 class="display-xl">What's on in Chicago</h1>
        <button type="button" class="search-pill" data-action="go-search" data-focus="1">${icon('search')}<span>Search events, venues, artists</span></button>
      </header>

      <nav class="quick-grid" aria-label="Browse by date">${quick}</nav>

      <section class="section" aria-labelledby="h-featured">
        <div class="section-head"><h2 class="section-title" id="h-featured">Featured</h2></div>
        <div class="scroll-x feature-rail" data-keep-scroll="featured">${featured.map(featureCard).join('')}</div>
      </section>

      <section class="section" aria-labelledby="h-cats">
        <div class="section-head"><h2 class="section-title" id="h-cats">Browse by category</h2></div>
        <div class="scroll-x cat-rail" data-keep-scroll="cats">${cats}</div>
      </section>

      <section class="section" aria-labelledby="h-foryou">
        <div class="section-head">
          <h2 class="section-title" id="h-foryou">Picked for you</h2>
          ${forYou.length ? '<button type="button" class="link-btn" data-action="tab" data-tab="account">Edit favorites</button>' : ''}
        </div>
        ${forYouHTML}
      </section>

      <section class="section" aria-labelledby="h-upcoming">
        <div class="section-head"><h2 class="section-title" id="h-upcoming">Upcoming</h2></div>
        <div class="upcoming">${upcomingHTML}</div>
        <button type="button" class="btn btn-ghost wide see-all" data-action="go-search" data-date="any">See all ${EVENTS.length} upcoming events</button>
      </section>`;
  }

  // ---------- Screen 2: Search ----------
  function chip(label, pressed, attrs) {
    return `<button type="button" class="chip" aria-pressed="${pressed}" ${attrs}>${label}</button>`;
  }

  function resultCountHTML(n) {
    const s = ui.search;
    const parts = [dateSummary()];
    if (s.cats.length) parts.push(s.cats.map((c) => CATS[c].label).join(', '));
    if (s.q.trim()) parts.push(`“${s.q.trim()}”`);
    return `${plural(n, 'event')} <span class="muted">· ${esc(parts.join(' · '))}</span>`;
  }

  function resultsHTML(list) {
    if (!list.length) {
      return emptyState(
        'No events match',
        'Try a wider date range, another day, or fewer categories.',
        '<button type="button" class="btn btn-primary" data-action="clear-filters">Clear filters</button>',
        'Zero'
      );
    }
    return list.map((e) => eventRow(e)).join('');
  }

  function renderSearch() {
    const s = ui.search;
    const range = s.date === 'any' ? null : rangeFor(s.date, s.day);
    const counts = {};
    EVENTS.forEach((e) => {
      counts[e.day] = (counts[e.day] || 0) + 1;
    });

    const dateChips = DATE_FILTERS.map((f) =>
      chip(esc(f.label), s.date === f.id, `data-action="set-date" data-date="${f.id}"`)
    ).join('');

    const days = Array.from({ length: 28 }, (_, i) => addDays(TODAY, i))
      .map((d, i) => {
        const iso = isoDay(d);
        const n = counts[iso] || 0;
        const selected = s.date === 'day' && s.day === iso;
        const highlighted = range && !selected && iso >= range[0] && iso <= range[1];
        const mon = i === 0 || d.getDate() === 1 ? fmt.mon(d) : '';
        return `<button type="button" class="day${highlighted ? ' in-range' : ''}${n ? '' : ' no-events'}" data-action="set-day" data-day="${iso}" aria-pressed="${selected}" aria-label="${esc(
          fmt.long(d)
        )}, ${plural(n, 'event')}">
          <span class="day-mon">${mon}</span>
          <span class="day-dow">${i === 0 ? 'Today' : fmt.dow(d)}</span>
          <span class="day-num">${d.getDate()}</span>
          <span class="day-dots">${'<i></i>'.repeat(Math.min(n, 3))}</span>
        </button>`;
      })
      .join('');

    const catChips =
      chip('All', !s.cats.length, 'data-action="toggle-cat" data-cat="all"') +
      DATA.categories
        .map((c) =>
          chip(
            `<span class="dot" style="${dotStyle(c.ink)}"></span>${esc(c.label)}`,
            s.cats.includes(c.id),
            `data-action="toggle-cat" data-cat="${c.id}"`
          )
        )
        .join('');

    const list = searchResults();
    const filtered = s.date !== 'any' || s.cats.length || s.q.trim();

    return `
      <header class="screen-head"><h1 class="display-lg">Search</h1></header>
      <div class="search-field">
        ${icon('search')}
        <label class="sr-only" for="q">Search events, venues and artists</label>
        <input id="q" type="search" placeholder="Events, venues, artists" autocomplete="off" enterkeyhint="search" value="${esc(s.q)}">
        <button type="button" class="icon-btn" id="clear-q" data-action="clear-query" aria-label="Clear search" ${s.q ? '' : 'hidden'}>${icon('close')}</button>
      </div>

      <section class="filters" aria-label="Filters">
        <div class="filter-head"><h2 class="label">When</h2><span class="filter-val">${esc(dateSummary())}</span></div>
        <div class="scroll-x chips" data-keep-scroll="dates" role="group" aria-label="Date range">${dateChips}</div>
        <div class="scroll-x daystrip" data-keep-scroll="days" role="group" aria-label="Pick a day">${days}</div>
        <div class="other-date">
          <label for="date-pick">Or pick any date</label>
          <input type="date" id="date-pick" min="${TODAY_ISO}" value="${s.date === 'day' && s.day ? s.day : ''}">
        </div>
        <div class="filter-head"><h2 class="label">Category</h2>${
          filtered ? '<button type="button" class="link-btn" data-action="clear-filters">Clear all</button>' : ''
        }</div>
        <div class="scroll-x chips" data-keep-scroll="catchips" role="group" aria-label="Category">${catChips}</div>
      </section>

      <div class="results-head">
        <p class="result-count" id="result-count" aria-live="polite">${resultCountHTML(list.length)}</p>
        <div class="segmented small" role="group" aria-label="Sort results">
          <button type="button" data-action="set-sort" data-sort="date" aria-pressed="${s.sort === 'date'}">Soonest</button>
          <button type="button" data-action="set-sort" data-sort="price" aria-pressed="${s.sort === 'price'}">Price</button>
        </div>
      </div>
      <div class="list" id="results">${resultsHTML(list)}</div>`;
  }

  // Typing updates only the results so the input keeps focus.
  function updateResults() {
    const list = searchResults();
    const results = $('#results');
    if (!results) return;
    results.innerHTML = resultsHTML(list);
    $('#result-count').innerHTML = resultCountHTML(list.length);
    $('#clear-q').hidden = !ui.search.q;
  }

  // ---------- Screen 3: Event ----------
  function tierButton(e, t) {
    const left = remaining(e, t);
    const price = store.prefs.allIn ? t.price + feeFor(t.price) : t.price;
    const leftText = left === 0 ? 'Sold out' : left <= 20 ? `Only ${left} left` : '';
    return `<button type="button" class="tier" data-action="buy" data-id="${e.id}" data-tier="${t.id}" ${left ? '' : 'disabled'}>
      <span class="tier-name">${esc(t.name)}</span>
      <span class="tier-price">${esc(money(price))}</span>
      <span class="tier-desc">${esc(t.desc)}</span>
      ${leftText ? `<span class="tier-left">${leftText}</span>` : ''}
    </button>`;
  }

  function renderEvent(id) {
    const e = BY_ID[id];
    if (!e) {
      return `<header class="screen-head"><h1 class="display-lg">Event not found</h1></header>
        ${emptyState('This event is gone', 'It may have ended or been removed.', '<button type="button" class="btn btn-primary" data-action="tab" data-tab="discover">Back to Discover</button>', 'Gone')}`;
    }
    const owned = store.orders.filter((o) => o.eventId === e.id).reduce((n, o) => n + o.qty, 0);
    const lowStock = e.tiers.some((t) => remaining(e, t) > 0 && remaining(e, t) <= 20);
    const timeMain = e.end ? `${fmtTime(e.start)} – ${fmtTime(e.end)}` : fmtTime(e.start);
    const timeSub = e.doors ? `Doors open at ${fmtTime(e.doors)}` : 'No separate door time';
    const more = EVENTS.filter((x) => x.cat === e.cat && x.id !== e.id).slice(0, 3);
    const address = `${e.venue.address}, ${e.venue.area}, ${DATA.city}`;
    const hasPaid = e.maxPrice > 0;

    return `
      <article class="event" aria-labelledby="ev-title">
        <div class="event-hero">
          ${posterHTML(e, 'poster--hero')}
          <div class="hero-bar">
            <button type="button" class="round-btn" data-action="back" aria-label="Back">${icon('back')}</button>
            ${saveBtn(e, 'round-btn')}
          </div>
        </div>

        <div class="event-body">
          <div class="tag-row">${catTag(e)}<span class="badge">${esc(e.age)}</span>${
      lowStock ? '<span class="badge warn">Selling fast</span>' : ''
    }</div>
          <h1 class="event-title" id="ev-title">${esc(e.title)}</h1>
          <p class="event-sub">${esc(e.subtitle)}</p>
          <p class="going">${icon('users', 'ic-sm')}<span>${e.going.toLocaleString('en-US')} going · Presented by ${esc(
      e.organizer
    )}</span></p>

          ${
            owned
              ? `<button type="button" class="owned" data-action="view-tickets">${icon('ticket')}<span>You have ${plural(
                  owned,
                  'ticket'
                )} for this event</span>${icon('chevron')}</button>`
              : ''
          }

          <dl class="facts">
            <div class="fact">${icon('calendar')}<div><dt>Date</dt><dd><strong>${esc(fmt.long(e.date))}</strong><span>${esc(
      relDay(e.day)
    )}</span></dd></div></div>
            <div class="fact">${icon('clock')}<div><dt>Time</dt><dd><strong>${esc(timeMain)}</strong><span>${esc(
      timeSub
    )}</span></dd></div></div>
            <div class="fact">${icon('pin')}<div><dt>Venue</dt><dd><strong>${esc(e.venue.name)}</strong><span>${esc(
      e.venue.address
    )}, ${esc(e.venue.area)}</span>
              <button type="button" class="link-btn" data-action="copy" data-copy="${esc(address)}" data-what="Address">${icon(
      'copy',
      'ic-sm'
    )}Copy address</button></dd></div></div>
          </dl>

          <section class="ev-sec" aria-labelledby="h-about">
            <h2 id="h-about">About</h2>
            ${e.desc.map((p) => `<p>${esc(p)}</p>`).join('')}
          </section>

          ${
            e.lineup && e.lineup.length
              ? `<section class="ev-sec" aria-labelledby="h-sched">
              <h2 id="h-sched">${e.cat === 'music' ? 'Set times' : 'Schedule'}</h2>
              <ol class="schedule">${e.lineup
                .map((l) => `<li><span class="sch-time">${esc(fmtTime(l.time))}</span><span>${esc(l.name)}</span></li>`)
                .join('')}</ol>
            </section>`
              : ''
          }

          <section class="ev-sec" aria-labelledby="h-tickets" id="tickets">
            <h2 id="h-tickets">Tickets</h2>
            <div class="tiers">${e.tiers.map((t) => tierButton(e, t)).join('')}</div>
            ${
              hasPaid
                ? `<p class="fine">Prices ${
                    store.prefs.allIn ? 'include' : 'exclude'
                  } the service fee of 10% plus $1.50 per paid ticket.</p>`
                : ''
            }
          </section>

          <section class="ev-sec" aria-labelledby="h-know">
            <h2 id="h-know">Good to know</h2>
            <dl class="know">
              <div><dt>Age</dt><dd>${esc(e.age)}</dd></div>
              <div><dt>Duration</dt><dd>${esc(e.good.duration)}</dd></div>
              <div><dt>Accessibility</dt><dd>${esc(e.good.access)}</dd></div>
              <div><dt>Refunds</dt><dd>${esc(e.good.refunds)}</dd></div>
            </dl>
          </section>

          ${
            more.length
              ? `<section class="ev-sec" aria-labelledby="h-more">
              <h2 id="h-more">More ${esc(e.category.label.toLowerCase())}</h2>
              <div class="list">${more.map((x) => eventRow(x)).join('')}</div>
            </section>`
              : ''
          }
        </div>
      </article>`;
  }

  function actionbarHTML(e) {
    const free = e.maxPrice === 0;
    const from = store.prefs.allIn && e.minPrice ? e.minPrice + feeFor(e.minPrice) : e.minPrice;
    const feeNote = e.minPrice === 0 ? '' : store.prefs.allIn ? 'incl. fees' : '+ fees';
    const soldOut = e.tiers.every((t) => remaining(e, t) === 0);
    return `<div class="ab-price"><span>${free ? 'Entry' : 'Tickets from'}</span><strong>${esc(money(from))}${
      feeNote ? ` <small>${feeNote}</small>` : ''
    }</strong></div>
      ${saveBtn(e, 'square-btn')}
      <button type="button" class="btn btn-primary" data-action="buy" data-id="${e.id}" ${soldOut ? 'disabled' : ''}>${
      soldOut ? 'Sold out' : free ? 'Reserve a spot' : 'Get tickets'
    }</button>`;
  }

  // ---------- Screen 4: Saved ----------
  function renderSaved() {
    const savedEvents = store.saved.map((id) => BY_ID[id]).filter(Boolean).sort(byDate);
    const orders = store.orders.slice().sort((a, b) => (a.day + a.start).localeCompare(b.day + b.start));
    const seg = ui.savedSeg;

    let panel;
    if (seg === 'saved') {
      if (!savedEvents.length) {
        panel = emptyState(
          'Nothing saved yet',
          'Tap the bookmark on any event to keep it here for later.',
          '<button type="button" class="btn btn-primary" data-action="tab" data-tab="discover">Browse events</button>',
          'Later'
        );
      } else {
        const soon = savedEvents.filter((e) => daysFromToday(e.day) < 7);
        const later = savedEvents.filter((e) => daysFromToday(e.day) >= 7);
        const next = savedEvents[0];
        panel = `<p class="saved-summary">Next up: <strong>${esc(next.title)}</strong> · ${esc(dayLabel(next))} at ${esc(
          fmtTime(next.start)
        )}</p>
          ${soon.length ? `<div class="day-group"><h3 class="day-head">This week</h3><div class="list">${soon.map((e) => eventRow(e)).join('')}</div></div>` : ''}
          ${later.length ? `<div class="day-group"><h3 class="day-head">Later</h3><div class="list">${later.map((e) => eventRow(e)).join('')}</div></div>` : ''}`;
      }
    } else if (!orders.length) {
      panel = emptyState(
        'No tickets yet',
        'Tickets you buy show up here with a barcode to scan at the door.',
        '<button type="button" class="btn btn-primary" data-action="tab" data-tab="discover">Find an event</button>',
        'Stubs'
      );
    } else {
      panel = `<div class="stub-list">${orders.map((o) => stubHTML(o, { link: true })).join('')}</div>`;
    }

    return `
      <header class="screen-head">
        <h1 class="display-lg">Saved</h1>
        <p class="sub">Events you're keeping an eye on, and the tickets you've bought.</p>
      </header>
      <div class="segmented" role="group" aria-label="Show">
        <button type="button" aria-pressed="${seg === 'saved'}" data-action="saved-seg" data-seg="saved">Saved <span class="count">${savedEvents.length}</span></button>
        <button type="button" aria-pressed="${seg === 'tickets'}" data-action="saved-seg" data-seg="tickets">Tickets <span class="count">${ticketCount()}</span></button>
      </div>
      <div id="seg-panel">${panel}</div>`;
  }

  // ---------- Screen 5: Account ----------
  const NOTIFY = [
    ['reminders', 'Event reminders', 'Before events you have tickets for'],
    ['savedUpdates', 'Saved event updates', 'Price drops, low availability and lineup changes'],
    ['newInFavs', 'New in your favorite categories', 'When matching events go on sale'],
    ['weekly', 'Weekend picks email', 'Every Thursday morning'],
    ['quiet', 'Quiet hours', 'No push notifications from 10 PM to 8 AM'],
  ];

  const BRAND_SHORT = { Mastercard: 'MC', 'American Express': 'Amex', Discover: 'Disc' };
  const brandShort = (brand) => BRAND_SHORT[brand] || brand;

  const initials = (name) =>
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0].toUpperCase())
      .join('');

  function switchRow(id, path, label, help, checked) {
    return `<label class="setting" for="${id}">
      <span class="setting-text"><span class="set-label">${esc(label)}</span><span class="set-help">${esc(help)}</span></span>
      <input type="checkbox" role="switch" class="switch" id="${id}" data-setting="${path}" data-label="${esc(label)}" ${checked ? 'checked' : ''}>
    </label>`;
  }

  function renderAccount() {
    if (!store.signedIn) {
      return `<header class="screen-head"><h1 class="display-lg">Account</h1></header>
        ${emptyState(
          "You're signed out",
          'Sign in to buy tickets and manage payment methods. Saved events stay on this device.',
          `<button type="button" class="btn btn-primary" data-action="sign-in">Sign in as ${esc(DATA.defaults.profile.name)}</button>`,
          'Hello'
        )}`;
    }
    const p = store.profile;
    const favChips = DATA.categories
      .map((c) =>
        chip(
          `<span class="dot" style="${dotStyle(c.ink)}"></span>${esc(c.label)}`,
          store.prefs.favCats.includes(c.id),
          `data-action="fav-cat" data-cat="${c.id}"`
        )
      )
      .join('');

    const cards = store.cards
      .map((c) => {
        const isDefault = c.id === store.defaultCard;
        return `<div class="pay-row">
          <span class="card-brand" aria-hidden="true">${esc(brandShort(c.brand))}</span>
          <span class="setting-text">
            <span class="set-label">${esc(c.brand)} •••• ${esc(c.last4)}${isDefault ? ' <span class="badge ok">Default</span>' : ''}</span>
            <span class="set-help">${esc(c.label)} · Expires ${esc(c.exp)}</span>
            ${
              isDefault
                ? ''
                : `<button type="button" class="link-btn" data-action="default-card" data-card="${c.id}">Make default</button>`
            }
          </span>
          <button type="button" class="icon-btn" data-action="remove-card" data-card="${c.id}" aria-label="Remove ${esc(c.brand)} ending in ${esc(
          c.last4
        )}">${icon('trash')}</button>
        </div>`;
      })
      .join('');

    const n = store.notify;
    const remindSelect = `<div class="setting">
      <label class="setting-text" for="remind-when"><span class="set-label">Remind me</span><span class="set-help">How long before an event starts</span></label>
      <select id="remind-when" data-setting="notify.remindWhen" ${n.reminders ? '' : 'disabled'}>
        ${[
          ['2h', '2 hours before'],
          ['1d', '1 day before'],
          ['2d', '2 days before'],
        ]
          .map(([v, l]) => `<option value="${v}" ${n.remindWhen === v ? 'selected' : ''}>${l}</option>`)
          .join('')}
      </select>
    </div>`;

    return `
      <header class="screen-head"><h1 class="display-lg">Account</h1></header>

      <section class="profile" aria-label="Profile">
        <div class="avatar" aria-hidden="true">${esc(initials(p.name))}</div>
        <div class="profile-main">
          <h2>${esc(p.name)}</h2>
          <p class="profile-email" title="${esc(p.email)}">${esc(p.email)}</p>
          <p>${esc(p.city)} · Member since ${esc(p.since)}</p>
        </div>
        <button type="button" class="icon-btn" data-action="edit-profile" aria-label="Edit profile">${icon('edit')}</button>
      </section>

      <dl class="stats">
        <div><dt>Saved</dt><dd>${store.saved.length}</dd></div>
        <div><dt>Tickets</dt><dd>${ticketCount()}</dd></div>
        <div><dt>Attended</dt><dd>${esc(p.attended)}</dd></div>
      </dl>

      <section class="group" aria-labelledby="h-prefs">
        <h2 class="label" id="h-prefs">Preferences</h2>
        <div class="group-card">
          <div class="pref-block">
            <div class="setting-text"><span class="set-label">Favorite categories</span><span class="set-help">Used for “Picked for you” on Discover</span></div>
            <div class="chips wrap" role="group" aria-label="Favorite categories">${favChips}</div>
          </div>
          ${switchRow('pref-allin', 'prefs.allIn', 'Show prices with fees', 'Include the service fee in every price', store.prefs.allIn)}
          <div class="setting">
            <span class="setting-text"><span class="set-label" id="clock-label">Time format</span><span class="set-help num">${esc(
              fmtTime('19:30')
            )}</span></span>
            <div class="segmented small" role="group" aria-labelledby="clock-label">
              <button type="button" data-action="set-clock" data-clock="12" aria-pressed="${store.prefs.clock === '12'}">12-hour</button>
              <button type="button" data-action="set-clock" data-clock="24" aria-pressed="${store.prefs.clock === '24'}">24-hour</button>
            </div>
          </div>
        </div>
      </section>

      <section class="group" aria-labelledby="h-notify">
        <h2 class="label" id="h-notify">Notifications</h2>
        <div class="group-card">
          ${switchRow('n-reminders', 'notify.reminders', NOTIFY[0][1], NOTIFY[0][2], n.reminders)}
          ${remindSelect}
          ${NOTIFY.slice(1)
            .map(([key, label, help]) => switchRow(`n-${key}`, `notify.${key}`, label, help, n[key]))
            .join('')}
        </div>
      </section>

      <section class="group" aria-labelledby="h-pay">
        <h2 class="label" id="h-pay">Payment methods</h2>
        <div class="group-card">
          ${cards || '<p class="setting set-help">No payment methods yet. Add one to buy paid tickets.</p>'}
          <button type="button" class="row-link" data-action="add-card">${icon('plus')}<span>Add payment method</span></button>
        </div>
      </section>

      <section class="group" aria-labelledby="h-support">
        <h2 class="label" id="h-support">Support and account</h2>
        <div class="group-card">
          <button type="button" class="row-link" data-action="help">${icon('help')}<span>Help and FAQ</span>${icon('chevron')}</button>
          <button type="button" class="row-link" data-action="contact">${icon('mail')}<span>Contact support</span>${icon('chevron')}</button>
          <button type="button" class="row-link" data-action="privacy">${icon('shield')}<span>Privacy and data</span>${icon('chevron')}</button>
          <button type="button" class="row-link" data-action="sign-out">${icon('logout')}<span>Sign out</span></button>
          <button type="button" class="row-link danger" data-action="delete-account">${icon('trash')}<span>Delete account</span></button>
        </div>
      </section>

      <p class="fineprint">Doors 1.0 · Sample data. Checkout is simulated and nothing is charged.</p>`;
  }

  // ---------- Bars ----------
  const TABS = [
    ['discover', 'Discover', 'discover'],
    ['search', 'Search', 'search'],
    ['saved', 'Saved', 'bookmark'],
    ['account', 'Account', 'user'],
  ];

  function renderBars() {
    const onEvent = ui.route.name === 'event' && BY_ID[ui.route.id];
    tabbarEl.hidden = !!onEvent;
    actionbarEl.hidden = !onEvent;
    const n = store.saved.length;
    tabbarEl.innerHTML = TABS.map(([id, label, ic]) => {
      const current = ui.route.name === id;
      const badge = id === 'saved' && n ? `<span class="tab-badge" aria-hidden="true">${n}</span>` : '';
      const srCount = id === 'saved' && n ? `<span class="sr-only">, ${plural(n, 'saved event')}</span>` : '';
      return `<button type="button" class="tab" data-action="tab" data-tab="${id}" ${current ? 'aria-current="page"' : ''}>${icon(
        ic
      )}${badge}<span class="tab-label">${label}</span>${srCount}</button>`;
    }).join('');
    if (onEvent) actionbarEl.innerHTML = actionbarHTML(BY_ID[ui.route.id]);
  }

  // ---------- Rendering and focus ----------
  const screenEl = $('#screen');
  const tabbarEl = $('#tabbar');
  const actionbarEl = $('#actionbar');
  const sheetRoot = $('#sheet-root');
  const toastEl = $('#toast');

  const FOCUS_KEYS = ['id', 'tab', 'date', 'day', 'cat', 'seg', 'clock', 'card', 'tier', 'delta', 'sort'];

  // Describe the focused control so the same control can be refocused after a re-render.
  function focusMemo() {
    const el = document.activeElement;
    if (!el || el === document.body || el === screenEl) return null;
    let sel = null;
    if (el.id) sel = `#${CSS.escape(el.id)}`;
    else if (el.dataset && el.dataset.action) {
      sel =
        `[data-action="${el.dataset.action}"]` +
        FOCUS_KEYS.filter((k) => el.dataset[k] != null)
          .map((k) => `[data-${k}="${CSS.escape(el.dataset[k])}"]`)
          .join('');
    } else if (el.name) sel = `[name="${CSS.escape(el.name)}"][value="${CSS.escape(el.value)}"]`;
    if (!sel) return null;
    return { sel, idx: $$(sel).indexOf(el) };
  }

  function restoreFocus(memo) {
    if (!memo) return;
    const all = $$(memo.sel);
    const el = all[memo.idx] || all[0];
    if (el) el.focus({ preventScroll: true });
  }

  function render(opts = {}) {
    const memo = opts.keep ? focusMemo() : null;
    const scrolls = {};
    if (opts.keep) $$('[data-keep-scroll]', screenEl).forEach((el) => (scrolls[el.dataset.keepScroll] = el.scrollLeft));

    const r = ui.route;
    let html;
    if (r.name === 'search') html = renderSearch();
    else if (r.name === 'event') html = renderEvent(r.id);
    else if (r.name === 'saved') html = renderSaved();
    else if (r.name === 'account') html = renderAccount();
    else html = renderDiscover();

    screenEl.innerHTML = html;
    screenEl.dataset.screen = r.name;
    renderBars();

    if (opts.keep) {
      $$('[data-keep-scroll]', screenEl).forEach((el) => {
        const x = scrolls[el.dataset.keepScroll];
        if (x) el.scrollLeft = x;
      });
      restoreFocus(memo);
    }
  }

  // ---------- Navigation ----------
  const routeKey = (r) => (r.name === 'event' ? `event-${r.id}` : r.name);

  function parseHash(h) {
    if (!h) return null;
    if (h.startsWith('event-')) {
      const id = h.slice(6);
      return BY_ID[id] ? { name: 'event', id } : null;
    }
    return TABS.some((t) => t[0] === h) ? { name: h } : null;
  }

  function syncHash(key, push) {
    if (location.hash.slice(1) === key) return;
    ui.suppressHash = key;
    try {
      if (push && !EMBEDDED) {
        location.hash = key;
        ui.pushedDepth += 1;
      } else {
        location.replace(`#${key}`);
      }
    } catch (_) {
      ui.suppressHash = null;
    }
  }

  function go(route, opts = {}) {
    ui.scroll[routeKey(ui.route)] = window.scrollY;
    if (opts.reset) {
      ui.backStack = [];
      ui.pushedDepth = 0;
    } else if (!opts.back && route.name === 'event') {
      ui.backStack.push(ui.route);
    }
    ui.route = route;
    render();
    screenEl.classList.remove('entering');
    void screenEl.offsetWidth;
    screenEl.classList.add('entering');

    const y = route.name === 'event' && !opts.back ? 0 : ui.scroll[routeKey(route)] || 0;
    window.scrollTo(0, y);
    if (!opts.fromHash) syncHash(routeKey(route), route.name === 'event' && !opts.back);
    if (!opts.noFocus) screenEl.focus({ preventScroll: true });
  }

  function openEvent(id) {
    if (!BY_ID[id]) return;
    closeSheet();
    go({ name: 'event', id });
  }

  function goBack() {
    if (!EMBEDDED && ui.pushedDepth > 0) {
      history.back();
      return;
    }
    const prev = ui.backStack.pop() || { name: 'discover' };
    go(prev, { back: true });
  }

  window.addEventListener('hashchange', () => {
    const h = location.hash.slice(1);
    if (h === ui.suppressHash) {
      ui.suppressHash = null;
      return;
    }
    const r = parseHash(h) || { name: 'discover' };
    if (routeKey(r) === routeKey(ui.route)) return;
    closeSheet();
    const top = ui.backStack[ui.backStack.length - 1];
    if (top && routeKey(top) === routeKey(r)) {
      ui.backStack.pop();
      ui.pushedDepth = Math.max(0, ui.pushedDepth - 1);
      go(r, { back: true, fromHash: true });
    } else if (r.name === 'event') {
      ui.pushedDepth += 1;
      go(r, { fromHash: true });
    } else {
      go(r, { fromHash: true, reset: true });
    }
  });

  function goSearch(params) {
    ui.search = Object.assign(clone(EMPTY_SEARCH), params);
    ui.scroll.search = 0;
    go({ name: 'search' }, { reset: true, noFocus: !!params.focus });
    if (params.focus) $('#q').focus();
  }

  // ---------- Saving ----------
  function toggleSave(id, opts = {}) {
    const e = BY_ID[id];
    if (!e) return;
    const was = isSaved(id);
    store.saved = was ? store.saved.filter((x) => x !== id) : store.saved.concat(id);
    persist();

    if (ui.route.name === 'saved' || ui.route.name === 'account') {
      render({ keep: true });
    } else {
      $$(`[data-action="toggle-save"][data-id="${id}"]`).forEach((b) => b.setAttribute('aria-pressed', String(!was)));
      const memo = focusMemo();
      renderBars();
      restoreFocus(memo);
    }
    if (opts.silent) return;
    if (was) toast(`Removed ${e.title} from Saved`, { label: 'Undo', run: () => toggleSave(id, { silent: true }) });
    else toast(`Saved ${e.title}`, { label: 'View', run: () => showSaved('saved') });
  }

  function showSaved(seg) {
    closeSheet();
    ui.savedSeg = seg;
    ui.scroll.saved = 0;
    go({ name: 'saved' }, { reset: true });
  }

  // ---------- Toast ----------
  function toast(message, action) {
    clearTimeout(ui.toastTimer);
    ui.toastAction = action ? action.run : null;
    toastEl.innerHTML = `<span>${esc(message)}</span>${
      action ? `<button type="button" class="toast-btn" data-action="toast-action">${esc(action.label)}</button>` : ''
    }`;
    toastEl.classList.add('show');
    ui.toastTimer = setTimeout(hideToast, 4500);
  }

  function hideToast() {
    clearTimeout(ui.toastTimer);
    toastEl.classList.remove('show');
    ui.toastAction = null;
  }

  // ---------- Sheets ----------
  let sheetReturnFocus = null;

  function openSheet(name, label, html) {
    const wasOpen = !sheetRoot.hidden;
    if (!wasOpen) sheetReturnFocus = document.activeElement;
    ui.sheet = name;
    sheetRoot.innerHTML = `<div class="sheet-backdrop" data-action="close-sheet"></div>
      <div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(label)}"><div class="sheet-body">${html}</div></div>`;
    sheetRoot.hidden = false;
    document.documentElement.classList.add('locked');
    const first = $('[autofocus]', sheetRoot) || focusables()[0];
    if (first) first.focus({ preventScroll: true });
  }

  function updateSheet(html) {
    const body = $('.sheet-body', sheetRoot);
    if (!body) return;
    const memo = focusMemo();
    body.innerHTML = html;
    restoreFocus(memo);
    if (!sheetRoot.contains(document.activeElement)) {
      const first = focusables()[0];
      if (first) first.focus({ preventScroll: true });
    }
  }

  function closeSheet() {
    if (sheetRoot.hidden) return;
    sheetRoot.hidden = true;
    sheetRoot.innerHTML = '';
    ui.sheet = null;
    ui.checkout = null;
    ui.afterCard = null;
    document.documentElement.classList.remove('locked');
    if (sheetReturnFocus && document.contains(sheetReturnFocus)) sheetReturnFocus.focus({ preventScroll: true });
    sheetReturnFocus = null;
  }

  const focusables = () =>
    $$('button:not([disabled]), input:not([disabled]), select:not([disabled]), summary, [href], [tabindex]:not([tabindex="-1"])', sheetRoot).filter(
      (el) => el.offsetParent !== null || el === document.activeElement
    );

  function sheetHead(title, sub, kicker) {
    return `<div class="sheet-head">
      <div>${kicker ? `<p class="label">${esc(kicker)}</p>` : ''}<h2 class="sheet-title">${esc(title)}</h2>${
      sub ? `<p class="sheet-sub">${esc(sub)}</p>` : ''
    }</div>
      <button type="button" class="icon-btn" data-action="close-sheet" aria-label="Close">${icon('close')}</button>
    </div>`;
  }

  // ---------- Checkout ----------
  function openCheckout(eventId, tierId) {
    const e = BY_ID[eventId];
    if (!e) return;
    const wanted = e.tiers.find((t) => t.id === tierId && remaining(e, t) > 0);
    const tier = wanted || e.tiers.find((t) => remaining(e, t) > 0);
    if (!tier) return;
    const card = cardById(store.defaultCard) || store.cards[0];
    ui.checkout = { eventId, tierId: tier.id, qty: 1, step: 'tickets', cardId: card ? card.id : null, order: null, busy: false };
    openSheet('checkout', 'Get tickets', checkoutHTML());
  }

  function checkoutTotals() {
    const c = ui.checkout;
    const e = BY_ID[c.eventId];
    const tier = e.tiers.find((t) => t.id === c.tierId);
    const fee = feeFor(tier.price);
    const subtotal = round2(tier.price * c.qty);
    const fees = round2(fee * c.qty);
    return { e, tier, subtotal, fees, total: round2(subtotal + fees) };
  }

  function summaryHTML(t, qty) {
    if (t.total === 0) {
      return `<dl class="summary"><div><dt>${qty} × ${esc(t.tier.name)}</dt><dd>Free</dd></div><div class="total"><dt>Total</dt><dd>$0.00</dd></div></dl>`;
    }
    return `<dl class="summary">
      <div><dt>${qty} × ${esc(t.tier.name)}</dt><dd>${moneyExact(t.subtotal)}</dd></div>
      <div><dt>Service fee</dt><dd>${moneyExact(t.fees)}</dd></div>
      <div class="total"><dt>Total</dt><dd id="checkout-total">${moneyExact(t.total)}</dd></div>
    </dl>`;
  }

  function checkoutHTML() {
    const c = ui.checkout;
    const e = BY_ID[c.eventId];
    const when = `${dayLabel(e)}, ${fmtTime(e.start)} · ${e.venue.name}`;

    if (!store.signedIn) {
      return `${sheetHead('Sign in to continue', e.title)}
        <p class="sub">You need to be signed in to buy or reserve tickets.</p>
        <button type="button" class="btn btn-primary wide" data-action="sign-in" data-then="checkout">Sign in as ${esc(
          DATA.defaults.profile.name
        )}</button>`;
    }

    if (c.step === 'done') {
      const o = c.order;
      return `<div class="done-head">
          <span class="done-mark">${icon('check')}</span>
          <h2 class="sheet-title">You're going</h2>
          <p class="sheet-sub">${plural(o.qty, 'ticket')} for ${esc(o.title)}. They're saved under Saved, then Tickets.</p>
        </div>
        ${stubHTML(o)}
        <div class="btn-row">
          <button type="button" class="btn btn-ghost" data-action="close-sheet">Done</button>
          <button type="button" class="btn btn-primary" data-action="view-tickets">View my tickets</button>
        </div>`;
    }

    const t = checkoutTotals();
    const left = remaining(e, t.tier);
    const maxQty = Math.min(MAX_QTY, left);

    if (c.step === 'tickets') {
      const tiers = e.tiers
        .map((tier) => {
          const n = remaining(e, tier);
          const note = n === 0 ? 'Sold out' : n <= 20 ? `Only ${n} left` : '';
          return `<label class="tier-opt${n ? '' : ' soldout'}">
            <input type="radio" name="tier" value="${tier.id}" ${tier.id === c.tierId ? 'checked' : ''} ${n ? '' : 'disabled'}>
            <span class="tier-body">
              <span class="tier-name">${esc(tier.name)}</span>
              <span class="tier-desc">${esc(tier.desc)}</span>
              ${note ? `<span class="tier-left">${note}</span>` : ''}
            </span>
            <span class="tier-price">${esc(money(tier.price))}</span>
          </label>`;
        })
        .join('');
      return `${sheetHead('Choose tickets', when, `Step 1 of 2 · ${e.title}`)}
        <fieldset class="tier-pick"><legend class="sr-only">Ticket type</legend>${tiers}</fieldset>
        <div class="qty-row">
          <span id="qty-label">Quantity</span>
          <div class="stepper" role="group" aria-labelledby="qty-label">
            <button type="button" data-action="qty" data-delta="-1" aria-label="One fewer ticket" ${c.qty <= 1 ? 'disabled' : ''}>${icon('minus')}</button>
            <output id="qty-out" aria-live="polite">${c.qty}</output>
            <button type="button" data-action="qty" data-delta="1" aria-label="One more ticket" ${c.qty >= maxQty ? 'disabled' : ''}>${icon('plus')}</button>
          </div>
        </div>
        ${summaryHTML(t, c.qty)}
        <button type="button" class="btn btn-primary wide" data-action="checkout-next">Continue · ${
          t.total ? moneyExact(t.total) : 'Free'
        }</button>`;
    }

    // Step 2: review and pay
    const needsCard = t.total > 0;
    const cards = store.cards
      .map(
        (card) => `<label class="card-opt">
          <input type="radio" name="paycard" value="${card.id}" ${card.id === c.cardId ? 'checked' : ''}>
          <span class="card-brand" aria-hidden="true">${esc(brandShort(card.brand))}</span>
          <span class="setting-text"><span class="set-label">${esc(card.brand)} •••• ${esc(card.last4)}</span><span class="set-help">${esc(
          card.label
        )} · Expires ${esc(card.exp)}</span></span>
        </label>`
      )
      .join('');
    const payBlock = needsCard
      ? `<fieldset class="card-pick"><legend class="label">Pay with</legend>
          ${cards || '<p class="sub">You have no payment methods yet.</p>'}
          <button type="button" class="btn btn-small btn-ghost" data-action="add-card" data-then="checkout">${icon('plus', 'ic-sm')}Add payment method</button>
        </fieldset>`
      : '';
    const canPay = !c.busy && (!needsCard || cardById(c.cardId));
    return `${sheetHead('Review and pay', when, `Step 2 of 2 · ${e.title}`)}
      ${summaryHTML(t, c.qty)}
      ${payBlock}
      <p class="notice">${icon('info')}<span>Tickets go to ${esc(store.profile.email)} and appear under Saved, then Tickets. This is a demo checkout, so no payment is taken.</span></p>
      <div class="btn-row">
        <button type="button" class="btn btn-ghost" data-action="checkout-back">Back</button>
        <button type="button" class="btn btn-primary" data-action="pay" ${canPay ? '' : 'disabled'}>${
      c.busy ? 'Processing…' : needsCard ? `Pay ${moneyExact(t.total)}` : 'Confirm'
    }</button>
      </div>`;
  }

  const ORDER_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  function orderId() {
    let s = 'DR-';
    for (let i = 0; i < 6; i++) s += ORDER_CHARS[Math.floor(Math.random() * ORDER_CHARS.length)];
    return s;
  }

  function pay() {
    const c = ui.checkout;
    if (!c || c.busy) return;
    const t = checkoutTotals();
    if (t.total > 0 && !cardById(c.cardId)) return;
    c.busy = true;
    updateSheet(checkoutHTML());
    setTimeout(() => {
      if (ui.checkout !== c) return;
      const card = cardById(c.cardId);
      const order = {
        id: orderId(),
        eventId: t.e.id,
        title: t.e.title,
        tierId: t.tier.id,
        tierName: t.tier.name,
        qty: c.qty,
        unit: t.tier.price,
        fees: t.fees,
        total: t.total,
        card: t.total && card ? `${card.brand} •••• ${card.last4}` : null,
        day: t.e.day,
        doors: t.e.doors || null,
        start: t.e.start,
        venue: t.e.venue.name,
        createdAt: new Date().toISOString(),
      };
      store.orders.push(order);
      persist();
      c.busy = false;
      c.order = order;
      c.step = 'done';
      render({ keep: true });
      updateSheet(checkoutHTML());
      const heading = $('.sheet-title', sheetRoot);
      if (heading) {
        heading.setAttribute('tabindex', '-1');
        heading.focus({ preventScroll: true });
      }
    }, 650);
  }

  // ---------- Account sheets ----------
  function profileSheet() {
    const p = store.profile;
    return `${sheetHead('Edit profile')}
      <form class="form" id="profile-form" novalidate>
        <div class="field"><label for="pf-name">Full name</label><input id="pf-name" name="name" required autocomplete="name" value="${esc(p.name)}"></div>
        <div class="field"><label for="pf-email">Email</label><input id="pf-email" name="email" type="email" required autocomplete="email" value="${esc(p.email)}"></div>
        <div class="field"><label for="pf-city">Home city</label><input id="pf-city" name="city" required autocomplete="address-level2" value="${esc(p.city)}"></div>
        <p class="form-error" id="pf-error" role="alert" hidden></p>
        <div class="btn-row"><button type="button" class="btn btn-ghost" data-action="close-sheet">Cancel</button><button type="submit" class="btn btn-primary">Save</button></div>
      </form>`;
  }

  function cardSheet() {
    return `${sheetHead('Add payment method', 'This demo stores only the card brand, the last four digits and the expiry date.')}
      <form class="form" id="card-form" novalidate>
        <div class="field"><label for="cf-brand">Card brand</label>
          <select id="cf-brand" name="brand">${['Visa', 'Mastercard', 'American Express', 'Discover']
            .map((b) => `<option>${b}</option>`)
            .join('')}</select></div>
        <div class="field-row">
          <div class="field"><label for="cf-last4">Last four digits</label><input id="cf-last4" name="last4" inputmode="numeric" maxlength="4" placeholder="1234" autocomplete="off"></div>
          <div class="field"><label for="cf-exp">Expiry (MM/YY)</label><input id="cf-exp" name="exp" inputmode="numeric" maxlength="5" placeholder="09/29" autocomplete="off"></div>
        </div>
        <div class="field"><label for="cf-label">Nickname</label><input id="cf-label" name="label" maxlength="24" placeholder="Personal" autocomplete="off"></div>
        <label class="check"><input type="checkbox" name="makeDefault" ${store.cards.length ? '' : 'checked'}> Use as my default payment method</label>
        <p class="form-error" id="cf-error" role="alert" hidden></p>
        <div class="btn-row"><button type="button" class="btn btn-ghost" data-action="close-sheet">Cancel</button><button type="submit" class="btn btn-primary">Add card</button></div>
      </form>`;
  }

  function confirmSheet(title, text, confirmLabel, action, extra) {
    return `${sheetHead(title)}
      <p class="sub">${esc(text)}</p>
      <div class="btn-row">
        <button type="button" class="btn btn-ghost" data-action="close-sheet">Cancel</button>
        <button type="button" class="btn btn-danger" data-action="${action}" ${extra || ''}>${esc(confirmLabel)}</button>
      </div>`;
  }

  const FAQ = [
    ['How do I get into the event?', 'Open Saved, then Tickets, and show the barcode at the door. Venues scan it from your screen, so there is nothing to print.'],
    ['Can I get a refund?', 'Each organizer sets its own policy, listed under Good to know on the event page. If an event is cancelled, you are refunded automatically.'],
    ['Can I give a ticket to a friend?', 'Contact support with your order number and your friend’s email, and we will move the ticket to them if the organizer allows transfers.'],
    ['What is the service fee?', '10% of the ticket price plus $1.50 for each paid ticket. Free tickets have no fee. Turn on “Show prices with fees” to see all-in prices everywhere.'],
    ['Why don’t my saved events show on another device?', 'This demo keeps saved events, tickets and settings in this browser only.'],
  ];

  function helpSheet() {
    return `${sheetHead('Help and FAQ')}
      <div class="faq">${FAQ.map(([q, a]) => `<details><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join('')}</div>
      <button type="button" class="btn btn-ghost wide" data-action="contact">Still stuck? Contact support</button>`;
  }

  function contactSheet() {
    const email = 'support@doors.example';
    return `${sheetHead('Contact support', 'We reply within one business day.')}
      <div class="field"><span class="field-label">Email us</span>
        <div class="copy-box"><code id="support-email">${email}</code>
          <button type="button" class="btn btn-small btn-ghost" data-action="copy" data-copy="${email}" data-what="Email address">${icon('copy', 'ic-sm')}Copy</button></div>
      </div>
      <p class="sub">For questions about a ticket, include your order number. It starts with DR- and is printed under the barcode.</p>
      <button type="button" class="btn btn-primary wide" data-action="close-sheet">Done</button>`;
  }

  function privacySheet() {
    return `${sheetHead('Privacy and data')}
      <p class="sub">Doors keeps the following in this browser only. Nothing is sent to a server.</p>
      <ul class="plain-list">
        <li>Saved events and tickets</li>
        <li>Preferences and notification settings</li>
        <li>Payment method labels (brand, last four digits, expiry)</li>
      </ul>
      <button type="button" class="btn btn-ghost wide" data-action="reset-demo">Reset to sample data</button>`;
  }

  function resetStore(overrides) {
    store = Object.assign(clone(DATA.defaults), overrides || {});
    persist();
  }

  // ---------- Events: clicks ----------
  document.addEventListener('click', (ev) => {
    const el = ev.target.closest('[data-action]');
    if (!el || el.disabled) return;
    const d = el.dataset;

    switch (d.action) {
      case 'tab':
        closeSheet();
        if (d.tab === ui.route.name) ui.scroll[d.tab] = 0;
        go({ name: d.tab }, { reset: true });
        break;
      case 'open-event':
        openEvent(d.id);
        break;
      case 'back':
        goBack();
        break;
      case 'toggle-save':
        toggleSave(d.id);
        break;
      case 'go-search': {
        const params = {};
        if (d.date) params.date = d.date;
        if (d.cat) params.cats = [d.cat];
        if (d.focus) params.focus = true;
        goSearch(params);
        break;
      }
      case 'set-date':
        ui.search.date = d.date;
        ui.search.day = null;
        render({ keep: true });
        break;
      case 'set-day':
        if (ui.search.date === 'day' && ui.search.day === d.day) {
          ui.search.date = 'any';
          ui.search.day = null;
        } else {
          ui.search.date = 'day';
          ui.search.day = d.day;
        }
        render({ keep: true });
        break;
      case 'toggle-cat': {
        const cats = ui.search.cats;
        if (d.cat === 'all') ui.search.cats = [];
        else ui.search.cats = cats.includes(d.cat) ? cats.filter((c) => c !== d.cat) : cats.concat(d.cat);
        render({ keep: true });
        break;
      }
      case 'set-sort':
        ui.search.sort = d.sort;
        render({ keep: true });
        break;
      case 'clear-filters':
        ui.search = clone(EMPTY_SEARCH);
        render({ keep: true });
        break;
      case 'clear-query': {
        ui.search.q = '';
        const q = $('#q');
        q.value = '';
        updateResults();
        q.focus();
        break;
      }
      case 'saved-seg':
        ui.savedSeg = d.seg;
        render({ keep: true });
        break;
      case 'view-tickets':
        showSaved('tickets');
        break;
      case 'buy':
        openCheckout(d.id, d.tier);
        break;
      case 'qty': {
        const c = ui.checkout;
        const t = checkoutTotals();
        const maxQty = Math.min(MAX_QTY, remaining(t.e, t.tier));
        c.qty = Math.max(1, Math.min(maxQty, c.qty + Number(d.delta)));
        updateSheet(checkoutHTML());
        break;
      }
      case 'checkout-next':
        ui.checkout.step = 'pay';
        updateSheet(checkoutHTML());
        break;
      case 'checkout-back':
        ui.checkout.step = 'tickets';
        updateSheet(checkoutHTML());
        break;
      case 'pay':
        pay();
        break;
      case 'close-sheet':
        closeSheet();
        break;
      case 'toast-action': {
        const run = ui.toastAction;
        hideToast();
        if (run) run();
        break;
      }
      case 'copy':
        copyText(d.copy, d.what || 'Text');
        break;
      case 'fav-cat': {
        const favs = store.prefs.favCats;
        store.prefs.favCats = favs.includes(d.cat) ? favs.filter((c) => c !== d.cat) : favs.concat(d.cat);
        persist();
        render({ keep: true });
        break;
      }
      case 'set-clock':
        store.prefs.clock = d.clock;
        persist();
        render({ keep: true });
        toast(`Times now show as ${fmtTime('19:30')}`);
        break;
      case 'default-card':
        store.defaultCard = d.card;
        persist();
        render({ keep: true });
        toast('Default payment method updated');
        break;
      case 'remove-card': {
        const card = cardById(d.card);
        if (!card) break;
        openSheet(
          'remove-card',
          'Remove payment method',
          confirmSheet(
            `Remove ${card.brand} •••• ${card.last4}?`,
            'You can add it again at any time.',
            'Remove card',
            'confirm-remove-card',
            `data-card="${card.id}"`
          )
        );
        break;
      }
      case 'confirm-remove-card':
        store.cards = store.cards.filter((c) => c.id !== d.card);
        if (store.defaultCard === d.card) store.defaultCard = store.cards[0] ? store.cards[0].id : null;
        persist();
        closeSheet();
        render({ keep: true });
        toast('Payment method removed');
        break;
      case 'add-card':
        // From checkout, return to the payment step once the card is added.
        ui.afterCard = d.then === 'checkout' ? ui.checkout : null;
        openSheet('add-card', 'Add payment method', cardSheet());
        break;
      case 'edit-profile':
        openSheet('profile', 'Edit profile', profileSheet());
        break;
      case 'help':
        openSheet('help', 'Help and FAQ', helpSheet());
        break;
      case 'contact':
        openSheet('contact', 'Contact support', contactSheet());
        break;
      case 'privacy':
        openSheet('privacy', 'Privacy and data', privacySheet());
        break;
      case 'reset-demo':
        resetStore();
        closeSheet();
        render();
        toast('Sample data restored');
        break;
      case 'sign-out':
        openSheet(
          'sign-out',
          'Sign out',
          confirmSheet('Sign out?', 'Your saved events stay on this device. You need to sign in again to buy tickets.', 'Sign out', 'confirm-sign-out')
        );
        break;
      case 'confirm-sign-out':
        store.signedIn = false;
        persist();
        closeSheet();
        render();
        toast('Signed out');
        break;
      case 'sign-in': {
        store.signedIn = true;
        if (!store.profile || !store.profile.name) store.profile = clone(DATA.defaults.profile);
        persist();
        const resume = d.then === 'checkout' && ui.checkout;
        render();
        if (resume) updateSheet(checkoutHTML());
        toast(`Signed in as ${store.profile.name}`);
        break;
      }
      case 'delete-account':
        openSheet(
          'delete',
          'Delete account',
          confirmSheet(
            'Delete your account?',
            'This removes your profile, saved events, tickets and payment methods from this device. It cannot be undone.',
            'Delete account',
            'confirm-delete'
          )
        );
        break;
      case 'confirm-delete':
        resetStore({ signedIn: false, saved: [], orders: [], cards: [], defaultCard: null });
        closeSheet();
        render();
        toast('Account deleted');
        break;
      default:
        break;
    }
  });

  function copyText(text, what) {
    const done = () => toast(`${what} copied`);
    const fail = () => toast(`Couldn't copy. Select the text and copy it yourself.`);
    try {
      navigator.clipboard.writeText(text).then(done, fail);
    } catch (_) {
      fail();
    }
  }

  // ---------- Events: inputs ----------
  document.addEventListener('input', (ev) => {
    if (ev.target.id === 'q') {
      ui.search.q = ev.target.value;
      updateResults();
    }
  });

  document.addEventListener('change', (ev) => {
    const t = ev.target;
    if (t.id === 'date-pick') {
      if (t.value) {
        ui.search.date = 'day';
        ui.search.day = t.value;
      } else {
        ui.search.date = 'any';
        ui.search.day = null;
      }
      render({ keep: true });
      return;
    }
    if (t.dataset.setting) {
      const [group, key] = t.dataset.setting.split('.');
      store[group][key] = t.type === 'checkbox' ? t.checked : t.value;
      persist();
      if (t.type === 'checkbox') toast(`${t.dataset.label} ${t.checked ? 'on' : 'off'}`);
      else toast('Reminder timing saved');
      if (t.dataset.setting === 'notify.reminders') render({ keep: true });
      return;
    }
    if (t.name === 'tier' && ui.checkout) {
      ui.checkout.tierId = t.value;
      const tt = checkoutTotals();
      ui.checkout.qty = Math.max(1, Math.min(ui.checkout.qty, MAX_QTY, remaining(tt.e, tt.tier)));
      updateSheet(checkoutHTML());
      return;
    }
    if (t.name === 'paycard' && ui.checkout) {
      ui.checkout.cardId = t.value;
      updateSheet(checkoutHTML());
    }
  });

  document.addEventListener('submit', (ev) => {
    const form = ev.target;
    ev.preventDefault();
    const fd = new FormData(form);

    if (form.id === 'profile-form') {
      const name = String(fd.get('name') || '').trim();
      const email = String(fd.get('email') || '').trim();
      const city = String(fd.get('city') || '').trim();
      const err = $('#pf-error');
      let msg = '';
      if (!name) msg = 'Enter your name.';
      else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) msg = 'Enter an email address like name@example.com.';
      else if (!city) msg = 'Enter your home city.';
      if (msg) {
        err.textContent = msg;
        err.hidden = false;
        return;
      }
      Object.assign(store.profile, { name, email, city });
      persist();
      closeSheet();
      render({ keep: true });
      toast('Profile updated');
      return;
    }

    if (form.id === 'card-form') {
      const brand = String(fd.get('brand'));
      const last4 = String(fd.get('last4') || '').trim();
      const exp = String(fd.get('exp') || '').trim();
      const label = String(fd.get('label') || '').trim() || brand;
      const err = $('#cf-error');
      let msg = '';
      const m = /^(0[1-9]|1[0-2])\/(\d{2})$/.exec(exp);
      if (!/^\d{4}$/.test(last4)) msg = 'Enter the last four digits of the card.';
      else if (!m) msg = 'Enter the expiry as MM/YY, for example 09/29.';
      else {
        const expEnd = new Date(2000 + Number(m[2]), Number(m[1]), 1);
        if (expEnd <= TODAY) msg = 'That card has expired. Check the expiry date.';
      }
      if (msg) {
        err.textContent = msg;
        err.hidden = false;
        return;
      }
      const card = { id: `c${Date.now().toString(36)}`, brand, last4, exp, label };
      store.cards.push(card);
      if (fd.get('makeDefault') || !store.defaultCard) store.defaultCard = card.id;
      persist();

      const resume = ui.afterCard;
      ui.afterCard = null;
      if (resume) {
        resume.cardId = card.id;
        resume.step = 'pay';
        ui.checkout = resume;
        openSheet('checkout', 'Get tickets', checkoutHTML());
      } else {
        closeSheet();
      }
      render({ keep: true });
      toast(`${brand} •••• ${last4} added`);
    }
  });

  document.addEventListener('keydown', (ev) => {
    if (sheetRoot.hidden) return;
    if (ev.key === 'Escape') {
      ev.preventDefault();
      closeSheet();
      return;
    }
    if (ev.key === 'Tab') {
      const f = focusables();
      if (!f.length) return;
      const first = f[0];
      const last = f[f.length - 1];
      if (ev.shiftKey && (document.activeElement === first || !sheetRoot.contains(document.activeElement))) {
        ev.preventDefault();
        last.focus();
      } else if (!ev.shiftKey && document.activeElement === last) {
        ev.preventDefault();
        first.focus();
      }
    }
  });

  // ---------- Start ----------
  const initial = parseHash(location.hash.slice(1));
  if (initial) {
    ui.route = initial;
    if (initial.name === 'event') ui.backStack = [{ name: 'discover' }];
  }
  render();
})();
