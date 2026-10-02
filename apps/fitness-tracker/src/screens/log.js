// Screen 3 — Log: record a completed session exercise by exercise, set by set.
// Typing updates the saved draft without re-rendering, so focus and caret stay put.

import { html, cx, icon } from '../html.js';
import { dayKey, formatDayAndDate, parseDayKey } from '../dates.js';
import { CATEGORIES, EXERCISES, MUSCLE_GROUPS, WORKOUTS, getWorkout, groupLabel } from '../catalog.js';
import { plannedWorkout } from '../plan.js';
import { lastPerformance, summarizeWeek } from '../stats.js';
import { addSession, goalById, setDraft } from '../store.js';
import {
  RPE_SCALE,
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
} from '../draft.js';
import { formatDuration, formatNumber, formatVolume, toDisplayWeight, unitLabel } from '../units.js';
import { emptyState, pageHeader } from '../components.js';

export const title = 'Log';

export const initialUi = () => ({ picker: false, pickerQuery: '', errors: [], confirmDiscard: false });

/** The draft in progress, or a new one based on today's plan. */
function currentDraft(state, today) {
  if (state.draft) return state.draft;
  const workout = plannedWorkout(state, today);
  return workout ? draftFromWorkout(workout.id, today, state.profile.units) : emptyDraft(today, state.profile.units);
}

const rpeText = (rpe) => `RPE ${rpe} · ${RPE_SCALE[rpe]}`;

function totalsText(draft) {
  const t = draftTotals(draft);
  const parts = [`${t.exercises} ${t.exercises === 1 ? 'exercise' : 'exercises'}`, `${t.sets} ${t.sets === 1 ? 'set' : 'sets'}`];
  if (t.volume > 0) parts.push(formatVolume(t.volume, draft.units));
  // Keep each figure with its unit; lines may only break between figures.
  return parts.map((p) => p.replace(/ /g, '\u00a0')).join(' · ');
}

function lastTimeText(sessions, exercise, draft) {
  const last = lastPerformance(sessions, exercise.exerciseId, draft.date);
  if (!last) return 'First time logging this';
  const reps = last.sets.map((s) => s.reps);
  const timed = last.measure === 'time';
  const repText = reps.every((r) => r === reps[0])
    ? `${reps.length} × ${timed ? formatDuration(reps[0]) : reps[0]}`
    : reps.map((r) => (timed ? formatDuration(r) : r)).join(', ');
  const top = Math.max(...last.sets.map((s) => s.weight));
  const load = top > 0 ? ` · ${formatNumber(toDisplayWeight(top, draft.units))} ${unitLabel(draft.units)}` : '';
  return `Last time, ${formatDayAndDate(parseDayKey(last.date))}: ${repText}${load}`;
}

function exerciseBlock(exercise, draft, sessions) {
  const timed = exercise.measure === 'time';
  const unit = unitLabel(draft.units);
  const ex = exercise.key;
  return html`<section class="card log-exercise" aria-labelledby="title-${ex}">
    <header class="log-ex-head">
      <div>
        <h3 class="ex-name" id="title-${ex}">${exercise.name}</h3>
        <p class="ex-meta">${groupLabel(exercise.group)} · ${lastTimeText(sessions, exercise, draft)}</p>
      </div>
      <button type="button" class="icon-btn" data-action="log:remove-exercise" data-ex="${ex}" aria-label="Remove ${exercise.name}">${icon('trash')}</button>
    </header>
    ${
      exercise.sets.length
        ? html`<table class="set-table">
          <thead>
            <tr>
              <th scope="col">Set</th>
              <th scope="col">Weight <span class="unit">${unit}</span></th>
              <th scope="col">${timed ? html`Time <span class="unit">sec</span>` : 'Reps'}</th>
              <th scope="col"><span class="sr-only">Remove</span></th>
            </tr>
          </thead>
          <tbody>
            ${exercise.sets.map(
              (set, i) => html`<tr>
                <td class="set-num">${i + 1}</td>
                <td>
                  <input id="w-${set.key}" class="num-input" type="text" inputmode="decimal" autocomplete="off" placeholder="0"
                    value="${set.weight}" aria-label="${exercise.name}, set ${i + 1}, weight in ${unit}"
                    data-input="log:set" data-ex="${ex}" data-set="${set.key}" data-field="weight" />
                </td>
                <td>
                  <input id="r-${set.key}" class="num-input" type="text" inputmode="numeric" autocomplete="off" placeholder="0"
                    value="${set.reps}" aria-label="${exercise.name}, set ${i + 1}, ${timed ? 'seconds' : 'reps'}"
                    data-input="log:set" data-ex="${ex}" data-set="${set.key}" data-field="reps" />
                </td>
                <td>
                  <button type="button" class="icon-btn small" data-action="log:remove-set" data-ex="${ex}" data-set="${set.key}" aria-label="Remove set ${i + 1}">${icon('close')}</button>
                </td>
              </tr>`,
            )}
          </tbody>
        </table>`
        : html`<p class="muted">No sets yet.</p>`
    }
    <button type="button" class="btn btn-quiet" data-action="log:add-set" data-ex="${ex}">${icon('plus')}Add set</button>
  </section>`;
}

