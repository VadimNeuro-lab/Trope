// Screen 2 — Workouts: browse routines by category and level, browse exercises by
// muscle group, and open a routine to see its full prescription.

import { html, cx, icon } from '../html.js';
import { dayKey, WEEKDAYS } from '../dates.js';
import {
  CATEGORIES,
  EXERCISES,
  LEVELS,
  MUSCLE_GROUPS,
  WORKOUTS,
  categoryLabel,
  getExercise,
  getWorkout,
  groupLabel,
  workoutGroups,
  workoutKicker,
  workoutSetCount,
  workoutsUsing,
} from '../catalog.js';
import { plannedWorkoutId } from '../plan.js';
import { setOverride } from '../store.js';
import { draftFromWorkout } from '../draft.js';
import { formatDuration } from '../units.js';
import { emptyState, levelBadge, pageHeader, prescription } from '../components.js';

export const title = 'Workouts';

/** On a routine's page the top bar shows the routine's name. */
export const appbarTitle = ({ route }) => (route.param ? (getWorkout(route.param)?.name ?? 'Workout') : title);

export const initialUi = () => ({ view: 'routines', category: 'all', level: 'all', query: '', group: 'all' });

function matches(workout, query) {
  if (!query) return true;
  const q = query.trim().toLowerCase();
  const haystack = [
    workout.name,
    workout.summary,
    workout.focus,
    categoryLabel(workout.category),
    ...workout.exercises.map((e) => getExercise(e.exercise)?.name ?? ''),
  ]
    .join(' ')
    .toLowerCase();
  return q.split(/\s+/).every((word) => haystack.includes(word));
}

export function filterWorkouts({ category, level, query }) {
  return WORKOUTS.filter(
    (w) => (category === 'all' || w.category === category) && (level === 'all' || w.level === level) && matches(w, query),
  );
}

function viewTabs(view) {
  const tab = (id, label) =>
    html`<button type="button" class="${cx('segment', { 'is-active': view === id })}" aria-pressed="${view === id}" data-action="workouts:view" data-view="${id}">${label}</button>`;
  return html`<div class="segmented" role="group" aria-label="Browse">
    ${tab('routines', 'Routines')}${tab('exercises', 'Exercises')}
  </div>`;
}

function chip({ label, count, active, action, data }) {
  return html`<button type="button" class="${cx('chip', { 'is-active': active })}" aria-pressed="${active}" data-action="${action}" ${data}>
    ${label}${count !== undefined ? html`<span class="chip-count">${count}</span>` : ''}
  </button>`;
}

function workoutCard(workout, isToday) {
  const groups = workoutGroups(workout).slice(0, 3).map(groupLabel);
  return html`<li>
    <a class="workout-card" href="#workout-${workout.id}">
      <span class="wc-top">
        <span class="wc-kicker">${workoutKicker(workout)}</span>
        ${isToday ? html`<span class="tag tag-accent">Today</span>` : ''}
      </span>
      <span class="wc-name">${workout.name}</span>
      <span class="wc-summary">${workout.summary}</span>
      <span class="wc-meta">
        <span class="wc-duration">${icon('clock')}${workout.minutes} min</span>
        <span>${workout.exercises.length} exercises</span>
        ${levelBadge(workout.level)}
      </span>
      <span class="wc-groups">${groups.join(' · ')}</span>
    </a>
  </li>`;
}

function routines({ state, today, ui }) {
  const u = ui.workouts;
  const list = filterWorkouts(u);
  const todayId = plannedWorkoutId(state, today);
  const countIn = (category) => WORKOUTS.filter((w) => category === 'all' || w.category === category).length;
  const filtered = u.category !== 'all' || u.level !== 'all' || u.query;
  return html`<div class="filters">
      <label class="search">
        ${icon('search')}
        <span class="sr-only">Search workouts</span>
        <input id="workout-search" type="search" placeholder="Search by name or exercise" autocomplete="off" value="${u.query}" data-input="workouts:query" />
      </label>
      <div class="filter-row">
        <div class="chips" role="group" aria-label="Category">
          ${chip({ label: 'All', count: countIn('all'), active: u.category === 'all', action: 'workouts:category', data: html`data-category="all"` })}
          ${CATEGORIES.map((c) =>
            chip({
              label: c.label,
              count: countIn(c.id),
              active: u.category === c.id,
              action: 'workouts:category',
              data: html`data-category="${c.id}"`,
            }),
          )}
        </div>
        <label class="select-inline">
          <span>Level</span>
          <select id="workout-level" data-change="workouts:level">
            <option value="all" ${u.level === 'all' ? 'selected' : ''}>Any level</option>
            ${LEVELS.map(
              (l) =>
                html`<option value="${l.id}" ${u.level === l.id ? 'selected' : ''}>${l.label}${l.id === state.profile.level ? ' (your level)' : ''}</option>`,
            )}
          </select>
        </label>
      </div>
    </div>
    <p class="result-count" aria-live="polite">
      ${list.length === 1 ? '1 routine' : `${list.length} routines`}${filtered ? ' match your filters' : ''}
      ${filtered ? html`<button type="button" class="link-button" data-action="workouts:clear">Clear filters</button>` : ''}
    </p>
    ${
      list.length
        ? html`<ul class="workout-grid">${list.map((w) => workoutCard(w, w.id === todayId))}</ul>`
        : emptyState({
            title: 'No routines match',
            body: 'Try another category or level, or search for an exercise such as “squat”.',
            action: html`<button type="button" class="btn btn-secondary" data-action="workouts:clear">Clear filters</button>`,
          })
    }`;
}

