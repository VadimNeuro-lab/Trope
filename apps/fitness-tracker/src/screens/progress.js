// Screen 4 — Progress: one week of training in numbers and charts, how consistent
// the last eight weeks have been, and how the main lifts are trending.

import { html, cx, icon } from '../html.js';
import { addDays, diffDays, formatDayAndDate, formatRange, formatShortDate, WEEKDAYS_SHORT } from '../dates.js';
import { getExercise, groupLabel } from '../catalog.js';
import { dayStatus } from '../plan.js';
import {
  consistencyRate,
  goalStreak,
  liftTrend,
  liftsWithHistory,
  muscleBreakdown,
  percentChange,
  summarizeWeek,
  weeklyHistory,
} from '../stats.js';
import { deleteSession, goalById } from '../store.js';
import { displayVolume, formatMinutes, formatNumber, toDisplayWeight, unitLabel } from '../units.js';
import { barList, columnChart, lineChart, tableView } from '../charts.js';
import { deltaText, emptyState, meter, pageHeader, sampleNotice, sessionRow, statTile } from '../components.js';

export const title = 'Progress';

export const initialUi = () => ({ weekOffset: 0, lift: null, confirmDelete: null });

const MAX_WEEKS_BACK = 52;

function weekName(offset) {
  if (offset === 0) return 'This week';
  if (offset === 1) return 'Last week';
  return `${offset} weeks ago`;
}

function weekNav(offset, week) {
  return html`<div class="week-nav">
    <button type="button" class="icon-btn" data-action="progress:week" data-step="1" aria-label="Previous week" ${offset >= MAX_WEEKS_BACK ? 'disabled' : ''}>${icon('back')}</button>
    <p class="week-nav-label" aria-live="polite"><strong>${weekName(offset)}</strong><span>${formatRange(week.start, week.end)}</span></p>
    <button type="button" class="icon-btn" data-action="progress:week" data-step="-1" aria-label="Next week" ${offset === 0 ? 'disabled' : ''}>${icon('next')}</button>
  </div>`;
}

/** Week labels that only name the month where it changes. */
function weekLabels(history) {
  return history.map((w, i) => {
    const prev = history[i - 1]?.start;
    return {
      label: String(w.start.getDate()),
      sublabel: !prev || prev.getMonth() !== w.start.getMonth() ? formatShortDate(w.start).split(' ')[1] : '',
    };
  });
}

function dailyChart(state, week, today) {
  const items = week.days.map((d) => {
    const day = dayStatus(state, d.date, today);
    const when = formatDayAndDate(d.date);
    let tip;
    if (d.sessions.length) tip = `${when} · ${d.sessions.map((s) => s.name).join(' + ')} · ${d.minutes} min`;
    else if (day.status === 'upcoming' || day.status === 'today') tip = `${when} · Planned: ${day.workout.name}`;
    else if (day.status === 'missed') tip = `${when} · ${day.workout.name} not logged`;
    else tip = `${when} · Rest day`;
    return { label: WEEKDAYS_SHORT[d.date.getDay()], sublabel: String(d.date.getDate()), value: d.minutes, tip, current: day.isToday };
  });
  return html`${columnChart({ items, label: 'Training minutes by day', format: (v) => `${v}` })}
    ${tableView(
      'Show as table',
      ['Day', 'Sessions', 'Minutes', `Volume (${unitLabel(state.profile.units)})`],
      week.days.map((d) => [
        formatDayAndDate(d.date),
        d.sessions.map((s) => s.name).join(', ') || '—',
        d.minutes,
        formatNumber(displayVolume(d.volume, state.profile.units)),
      ]),
    )}`;
}

