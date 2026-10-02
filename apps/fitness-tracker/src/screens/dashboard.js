// Screen 1 — Today: the assigned workout and a compact view of the current week.

import { html, cx, icon } from '../html.js';
import { addDays, formatLongDate, formatRange, isoWeek, WEEKDAYS, WEEKDAYS_SHORT } from '../dates.js';
import { getExercise, getLevel, getWorkout, workoutSetCount } from '../catalog.js';
import { dayStatus, plannedWorkout, todayPlan } from '../plan.js';
import { percentChange, sessionVolume, summarizeWeek } from '../stats.js';
import { goalById } from '../store.js';
import { draftFromWorkout } from '../draft.js';
import { formatMinutes, formatNumber, formatVolume } from '../units.js';
import { deltaText, linkArrow, meter, pageHeader, prescription, sampleNotice, sectionHeader, sessionRow } from '../components.js';

export const title = 'Today';

export const appbarAction = () => html`<a class="icon-btn" href="#log" aria-label="Log a session">${icon('plus')}</a>`;

function greeting(now) {
  const h = now.getHours();
  if (h >= 5 && h < 12) return 'Good morning';
  if (h >= 12 && h < 18) return 'Good afternoon';
  return 'Good evening';
}

/** The next day after today that has a workout in the plan. */
function nextPlanned(state, today) {
  for (let i = 1; i <= 7; i++) {
    const date = addDays(today, i);
    const workout = plannedWorkout(state, date);
    if (workout) return { date, workout, label: i === 1 ? 'tomorrow' : `on ${WEEKDAYS[date.getDay()]}` };
  }
  return null;
}

function reminder(state, plan, now) {
  const n = state.notifications;
  if (!n.reminders || !plan.workout || plan.completed) return '';
  const [h, m] = n.reminderTime.split(':').map(Number);
  if (now.getHours() * 60 + now.getMinutes() < h * 60 + m) return '';
  return html`<p class="reminder" role="note">${icon('bell')}<span><strong>Reminder:</strong> ${plan.workout.name} is planned for today and isn't logged yet.</span></p>`;
}

function weekInReview(state, today) {
  if (!state.notifications.weeklySummary) return '';
  const lastDay = (state.profile.weekStart + 6) % 7;
  if (today.getDay() !== lastDay) return '';
  return html`<p class="reminder" role="note">${icon('progress')}<span><strong>Week in review:</strong> your weekly summary is ready. <a href="#progress">See how the week went</a></span></p>`;
}

function programPreview(workout, units) {
  const shown = workout.exercises.slice(0, 4);
  const more = workout.exercises.length - shown.length;
  return html`<ol class="hero-program">
    ${shown.map((item) => html`<li><span>${getExercise(item.exercise)?.name}</span><span class="mono">${prescription(item, units)}</span></li>`)}
    ${more > 0 ? html`<li class="hero-more">+ ${more} more</li>` : ''}
  </ol>`;
}

function hero(state, today) {
  const units = state.profile.units;
  const plan = todayPlan(state, today);
  const { workout, completed, logged } = plan;

  if (!workout) {
    const next = nextPlanned(state, today);
    const recovery = getWorkout('mobility-flow');
    return html`<section class="hero is-rest" aria-labelledby="today-title">
      <div class="hero-top"><p class="hero-eyebrow">Today's plan</p>${icon('rest')}</div>
      <h2 class="hero-title" id="today-title">Rest day</h2>
      <p class="hero-copy">
        Recovery is part of the plan.
        ${next ? html`Next up ${next.label}: <strong>${next.workout.name}</strong>, ${next.workout.minutes} min.` : 'No workouts are planned this week.'}
      </p>
      ${logged.length ? html`<p class="hero-copy">You logged ${logged.map((s) => s.name).join(' and ')} today.</p>` : ''}
      ${
        state.notifications.restDay
          ? html`<p class="hero-copy">Check-in: sleep well, drink water, and keep moving with an easy walk.</p>`
          : ''
      }
      <div class="hero-actions">
        <a class="btn btn-hero" href="#workout-${recovery.id}">Try ${recovery.name} · ${recovery.minutes} min</a>
        <a class="btn btn-hero-ghost" href="#profile-plan">Change weekly plan</a>
      </div>
    </section>`;
  }

  const level = getLevel(workout.level);
  return html`<section class="${cx('hero', { 'is-done': completed })}" aria-labelledby="today-title">
    <div class="hero-top">
      <p class="hero-eyebrow">${completed ? 'Today · completed' : "Today's workout"}</p>
      <span class="hero-tag">${workout.focus}</span>
    </div>
    <h2 class="hero-title" id="today-title">${workout.name}</h2>
    <ul class="hero-meta">
      <li>${icon('clock')}<strong>${workout.minutes} min</strong></li>
      <li>${workout.exercises.length} exercises</li>
      <li>${workoutSetCount(workout)} sets</li>
      <li>${level.label}</li>
    </ul>
    ${
      completed
        ? html`<p class="hero-copy hero-done">${icon('check')}<span>Logged ${formatMinutes(completed.minutes)} at RPE ${completed.rpe}${
            sessionVolume(completed) ? ` · ${formatVolume(sessionVolume(completed), units)} moved` : ''
          }. Nice work.</span></p>`
        : programPreview(workout, units)
    }
    <div class="hero-actions">
      ${
        completed
          ? html`<a class="btn btn-hero" href="#progress">See weekly progress</a>
            <a class="btn btn-hero-ghost" href="#workout-${workout.id}">Review workout</a>`
          : html`<a class="btn btn-hero" href="#workout-${workout.id}">Open workout ${icon('next')}</a>
            <button class="btn btn-hero-ghost" type="button" data-action="today:log">Log as done</button>`
      }
    </div>
  </section>`;
}

