// Hash routes. Plain tokens only ("#progress", "#workout-upper-push"), so links
// survive hosts that pass nothing but a bare anchor through.

export const SCREEN_IDS = ['today', 'workouts', 'log', 'progress', 'profile'];

/** "#workout-upper-push" → workout detail; "#profile-plan" → Profile, scrolled to its plan. */
export function parseRoute(hash) {
  const h = String(hash).replace(/^#/, '');
  if (h.startsWith('workout-')) return { screen: 'workouts', param: h.slice('workout-'.length), anchor: null };
  const [screen, ...rest] = h.split('-');
  if (SCREEN_IDS.includes(screen)) return { screen, param: null, anchor: rest.join('-') || null };
  return { screen: 'today', param: null, anchor: null };
}
