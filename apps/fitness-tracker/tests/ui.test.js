import test from 'node:test';
import assert from 'node:assert/strict';
import { html, raw, escapeHtml, cx } from '../src/html.js';
import { niceTicks } from '../src/charts.js';
import { parseRoute } from '../src/routes.js';
import { formatDuration, formatMinutes, formatVolume, formatWeight, fromDisplayWeight, toDisplayWeight } from '../src/units.js';
import { EXERCISES, WORKOUTS, getExercise, workoutGroups, workoutKicker } from '../src/catalog.js';
import { filterWorkouts } from '../src/screens/workouts.js';

test('html escapes interpolated text but not nested templates', () => {
  const name = '<img src=x onerror=alert(1)>';
  assert.equal(String(html`<p>${name}</p>`), '<p>&lt;img src=x onerror=alert(1)&gt;</p>');
  assert.equal(String(html`<ul>${['a', 'b'].map((x) => html`<li>${x}</li>`)}</ul>`), '<ul><li>a</li><li>b</li></ul>');
  assert.equal(String(html`${null}${false}${undefined}${0}`), '0');
  assert.equal(String(html`${raw('<b>ok</b>')}`), '<b>ok</b>');
  assert.equal(escapeHtml(`"quotes" & 'apostrophes'`), '&quot;quotes&quot; &amp; &#39;apostrophes&#39;');
  assert.equal(cx('a', { b: true, c: false }, '', null), 'a b');
});

test('chart ticks are round numbers that cover the data', () => {
  assert.deepEqual(niceTicks(0, 64, 3), [0, 25, 50, 75]);
  assert.deepEqual(niceTicks(0, 4, 3), [0, 2, 4]);
  assert.deepEqual(niceTicks(76, 93.5, 3), [70, 80, 90, 100]);
  assert.deepEqual(niceTicks(0, 0, 3), [0, 0.5, 1]);
});

test('routes', () => {
  assert.deepEqual(parseRoute(''), { screen: 'today', param: null, anchor: null });
  assert.deepEqual(parseRoute('#log'), { screen: 'log', param: null, anchor: null });
  assert.deepEqual(parseRoute('#workout-upper-push'), { screen: 'workouts', param: 'upper-push', anchor: null });
  assert.deepEqual(parseRoute('#profile-plan'), { screen: 'profile', param: null, anchor: 'plan' });
  assert.deepEqual(parseRoute('#nope'), { screen: 'today', param: null, anchor: null });
});

test('units and durations', () => {
  assert.equal(toDisplayWeight(61.3, 'kg'), 61.5);
  assert.equal(toDisplayWeight(60, 'lb'), 132);
  assert.equal(fromDisplayWeight(132, 'lb'), 59.87);
  assert.equal(formatWeight(100, 'kg'), '100 kg');
  assert.equal(formatVolume(12345.6, 'kg'), '12,346 kg');
  assert.equal(formatVolume(1000, 'lb'), '2,205 lb');
  assert.equal(formatDuration(45), '45 s');
  assert.equal(formatDuration(90), '1:30');
  assert.equal(formatDuration(2100), '35 min');
  assert.equal(formatMinutes(64), '1 h 4 min');
  assert.equal(formatMinutes(120), '2 h');
});

test('catalog integrity: every routine references real exercises', () => {
  const ids = new Set(EXERCISES.map((e) => e.id));
  assert.equal(ids.size, EXERCISES.length, 'exercise ids are unique');
  assert.equal(new Set(WORKOUTS.map((w) => w.id)).size, WORKOUTS.length, 'workout ids are unique');
  for (const w of WORKOUTS) {
    assert.ok(w.exercises.length > 0, w.id);
    for (const item of w.exercises) assert.ok(getExercise(item.exercise), `${w.id} → ${item.exercise}`);
  }
  assert.deepEqual(workoutGroups(WORKOUTS.find((w) => w.id === 'zone2-run')), ['cardio', 'mobility']);
  assert.equal(workoutKicker(WORKOUTS.find((w) => w.id === 'mobility-flow')), 'Mobility');
  assert.equal(workoutKicker(WORKOUTS.find((w) => w.id === 'upper-push')), 'Upper body · Strength');
});

test('workout filters combine category, level and search words', () => {
  const ids = (f) => filterWorkouts({ category: 'all', level: 'all', query: '', ...f }).map((w) => w.id);
  assert.equal(ids({}).length, WORKOUTS.length);
  assert.deepEqual(ids({ category: 'lower' }), ['lower-strength', 'leg-volume']);
  assert.deepEqual(ids({ category: 'lower', level: 'advanced' }), ['lower-strength']);
  assert.deepEqual(ids({ query: 'goblet' }), ['full-foundations', 'kettlebell-complex']);
  assert.deepEqual(ids({ query: 'KETTLEBELL swing', level: 'advanced' }), ['hiit-engine']);
  assert.deepEqual(ids({ query: 'zumba' }), []);
});
