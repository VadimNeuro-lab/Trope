import test from 'node:test';
import assert from 'node:assert/strict';
import {
  addExercise,
  addSet,
  draftFromWorkout,
  draftTotals,
  emptyDraft,
  removeExercise,
  removeSet,
  sessionFromDraft,
  updateSet,
  validateDraft,
} from '../src/draft.js';

const TODAY = new Date(2026, 9, 2);

test('a draft from a routine copies its prescription', () => {
  const draft = draftFromWorkout('upper-push', TODAY, 'kg');
  assert.equal(draft.name, 'Upper Body Push');
  assert.equal(draft.minutes, '50');
  assert.equal(draft.date, '2026-10-02');
  assert.equal(draft.exercises.length, 5);
  assert.deepEqual(
    draft.exercises[0].sets.map((s) => [s.weight, s.reps]),
    [
      ['60', '6'],
      ['60', '6'],
      ['60', '6'],
      ['60', '6'],
    ],
  );
  assert.deepEqual(draftTotals(draft), { exercises: 5, sets: 16, volume: 4140 });
});

test('a draft in pounds converts prescribed loads', () => {
  const draft = draftFromWorkout('upper-push', TODAY, 'lb');
  assert.equal(draft.exercises[0].sets[0].weight, '132');
  const saved = sessionFromDraft(draft, { id: 'x', loggedAt: 'now' });
  assert.equal(saved.exercises[0].sets[0].weight, 59.87);
});

test('unknown routines fall back to an empty draft', () => {
  assert.deepEqual(draftFromWorkout('nope', TODAY, 'kg').exercises, []);
});

test('editing sets keeps keys unique and copies the last set', () => {
  let draft = addExercise(emptyDraft(TODAY, 'kg'), 'deadlift');
  const ex = draft.exercises[0];
  draft = updateSet(draft, ex.key, ex.sets[0].key, 'weight', '140');
  draft = updateSet(draft, ex.key, ex.sets[0].key, 'reps', '5');
  draft = addSet(draft, ex.key);
  const sets = draft.exercises[0].sets;
  assert.equal(sets.length, 2);
  assert.deepEqual([sets[1].weight, sets[1].reps], ['140', '5']);
  assert.notEqual(sets[0].key, sets[1].key);
  draft = removeSet(draft, ex.key, sets[0].key);
  assert.equal(draft.exercises[0].sets.length, 1);
  draft = removeExercise(draft, ex.key);
  assert.equal(draft.exercises.length, 0);
});

test('validation explains what to fix', () => {
  const empty = { ...emptyDraft(TODAY, 'kg'), minutes: '' };
  assert.deepEqual(validateDraft(empty, TODAY), ['Enter how long you trained, between 1 and 600 minutes.', 'Add at least one exercise.']);

  const future = { ...draftFromWorkout('core-stability', TODAY, 'kg'), date: '2026-10-03' };
  assert.match(validateDraft(future, TODAY)[0], /in the future/);

  let noReps = addExercise({ ...emptyDraft(TODAY, 'kg'), minutes: '30' }, 'bench-press');
  assert.deepEqual(validateDraft(noReps, TODAY), ['Fill in reps for at least one set.']);

  const ex = noReps.exercises[0];
  noReps = updateSet(noReps, ex.key, ex.sets[0].key, 'reps', 'ten');
  assert.match(validateDraft(noReps, TODAY).at(-1), /Bench press has a set with an invalid value/);

  assert.deepEqual(validateDraft(draftFromWorkout('upper-pull', TODAY, 'kg'), TODAY), []);
});

test('saving drops empty sets and exercises and parses numbers', () => {
  let draft = { ...emptyDraft(TODAY, 'kg'), minutes: '42', rpe: 9, name: '  Pull-up ladder  ', notes: ' felt strong ' };
  draft = addExercise(draft, 'pull-up');
  draft = addExercise(draft, 'barbell-curl');
  const [pull] = draft.exercises;
  draft = updateSet(draft, pull.key, pull.sets[0].key, 'reps', '8');
  draft = addSet(draft, pull.key);
  draft = updateSet(draft, pull.key, draft.exercises[0].sets[1].key, 'weight', '7,5');
  const saved = sessionFromDraft(draft, { id: 's1', loggedAt: '2026-10-02T18:00:00.000Z' });
  assert.equal(saved.name, 'Pull-up ladder');
  assert.equal(saved.notes, 'felt strong');
  assert.equal(saved.minutes, 42);
  assert.equal(saved.rpe, 9);
  assert.equal(saved.exercises.length, 1);
  assert.deepEqual(saved.exercises[0].sets, [
    { reps: 8, weight: 0 },
    { reps: 8, weight: 7.5 },
  ]);
});
