// Screen 5 — Profile: personal goals, training preferences and the weekly plan,
// notification preferences and basic settings.

import { html, cx, icon } from '../html.js';
import { formatMonthYear, parseDayKey, WEEKDAYS } from '../dates.js';
import { CATEGORIES, LEVELS, WORKOUTS, getLevel, getWorkout } from '../catalog.js';
import { goalProgress, summarizeWeek } from '../stats.js';
import {
  addGoal,
  clearSampleSessions,
  goalById,
  removeGoal,
  resetState,
  setGoalCurrent,
  setGoalTarget,
  setSchedule,
  updateNotifications,
  updateProfile,
} from '../store.js';
import { formatNumber } from '../units.js';
import { meter, pageHeader } from '../components.js';

export const title = 'Profile';

export const initialUi = () => ({ addingGoal: false, goalErrors: [], confirmGoal: null, confirmReset: false });

const SESSION_LENGTHS = [20, 30, 45, 60, 75, 90];

const TARGET_LIMITS = {
  sessions: { step: 1, min: 1, max: 14, unit: 'workouts' },
  minutes: { step: 15, min: 15, max: 1500, unit: 'min' },
};

function segmented({ name, options, value, action, label }) {
  return html`<div class="segmented" role="group" aria-label="${label}">
    ${options.map(
      (o) => html`<button type="button" class="${cx('segment', { 'is-active': o.value === value })}" aria-pressed="${o.value === value}"
        data-action="${action}" data-value="${o.value}" data-name="${name}">${o.label}</button>`,
    )}
  </div>`;
}

function profileHead(state) {
  const { profile, sessions } = state;
  const minutes = sessions.reduce((t, s) => t + s.minutes, 0);
  const initial = (profile.name.trim()[0] ?? '?').toUpperCase();
  return html`<section class="card profile-head" aria-label="Your profile">
    <span class="avatar" aria-hidden="true">${initial}</span>
    <div class="profile-id">
      <label class="sr-only" for="profile-name">Your name</label>
      <input id="profile-name" class="name-input" type="text" value="${profile.name}" placeholder="Add your name" autocomplete="given-name" data-change="profile:name" />
      <p class="muted">Training since ${formatMonthYear(parseDayKey(profile.since))} · ${getLevel(profile.level).label}</p>
    </div>
    <dl class="profile-totals">
      <div><dt>Workouts logged</dt><dd>${formatNumber(sessions.length)}</dd></div>
      <div><dt>Hours trained</dt><dd>${formatNumber(Math.round(minutes / 6) / 10)}</dd></div>
    </dl>
  </section>`;
}

function weeklyTarget(goal, current) {
  const limits = TARGET_LIMITS[goal.kind];
  return html`<li class="goal-row">
    <div class="goal-info">
      <p class="goal-title">${goal.title}</p>
      <p class="goal-figure"><strong>${formatNumber(current)}</strong> of ${goal.target} ${limits.unit} this week</p>
      ${meter(current / goal.target, { label: `${goal.title} progress` })}
      <p class="goal-note">Tracked automatically from your log</p>
    </div>
    <div class="stepper" role="group" aria-label="${goal.title} target">
      <button type="button" class="icon-btn" data-action="profile:target" data-id="${goal.id}" data-step="-1"
        aria-label="Lower target" ${goal.target <= limits.min ? 'disabled' : ''}>${icon('minus')}</button>
      <output class="stepper-value" aria-live="polite">${goal.target}</output>
      <button type="button" class="icon-btn" data-action="profile:target" data-id="${goal.id}" data-step="1"
        aria-label="Raise target" ${goal.target >= limits.max ? 'disabled' : ''}>${icon('plus')}</button>
    </div>
  </li>`;
}

