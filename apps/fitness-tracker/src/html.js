// A tiny tagged-template renderer. Interpolated values are escaped unless they are
// themselves the result of `html` (or `raw`), so markup composes safely.

class SafeHtml {
  constructor(value) {
    this.value = value;
  }
  toString() {
    return this.value;
  }
}

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ESCAPES[c]);

export const raw = (s) => new SafeHtml(String(s));

function stringify(value) {
  if (value === null || value === undefined || value === false) return '';
  if (Array.isArray(value)) return value.map(stringify).join('');
  if (value instanceof SafeHtml) return value.value;
  return escapeHtml(value);
}

export function html(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i++) out += stringify(values[i]) + strings[i + 1];
  return new SafeHtml(out);
}

/** Space-separated class names from strings and `{ name: condition }` objects. */
export function cx(...parts) {
  return parts
    .flatMap((p) =>
      p && typeof p === 'object'
        ? Object.entries(p)
            .filter(([, on]) => on)
            .map(([k]) => k)
        : [p],
    )
    .filter(Boolean)
    .join(' ');
}

const ICONS = {
  today: '<path d="M4 9h16M8 3v4M16 3v4"/><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M9 14l2 2 4-4"/>',
  workouts: '<path d="M6.5 6.5v11M17.5 6.5v11M3.5 9v6M20.5 9v6M6.5 12h11"/>',
  log: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 10h6M9 14h6M9 18h3"/>',
  progress: '<path d="M4 20h16"/><path d="M7 16v-4M12 16V8M17 16v-7"/>',
  profile: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  next: '<path d="M9 5l7 7-7 7"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/>',
  bell: '<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  trash: '<path d="M5 7h14M10 7V5h4v2M7 7l1 13h8l1-13"/>',
  flame:
    '<path d="M12 21c-3.9 0-6.5-2.6-6.5-6.2 0-3.2 2.2-5.3 3.6-7 .4 1.8 1.4 3 2.4 3.4C11.3 7.5 12.6 5 15 3c-.3 2.6.8 4.6 2.2 6.4 1 1.3 1.8 2.9 1.8 5.1C19 18.3 16 21 12 21z"/>',
  rest: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
};

export const icon = (name, label = '') =>
  raw(
    `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${
      label ? `role="img" aria-label="${escapeHtml(label)}"` : 'aria-hidden="true"'
    }>${ICONS[name] ?? ''}</svg>`,
  );
