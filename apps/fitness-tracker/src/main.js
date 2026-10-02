// App shell: hash routing, rendering, event delegation and toasts.

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

const nav = document.getElementById('nav');
const main = document.getElementById('screen');
const toastEl = document.getElementById('toast');

// The host page may set its own theme; only override it while the user has picked one.
const hostTheme = document.documentElement.getAttribute('data-theme');
function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === 'light' || theme === 'dark') root.setAttribute('data-theme', theme);
  else if (hostTheme) root.setAttribute('data-theme', hostTheme);
  else root.removeAttribute('data-theme');
}

function renderNav(active) {
  nav.innerHTML = String(html`<a class="brand" href="#today"><span class="brand-mark" aria-hidden="true"></span>Workset</a>
    <ul class="nav-list">
      ${NAV.map(
        ([id, label]) => html`<li>
          <a class="nav-link" href="#${id}" ${id === active ? html`aria-current="page"` : ''}>
            <span class="nav-icon">${icon(id)}</span><span class="nav-label">${label}</span>
          </a>
        </li>`,
      )}
    </ul>`);
}

/** Re-renders the current screen, keeping focus and the caret in the field being edited. */
function render() {
  const route = parseRoute(location.hash);
  const screen = SCREENS[route.screen];
  const active = document.activeElement;
  const focusId = active && main.contains(active) ? active.id : '';
  let selection = null;
  try {
    if (focusId && typeof active.selectionStart === 'number') selection = [active.selectionStart, active.selectionEnd];
  } catch {
    // Some input types do not expose a selection.
  }

  const now = new Date();
  main.innerHTML = String(screen.render({ state: store.state, today: startOfDay(now), now, ui, route, storageOk: Boolean(storage) }));
  renderNav(route.screen);
  applyTheme(store.state.profile.theme);
  document.title = `${screen.title} · Workset`;

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

function onRouteChange() {
  // Confirmations never carry over to another screen.
  ui.progress.confirmDelete = null;
  Object.assign(ui.profile, { confirmGoal: null, confirmReset: false });
  Object.assign(ui.log, { confirmDiscard: false, errors: [] });
  render();
  const { anchor } = parseRoute(location.hash);
  const target = anchor && document.getElementById(`section-${anchor}`);
  if (target) target.scrollIntoView({ block: 'start' });
  else window.scrollTo(0, 0);
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

const handlers = Object.assign({}, ...Object.values(SCREENS).map((s) => s.handlers ?? {}));

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

store.subscribe(render);
window.addEventListener('hashchange', onRouteChange);
// Coming back to the tab on a new day should show that day's plan.
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) render();
});

render();
