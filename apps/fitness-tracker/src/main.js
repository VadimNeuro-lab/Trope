// App shell: hash routing, rendering, the top bar and bottom sheet, event
// delegation, toasts, and install/offline support.

import { html, icon } from './html.js';
import { startOfDay } from './dates.js';
import { createStore, loadState } from './store.js';
import { parseRoute } from './routes.js';
import * as dashboard from './screens/dashboard.js';
import * as workouts from './screens/workouts.js';
import * as log from './screens/log.js';
import * as progress from './screens/progress.js';
import * as profile from './screens/profile.js';

const SCREENS = { today: dashboard, workouts, log, progress, profile };
const NAV = [
  ['today', 'Today'],
  ['workouts', 'Workouts'],
  ['log', 'Log'],
  ['progress', 'Progress'],
  ['profile', 'Profile'],
];

function openStorage() {
  try {
    const s = window.localStorage;
    s.setItem('workset.probe', '1');
    s.removeItem('workset.probe');
    return s;
  } catch {
    return null;
  }
}

const storage = openStorage();
const store = createStore(loadState(storage, startOfDay(new Date())), storage);
const freshUi = () =>
  Object.fromEntries(
    Object.entries(SCREENS)
      .filter(([, s]) => s.initialUi)
      .map(([k, s]) => [k, s.initialUi()]),
  );
const ui = freshUi();

const device = document.querySelector('.device');
const appbar = document.getElementById('appbar');
const nav = document.getElementById('nav');
const main = document.getElementById('screen');
const sheetEl = document.getElementById('sheet');
const toastEl = document.getElementById('toast');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

// ---- Install & offline ----------------------------------------------------

const standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
const topLevel = window.top === window;
const canInstall = topLevel && window.isSecureContext && 'serviceWorker' in navigator;
let installPrompt = null;

function installStatus() {
  if (standalone) return 'installed';
  if (!canInstall) return 'unavailable';
  if (installPrompt) return 'prompt';
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  return ios ? 'ios' : 'manual';
}

if (canInstall) {
  navigator.serviceWorker.register('sw.js').catch(() => {
    // Without a service worker the app still works; it just needs the network.
  });
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    installPrompt = event;
    render();
  });
  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    toast('Workset is on your Home Screen');
    render();
  });
}

// ---- Rendering ------------------------------------------------------------

// The host page may set its own theme; only override it while the user has picked one.
const hostTheme = document.documentElement.getAttribute('data-theme');
function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === 'light' || theme === 'dark') root.setAttribute('data-theme', theme);
  else if (hostTheme) root.setAttribute('data-theme', hostTheme);
  else root.removeAttribute('data-theme');
}

function renderNav(active) {
  nav.innerHTML = String(html`<ul class="nav-list">
    ${NAV.map(
      ([id, label]) => html`<li>
        <a class="nav-link" href="#${id}" ${id === active ? html`aria-current="page"` : ''}>
          <span class="nav-icon">${icon(id)}</span><span class="nav-label">${label}</span>
        </a>
      </li>`,
    )}
  </ul>`);
}

function renderAppbar(route, screen, ctx) {
  const back = route.param ? html`<a class="appbar-back" href="#${route.screen}">${icon('back')}${screen.title}</a>` : '';
  appbar.innerHTML = String(html`<div class="appbar-start">${back}</div>
    <p class="appbar-title" aria-hidden="true">${screen.appbarTitle?.(ctx) ?? screen.title}</p>
    <div class="appbar-end">${screen.appbarAction?.(ctx) ?? ''}</div>`);
}

// The top bar shows the screen's title once the large title has scrolled out of view.
let titleObserver = null;
function watchTitle() {
  titleObserver?.disconnect();
  const title = main.querySelector('.page-title');
  if (!title || !('IntersectionObserver' in window)) {
    appbar.classList.toggle('is-condensed', !title);
    return;
  }
  titleObserver = new IntersectionObserver(([entry]) => appbar.classList.toggle('is-condensed', !entry.isIntersecting), {
    root: main,
  });
  titleObserver.observe(title);
}