function customGoal(goal, confirming) {
  const progress = goalProgress(goal);
  const done = progress >= 1;
  return html`<li class="${cx('goal-row', { 'is-done': done })}">
    <div class="goal-info">
      <p class="goal-title">${goal.title} ${done ? html`<span class="tag tag-good">${icon('check')}Achieved</span>` : ''}</p>
      <p class="goal-figure"><strong>${formatNumber(goal.current)}</strong> of ${formatNumber(goal.target)} ${goal.unit} · ${Math.round(progress * 100)}%</p>
      ${meter(progress, { label: `${goal.title} progress`, tone: done ? 'good' : '' })}
      <p class="goal-note">Started at ${formatNumber(goal.start)} ${goal.unit}</p>
    </div>
    <div class="goal-actions">
      <label class="goal-update">
        <span class="goal-update-label">Now</span>
        <input id="goal-current-${goal.id}" class="num-input" type="text" inputmode="decimal" value="${goal.current}"
          aria-label="Current value for ${goal.title}, in ${goal.unit}" data-change="profile:goal-current" data-id="${goal.id}" />
      </label>
      ${
        confirming
          ? html`<span class="row-confirm">
            <button type="button" class="btn btn-danger btn-small" data-action="profile:goal-remove" data-id="${goal.id}">Remove</button>
            <button type="button" class="btn btn-quiet btn-small" data-action="profile:goal-keep">Keep</button>
          </span>`
          : html`<button type="button" class="icon-btn" data-action="profile:goal-remove" data-id="${goal.id}" aria-label="Remove goal: ${goal.title}">${icon('trash')}</button>`
      }
    </div>
  </li>`;
}

function goalForm(errors) {
  return html`<form class="card goal-form" data-submit="profile:goal-add" novalidate aria-labelledby="new-goal-title">
    <h3 class="card-title" id="new-goal-title">New goal</h3>
    <label class="field field-wide">
      <span class="field-label">Goal</span>
      <input id="goal-title" name="title" type="text" placeholder="Deadlift 1RM" autocomplete="off" />
    </label>
    <label class="field">
      <span class="field-label">Where you are now</span>
      <input id="goal-start" name="start" type="text" inputmode="decimal" placeholder="100" autocomplete="off" />
    </label>
    <label class="field">
      <span class="field-label">Target</span>
      <input id="goal-target" name="target" type="text" inputmode="decimal" placeholder="140" autocomplete="off" />
    </label>
    <label class="field">
      <span class="field-label">Unit</span>
      <input id="goal-unit" name="unit" type="text" placeholder="kg" autocomplete="off" />
    </label>
    <p class="field-help field-wide">A target can be lower than where you are now, for a faster run time or a lighter body weight.</p>
    ${errors.length ? html`<ul class="form-errors field-wide" role="alert">${errors.map((e) => html`<li>${e}</li>`)}</ul>` : ''}
    <div class="form-actions field-wide">
      <button type="submit" class="btn btn-primary">Add goal</button>
      <button type="button" class="btn btn-quiet" data-action="profile:goal-cancel">Cancel</button>
    </div>
  </form>`;
}

function goalsSection(state, today, ui) {
  const week = summarizeWeek(state.sessions, today, state.profile.weekStart);
  const sessions = goalById(state, 'weekly-sessions');
  const minutes = goalById(state, 'weekly-minutes');
  const custom = state.goals.filter((g) => g.kind === 'custom');
  return html`<section class="profile-section" aria-labelledby="section-goals">
    <div class="section-header">
      <h2 class="section-title" id="section-goals">Goals</h2>
      ${ui.addingGoal ? '' : html`<button type="button" class="btn btn-secondary btn-small" data-action="profile:goal-open">${icon('plus')}Add goal</button>`}
    </div>
    ${ui.addingGoal ? goalForm(ui.goalErrors) : ''}
    <div class="card">
      <h3 class="card-title">Weekly targets</h3>
      <ul class="goal-list">
        ${sessions ? weeklyTarget(sessions, week.count) : ''}
        ${minutes ? weeklyTarget(minutes, week.minutes) : ''}
      </ul>
    </div>
    <div class="card">
      <h3 class="card-title">Personal goals</h3>
      ${
        custom.length
          ? html`<ul class="goal-list">${custom.map((g) => customGoal(g, ui.confirmGoal === g.id))}</ul>`
          : html`<p class="muted">Add a goal you want to work toward, like a lift, a run time or a skill.</p>`
      }
    </div>
  </section>`;
}