function matchesQuery(exercise, query) {
  const q = query.trim().toLowerCase();
  return !q || `${exercise.name} ${exercise.equipment}`.toLowerCase().includes(q);
}

/** Bottom sheet for choosing an exercise, grouped by muscle group and searchable. */
export function sheet({ ui }) {
  const u = ui.log;
  if (!u.picker) return '';
  const groups = MUSCLE_GROUPS.map((g) => ({
    g,
    list: EXERCISES.filter((e) => e.group === g.id && matchesQuery(e, u.pickerQuery)),
  })).filter((x) => x.list.length);
  return html`<button type="button" class="sheet-backdrop" tabindex="-1" aria-label="Close" data-action="log:close-picker"></button>
    <section class="sheet" role="dialog" aria-modal="true" aria-labelledby="picker-title" tabindex="-1">
      <span class="sheet-handle" aria-hidden="true"></span>
      <div class="sheet-head">
        <h2 class="sheet-title" id="picker-title">Add exercise</h2>
        <button type="button" class="btn btn-quiet btn-small" data-action="log:close-picker" data-sheet-dismiss>Done</button>
      </div>
      <label class="search">
        ${icon('search')}
        <span class="sr-only">Search exercises</span>
        <input id="picker-search" type="search" placeholder="Search exercises" autocomplete="off" value="${u.pickerQuery}" data-input="log:picker-query" />
      </label>
      <div class="sheet-body">
        ${
          groups.length
            ? groups.map(
                ({ g, list }) => html`<section class="picker-group" aria-labelledby="pick-${g.id}">
                  <h3 class="picker-group-title" id="pick-${g.id}">${g.label}</h3>
                  <ul class="picker-list">
                    ${list.map(
                      (e) => html`<li>
                        <button type="button" class="picker-item" data-action="log:pick" data-id="${e.id}">
                          <span class="picker-item-name">${e.name}</span>
                          <span class="picker-item-meta">${e.equipment}${e.measure === 'time' ? ' · timed' : ''}</span>
                        </button>
                      </li>`,
                    )}
                  </ul>
                </section>`,
              )
            : html`<p class="muted">No exercises match “${u.pickerQuery.trim()}”.</p>`
        }
      </div>
    </section>`;
}

export function render({ state, today, ui }) {
  const draft = currentDraft(state, today);
  const u = ui.log;
  return html`${pageHeader({ title: 'Log a session', sub: 'Record what you actually did. Sets without reps are left out.' })}
    <form class="log-form" data-submit="log:save" novalidate>
      <section class="card log-details" aria-label="Session details">
        <label class="field field-wide">
          <span class="field-label">Start from</span>
          <select id="log-template" data-change="log:template">
            <option value="" ${draft.workoutId ? '' : 'selected'}>Empty session</option>
            ${CATEGORIES.map((c) => {
              const list = WORKOUTS.filter((w) => w.category === c.id);
              return html`<optgroup label="${c.label}">
                ${list.map((w) => html`<option value="${w.id}" ${draft.workoutId === w.id ? 'selected' : ''}>${w.name} · ${w.minutes} min</option>`)}
              </optgroup>`;
            })}
          </select>
        </label>
        <label class="field field-wide">
          <span class="field-label">Session name</span>
          <input id="log-name" type="text" value="${draft.name}" data-input="log:field" data-field="name" autocomplete="off" />
        </label>
        <label class="field">
          <span class="field-label">Date</span>
          <input id="log-date" type="date" value="${draft.date}" max="${dayKey(today)}" data-input="log:field" data-field="date" />
        </label>
        <label class="field">
          <span class="field-label">Duration</span>
          <span class="input-suffix">
            <input id="log-minutes" type="text" inputmode="numeric" value="${draft.minutes}" placeholder="45" data-input="log:field" data-field="minutes" autocomplete="off" />
            <span>min</span>
          </span>
        </label>
        <label class="field field-wide">
          <span class="field-label">Effort <output id="rpe-output" class="rpe-output" for="log-rpe">${rpeText(draft.rpe)}</output></span>
          <input id="log-rpe" class="range" type="range" min="1" max="10" step="1" value="${draft.rpe}" data-input="log:field" data-field="rpe" />
          <span class="range-scale" aria-hidden="true"><span>Easy</span><span>Hard</span><span>Max</span></span>
        </label>
      </section>

      <div class="section-header">
        <h2 class="section-title">Exercises</h2>
        <span class="muted">${draft.workoutId ? `Prefilled from ${getWorkout(draft.workoutId)?.name}` : ''}</span>
      </div>
      ${
        draft.exercises.length
          ? draft.exercises.map((e) => exerciseBlock(e, draft, state.sessions))
          : emptyState({ title: 'No exercises yet', body: 'Add the exercises you did, or start from a routine above.' })
      }
      <button type="button" class="btn btn-secondary btn-block" data-action="log:open-picker">${icon('plus')}Add exercise</button>

      <label class="field field-wide card log-notes">
        <span class="field-label">Notes</span>
        <textarea id="log-notes" rows="3" placeholder="How did it feel? Anything to change next time?" data-input="log:field" data-field="notes">${draft.notes}</textarea>
      </label>

      ${
        u.errors.length
          ? html`<div class="form-errors" role="alert" tabindex="-1" id="log-errors">
            <p><strong>The session wasn't saved.</strong></p>
            <ul>${u.errors.map((e) => html`<li>${e}</li>`)}</ul>
          </div>`
          : ''
      }

      <div class="discard-row">
        <button type="button" class="${cx('btn', 'btn-small', u.confirmDiscard ? 'btn-danger' : 'btn-quiet-danger')}" data-action="log:discard">
          ${u.confirmDiscard ? 'Tap again to discard' : 'Discard draft'}
        </button>
      </div>

      <div class="action-bar log-bar">
        <p class="log-totals" id="log-totals" aria-live="polite">${totalsText(draft)}</p>
        <button type="submit" class="btn btn-primary">${icon('check')}Save session</button>
      </div>
    </form>`;
}

