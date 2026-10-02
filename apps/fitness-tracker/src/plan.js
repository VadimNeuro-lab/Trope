// The weekly training plan: which workout is assigned to a given day, and how
// that day went.

import { dayKey, diffDays } from './dates.js';
import { getWorkout } from './catalog.js';

/** Workout id assigned to `date` (a one-day override wins over the weekly plan), or null for rest. */
export function plannedWorkoutId(state, date) {
  const key = dayKey(date);
  if (Object.hasOwn(state.overrides ?? {}, key)) return state.overrides[key];
  return state.schedule[date.getDay()] ?? null;
}

export const plannedWorkout = (state, date) => getWorkout(plannedWorkoutId(state, date));

/**
 * How a day in the plan stands relative to today:
 * done · today · upcoming · missed · rest
 */
export function dayStatus(state, date, today) {
  const key = dayKey(date);
  const workout = plannedWorkout(state, date);
  const sessions = state.sessions.filter((s) => s.date === key);
  const delta = diffDays(date, today);
  let status;
  if (sessions.length) status = 'done';
  else if (!workout) status = 'rest';
  else if (delta === 0) status = 'today';
  else if (delta > 0) status = 'upcoming';
  else status = 'missed';
  return { date, key, workout, sessions, status, isToday: delta === 0 };
}

/** Today's planned workout and whether a session for it has been logged. */
export function todayPlan(state, today) {
  const workout = plannedWorkout(state, today);
  const key = dayKey(today);
  const logged = state.sessions.filter((s) => s.date === key);
  const completed = workout ? (logged.find((s) => s.workoutId === workout.id) ?? null) : null;
  return { workout, logged, completed };
}