function preferencesSection(state) {
  const { profile, schedule } = state;
  const order = Array.from({ length: 7 }, (_, i) => (profile.weekStart + i) % 7);
  const planned = schedule.map(getWorkout).filter(Boolean);
  const plannedMinutes = planned.reduce((t, w) => t + w.minutes, 0);
  return html`<section class="profile-section" aria-labelledby="section-preferences">
    <h2 class="section-title" id="section-preferences">Training preferences</h2>
    <div class="card settings-list">
      <div class="setting">
        <div class="setting-text"><p class="setting-title">Experience level</p><p class="setting-help">Marked as your level in the Workouts filter.</p></div>
        ${segmented({ name: 'level', label: 'Experience level', action: 'profile:set', value: profile.level, options: LEVELS.map((l) => ({ value: l.id, label: l.label })) })}
      </div>
      <div class="setting">
        <div class="setting-text"><p class="setting-title"><label for="pref-length">Preferred session length</label></p><p class="setting-help">Routines longer than this are flagged in your plan.</p></div>
        <select id="pref-length" data-change="profile:length">
          ${SESSION_LENGTHS.map((m) => html`<option value="${m}" ${profile.sessionLength === m ? 'selected' : ''}>${m} min</option>`)}
        </select>
      </div>
    </div>
    <div class="card">
      <div class="card-title-row">
        <h3 class="card-title" id="section-plan">Weekly plan</h3>
        <p class="muted">${planned.length} training days · ${plannedMinutes} min</p>
      </div>
      <ul class="plan-list">
        ${order.map((day) => {
          const workout = getWorkout(schedule[day]);
          const long = workout && workout.minutes > profile.sessionLength;
          return html`<li class="plan-row">
            <label class="plan-day" for="plan-${day}">${WEEKDAYS[day]}</label>
            <select id="plan-${day}" data-change="profile:schedule" data-day="${day}">
              <option value="" ${workout ? '' : 'selected'}>Rest day</option>
              ${CATEGORIES.map(
                (c) => html`<optgroup label="${c.label}">
                  ${WORKOUTS.filter((w) => w.category === c.id).map(
                    (w) => html`<option value="${w.id}" ${workout?.id === w.id ? 'selected' : ''}>${w.name}</option>`,
                  )}
                </optgroup>`,
              )}
            </select>
            ${
              workout
                ? html`<span class="plan-meta">
                  <span>${workout.minutes} min · ${workout.focus}</span>
                  ${long ? html`<span class="plan-flag">${icon('clock')}Longer than your preferred ${profile.sessionLength} min</span>` : ''}
                </span>`
                : ''
            }
          </li>`;
        })}
      </ul>
    </div>
  </section>`;
}

function toggle({ key, title, help, checked, extra = '' }) {
  return html`<div class="setting">
    <div class="setting-text">
      <p class="setting-title" id="notif-${key}-title">${title}</p>
      <p class="setting-help">${help}</p>
      ${extra}
    </div>
    <input id="notif-${key}" class="switch" type="checkbox" role="switch" ${checked ? 'checked' : ''}
      aria-labelledby="notif-${key}-title" data-change="profile:notify" data-key="${key}" />
  </div>`;
}

function notificationsSection(state) {
  const n = state.notifications;
  return html`<section class="profile-section" aria-labelledby="section-notifications">
    <h2 class="section-title" id="section-notifications">Notifications</h2>
    <div class="card settings-list">
      ${toggle({
        key: 'reminders',
        title: 'Workout reminder',
        help: "Shows a reminder on Today when the planned workout isn't logged by this time.",
        checked: n.reminders,
        extra: html`<label class="time-field">
          <span class="sr-only">Reminder time</span>
          <input id="notif-time" type="time" value="${n.reminderTime}" ${n.reminders ? '' : 'disabled'} data-change="profile:notify-time" />
        </label>`,
      })}
      ${toggle({ key: 'weeklySummary', title: 'Weekly summary', help: 'A week-in-review prompt on the last day of your training week.', checked: n.weeklySummary })}
      ${toggle({ key: 'milestones', title: 'Goal milestones', help: 'A message when a session completes your weekly workout goal.', checked: n.milestones })}
      ${toggle({ key: 'restDay', title: 'Rest-day check-ins', help: 'Recovery tips on days with nothing planned.', checked: n.restDay })}
    </div>
    <p class="field-help">Notifications appear inside the app while it is open.</p>
  </section>`;
}