function exercises({ ui }) {
  const active = ui.workouts.group;
  const groups = MUSCLE_GROUPS.filter((g) => active === 'all' || g.id === active);
  return html`<div class="filters">
      <div class="chips" role="group" aria-label="Muscle group">
        ${chip({ label: 'All', count: EXERCISES.length, active: active === 'all', action: 'workouts:group', data: html`data-group="all"` })}
        ${MUSCLE_GROUPS.map((g) =>
          chip({
            label: g.label,
            count: EXERCISES.filter((e) => e.group === g.id).length,
            active: active === g.id,
            action: 'workouts:group',
            data: html`data-group="${g.id}"`,
          }),
        )}
      </div>
    </div>
    <div class="exercise-groups">
      ${groups.map((g) => {
        const list = EXERCISES.filter((e) => e.group === g.id);
        return html`<section class="card exercise-group" aria-labelledby="group-${g.id}">
          <h2 class="group-title" id="group-${g.id}">${g.label}<span>${list.length}</span></h2>
          <ul class="exercise-index">
            ${list.map((e) => {
              const used = workoutsUsing(e.id);
              return html`<li>
                <p class="ex-name">${e.name}</p>
                <p class="ex-meta">${e.equipment}${e.measure === 'time' ? ' · timed' : ''}</p>
                <p class="ex-used">
                  ${
                    used.length
                      ? html`In ${used.map((w, i) => html`${i ? ', ' : ''}<a href="#workout-${w.id}">${w.name}</a>`)}`
                      : 'Not in a routine yet'
                  }
                </p>
              </li>`;
            })}
          </ul>
        </section>`;
      })}
    </div>`;
}

function library(ctx) {
  const view = ctx.ui.workouts.view;
  return html`${pageHeader({
    title: 'Workouts',
    sub: `${WORKOUTS.length} routines and ${EXERCISES.length} exercises to choose from`,
    aside: viewTabs(view),
  })}
    ${view === 'exercises' ? exercises(ctx) : routines(ctx)}`;
}

function scheduledDays(state, workoutId) {
  return state.schedule.map((id, day) => (id === workoutId ? WEEKDAYS[day] : null)).filter(Boolean);
}

function detail({ state, today }, workout) {
  if (!workout) {
    return html`${emptyState({ title: 'Workout not found', body: 'This routine is not in the library. Pick another one from the list.' })}`;
  }
  const units = state.profile.units;
  const isToday = plannedWorkoutId(state, today) === workout.id;
  const days = scheduledDays(state, workout.id);
  return html`${pageHeader({ eyebrow: workoutKicker(workout), title: workout.name, sub: workout.summary })}
    <dl class="detail-stats card">
      <div><dt>Duration</dt><dd>${workout.minutes} min</dd></div>
      <div><dt>Exercises</dt><dd>${workout.exercises.length}</dd></div>
      <div><dt>Working sets</dt><dd>${workoutSetCount(workout)}</dd></div>
      <div><dt>Level</dt><dd>${levelBadge(workout.level)}</dd></div>
    </dl>
    <p class="plan-line">
      ${isToday ? html`<span class="tag tag-accent">Today's workout</span>` : ''}
      ${days.length ? `In your weekly plan on ${days.join(' and ')}.` : 'Not in your weekly plan.'}
      <a href="#profile-plan">Edit plan</a>
    </p>
    <h2 class="section-title">Exercises</h2>
    <ol class="exercise-list card">
      ${workout.exercises.map((item, i) => {
        const info = getExercise(item.exercise);
        return html`<li>
          <span class="ex-num" aria-hidden="true">${i + 1}</span>
          <div class="ex-body">
            <p class="ex-name">${info.name}</p>
            <p class="ex-meta">${groupLabel(info.group)} · ${info.equipment}${item.rest ? ` · rest ${formatDuration(item.rest)}` : ''}</p>
          </div>
          <p class="ex-rx mono">${prescription(item, units)}</p>
        </li>`;
      })}
    </ol>
    <div class="action-bar">
      <button type="button" class="btn btn-primary" data-action="workouts:log" data-id="${workout.id}">${icon('log')}Log this workout</button>
      ${
        isToday
          ? ''
          : html`<button type="button" class="btn btn-secondary" data-action="workouts:today" data-id="${workout.id}">Do it today instead</button>`
      }
    </div>`;
}

export function render(ctx) {
  if (ctx.route.param) return detail(ctx, getWorkout(ctx.route.param));
  return library(ctx);
}

export const handlers = {
  'workouts:view'(app, el) {
    app.ui.workouts.view = el.dataset.view;
    app.render();
  },
  'workouts:category'(app, el) {
    app.ui.workouts.category = el.dataset.category;
    app.render();
  },
  'workouts:group'(app, el) {
    app.ui.workouts.group = el.dataset.group;
    app.render();
  },
  'workouts:level'(app, el) {
    app.ui.workouts.level = el.value;
    app.render();
  },
  'workouts:query'(app, el) {
    app.ui.workouts.query = el.value;
    app.render();
  },
  'workouts:clear'(app) {
    Object.assign(app.ui.workouts, { category: 'all', level: 'all', query: '' });
    app.render();
  },
  'workouts:log'(app, el) {
    const today = app.today();
    app.store.update((s) => ({ ...s, draft: draftFromWorkout(el.dataset.id, today, s.profile.units) }), { silent: true });
    app.navigate('#log');
  },
  'workouts:today'(app, el) {
    const workout = getWorkout(el.dataset.id);
    app.store.update((s) => setOverride(s, dayKey(app.today()), workout.id), { silent: true });
    app.toast(`${workout.name} is now today's workout`);
    app.navigate('#today');
  },
};
