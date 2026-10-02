// The session being logged. Inputs are kept as the strings the user typed, in the
// unit they typed them in, and only parsed when the session is saved.

import { dayKey, isDayKey, parseDayKey } from './dates.js';
import { getExercise, getWorkout } from './catalog.js';
import { fromDisplayWeight, toDisplayWeight } from './units.js';

const text = (n) => (n ? String(n) : '');

function nextKey(draft) {
  draft.seq = (draft.seq ?? 0) + 1;
  return `k${draft.seq}`;
}

function draftExercise(draft, exerciseId, sets) {
  const info = getExercise(exerciseId);
  return {
    key: nextKey(draft),
    exerciseId,
    name: info?.name ?? exerciseId,
    group: info?.group ?? 'other',
    measure: info?.measure ?? 'reps',
    sets: sets.map((s) => ({ key: nextKey(draft), ...s })),
  };
}

export function emptyDraft(date, units) {
  return { workoutId: null, name: 'Custom session', date: dayKey(date), minutes: '', rpe: 7, notes: '', units, seq: 0, exercises: [] };
}

/** A draft prefilled with a routine's prescribed sets, reps and loads. */
export function draftFromWorkout(workoutId, date, units) {
  const workout = getWorkout(workoutId);
  if (!workout) return emptyDraft(date, units);
  const draft = { ...emptyDraft(date, units), workoutId, name: workout.name, minutes: String(workout.minutes) };
  draft.exercises = workout.exercises.map((item) =>
    draftExercise(
      draft,
      item.exercise,
      Array.from({ length: item.sets }, () => ({
        weight: text(toDisplayWeight(item.weight, units)),
        reps: String(item.reps),
      })),
    ),
  );
  return draft;
}

export function addExercise(draft, exerciseId) {
  const next = structuredClone(draft);
  next.exercises.push(draftExercise(next, exerciseId, [{ weight: '', reps: '' }]));
  return next;
}

export function removeExercise(draft, exerciseKey) {
  return { ...draft, exercises: draft.exercises.filter((e) => e.key !== exerciseKey) };
}

/** Adds a set that repeats the previous one, the usual way a straight-set workout goes. */
export function addSet(draft, exerciseKey) {
  const next = structuredClone(draft);
  const exercise = next.exercises.find((e) => e.key === exerciseKey);
  if (!exercise) return draft;
  const last = exercise.sets.at(-1) ?? { weight: '', reps: '' };
  exercise.sets.push({ key: nextKey(next), weight: last.weight, reps: last.reps });
  return next;
}

export function removeSet(draft, exerciseKey, setKey) {
  return {
    ...draft,
    exercises: draft.exercises.map((e) => (e.key === exerciseKey ? { ...e, sets: e.sets.filter((s) => s.key !== setKey) } : e)),
  };
}

export function updateSet(draft, exerciseKey, setKey, field, value) {
  return {
    ...draft,
    exercises: draft.exercises.map((e) =>
      e.key !== exerciseKey ? e : { ...e, sets: e.sets.map((s) => (s.key === setKey ? { ...s, [field]: value } : s)) },
    ),
  };
}

const toNumber = (value) => {
  const n = Number(String(value).trim().replace(',', '.'));
  return String(value).trim() !== '' && Number.isFinite(n) ? n : NaN;
};

/** Sets that will be saved: a positive rep (or second) count, and a load that is blank or ≥ 0. */
function completedSets(exercise, units) {
  return exercise.sets
    .map((s) => ({ reps: toNumber(s.reps), weight: s.weight === '' ? 0 : toNumber(s.weight) }))
    .filter((s) => s.reps > 0 && s.weight >= 0)
    .map((s) => ({ reps: Math.round(s.reps), weight: fromDisplayWeight(s.weight, units) }));
}

/** Live totals for the log footer. Volume is in kilograms. */
export function draftTotals(draft) {
  let sets = 0;
  let volume = 0;
  for (const exercise of draft.exercises) {
    const done = completedSets(exercise, draft.units);
    sets += done.length;
    if (exercise.measure !== 'time') volume += done.reduce((t, s) => t + s.weight * s.reps, 0);
  }
  return { exercises: draft.exercises.length, sets, volume };
}

/** Problems that block saving, each phrased as what to fix. */
export function validateDraft(draft, today) {
  const errors = [];
  if (!isDayKey(draft.date)) errors.push('Pick the date you trained.');
  else if (parseDayKey(draft.date) > today) errors.push('The date is in the future. Log sessions once you have done them.');
  const minutes = toNumber(draft.minutes);
  if (!(minutes >= 1 && minutes <= 600)) errors.push('Enter how long you trained, between 1 and 600 minutes.');
  if (!draft.exercises.length) errors.push('Add at least one exercise.');
  else if (draftTotals(draft).sets === 0) errors.push('Fill in reps for at least one set.');
  for (const exercise of draft.exercises) {
    const bad = exercise.sets.some((s) => (s.reps !== '' && !(toNumber(s.reps) >= 0)) || (s.weight !== '' && !(toNumber(s.weight) >= 0)));
    if (bad) errors.push(`${exercise.name} has a set with an invalid value. Use positive numbers, for example 62.5.`);
  }
  return errors;
}

export function sessionFromDraft(draft, { id, loggedAt }) {
  return {
    id,
    date: draft.date,
    workoutId: draft.workoutId,
    name: draft.name.trim() || 'Custom session',
    minutes: Math.round(toNumber(draft.minutes)),
    rpe: Number(draft.rpe),
    notes: draft.notes.trim(),
    loggedAt,
    exercises: draft.exercises
      .map((e) => ({ exerciseId: e.exerciseId, name: e.name, group: e.group, measure: e.measure, sets: completedSets(e, draft.units) }))
      .filter((e) => e.sets.length > 0),
  };
}

/** What each point on the RPE scale means in reps left in the tank. */
export const RPE_SCALE = {
  1: 'Very light',
  2: 'Very light',
  3: 'Light',
  4: 'Light',
  5: 'Moderate',
  6: '4 or more reps in reserve',
  7: '3 reps in reserve',
  8: '2 reps in reserve',
  9: '1 rep in reserve',
  10: 'Maximal effort',
};
