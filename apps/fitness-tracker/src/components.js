// Small presentational pieces shared by several screens.

import { html, cx, icon } from './html.js';
import { getExercise, getLevel } from './catalog.js';
import { parseDayKey, relativeDay } from './dates.js';
import { sessionSetCount, sessionVolume } from './stats.js';
import { hasSampleSessions } from './store.js';
import { formatDuration, formatMinutes, formatVolume, formatWeight } from './units.js';

export function pageHeader({ eyebrow = '', title, sub = '', aside = '' }) {
  return html`<header class="page-header">
    <div class="page-heading">
      ${eyebrow ? html`<p class="eyebrow">${eyebrow}</p>` : ''}
      <h1 class="page-title">${title}</h1>
      ${sub ? html`<p class="page-sub">${sub}</p>` : ''}
    </div>
    ${aside ? html`<div class="page-aside">${aside}</div>` : ''}
  </header>`;
}

/** Three ascending bars, filled to the routine's difficulty. */
export function levelBadge(levelId) {
  const level = getLevel(levelId);
  return html`<span class="level" data-rank="${level.rank}">
    <span class="level-bars" aria-hidden="true"><i></i><i></i><i></i></span>${level.label}
  </span>`;
}

/** A progress bar with a text value; `fraction` is clamped to 0–1. */
export function meter(fraction, { label, tone = '' } = {}) {
  const f = Math.max(0, Math.min(1, fraction || 0));
  return html`<span class="${cx('meter', tone)}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(f * 100)}" aria-label="${label}">
    <span class="meter-fill" style="width:${f * 100}%"></span>
  </span>`;
}

export function statTile({ label, value, unit = '', detail = '', tone = '' }) {
  return html`<div class="${cx('stat', tone)}">
    <p class="stat-label">${label}</p>
    <p class="stat-value">${value}${unit ? html`<span class="stat-unit">${unit}</span>` : ''}</p>
    ${detail ? html`<p class="stat-detail">${detail}</p>` : ''}
  </div>`;
}

/** Signed comparison with the previous period, worded for a person rather than a spreadsheet. */
export function deltaText(change, period = 'last week') {
  if (change === null) return `No sessions ${period}`;
  const pctValue = Math.round(change * 100);
  if (pctValue === 0) return `Same as ${period}`;
  return html`<span class="${cx('delta', pctValue > 0 ? 'up' : 'down')}">${pctValue > 0 ? '+' : '−'}${Math.abs(pctValue)}%</span> vs ${period}`;
}

export function sampleNotice(state) {
  if (!hasSampleSessions(state)) return '';
  return html`<p class="notice">
    <span class="notice-tag">Sample data</span>
    <span>Past sessions are examples so you can explore the app. Clear them in <a href="#profile-data">Profile</a> when you start logging your own.</span>
  </p>`;
}

export function emptyState({ title, body, action = '' }) {
  return html`<div class="empty">
    <p class="empty-title">${title}</p>
    <p class="empty-body">${body}</p>
    ${action}
  </div>`;
}

export function sectionHeader(title, aside = '', id = '') {
  return html`<div class="section-header">
    <h2 class="section-title" ${id ? html`id="${id}"` : ''}>${title}</h2>
    ${aside}
  </div>`;
}

export const linkArrow = (href, label) => html`<a class="link-arrow" href="${href}">${label}${icon('next')}</a>`;

/** Lifter's shorthand for a prescription: "4 × 6 · 60 kg" or "3 × 40 s". */
export function prescription(item, units) {
  const info = getExercise(item.exercise);
  if (info?.measure === 'time') return `${item.sets} × ${formatDuration(item.reps)}`;
  return `${item.sets} × ${item.reps}${item.weight ? ` · ${formatWeight(item.weight, units)}` : ''}`;
}

export function sessionRow(session, { today, units, actions = '' }) {
  const volume = sessionVolume(session);
  return html`<li class="session-row">
    <div class="session-main">
      <p class="session-name">${session.name}${session.sample ? html` <span class="tag">Sample</span>` : ''}</p>
      <p class="session-meta">
        ${relativeDay(parseDayKey(session.date), today)} · ${formatMinutes(session.minutes)}${Number.isFinite(session.rpe) ? ` · RPE ${session.rpe}` : ''}
      </p>
    </div>
    <p class="session-figure">${volume > 0 ? formatVolume(volume, units) : `${sessionSetCount(session)} sets`}</p>
    ${actions}
  </li>`;
}