function consistencyCard(state, ref, offset, target) {
  const history = weeklyHistory(state.sessions, ref, state.profile.weekStart, 8);
  const streak = goalStreak(history, target);
  const rate = consistencyRate(history, target);
  const finished = history.length - 1;
  const onTarget = Math.round(rate * finished);
  const labels = weekLabels(history);
  const items = history.map((w, i) => ({
    ...labels[i],
    value: w.count,
    tone: w.count >= target ? 'accent' : 'soft',
    current: i === history.length - 1,
    tip: `Week of ${formatShortDate(w.start)} · ${w.count} ${w.count === 1 ? 'workout' : 'workouts'} · ${formatMinutes(w.minutes)}`,
  }));
  return html`<section class="card chart-card" aria-labelledby="consistency-title">
    <div class="chart-head">
      <div>
        <h2 class="section-title" id="consistency-title">Consistency</h2>
        <p class="card-sub">Workouts per week against your goal of ${target}</p>
      </div>
      <div class="streak">
        ${icon('flame')}
        <p><strong>${streak ? `${streak}-week streak` : 'No streak yet'}</strong><span>${onTarget} of ${finished} finished weeks on target</span></p>
      </div>
    </div>
    <ul class="legend" aria-label="Legend">
      <li><span class="swatch accent"></span>Met goal</li>
      <li><span class="swatch soft"></span>Below goal</li>
    </ul>
    ${columnChart({ items, goal: { value: target, label: `Goal ${target}` }, label: 'Workouts per week for eight weeks' })}
    ${tableView(
      'Show as table',
      ['Week of', 'Workouts', 'Minutes', 'Goal met'],
      history.map((w) => [formatShortDate(w.start), w.count, w.minutes, w.count >= target ? 'Yes' : 'No']),
    )}
    ${offset ? html`<p class="card-foot">Eight weeks ending ${formatRange(history.at(-1).start, addDays(history.at(-1).start, 6))}.</p>` : ''}
  </section>`;
}

function liftCard(state, ref, ui) {
  const lifts = liftsWithHistory(state.sessions);
  if (!lifts.length) return '';
  const lift = lifts.includes(ui.lift) ? ui.lift : lifts[0];
  const units = state.profile.units;
  const unit = unitLabel(units);
  const trend = liftTrend(state.sessions, lift, ref, state.profile.weekStart, 8);
  const labels = weekLabels(trend);
  const known = trend.filter((p) => p.value !== null);
  const show = (kg) => formatNumber(toDisplayWeight(kg, units));
  const change = known.length > 1 ? known.at(-1).value - known[0].value : 0;
  const points = trend.map((p, i) => ({
    label: labels[i].sublabel ? `${labels[i].label} ${labels[i].sublabel}` : labels[i].label,
    value: p.value === null ? null : toDisplayWeight(p.value, units),
    tip: p.value === null ? '' : `Week of ${formatShortDate(p.start)} · est. 1RM ${show(p.value)} ${unit}`,
  }));
  return html`<section class="card chart-card" aria-labelledby="lift-title">
    <div class="chart-head">
      <div>
        <h2 class="section-title" id="lift-title">Strength trend</h2>
        <p class="card-sub">Estimated one-rep max from your best set each week</p>
      </div>
      <label class="select-inline">
        <span class="sr-only">Exercise</span>
        <select id="lift-select" data-change="progress:lift">
          ${lifts.map((id) => html`<option value="${id}" ${id === lift ? 'selected' : ''}>${getExercise(id)?.name ?? id}</option>`)}
        </select>
      </label>
    </div>
    ${
      known.length > 1
        ? html`<p class="trend-summary">
            <strong>${show(known.at(-1).value)} ${unit}</strong>
            ${change > 0 ? html`<span class="delta up">+${show(change)} ${unit}</span>` : change < 0 ? html`<span class="delta down">−${show(-change)} ${unit}</span>` : ''}
            <span class="muted">over ${diffDays(trend.at(-1).start, known[0].start) / 7 + 1} weeks</span>
          </p>
          ${lineChart({ points, label: `Estimated one-rep max for ${getExercise(lift)?.name}`, format: (v) => formatNumber(v) })}
          ${tableView(
            'Show as table',
            ['Week of', `Est. 1RM (${unit})`],
            trend.map((p) => [formatShortDate(p.start), p.value === null ? '—' : show(p.value)]),
          )}`
        : html`<p class="muted">Log this lift in at least two different weeks to see a trend.</p>`
    }
  </section>`;
}

function muscleCard(week) {
  const rows = muscleBreakdown(week.sessions);
  return html`<section class="card chart-card" aria-labelledby="muscle-title">
    <h2 class="section-title" id="muscle-title">Sets by muscle group</h2>
    <p class="card-sub">${week.sets} working sets this week</p>
    ${
      rows.length
        ? barList(rows.map((r) => ({ label: groupLabel(r.group), value: r.sets, display: `${r.sets} ${r.sets === 1 ? 'set' : 'sets'}` })))
        : html`<p class="muted">No sets logged in this week.</p>`
    }
  </section>`;
}

