import test from 'node:test';
import assert from 'node:assert/strict';
import {
  STORAGE_KEY,
  addGoal,
  addSession,
  clearSampleSessions,
  createStore,
  deleteSession,
  hasSampleSessions,
  loadState,
  removeGoal,
  saveState,
  setGoalTarget,
  setOverride,
  setSchedule,
} from '../src/store.js';
import { createInitialState, sampleSessions } from '../src/seed.js';
import { dayStatus, plannedWorkoutId, todayPlan } from '../src/plan.js';
import { summarizeWeek } from '../src/stats.js';

const TODAY = new Date(2026, 9, 2); // Friday

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => {
      data[k] = String(v);
    },
    data,
  };
}

test('first run seeds a plan, goals and flagged sample sessions', () => {
  const state = loadState(memoryStorage(), TODAY);
  assert.equal(state.version, 1);
  assert.equal(state.schedule.length, 7);
  assert.ok(state.sessions.length > 20);
  assert.ok(state.sessions.every((s) => s.sample && s.date < '2026-10-02'));
  assert.ok(hasSampleSessions(state));
  // The sample week up to today follows the plan: Mon, Tue and Wed done, Thursday rest.
  const week = summarizeWeek(state.sessions, TODAY, 1);
  assert.deepEqual(
    week.days.map((d) => d.sessions.length),
    [1, 1, 1, 0, 0, 0, 0],
  );
});

test('sample loads ramp up toward the prescription', () => {
  const sessions = sampleSessions(TODAY).filter((s) => s.workoutId === 'lower-strength');
  const squat = (s) => s.exercises[0].sets[0].weight;
  assert.ok(squat(sessions[0]) < squat(sessions.at(-1)));
  assert.ok(squat(sessions.at(-1)) <= 80);
});

test('saved state loads back; corrupt or blocked storage falls back', () => {
  const storage = memoryStorage();
  const state = createInitialState(TODAY, { samples: false });
  assert.ok(saveState(storage, state));
  assert.deepEqual(loadState(storage, TODAY), state);

  const corrupt = memoryStorage({ [STORAGE_KEY]: '{not json' });
  assert.equal(loadState(corrupt, TODAY).version, 1);

  const wrongShape = memoryStorage({ [STORAGE_KEY]: JSON.stringify({ version: 1, sessions: 'x' }) });
  assert.ok(Array.isArray(loadState(wrongShape, TODAY).sessions));

  const blocked = {
    getItem() {
      throw new Error('SecurityError');
    },
    setItem() {
      throw new Error('QuotaExceededError');
    },
  };
  assert.equal(loadState(blocked, TODAY).version, 1);
  assert.equal(saveState(blocked, state), false);
  assert.equal(loadState(null, TODAY).version, 1);
});

test('old one-day overrides are pruned on load', () => {
  const storage = memoryStorage();
  const state = {
    ...createInitialState(TODAY, { samples: false }),
    overrides: { '2026-09-01': 'hiit-engine', '2026-10-02': 'core-stability' },
  };
  saveState(storage, state);
  assert.deepEqual(loadState(storage, TODAY).overrides, { '2026-10-02': 'core-stability' });
});

test('store notifies subscribers unless the update is silent, and always persists', () => {
  const storage = memoryStorage();
  const store = createStore(createInitialState(TODAY, { samples: false }), storage);
  let calls = 0;
  store.subscribe(() => calls++);
  store.update((s) => setGoalTarget(s, 'weekly-sessions', 5));
  store.update((s) => setGoalTarget(s, 'weekly-sessions', 6), { silent: true });
  assert.equal(calls, 1);
  assert.equal(JSON.parse(storage.data[STORAGE_KEY]).goals[0].target, 6);
});

test('sessions: add keeps date order and clears the draft; delete and clear samples', () => {
  let state = { ...createInitialState(TODAY), draft: { name: 'x' } };
  const mine = { id: 'mine', date: '2026-09-01', loggedAt: '2026-09-01T10:00:00Z', name: 'Mine', minutes: 30, exercises: [] };
  state = addSession(state, mine);
  assert.equal(state.draft, null);
  const index = state.sessions.findIndex((s) => s.id === 'mine');
  assert.ok(state.sessions[index - 1].date <= '2026-09-01' && state.sessions[index + 1].date >= '2026-09-01');
  state = clearSampleSessions(state);
  assert.deepEqual(
    state.sessions.map((s) => s.id),
    ['mine'],
  );
  state = deleteSession(state, 'mine');
  assert.equal(state.sessions.length, 0);
});

test('only personal goals can be removed', () => {
  let state = createInitialState(TODAY, { samples: false });
  state = addGoal(state, { id: 'g', kind: 'custom', title: 'Row 2 km', start: 9, current: 9, target: 8, unit: 'min' });
  state = removeGoal(state, 'weekly-sessions');
  state = removeGoal(state, 'g');
  assert.ok(state.goals.some((g) => g.id === 'weekly-sessions'));
  assert.ok(!state.goals.some((g) => g.id === 'g'));
});

test('plan: weekly schedule, one-day overrides and day status', () => {
  let state = createInitialState(TODAY);
  assert.equal(plannedWorkoutId(state, TODAY), 'upper-pull');
  assert.equal(todayPlan(state, TODAY).completed, null);

  state = setOverride(state, '2026-10-02', 'hiit-engine');
  assert.equal(plannedWorkoutId(state, TODAY), 'hiit-engine');
  state = setOverride(state, '2026-10-02', '');
  assert.equal(plannedWorkoutId(state, TODAY), null);

  state = setSchedule(state, 4, 'core-stability');
  assert.equal(plannedWorkoutId(state, new Date(2026, 9, 8)), 'core-stability');

  const fresh = createInitialState(TODAY);
  assert.equal(dayStatus(fresh, new Date(2026, 8, 28), TODAY).status, 'done');
  assert.equal(dayStatus(fresh, new Date(2026, 9, 1), TODAY).status, 'rest');
  assert.equal(dayStatus(fresh, TODAY, TODAY).status, 'today');
  assert.equal(dayStatus(fresh, new Date(2026, 9, 3), TODAY).status, 'upcoming');
  const skipped = { ...fresh, sessions: [] };
  assert.equal(dayStatus(skipped, new Date(2026, 8, 28), TODAY).status, 'missed');

  const logged = addSession(fresh, { id: 'x', date: '2026-10-02', workoutId: 'upper-pull', loggedAt: 'z', minutes: 45, exercises: [] });
  assert.equal(todayPlan(logged, TODAY).completed.id, 'x');
});