const STATUS_TEXT = { done: 'Done', today: 'Planned today', upcoming: 'Planned', missed: 'Missed', rest: 'Rest' };

function weekStrip(state, today) {
  const week = summarizeWeek(state.sessions, today, state.profile.weekStart);
  return html`<ol class="week-strip">
    ${week.days.map(({ date }) => {
      const day = dayStatus(state, date, today);
      const shown = day.sessions[0] ? (getWorkout(day.sessions[0].workoutId)?.short ?? 'Custom') : (day.workout?.short ?? 'Rest');
      const name = day.sessions[0]?.name ?? day.workout?.name ?? 'Rest';
      return html`<li class="${cx('day', `is-${day.status}`, { 'is-today': day.isToday })}">
        <span class="day-name" aria-hidden="true">${WEEKDAYS_SHORT[date.getDay()].slice(0, 1)}<small>${date.getDate()}</small></span>
        <span class="day-mark" aria-hidden="true">${day.status === 'done' ? icon('check') : ''}</span>
        <span class="day-label" aria-hidden="true">${shown}</span>
        <span class="sr-only">${WEEKDAYS[date.getDay()]} ${date.getDate()}: ${name}, ${STATUS_TEXT[day.status]}</span>
      </li>`;
    })}
  </ol>`;
}

function weekCard(state, today) {
  const { profile } = state;
  const week = summarizeWeek(state.sessions, today, profile.weekStart);
  const last = summarizeWeek(state.sessions, addDays(today, -7), profile.weekStart);
  const sessionsTarget = goalById(state, 'weekly-sessions')?.target ?? 4;
  const minutesTarget = goalById(state, 'weekly-minutes')?.target ?? 150;
  return html`<section class="card week-card" aria-labelledby="week-title">
    ${sectionHeader('This week', linkArrow('#progress', 'Progress'), 'week-title')}
    <p class="card-sub">${formatRange(week.start, week.end)} · Week ${isoWeek(today)}</p>
    ${weekStrip(state, today)}
    <ul class="strip-key" aria-hidden="true">
      <li><span class="key-mark done"></span>Done</li>
      <li><span class="key-mark"></span>Planned</li>
      <li><span class="key-mark missed"></span>Missed</li>
      <li><span class="key-mark rest"></span>Rest</li>
    </ul>
    <dl class="week-stats">
      <div>
        <dt>Workouts</dt>
        <dd><strong>${week.count}</strong> of ${sessionsTarget}</dd>
        ${meter(week.count / sessionsTarget, { label: 'Workouts toward weekly goal' })}
      </div>
      <div>
        <dt>Active time</dt>
        <dd><strong>${formatNumber(week.minutes)}</strong> of ${minutesTarget} min</dd>
        ${meter(week.minutes / minutesTarget, { label: 'Minutes toward weekly goal' })}
      </div>
      <div>
        <dt>Volume</dt>
        <dd><strong>${formatVolume(week.volume, profile.units)}</strong></dd>
        <p class="week-delta">${deltaText(percentChange(week.volume, last.volume))}</p>
      </div>
    </dl>
  </section>`;
}

function recent(state, today) {
  const list = [...state.sessions].sort((a, b) => b.date.localeCompare(a.date) || b.loggedAt.localeCompare(a.loggedAt)).slice(0, 3);
  return html`<section class="recent" aria-labelledby="recent-title">
    ${sectionHeader('Recent sessions', linkArrow('#log', 'Log a session'), 'recent-title')}
    ${
      list.length
        ? html`<ul class="session-list card">${list.map((s) => sessionRow(s, { today, units: state.profile.units }))}</ul>`
        : html`<p class="card empty-inline">No sessions yet. Finish today's workout and log it to start your history.</p>`
    }
  </section>`;
}

export function render({ state, today, now }) {
  return html`${pageHeader({
    eyebrow: formatLongDate(today),
    title: `${greeting(now)}${state.profile.name ? `, ${state.profile.name}` : ''}`,
  })}
    ${sampleNotice(state)}
    ${reminder(state, todayPlan(state, today), now)}
    ${weekInReview(state, today)}
    <div class="dash-grid">
      ${hero(state, today)}
      ${weekCard(state, today)}
    </div>
    ${recent(state, today)}`;
}

export const handlers = {
  'today:log'(app) {
    const workout = plannedWorkout(app.store.state, app.today());
    app.store.update((s) => ({ ...s, draft: draftFromWorkout(workout?.id, app.today(), s.profile.units) }), { silent: true });
    app.navigate('#log');
  },
};