const INSTALL_TEXT = {
  installed: ['Installed', 'Workset is on your Home Screen and works without a connection.'],
  prompt: ['Install Workset', 'Add it to your Home Screen. It opens full screen and works offline.'],
  ios: ['Add to Home Screen', 'In Safari, tap Share, then Add to Home Screen. It opens full screen and works offline.'],
  manual: ['Add to Home Screen', "Open this page on your phone and choose Add to Home Screen from the browser's menu."],
};

function installSection(status) {
  if (!INSTALL_TEXT[status]) return '';
  const [heading, help] = INSTALL_TEXT[status];
  return html`<section class="profile-section" aria-labelledby="section-app">
    <h2 class="section-title" id="section-app">App</h2>
    <div class="card install-row">
      <span class="brand-mark" aria-hidden="true"></span>
      <div class="setting-text"><p class="setting-title">${heading}</p><p class="setting-help">${help}</p></div>
      ${status === 'prompt' ? html`<button type="button" class="btn btn-primary btn-small" data-action="app:install">Install</button>` : ''}
    </div>
  </section>`;
}

function settingsSection(state, ui, storageOk) {
  const { profile } = state;
  const samples = state.sessions.filter((s) => s.sample).length;
  return html`<section class="profile-section" aria-labelledby="section-settings">
    <h2 class="section-title" id="section-settings">Settings</h2>
    <div class="card settings-list">
      <div class="setting">
        <div class="setting-text"><p class="setting-title">Weight unit</p><p class="setting-help">Saved sessions convert automatically.</p></div>
        ${segmented({
          name: 'units',
          label: 'Weight unit',
          action: 'profile:set',
          value: profile.units,
          options: [
            { value: 'kg', label: 'kg' },
            { value: 'lb', label: 'lb' },
          ],
        })}
      </div>
      <div class="setting">
        <div class="setting-text"><p class="setting-title">Week starts on</p></div>
        ${segmented({
          name: 'weekStart',
          label: 'Week starts on',
          action: 'profile:set',
          value: String(profile.weekStart),
          options: [
            { value: '1', label: 'Monday' },
            { value: '0', label: 'Sunday' },
          ],
        })}
      </div>
      <div class="setting">
        <div class="setting-text"><p class="setting-title">Appearance</p></div>
        ${segmented({
          name: 'theme',
          label: 'Appearance',
          action: 'profile:set',
          value: profile.theme,
          options: [
            { value: 'system', label: 'System' },
            { value: 'light', label: 'Light' },
            { value: 'dark', label: 'Dark' },
          ],
        })}
      </div>
    </div>
    <div class="card settings-list">
      <h3 class="card-title" id="section-data">Your data</h3>
      <p class="setting-help">${storageOk ? 'Everything is saved in this browser on this device.' : 'This browser is blocking storage, so changes last only until you close the page.'}</p>
      ${
        samples
          ? html`<div class="setting">
            <div class="setting-text"><p class="setting-title">Sample sessions</p><p class="setting-help">${samples} example sessions are mixed into your history. Sessions you logged stay.</p></div>
            <button type="button" class="btn btn-secondary" data-action="profile:clear-samples">Clear samples</button>
          </div>`
          : ''
      }
      <div class="setting">
        <div class="setting-text"><p class="setting-title">Reset everything</p><p class="setting-help">Deletes all sessions, goals and settings on this device.</p></div>
        <button type="button" class="${cx('btn', ui.confirmReset ? 'btn-danger' : 'btn-secondary')}" data-action="profile:reset">
          ${ui.confirmReset ? 'Tap again to reset' : 'Reset'}
        </button>
      </div>
    </div>
  </section>`;
}

export function render({ state, today, ui, storageOk, install }) {
  return html`${pageHeader({ title: 'Profile' })}
    ${profileHead(state)}
    <div class="profile-grid">
      ${goalsSection(state, today, ui.profile)}
      <div class="profile-column">
        ${preferencesSection(state)}
        ${notificationsSection(state)}
        ${installSection(install)}
        ${settingsSection(state, ui.profile, storageOk)}
      </div>
    </div>`;
}

const toNumber = (value) => {
  const n = Number(
    String(value ?? '')
      .trim()
      .replace(',', '.'),
  );
  return String(value ?? '').trim() !== '' && Number.isFinite(n) ? n : NaN;
};

