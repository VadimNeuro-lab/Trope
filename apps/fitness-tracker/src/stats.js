// Pure training statistics. Every function takes sessions and dates explicitly,
// so the screens and the tests share one source of truth.

import { addDays, dayKey, startOfWeek } from './dates.js';
import { getExercise } from './catalog.js';

const sum = (list, fn) => list.reduce((total, x) => total + fn(x), 0);

const isTimed = (exercise) => (exercise.measure ?? getExercise(exercise.exerciseId)?.measure) === 'time';

/** Kilograms moved in a session: weight × reps over every rep-based set. */
export const sessionVolume = (session) =>
  sum(
    session.exercises.filter((e) => !isTimed(e)),
    (e) => sum(e.sets, (s) => s.weight * s.reps),
  );

export const sessionSetCount = (session) => sum(session.exercises, (e) => e.sets.length);

/** Sessions on or after `start` and before `end` (both Dates, end exclusive). */
export function sessionsBetween(sessions, start, end) {
  const from = dayKey(start);
  const to = dayKey(end);
  return sessions.filter((s) => s.date >= from && s.date < to);
}

const round1 = (n) => Math.round(n * 10) / 10;

/** Totals for the calendar week that contains `refDate`, with a per-day breakdown. */
export function summarizeWeek(sessions, refDate, weekStart = 1) {
  const start = startOfWeek(refDate, weekStart);
  const inWeek = sessionsBetween(sessions, start, addDays(start, 7));
  const days = Array.from({ length: 7 }, (_, i) => {
    const date = addDays(start, i);
    const key = dayKey(date);
    const list = inWeek.filter((s) => s.date === key);
    return {
      date,
      key,
      sessions: list,
      minutes: sum(list, (s) => s.minutes),
      volume: sum(list, sessionVolume),
      sets: sum(list, sessionSetCount),
    };
  });
  const rated = inWeek.filter((s) => Number.isFinite(s.rpe));
  return {
    start,
    end: addDays(start, 6),
    days,
    sessions: inWeek,
    count: inWeek.length,
    minutes: sum(inWeek, (s) => s.minutes),
    volume: sum(inWeek, sessionVolume),
    sets: sum(inWeek, sessionSetCount),
    activeDays: days.filter((d) => d.sessions.length > 0).length,
    avgRpe: rated.length ? round1(sum(rated, (s) => s.rpe) / rated.length) : null,
  };
}

/** One entry per week, oldest first, ending with the week that contains `refDate`. */
export function weeklyHistory(sessions, refDate, weekStart = 1, weeks = 8) {
  const current = startOfWeek(refDate, weekStart);
  return Array.from({ length: weeks }, (_, i) => {
    const start = addDays(current, (i - weeks + 1) * 7);
    const list = sessionsBetween(sessions, start, addDays(start, 7));
    return {
      start,
      count: list.length,
      minutes: sum(list, (s) => s.minutes),
      volume: sum(list, sessionVolume),
    };
  });
}

/**
 * Consecutive weeks that met the session target, counting back from the newest.
 * The newest week is still in progress, so falling short there does not break the streak.
 */
export function goalStreak(history, target) {
  let streak = 0;
  for (let i = history.length - 1; i >= 0; i--) {
    const met = history[i].count >= target;
    if (met) streak++;
    else if (i !== history.length - 1) break;
  }
  return streak;
}

/** Share of completed weeks (all but the newest) that met the target, 0–1. */
export function consistencyRate(history, target) {
  const finished = history.slice(0, -1);
  if (!finished.length) return 0;
  return finished.filter((w) => w.count >= target).length / finished.length;
}

/** Working sets per muscle group, largest first. */
export function muscleBreakdown(sessions) {
  const totals = new Map();
  for (const session of sessions) {
    for (const e of session.exercises) {
      const group = e.group ?? getExercise(e.exerciseId)?.group ?? 'other';
      totals.set(group, (totals.get(group) ?? 0) + e.sets.length);
    }
  }
  return [...totals.entries()].map(([group, sets]) => ({ group, sets })).sort((a, b) => b.sets - a.sets);
}

/** Epley estimate of a one-rep max. Sets above 12 reps are too far out to be useful. */
export function estimateOneRepMax(weight, reps) {
  if (!(weight > 0) || !(reps >= 1) || reps > 12) return null;
  return reps === 1 ? weight : weight * (1 + reps / 30);
}

/** Best estimated 1RM for one exercise in each week; weeks without the lift are null. */
export function liftTrend(sessions, exerciseId, refDate, weekStart = 1, weeks = 8) {
  const current = startOfWeek(refDate, weekStart);
  return Array.from({ length: weeks }, (_, i) => {
    const start = addDays(current, (i - weeks + 1) * 7);
    let best = null;
    for (const session of sessionsBetween(sessions, start, addDays(start, 7))) {
      for (const e of session.exercises) {
        if (e.exerciseId !== exerciseId) continue;
        for (const s of e.sets) {
          const e1rm = estimateOneRepMax(s.weight, s.reps);
          if (e1rm !== null && (best === null || e1rm > best)) best = e1rm;
        }
      }
    }
    return { start, value: best === null ? null : round1(best) };
  });
}

/** Weighted, rep-based exercises in the log, most frequently trained first. */
export function liftsWithHistory(sessions) {
  const counts = new Map();
  for (const session of sessions) {
    for (const e of session.exercises) {
      if (isTimed(e) || !e.sets.some((s) => s.weight > 0)) continue;
      counts.set(e.exerciseId, (counts.get(e.exerciseId) ?? 0) + 1);
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([id]) => id);
}

/** Relative change from `previous` to `current`, or null when there is no baseline. */
export const percentChange = (current, previous) => (previous > 0 ? (current - previous) / previous : null);

/** Progress toward a goal from its starting point, 0–1. Works for goals that count down. */
export function goalProgress({ start = 0, current, target }) {
  if (target === start) return current === target ? 1 : 0;
  return Math.min(1, Math.max(0, (current - start) / (target - start)));
}

/** The most recent logged performance of an exercise before `beforeKey` ("YYYY-MM-DD"), if any. */
export function lastPerformance(sessions, exerciseId, beforeKey) {
  let best = null;
  for (const session of sessions) {
    if (session.date >= beforeKey || (best && session.date <= best.date)) continue;
    const found = session.exercises.find((e) => e.exerciseId === exerciseId && e.sets.length);
    if (found) best = { date: session.date, sets: found.sets, measure: found.measure };
  }
  return best;
}
