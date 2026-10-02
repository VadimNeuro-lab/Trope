// Charts built from HTML and a little SVG. Labels are real text, so they stay crisp
// and readable at any width; every chart has a table view with the same numbers.

import { html, cx } from './html.js';

/** Round tick values covering [min, max], about `count` intervals apart. */
export function niceTicks(min, max, count = 4) {
  if (!(max > min)) max = min + 1;
  const rough = (max - min) / count;
  const pow = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= rough);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Math.round(v * 1000) / 1000);
  return ticks;
}

const pct = (value, lo, hi) => ((value - lo) / (hi - lo)) * 100;

function tipAlign(i, n) {
  if (i === 0) return 'tip-start';
  if (i === n - 1) return 'tip-end';
  return '';
}

function axis(ticks, lo, hi, format) {
  return html`<div class="chart-axis" aria-hidden="true">
      ${ticks.map((t) => html`<span style="bottom:${pct(t, lo, hi)}%">${format(t)}</span>`)}
    </div>
    <div class="chart-grid" aria-hidden="true">
      ${ticks.map((t) => html`<i style="bottom:${pct(t, lo, hi)}%"></i>`)}
    </div>`;
}

export function tableView(summary, headers, rows) {
  return html`<details class="table-view">
    <summary>${summary}</summary>
    <div class="table-scroll">
      <table>
        <thead><tr>${headers.map((h) => html`<th scope="col">${h}</th>`)}</tr></thead>
        <tbody>${rows.map((r) => html`<tr>${r.map((c, i) => (i === 0 ? html`<th scope="row">${c}</th>` : html`<td>${c}</td>`))}</tr>`)}</tbody>
      </table>
    </div>
  </details>`;
}

/**
 * Vertical columns from one baseline.
 * items: { label, sublabel?, value, tone?: 'accent' | 'soft', tip, current? }
 */
export function columnChart({ items, goal = null, format = (v) => v, label }) {
  const peak = Math.max(1, goal?.value ?? 0, ...items.map((d) => d.value));
  const ticks = niceTicks(0, peak, 3);
  const hi = ticks.at(-1);
  return html`<figure class="chart" aria-label="${label}">
    <div class="chart-body" style="--cols:${items.length}">
      ${axis(ticks, 0, hi, format)}
      <div class="chart-plot">
        ${
          goal
            ? html`<div class="chart-goal" style="bottom:${pct(goal.value, 0, hi)}%" aria-hidden="true"><span>${goal.label}</span></div>`
            : ''
        }
        ${items.map(
          (
            d,
            i,
          ) => html`<div class="${cx('col', { 'is-current': d.current })}" style="--h:${pct(d.value, 0, hi)}%" tabindex="0" aria-label="${d.tip}">
            <div class="${cx('col-bar', d.tone ?? 'accent')}"></div>
            <div class="${cx('tip', tipAlign(i, items.length))}" role="presentation">${d.tip}</div>
          </div>`,
        )}
      </div>
      <div class="chart-x" aria-hidden="true">
        ${items.map(
          (d) =>
            html`<span class="${cx({ 'is-current': d.current })}">${d.label}${d.sublabel ? html`<small>${d.sublabel}</small>` : ''}</span>`,
        )}
      </div>
    </div>
  </figure>`;
}

/**
 * A single series over evenly spaced points, with an area wash and an end marker.
 * points: { label, value | null, tip }
 */
export function lineChart({ points, format = (v) => v, label }) {
  const values = points.map((p) => p.value).filter((v) => v !== null);
  if (!values.length) return '';
  const ticks = niceTicks(Math.min(...values), Math.max(...values), 3);
  const lo = ticks[0];
  const hi = ticks.at(-1);
  const n = points.length;
  const coords = points
    .map((p, i) => (p.value === null ? null : { x: ((i + 0.5) / n) * 100, y: 100 - pct(p.value, lo, hi), i }))
    .filter(Boolean);
  const line = coords.map((c, i) => `${i ? 'L' : 'M'}${c.x.toFixed(2)},${c.y.toFixed(2)}`).join(' ');
  const area = `${line} L${coords.at(-1).x.toFixed(2)},100 L${coords[0].x.toFixed(2)},100 Z`;
  const last = coords.at(-1);
  return html`<figure class="chart" aria-label="${label}">
    <div class="chart-body" style="--cols:${n}">
      ${axis(ticks, lo, hi, format)}
      <div class="chart-plot">
        <svg class="line-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path class="line-area" d="${area}"></path>
          <path class="line-path" d="${line}" vector-effect="non-scaling-stroke"></path>
        </svg>
        <span class="line-dot is-end" style="left:${last.x}%;top:${last.y}%" aria-hidden="true"></span>
        <span class="line-end-label" style="left:${last.x}%;top:${last.y}%" aria-hidden="true">${format(points[last.i].value)}</span>
        ${points.map((p, i) => {
          const c = coords.find((k) => k.i === i);
          if (!c) return '';
          return html`<div class="line-hit" style="left:${(i / n) * 100}%;width:${100 / n}%" tabindex="0" aria-label="${p.tip}">
            <i class="crosshair"></i>
            <span class="line-dot" style="top:${c.y}%"></span>
            <div class="${cx('tip', tipAlign(i, n))}" style="bottom:${100 - c.y}%" role="presentation">${p.tip}</div>
          </div>`;
        })}
      </div>
      <div class="chart-x" aria-hidden="true">
        ${points.map((p, i) => html`<span class="${cx({ 'is-alt': (n - 1 - i) % 2 === 1 })}">${p.label}</span>`)}
      </div>
    </div>
  </figure>`;
}

/** Horizontal bars for a ranked list. items: { label, value, display } */
export function barList(items) {
  const max = Math.max(1, ...items.map((d) => d.value));
  return html`<ul class="barlist">
    ${items.map(
      (d) => html`<li>
        <span class="barlist-label">${d.label}</span>
        <span class="barlist-track" aria-hidden="true"><span class="barlist-bar" style="width:${(d.value / max) * 100}%"></span></span>
        <span class="barlist-value">${d.display}</span>
      </li>`,
    )}
  </ul>`;
}