function renderSheet(markup) {
  const wasOpen = sheetEl.childElementCount > 0;
  sheetEl.innerHTML = markup;
  const open = sheetEl.childElementCount > 0;
  sheetEl.classList.toggle('is-entering', open && !wasOpen && !reducedMotion.matches);
  // While a sheet is open, everything behind it is out of reach.
  for (const el of [appbar, main, nav]) el.inert = open;
}

/** Re-renders the current screen, keeping focus and the caret in the field being edited. */
function render() {
  const route = parseRoute(location.hash);
  const screen = SCREENS[route.screen];
  const active = document.activeElement;
  const focusId = active && device.contains(active) ? active.id : '';
  let selection = null;
  try {
    if (focusId && typeof active.selectionStart === 'number') selection = [active.selectionStart, active.selectionEnd];
  } catch {
    // Some input types do not expose a selection.
  }

  const now = new Date();
  const ctx = {
    state: store.state,
    today: startOfDay(now),
    now,
    ui,
    route,
    storageOk: Boolean(storage),
    install: installStatus(),
  };
  main.innerHTML = String(screen.render(ctx));
  renderSheet(String(screen.sheet?.(ctx) ?? ''));
  renderAppbar(route, screen, ctx);
  renderNav(route.screen);
  applyTheme(store.state.profile.theme);
  watchTitle();
  document.title = `${screen.appbarTitle?.(ctx) ?? screen.title} · Workset`;

  const again = focusId && document.getElementById(focusId);
  if (again) {
    again.focus({ preventScroll: true });
    if (selection) {
      try {
        again.setSelectionRange(...selection);
      } catch {
        // Ignore inputs without selection support.
      }
    }
  }
}

// Each tab keeps its scroll position, the way native tab bars do.
const scrollMemory = new Map();
let currentHash = location.hash || '#today';

function onRouteChange() {
  scrollMemory.set(currentHash, main.scrollTop);
  currentHash = location.hash || '#today';
  // Confirmations and sheets never carry over to another screen.
  ui.progress.confirmDelete = null;
  Object.assign(ui.profile, { confirmGoal: null, confirmReset: false });
  Object.assign(ui.log, { confirmDiscard: false, errors: [], picker: false });
  render();
  const { anchor } = parseRoute(location.hash);
  const target = anchor && document.getElementById(`section-${anchor}`);
  if (target) target.scrollIntoView({ block: 'start' });
  else main.scrollTop = scrollMemory.get(currentHash) ?? 0;
  main.focus({ preventScroll: true });
}

let toastTimer = 0;
function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove('is-visible'), 3200);
}

const app = {
  store,
  ui,
  today: () => startOfDay(new Date()),
  render,
  toast,
  navigate(hash) {
    if (location.hash === hash) onRouteChange();
    else location.hash = hash;
  },
  focus(selector) {
    document.querySelector(selector)?.focus();
  },
  resetUi() {
    Object.assign(ui, freshUi());
  },
};

// ---- Events ---------------------------------------------------------------

const handlers = Object.assign(
  {
    async 'app:install'() {
      if (!installPrompt) return;
      installPrompt.prompt();
      await installPrompt.userChoice.catch(() => null);
      installPrompt = null;
      render();
    },
  },
  ...Object.values(SCREENS).map((s) => s.handlers ?? {}),
);

function delegate(type, attribute) {
  document.addEventListener(type, (event) => {
    const el = event.target.closest(`[${attribute}]`);
    const handler = el && handlers[el.getAttribute(attribute)];
    if (!handler || el.disabled) return;
    if (type === 'click' || type === 'submit') event.preventDefault();
    handler(app, el, event);
  });
}

delegate('click', 'data-action');
delegate('change', 'data-change');
delegate('input', 'data-input');
delegate('submit', 'data-submit');

// Tapping the tab you're already on scrolls back to the top.
nav.addEventListener('click', (event) => {
  const link = event.target.closest('.nav-link');
  if (!link || link.getAttribute('href') !== (location.hash || '#today')) return;
  event.preventDefault();
  main.scrollTo({ top: 0, behavior: reducedMotion.matches ? 'auto' : 'smooth' });
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') sheetEl.querySelector('[data-sheet-dismiss]')?.click();
});

store.subscribe(render);
window.addEventListener('hashchange', onRouteChange);
// Coming back to the app on a new day should show that day's plan.
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) render();
});

render();