function sessionsCard(state, week, today, confirmId) {
  const units = state.profile.units;
  const list = [...week.sessions].reverse();
  return html`<section class="sessions-card" aria-labelledby="sessions-title">
    <h2 class="section-title" id="sessions-title">Sessions</h2>
    ${
      list.length
        ? html`<ul class="session-list card">
          ${list.map((s) =>
            sessionRow(s, {
              today,
              units,
              actions:
                confirmId === s.id
                  ? html`<span class="row-confirm">
                      <button type="button" class="btn btn-danger btn-small" data-action="progress:delete" data-id="${s.id}">Delete</button>
                      <button type="button" class="btn btn-quiet btn-small" data-action="progress:cancel-delete">Keep</button>
                    </span>`
                  : html`<button type="button" class="icon-btn" data-action="progress:delete" data-id="${s.id}" aria-label="Delete ${s.name} session">${icon('trash')}</button>`,
            }),
          )}
        </ul>`
        : emptyState({
            title: 'No sessions in this week',
            body: 'Logged workouts appear here with their duration, effort and volume.',
            action: html`<a class="btn btn-secondary" href="#log">Log a session</a>`,
          })
    }
  </section>`;
}

export function render({ state, today, ui }) {
  const u = ui.progress;
  const { profile } = state;
  const ref = addDays(today, -7 * u.weekOffset);
  const week = summarizeWeek(state.sessions, ref, profile.weekStart);
  const prev = summarizeWeek(state.sessions, addDays(ref, -7), profile.weekStart);
  const sessionsTarget = goalById(state, 'weekly-sessions')?.target ?? 4;
  const minutesTarget = goalById(state, 'weekly-minutes')?.target ?? 150;
  const remaining = Math.max(0, sessionsTarget - week.count);

  return html`${pageHeader({ title: 'Progress', aside: weekNav(u.weekOffset, week) })}
    ${sampleNotice(state)}
    <div class="stat-grid">
      ${statTile({
        label: 'Workouts',
        value: week.count,
        unit: `of ${sessionsTarget}`,
        detail: html`${meter(week.count / sessionsTarget, { label: 'Workouts toward weekly goal' })}<span>${
          remaining ? `${remaining} to go` : 'Weekly goal met'
        }</span>`,
        tone: cx({ 'is-met': !remaining }),
      })}
      ${statTile({
        label: 'Active time',
        value: formatNumber(week.minutes),
        unit: 'min',
        detail: html`${meter(week.minutes / minutesTarget, { label: 'Minutes toward weekly goal' })}<span>${deltaText(percentChange(week.minutes, prev.minutes), 'the week before')}</span>`,
      })}
      ${statTile({
        label: 'Volume',
        value: formatNumber(displayVolume(week.volume, profile.units)),
        unit: unitLabel(profile.units),
        detail: deltaText(percentChange(week.volume, prev.volume), 'the week before'),
      })}
      ${statTile({
        label: 'Average effort',
        value: week.avgRpe ?? '—',
        unit: week.avgRpe ? 'RPE' : '',
        detail: `${week.activeDays} active ${week.activeDays === 1 ? 'day' : 'days'} · ${week.sets} sets`,
      })}
    </div>
    <div class="progress-grid">
      <section class="card chart-card" aria-labelledby="daily-title">
        <h2 class="section-title" id="daily-title">Minutes by day</h2>
        <p class="card-sub">${formatMinutes(week.minutes)} across ${week.count} ${week.count === 1 ? 'session' : 'sessions'}</p>
        ${dailyChart(state, week, today)}
      </section>
      ${consistencyCard(state, ref, u.weekOffset, sessionsTarget)}
      ${muscleCard(week)}
      ${liftCard(state, ref, u)}
    </div>
    ${sessionsCard(state, week, today, u.confirmDelete)}`;
}

export const handlers = {
  'progress:week'(app, el) {
    const u = app.ui.progress;
    u.weekOffset = Math.min(MAX_WEEKS_BACK, Math.max(0, u.weekOffset + Number(el.dataset.step)));
    u.confirmDelete = null;
    app.render();
  },
  'progress:lift'(app, el) {
    app.ui.progress.lift = el.value;
    app.render();
  },
  'progress:delete'(app, el) {
    const u = app.ui.progress;
    const id = el.dataset.id;
    if (u.confirmDelete !== id) {
      u.confirmDelete = id;
      app.render();
      return;
    }
    u.confirmDelete = null;
    const session = app.store.state.sessions.find((s) => s.id === id);
    app.store.update((s) => deleteSession(s, id));
    app.toast(`Deleted ${session?.name ?? 'session'}`);
  },
  'progress:cancel-delete'(app) {
    app.ui.progress.confirmDelete = null;
    app.render();
  },
};
