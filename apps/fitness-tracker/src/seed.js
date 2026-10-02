// First-run state: a sensible plan and goals, plus eight weeks of sample sessions
// generated relative to today so the dashboard and charts have something to show.
// Sample sessions are flagged and can be cleared from the Profile screen.

import { addDays, dayKey } from './dates.js';
import { getExercise, getWorkout } from './catalog.js';

// Indexed by Date#getDay(): Sunday first.
export const DEFAULT_SCHEDULE = [null, 'upper-push', 'zone2-run', 'lower-strength', null, 'upper-pull', 'mobility-flow'];

export function defaultGoals() {
  return [
    { id: 'weekly-sessions', kind: 'sessions', title: 'Workouts per week', target: 4 },
    { id: 'weekly-minutes', kind: 'minutes', title: 'Active minutes per week', target: 180 },
    { id: 'goal-squat', kind: 'custom', title: 'Back squat 1RM', start: 85, current: 95, target: 110, unit: 'kg' },
    { id: 'goal-5k', kind: 'custom', title: '5 km run time', start: 31, current: 27.5, target: 25, unit: 'min' },
    { id: 'goal-pullups', kind: 'custom', title: 'Strict pull-ups in one set', start: 4, current: 8, target: 12, unit: 'reps' },
  ];
}

const roundTo = (n, step) => Math.round(n / step) * step;

function sampleSession(workout, date, daysAgo) {
  // Loads ramp up ~2.5% a week toward today's prescription: visible progressive overload.
  const factor = 1 - 0.025 * Math.floor(daysAgo / 7);
  return {
    id: `sample-${dayKey(date)}`,
    date: dayKey(date),
    workoutId: workout.id,
    name: workout.name,
    minutes: workout.minutes + ((daysAgo * 13) % 9) - 4,
    rpe: 6 + ((daysAgo * 5) % 4),
    notes: '',
    loggedAt: new Date(date.getFullYear(), date.getMonth(), date.getDate(), 18, 30).toISOString(),
    sample: true,
    exercises: workout.exercises.map((item) => {
      const info = getExercise(item.exercise);
      return {
        exerciseId: item.exercise,
        name: info.name,
        group: info.group,
        measure: info.measure,
        sets: Array.from({ length: item.sets }, (_, i) => ({
          // The last set of a hard exercise sometimes falls a rep short.
          reps: i === item.sets - 1 && info.measure === 'reps' && (daysAgo + i) % 3 === 0 ? Math.max(1, item.reps - 1) : item.reps,
          weight: item.weight ? roundTo(item.weight * factor, 2.5) : 0,
        })),
      };
    }),
  };
}

export function sampleSessions(today, schedule = DEFAULT_SCHEDULE, days = 56) {
  const sessions = [];
  for (let daysAgo = days; daysAgo >= 1; daysAgo--) {
    const date = addDays(today, -daysAgo);
    const workout = getWorkout(schedule[date.getDay()]);
    // Skip roughly one planned session in six, like a real training block.
    if (!workout || (daysAgo * 7 + 3) % 11 < 2) continue;
    sessions.push(sampleSession(workout, date, daysAgo));
  }
  return sessions;
}

export function createInitialState(today, { samples = true } = {}) {
  return {
    version: 1,
    profile: {
      name: 'Alex',
      since: dayKey(addDays(today, -210)),
      level: 'intermediate',
      sessionLength: 45,
      units: 'kg',
      weekStart: 1,
      theme: 'system',
    },
    schedule: [...DEFAULT_SCHEDULE],
    overrides: {},
    goals: defaultGoals(),
    notifications: { reminders: true, reminderTime: '07:30', weeklySummary: true, milestones: true, restDay: false },
    sessions: samples ? sampleSessions(today) : [],
    draft: null,
  };
}