export const handlers = {
  'profile:name'(app, el) {
    app.store.update((s) => updateProfile(s, { name: el.value.trim() }));
  },
  'profile:target'(app, el) {
    const goal = goalById(app.store.state, el.dataset.id);
    const limits = TARGET_LIMITS[goal.kind];
    const target = Math.min(limits.max, Math.max(limits.min, goal.target + Number(el.dataset.step) * limits.step));
    app.store.update((s) => setGoalTarget(s, goal.id, target));
  },
  'profile:goal-current'(app, el) {
    const value = toNumber(el.value);
    const goal = goalById(app.store.state, el.dataset.id);
    if (!Number.isFinite(value) || value < 0) {
      app.toast(`Enter a number for ${goal.title}, for example ${goal.current}.`);
      app.render();
      return;
    }
    app.store.update((s) => setGoalCurrent(s, goal.id, value));
    if (goalProgress({ ...goal, current: value }) >= 1 && goalProgress(goal) < 1) app.toast(`Goal achieved: ${goal.title}`);
  },
  'profile:goal-remove'(app, el) {
    const u = app.ui.profile;
    if (u.confirmGoal !== el.dataset.id) {
      u.confirmGoal = el.dataset.id;
      app.render();
      return;
    }
    u.confirmGoal = null;
    app.store.update((s) => removeGoal(s, el.dataset.id));
    app.toast('Goal removed');
  },
  'profile:goal-keep'(app) {
    app.ui.profile.confirmGoal = null;
    app.render();
  },
  'profile:goal-open'(app) {
    Object.assign(app.ui.profile, { addingGoal: true, goalErrors: [] });
    app.render();
    app.focus('#goal-title');
  },
  'profile:goal-cancel'(app) {
    Object.assign(app.ui.profile, { addingGoal: false, goalErrors: [] });
    app.render();
  },
  'profile:goal-add'(app, form) {
    const data = Object.fromEntries(new FormData(form));
    const goal = {
      id: `goal-${Date.now().toString(36)}`,
      kind: 'custom',
      title: String(data.title ?? '').trim(),
      start: toNumber(data.start),
      target: toNumber(data.target),
      unit: String(data.unit ?? '').trim(),
    };
    const errors = [];
    if (!goal.title) errors.push('Name the goal, for example “Deadlift 1RM”.');
    if (!Number.isFinite(goal.start)) errors.push('Enter where you are now as a number.');
    if (!Number.isFinite(goal.target)) errors.push('Enter a target as a number.');
    else if (goal.target === goal.start) errors.push('Set a target different from where you are now.');
    if (errors.length) {
      app.ui.profile.goalErrors = errors;
      app.render();
      // Keep what was typed: the form re-renders empty, so put the values back.
      for (const [key, value] of Object.entries(data)) {
        const input = document.getElementById(`goal-${key}`);
        if (input) input.value = value;
      }
      return;
    }
    Object.assign(app.ui.profile, { addingGoal: false, goalErrors: [] });
    app.store.update((s) => addGoal(s, { ...goal, current: goal.start }));
    app.toast(`Added goal: ${goal.title}`);
  },
  'profile:set'(app, el) {
    const { name, value } = el.dataset;
    const patch = { [name]: name === 'weekStart' ? Number(value) : value };
    app.store.update((s) => updateProfile(s, patch));
  },
  'profile:length'(app, el) {
    app.store.update((s) => updateProfile(s, { sessionLength: Number(el.value) }));
  },
  'profile:schedule'(app, el) {
    const day = Number(el.dataset.day);
    app.store.update((s) => setSchedule(s, day, el.value));
    const workout = getWorkout(el.value);
    app.toast(`${WEEKDAYS[day]}: ${workout ? workout.name : 'rest day'}`);
  },
  'profile:notify'(app, el) {
    app.store.update((s) => updateNotifications(s, { [el.dataset.key]: el.checked }));
  },
  'profile:notify-time'(app, el) {
    if (el.value) app.store.update((s) => updateNotifications(s, { reminderTime: el.value }));
  },
  'profile:clear-samples'(app) {
    app.store.update(clearSampleSessions);
    app.toast('Sample sessions cleared');
  },
  'profile:reset'(app) {
    const u = app.ui.profile;
    if (!u.confirmReset) {
      u.confirmReset = true;
      app.render();
      return;
    }
    app.resetUi();
    app.store.update(() => resetState(app.today()));
    app.toast('All data reset');
  },
};
