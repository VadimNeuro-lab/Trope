// Calendar helpers. Days are identified by local-time keys ("2026-10-02") so that
// a session logged late in the evening never slides into the next day in UTC.

export const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
export const WEEKDAYS_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const MONTHS_SHORT = MONTHS.map((m) => m.slice(0, 3));

const pad = (n) => String(n).padStart(2, '0');

export const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

export const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);

export const dayKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

export function parseDayKey(key) {
  const [y, m, d] = String(key).split('-').map(Number);
  return new Date(y, m - 1, d);
}

export const isDayKey = (key) => /^\d{4}-\d{2}-\d{2}$/.test(String(key)) && dayKey(parseDayKey(key)) === key;

/** Whole days from `b` to `a`; rounding absorbs daylight-saving shifts. */
export const diffDays = (a, b) => Math.round((startOfDay(a) - startOfDay(b)) / 86400000);

/** First day of the week containing `d`. `weekStart` is 0 (Sunday) or 1 (Monday). */
export function startOfWeek(d, weekStart = 1) {
  const offset = (d.getDay() - weekStart + 7) % 7;
  return addDays(startOfDay(d), -offset);
}

export const weekDays = (d, weekStart = 1) => {
  const start = startOfWeek(d, weekStart);
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
};

/** ISO-8601 week number, the one printed on most training calendars. */
export function isoWeek(d) {
  const t = startOfDay(d);
  t.setDate(t.getDate() + 3 - ((t.getDay() + 6) % 7));
  const firstThursday = new Date(t.getFullYear(), 0, 4);
  return 1 + Math.round(((t - firstThursday) / 86400000 - 3 + ((firstThursday.getDay() + 6) % 7)) / 7);
}

export const formatLongDate = (d) => `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`;
export const formatShortDate = (d) => `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
export const formatDayAndDate = (d) => `${WEEKDAYS_SHORT[d.getDay()]} ${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
export const formatMonthYear = (d) => `${MONTHS[d.getMonth()]} ${d.getFullYear()}`;

export function formatRange(start, end) {
  if (start.getMonth() === end.getMonth()) return `${start.getDate()}–${end.getDate()} ${MONTHS_SHORT[end.getMonth()]}`;
  return `${formatShortDate(start)} – ${formatShortDate(end)}`;
}

/** "Today", "Yesterday", or a short weekday-and-date label. */
export function relativeDay(d, today) {
  const delta = diffDays(today, d);
  if (delta === 0) return 'Today';
  if (delta === 1) return 'Yesterday';
  return formatDayAndDate(d);
}
