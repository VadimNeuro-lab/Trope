// Application state: loading, saving, and the pure updates the screens apply to it.

import { addDays, dayKey } from './dates.js';
import { createInitialState } from './seed.js';

export const STORAGE_KEY = 'workset.state.v1';

function isValidState(value) {
  return (
    value?.version === 1 &&
    typeof value.profile === 'object' &&
    Array.isArray(value.schedule) &&
    value.schedule.length === 7 &&
    Array.isArray(value.goals) &&
    Array.isArray(value.sessions)
  );
}

/** Reads saved state, falling back to a fresh state when storage is empty, blocked or corrupt. */
export function loadState(storage, today) {
  try {
    const saved = JSON.parse(storage?.getItem(STORAGE_KEY) ?? 'null');
    if (isValidState(saved)) return pruneOverrides({ overrides: {}, draft: null, ...saved }, today);
  } catch {
    // Unreadable storage behaves like a first visit.
  }
  return createInitialState(today);
}

export function saveState(storage, state) {
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(state));
    return true;
  } catch {
    return false;
  }
}

/** Drops one-day plan changes that are more than a week old. */
function pruneOverrides(state, today) {
  const cutoff = dayKey(addDays(today, -7));
  const overrides = Object.fromEntries(Object.entries(state.overrides).filter(([key]) => key >= cutoff));
  return { ...state, overrides };
}

/** A minimal observable store. `silent` updates persist without re-rendering. */
export function createStore(initial, storage) {
  let state = initial;
  const listeners = new Set();
  return {
    get state() {
      return state;
    },
    update(fn, { silent = false } = {}) {
      state = fn(state);
      saveState(storage, state);
      if (!silent) listeners.forEach((l) => l(state));
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

// ---- Updates ------------------------------------------------------------------

const byDate = (a, b) => (a.date === b.date ? a.loggedAt.localeCompare(b.loggedAt) : a.date.localeCompare(b.date));

export const addSession = (state, session) => ({ ...state, sessions: [...state.sessions, session].sort(byDate), draft: null });

export const deleteSession = (state, id) => ({ ...state, sessions: state.sessions.filter((s) => s.id !== id) });

export const clearSampleSessions = (state) => ({ ...state, sessions: state.sessions.filter((s) => !s.sample) });

export const hasSampleSessions = (state) => state.sessions.some((s) => s.sample);

export const setDraft = (state, draft) => ({ ...state, draft });

const mapGoal = (state, id, fn) => ({ ...state, goals: state.goals.map((g) => (g.id === id ? fn(g) : g)) });

export const setGoalTarget = (state, id, target) => mapGoal(state, id, (g) => ({ ...g, target }));

export const setGoalCurrent = (state, id, current) => mapGoal(state, id, (g) => ({ ...g, current }));

export const addGoal = (state, goal) => ({ ...state, goals: [...state.goals, goal] });

export const removeGoal = (state, id) => ({ ...state, goals: state.goals.filter((g) => g.id !== id || g.kind !== 'custom') });

export const goalById = (state, id) => state.goals.find((g) => g.id === id) ?? null;

export function setSchedule(state, weekday, workoutId) {
  const schedule = [...state.schedule];
  schedule[weekday] = workoutId || null;
  return { ...state, schedule };
}

/** Swaps the workout for one date only, leaving the weekly plan alone. */
export const setOverride = (state, key, workoutId) => ({ ...state, overrides: { ...state.overrides, [key]: workoutId || null } });

export const updateProfile = (state, patch) => ({ ...state, profile: { ...state.profile, ...patch } });

export const updateNotifications = (state, patch) => ({ ...state, notifications: { ...state.notifications, ...patch } });

export const resetState = (today) => createInitialState(today, { samples: false });