function edit(app, fn, { silent = false } = {}) {
  const today = app.today();
  app.ui.log.confirmDiscard = false;
  app.store.update((s) => setDraft(s, fn(currentDraft(s, today))), { silent });
}

export const handlers = {
  'log:template'(app, el) {
    const today = app.today();
    app.store.update((s) => {
      const previous = currentDraft(s, today);
      const draft = el.value ? draftFromWorkout(el.value, today, s.profile.units) : emptyDraft(today, s.profile.units);
      // Keep what the user already set for when and how hard.
      return setDraft(s, { ...draft, date: previous.date, rpe: previous.rpe, notes: previous.notes });
    });
  },
  'log:field'(app, el) {
    const field = el.dataset.field;
    const value = field === 'rpe' ? Number(el.value) : el.value;
    edit(app, (d) => ({ ...d, [field]: value }), { silent: true });
    if (field === 'rpe') document.getElementById('rpe-output').textContent = rpeText(value);
  },
  'log:set'(app, el) {
    edit(app, (d) => updateSet(d, el.dataset.ex, el.dataset.set, el.dataset.field, el.value), { silent: true });
    document.getElementById('log-totals').textContent = totalsText(currentDraft(app.store.state, app.today()));
  },
  'log:add-set'(app, el) {
    edit(app, (d) => addSet(d, el.dataset.ex));
    const exercise = app.store.state.draft.exercises.find((e) => e.key === el.dataset.ex);
    app.focus(`#r-${exercise.sets.at(-1).key}`);
  },
  'log:remove-set'(app, el) {
    edit(app, (d) => removeSet(d, el.dataset.ex, el.dataset.set));
  },
  'log:remove-exercise'(app, el) {
    edit(app, (d) => removeExercise(d, el.dataset.ex));
  },
  'log:open-picker'(app) {
    Object.assign(app.ui.log, { picker: true, pickerQuery: '' });
    app.render();
    app.focus('.sheet');
  },
  'log:close-picker'(app) {
    app.ui.log.picker = false;
    app.render();
    app.focus('[data-action="log:open-picker"]');
  },
  'log:picker-query'(app, el) {
    app.ui.log.pickerQuery = el.value;
    app.render();
  },
  'log:pick'(app, el) {
    app.ui.log.picker = false;
    edit(app, (d) => addExercise(d, el.dataset.id));
    const added = app.store.state.draft.exercises.at(-1);
    app.toast(`Added ${added.name}`);
    document.getElementById(`title-${added.key}`)?.scrollIntoView({ block: 'center' });
  },
  'log:discard'(app) {
    if (!app.ui.log.confirmDiscard) {
      app.ui.log.confirmDiscard = true;
      app.render();
      return;
    }
    Object.assign(app.ui.log, initialUi());
    app.store.update((s) => setDraft(s, null));
    app.toast('Draft discarded');
  },
  'log:save'(app) {
    const today = app.today();
    const { state } = app.store;
    const draft = currentDraft(state, today);
    const errors = validateDraft(draft, today);
    if (errors.length) {
      app.ui.log.errors = errors;
      app.render();
      app.focus('#log-errors');
      return;
    }
    const session = sessionFromDraft(draft, { id: `s-${Date.now().toString(36)}`, loggedAt: new Date().toISOString() });
    const target = goalById(state, 'weekly-sessions')?.target ?? 0;
    const before = summarizeWeek(state.sessions, today, state.profile.weekStart).count;
    Object.assign(app.ui.log, initialUi());
    app.store.update((s) => addSession(s, session), { silent: true });
    const after = summarizeWeek(app.store.state.sessions, today, state.profile.weekStart).count;
    const reachedGoal = state.notifications.milestones && target > 0 && before < target && after >= target;
    app.toast(`Saved ${session.name}${reachedGoal ? `. Weekly goal reached: ${after} of ${target} workouts` : ''}`);
    app.navigate('#today');
  },
};
