// Generates the top-down dish images used by the recipe app screens.
// Every image is a deterministic SVG (seeded RNG), 1000x750, light from the top-left.
// Usage: node generate.mjs   -> writes <dish>.svg next to this file.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = path.dirname(fileURLToPath(import.meta.url));
const W = 1000, H = 750;

// ---------- utilities ----------
function rng(seed) {
  let a = seed >>> 0;
  const r = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  r.range = (lo, hi) => lo + r() * (hi - lo);
  r.pick = (arr) => arr[Math.floor(r() * arr.length)];
  r.gauss = () => (r() + r() + r() - 1.5) / 1.5;
  return r;
}
const f = (n) => Math.round(n * 10) / 10;
const rad = (d) => (d * Math.PI) / 180;

function hexToRgb(h) {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function rgbToHex([r, g, b]) {
  return '#' + [r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
}
// shade(color, amt): amt>0 lightens toward white, amt<0 darkens toward black
function shade(hex, amt) {
  const c = hexToRgb(hex);
  return rgbToHex(c.map((v) => (amt >= 0 ? v + (255 - v) * amt : v * (1 + amt))));
}
function mix(a, b, t) {
  const A = hexToRgb(a), B = hexToRgb(b);
  return rgbToHex(A.map((v, i) => v + (B[i] - v) * t));
}
function jitterColor(r, hex, amt) {
  return shade(hex, r.range(-amt, amt));
}

// Smooth closed/open path through points (Catmull-Rom -> cubic Bezier)
function smooth(pts, closed = false) {
  if (pts.length < 2) return '';
  const p = closed ? [pts[pts.length - 1], ...pts, pts[0], pts[1]] : [pts[0], ...pts, pts[pts.length - 1]];
  let d = `M${f(p[1][0])},${f(p[1][1])}`;
  for (let i = 1; i < p.length - 2; i++) {
    const [x0, y0] = p[i - 1], [x1, y1] = p[i], [x2, y2] = p[i + 1], [x3, y3] = p[i + 2];
    const c1x = x1 + (x2 - x0) / 6, c1y = y1 + (y2 - y0) / 6;
    const c2x = x2 - (x3 - x1) / 6, c2y = y2 - (y3 - y1) / 6;
    d += ` C${f(c1x)},${f(c1y)} ${f(c2x)},${f(c2y)} ${f(x2)},${f(y2)}`;
  }
  return d + (closed ? 'Z' : '');
}
// Irregular blob around (cx,cy)
function blob(r, cx, cy, rx, ry, irregular = 0.18, n = 10, rot = 0) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const k = 1 + r.range(-irregular, irregular);
    const x = Math.cos(a) * rx * k, y = Math.sin(a) * ry * k;
    const c = Math.cos(rot), s = Math.sin(rot);
    pts.push([cx + x * c - y * s, cy + x * s + y * c]);
  }
  return smooth(pts, true);
}

class Scene {
  constructor(seed) {
    this.r = rng(seed);
    this.defs = [];
    this.layers = [];
    this.uid = 0;
  }
  id(p = 'g') { return `${p}${++this.uid}`; }
  def(s) { this.defs.push(s); }
  add(s) { this.layers.push(s); }
  radial(stops, attrs = '') {
    const id = this.id('rg');
    this.def(`<radialGradient id="${id}" ${attrs}>${stops.map(([o, c, op = 1]) => `<stop offset="${o}" stop-color="${c}" stop-opacity="${op}"/>`).join('')}</radialGradient>`);
    return `url(#${id})`;
  }
  linear(stops, x1 = 0, y1 = 0, x2 = 0, y2 = 1, attrs = '') {
    const id = this.id('lg');
    this.def(`<linearGradient id="${id}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" ${attrs}>${stops.map(([o, c, op = 1]) => `<stop offset="${o}" stop-color="${c}" stop-opacity="${op}"/>`).join('')}</linearGradient>`);
    return `url(#${id})`;
  }
  svg() {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">
<defs>
<filter id="blur4" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter>
<filter id="blur10" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="10"/></filter>
<filter id="blur22" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="22"/></filter>
<filter id="blur2" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2"/></filter>
<filter id="blur1" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="0.9"/></filter>
<filter id="organic" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="4" result="t"/><feDisplacementMap in="SourceGraphic" in2="t" scale="9" xChannelSelector="R" yChannelSelector="G"/></filter>
<filter id="organicFine" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency="0.09" numOctaves="2" seed="7" result="t"/><feDisplacementMap in="SourceGraphic" in2="t" scale="5" xChannelSelector="R" yChannelSelector="G"/></filter>
<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="11" stitchTiles="stitch"/><feColorMatrix type="matrix" values="0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 1.4 -0.55"/></filter>
<filter id="mottle" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves="3" seed="2"/><feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -1.6 1.05" result="m"/><feComposite in="m" in2="SourceGraphic" operator="in"/></filter>
${this.defs.join('\n')}
</defs>
${this.layers.join('\n')}
</svg>`;
  }
}

// ---------- surfaces ----------
function surfaceLinen(sc, base) {
  sc.add(`<rect width="${W}" height="${H}" fill="${base}"/>`);
  const id = sc.id('lin');
  sc.def(`<filter id="${id}" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.9 0.03" numOctaves="2" seed="5" result="a"/><feTurbulence type="fractalNoise" baseFrequency="0.03 0.9" numOctaves="2" seed="9" result="b"/><feBlend in="a" in2="b" mode="multiply" result="c"/><feColorMatrix in="c" type="matrix" values="0 0 0 0 0.25  0 0 0 0 0.22  0 0 0 0 0.2  0 0 0 -1.1 0.75"/></filter>`);
  sc.add(`<rect width="${W}" height="${H}" filter="url(#${id})" opacity="0.55"/>`);
}
function surfaceWood(sc, base) {
  sc.add(`<rect width="${W}" height="${H}" fill="${base}"/>`);
  const id = sc.id('wood');
  sc.def(`<filter id="${id}" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.004 0.09" numOctaves="4" seed="12"/><feColorMatrix type="matrix" values="0 0 0 0 0.35  0 0 0 0 0.2  0 0 0 0 0.08  0 0 0 -2.2 1.25"/></filter>`);
  sc.add(`<rect width="${W}" height="${H}" filter="url(#${id})" opacity="0.6"/>`);
  // plank seams
  for (const y of [180, 430, 690]) sc.add(`<rect x="0" y="${y}" width="${W}" height="2.5" fill="${shade(base, -0.35)}" opacity="0.45"/><rect x="0" y="${y + 2.5}" width="${W}" height="1.5" fill="#fff" opacity="0.18"/>`);
}
function surfaceMarble(sc, base) {
  sc.add(`<rect width="${W}" height="${H}" fill="${base}"/>`);
  const id = sc.id('mar');
  sc.def(`<filter id="${id}" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.006 0.012" numOctaves="5" seed="21"/><feColorMatrix type="matrix" values="0 0 0 0 0.45  0 0 0 0 0.45  0 0 0 0 0.47  -3 0 0 0 1.62"/></filter>`);
  sc.add(`<rect width="${W}" height="${H}" filter="url(#${id})" opacity="0.5"/>`);
}
function surfaceStone(sc, base) {
  sc.add(`<rect width="${W}" height="${H}" fill="${base}"/>`);
  sc.add(`<rect width="${W}" height="${H}" filter="url(#mottle)" opacity="0.18"/>`);
}
function lighting(sc) {
  // soft window light from the top-left, gentle vignette
  sc.add(`<rect width="${W}" height="${H}" fill="${sc.radial([[0, '#ffffff', 0.32], [0.55, '#ffffff', 0.0]], 'cx="0.15" cy="0.05" r="0.9"')}"/>`);
  sc.add(`<rect width="${W}" height="${H}" fill="${sc.radial([[0.55, '#000', 0], [1, '#2a1d10', 0.22]], 'cx="0.45" cy="0.42" r="0.78"')}"/>`);
  sc.add(`<rect width="${W}" height="${H}" filter="url(#grain)" opacity="0.22"/>`);
}

// ---------- tableware ----------
function dropShadow(sc, shapeSvg, dx = 16, dy = 22, op = 0.3, blur = 'blur22') {
  sc.add(`<g transform="translate(${dx},${dy})" filter="url(#${blur})" opacity="${op}">${shapeSvg}</g>`);
}
function plate(sc, cx, cy, r, { color = '#f7f5f1', rim = 0.76 } = {}) {
  dropShadow(sc, `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#000"/>`, 14, 22, 0.32);
  dropShadow(sc, `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#000"/>`, 4, 6, 0.25, 'blur4');
  sc.add(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="${sc.radial([[0, '#ffffff'], [0.72, color], [0.93, shade(color, -0.03)], [1, shade(color, -0.12)]], 'cx="0.42" cy="0.4" r="0.62"')}"/>`);
  sc.add(`<circle cx="${cx}" cy="${cy}" r="${r * rim}" fill="none" stroke="${shade(color, -0.1)}" stroke-width="5" opacity="0.5" filter="url(#blur2)"/>`);
  sc.add(`<circle cx="${cx - 3}" cy="${cy - 3}" r="${r * rim + 4}" fill="none" stroke="#fff" stroke-width="3" opacity="0.7" filter="url(#blur1)"/>`);
  sc.add(`<path d="M${cx - r * 0.93},${cy - r * 0.05} A${r * 0.93},${r * 0.93} 0 0 1 ${cx + r * 0.2},${cy - r * 0.91}" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" opacity="0.65" filter="url(#blur2)"/>`);
}
function bowl(sc, cx, cy, r, { outer = '#f4f1ec', inner = '#faf8f4', rimW = 0.1 } = {}) {
  dropShadow(sc, `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#000"/>`, 18, 26, 0.36);
  dropShadow(sc, `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#000"/>`, 5, 7, 0.28, 'blur4');
  sc.add(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="${sc.radial([[0, shade(outer, 0.25)], [0.85, outer], [1, shade(outer, -0.18)]], 'cx="0.4" cy="0.38" r="0.65"')}"/>`);
  const ri = r * (1 - rimW);
  sc.add(`<circle cx="${cx}" cy="${cy}" r="${ri}" fill="${sc.radial([[0, inner], [0.75, shade(inner, -0.03)], [1, shade(inner, -0.2)]], 'cx="0.56" cy="0.6" r="0.6"')}"/>`);
  sc.add(`<circle cx="${cx}" cy="${cy}" r="${ri}" fill="none" stroke="${shade(outer, -0.3)}" stroke-width="2" opacity="0.35"/>`);
  sc.add(`<path d="M${cx - r * 0.96},${cy + r * 0.1} A${r * 0.96},${r * 0.96} 0 0 1 ${cx + r * 0.1},${cy - r * 0.96}" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" opacity="0.55" filter="url(#blur2)"/>`);
  return ri;
}
// darkening ring at the inner bowl wall so the food sits "inside"
function bowlInnerShade(sc, cx, cy, ri) {
  sc.add(`<circle cx="${cx}" cy="${cy}" r="${ri}" fill="${sc.radial([[0.78, '#000', 0], [1, '#000', 0.22]], 'cx="0.47" cy="0.45" r="0.55"')}"/>`);
}
function napkin(sc, x, y, w, h, rot, color, stripe) {
  dropShadow(sc, `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" transform="rotate(${rot} ${x + w / 2} ${y + h / 2})" fill="#000"/>`, 6, 10, 0.18, 'blur10');
  const id = sc.id('nap');
  sc.def(`<filter id="${id}" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.6 0.05" numOctaves="2" seed="3"/><feColorMatrix type="matrix" values="0 0 0 0 0.2  0 0 0 0 0.2  0 0 0 0 0.2  0 0 0 -1 0.62"/></filter>`);
  let s = `<g transform="rotate(${rot} ${x + w / 2} ${y + h / 2})"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" fill="${color}"/>`;
  if (stripe) s += `<rect x="${x}" y="${y + h * 0.18}" width="${w}" height="10" fill="${stripe}" opacity="0.85"/><rect x="${x}" y="${y + h * 0.18 + 16}" width="${w}" height="4" fill="${stripe}" opacity="0.85"/>`;
  s += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" filter="url(#${id})" opacity="0.6"/>`;
  s += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" fill="${sc.linear([[0, '#fff', 0.25], [1, '#000', 0.08]], 0, 0, 1, 1)}"/></g>`;
  sc.add(s);
}
function fork(sc, x, y, len, rot, color = '#c9c6c0', k = 1.8) {
  const g = sc.linear([[0, shade(color, 0.5)], [0.5, color], [1, shade(color, -0.25)]], 0, 0, 1, 0);
  const L = len / k;
  const shape = `<path d="M-7,0 L-7,-46 M-2.4,0 L-2.4,-46 M2.4,0 L2.4,-46 M7,0 L7,-46" stroke-width="3.2" stroke-linecap="round"/><path d="M-9,-6 Q-9,18 -3,26 L-4.5,${L - 8} Q0,${L} 4.5,${L - 8} L3,26 Q9,18 9,-6 Z"/>`;
  dropShadow(sc, `<g transform="translate(${x},${y}) rotate(${rot}) scale(${k})" fill="#000" stroke="#000">${shape}</g>`, 8, 12, 0.28, 'blur4');
  sc.add(`<g transform="translate(${x},${y}) rotate(${rot}) scale(${k})" fill="${g}" stroke="${g}">${shape}<path d="M-1,30 L-1.5,${L - 14}" stroke="#fff" stroke-width="1.5" opacity="0.7"/></g>`);
}

// ---------- ingredients ----------
function leaf(sc, x, y, len, wid, rotDeg, color, { vein = true, curl = 0 } = {}) {
  const r = sc.r;
  const w = wid, l = len;
  const d = `M0,0 C${w * 0.9},${-l * 0.18} ${w * (1 + curl)},${-l * 0.72} 0,${-l} C${-w * (1 - curl)},${-l * 0.72} ${-w * 0.95},${-l * 0.2} 0,0Z`;
  const g = sc.linear([[0, shade(color, 0.22)], [0.55, color], [1, shade(color, -0.3)]], 0, 0, 1, 1);
  let s = `<g transform="translate(${f(x)},${f(y)}) rotate(${f(rotDeg)})">`;
  s += `<path d="${d}" transform="translate(3,4)" fill="#000" opacity="0.22" filter="url(#blur2)"/>`;
  s += `<path d="${d}" fill="${g}"/>`;
  if (vein) {
    s += `<path d="M0,-2 Q${w * 0.12},${-l * 0.5} 0,${-l * 0.92}" stroke="${shade(color, 0.35)}" stroke-width="${Math.max(1, wid * 0.08)}" fill="none" opacity="0.7"/>`;
    for (let i = 1; i <= 3; i++) {
      const t = i / 4.3;
      s += `<path d="M${w * 0.04},${-l * t} q${w * 0.45},${-l * 0.1} ${w * 0.62},${-l * 0.2}" stroke="${shade(color, 0.3)}" stroke-width="${Math.max(0.6, wid * 0.04)}" fill="none" opacity="0.45"/>`;
      s += `<path d="M${-w * 0.02},${-l * t} q${-w * 0.45},${-l * 0.1} ${-w * 0.62},${-l * 0.2}" stroke="${shade(color, 0.3)}" stroke-width="${Math.max(0.6, wid * 0.04)}" fill="none" opacity="0.45"/>`;
    }
  }
  s += `<path d="${d}" fill="${sc.radial([[0, '#fff', 0.35], [1, '#fff', 0]], 'cx="0.3" cy="0.3" r="0.6"')}"/>`;
  s += '</g>';
  sc.add(s);
}
function sprigDill(sc, x, y, len, rotDeg, color = '#5f8f3a') {
  const r = sc.r;
  let s = `<g transform="translate(${x},${y}) rotate(${rotDeg})" stroke-linecap="round" fill="none">`;
  const stem = `M0,0 Q${len * 0.08},${-len * 0.5} 0,${-len}`;
  s += `<path d="${stem}" stroke="#000" stroke-width="3" opacity="0.18" transform="translate(2,3)" filter="url(#blur1)"/>`;
  s += `<path d="${stem}" stroke="${shade(color, -0.1)}" stroke-width="2.4"/>`;
  for (let i = 0; i < 9; i++) {
    const t = 0.15 + (i / 9) * 0.85;
    const py = -len * t, px = len * 0.08 * Math.sin(t * Math.PI) * 0.9;
    for (const side of [-1, 1]) {
      const bl = len * 0.28 * (1 - t * 0.55);
      const ang = side * r.range(35, 60);
      const ex = px + Math.sin(rad(ang)) * bl, ey = py - Math.cos(rad(ang)) * bl;
      s += `<path d="M${f(px)},${f(py)} L${f(ex)},${f(ey)}" stroke="${color}" stroke-width="1.3"/>`;
      for (let k = 1; k <= 3; k++) {
        const qx = px + (ex - px) * (k / 3.4), qy = py + (ey - py) * (k / 3.4);
        for (const s2 of [-1, 1]) {
          const a2 = rad(ang + s2 * 40);
          const l2 = bl * 0.33;
          s += `<path d="M${f(qx)},${f(qy)} l${f(Math.sin(a2) * l2)},${f(-Math.cos(a2) * l2)}" stroke="${shade(color, r.range(-0.1, 0.2))}" stroke-width="1.1"/>`;
        }
      }
    }
  }
  s += '</g>';
  sc.add(s);
}
function herbFlecks(sc, cx, cy, rx, ry, n, color = '#4f8a2b', size = 5) {
  const r = sc.r;
  let s = '<g>';
  for (let i = 0; i < n; i++) {
    const a = r() * Math.PI * 2, d = Math.sqrt(r());
    const x = cx + Math.cos(a) * rx * d, y = cy + Math.sin(a) * ry * d;
    const sz = size * r.range(0.6, 1.4);
    const c = jitterColor(r, color, 0.25);
    s += `<path d="${blob(r, x, y, sz, sz * r.range(0.5, 0.9), 0.4, 6, r() * 6)}" fill="${c}"/>`;
  }
  sc.add(s + '</g>');
}
function pepper(sc, cx, cy, rx, ry, n, color = '#2b211a') {
  const r = sc.r;
  let s = '<g>';
  for (let i = 0; i < n; i++) {
    const a = r() * Math.PI * 2, d = Math.sqrt(r());
    s += `<circle cx="${f(cx + Math.cos(a) * rx * d)}" cy="${f(cy + Math.sin(a) * ry * d)}" r="${f(r.range(0.8, 2.2))}" fill="${color}" opacity="${f(r.range(0.6, 0.95))}"/>`;
  }
  sc.add(s + '</g>');
}
function lemonSlice(sc, x, y, rr, { half = false, rot = 0 } = {}) {
  const r = sc.r;
  let s = `<g transform="translate(${x},${y}) rotate(${rot})">`;
  const clip = half ? sc.id('lh') : null;
  if (half) sc.def(`<clipPath id="${clip}"><rect x="${-rr - 2}" y="${-rr - 2}" width="${2 * rr + 4}" height="${rr + 2}"/></clipPath>`);
  s += `<g ${half ? `clip-path="url(#${clip})"` : ''}>`;
  s += `<circle r="${rr}" transform="translate(4,5)" fill="#000" opacity="0.2" filter="url(#blur2)"/>`;
  s += `<circle r="${rr}" fill="#f2c230"/><circle r="${rr * 0.9}" fill="#fbf3d0"/><circle r="${rr * 0.82}" fill="#f6dd6c"/>`;
  const n = 9;
  for (let i = 0; i < n; i++) {
    const a = (i / n) * 360;
    s += `<path d="M0,0 L${f(Math.cos(rad(a)) * rr * 0.8)},${f(Math.sin(rad(a)) * rr * 0.8)}" stroke="#fdf6dc" stroke-width="${f(rr * 0.07)}"/>`;
  }
  for (let i = 0; i < 40; i++) {
    const a = r() * Math.PI * 2, d = r.range(0.15, 0.75) * rr;
    s += `<ellipse cx="${f(Math.cos(a) * d)}" cy="${f(Math.sin(a) * d)}" rx="${f(rr * 0.05)}" ry="${f(rr * 0.02)}" transform="rotate(${f((a * 180) / Math.PI)} ${f(Math.cos(a) * d)} ${f(Math.sin(a) * d)})" fill="#fff" opacity="0.55"/>`;
  }
  s += `<circle r="${rr * 0.1}" fill="#fbf3d0"/>`;
  s += `<circle r="${rr}" fill="${sc.radial([[0, '#fff', 0.3], [1, '#fff', 0]], 'cx="0.3" cy="0.3" r="0.7"')}"/>`;
  s += '</g></g>';
  sc.add(s);
}
function cherryTomatoHalf(sc, x, y, rr, rot = 0) {
  const r = sc.r;
  let s = `<g transform="translate(${x},${y}) rotate(${rot})">`;
  s += `<ellipse rx="${rr}" ry="${rr * 0.92}" transform="translate(3,4)" fill="#000" opacity="0.25" filter="url(#blur2)"/>`;
  s += `<ellipse rx="${rr}" ry="${rr * 0.92}" fill="#d7372a"/>`;
  s += `<ellipse rx="${rr * 0.86}" ry="${rr * 0.78}" fill="#ee6a4c"/>`;
  for (const [a, b] of [[-0.35, -0.2], [0.35, -0.2], [0, 0.38]]) {
    s += `<ellipse cx="${f(a * rr)}" cy="${f(b * rr)}" rx="${f(rr * 0.26)}" ry="${f(rr * 0.2)}" fill="#f6b64f" opacity="0.85"/>`;
    for (let k = 0; k < 3; k++) s += `<ellipse cx="${f(a * rr + r.range(-3, 3) * rr / 20)}" cy="${f(b * rr + r.range(-3, 3) * rr / 20)}" rx="${f(rr * 0.05)}" ry="${f(rr * 0.035)}" fill="#f9e7b5"/>`;
  }
  s += `<path d="M0,${-rr * 0.75} L0,${rr * 0.75} M${-rr * 0.7},0 L${rr * 0.7},0" stroke="#f08a6c" stroke-width="${rr * 0.08}" opacity="0.5"/>`;
  s += `<ellipse rx="${rr}" ry="${rr * 0.92}" fill="${sc.radial([[0, '#fff', 0.4], [0.6, '#fff', 0]], 'cx="0.3" cy="0.28" r="0.5"')}"/>`;
  sc.add(s + '</g>');
}
function berry(sc, x, y, rr, kind) {
  const r = sc.r;
  let s = `<g transform="translate(${x},${y})">`;
  s += `<circle r="${rr}" transform="translate(3,4)" fill="#000" opacity="0.3" filter="url(#blur2)"/>`;
  if (kind === 'blue') {
    s += `<circle r="${rr}" fill="${sc.radial([[0, '#5d6fa8'], [0.6, '#2f3a6b'], [1, '#1c2244']], 'cx="0.35" cy="0.32" r="0.75"')}"/>`;
    s += `<circle r="${rr}" fill="#c7d0ea" opacity="0.18"/>`;
    s += `<path d="${blob(r, rr * 0.15, rr * 0.1, rr * 0.28, rr * 0.28, 0.4, 5)}" fill="#1a1d33"/>`;
    s += `<ellipse cx="${-rr * 0.35}" cy="${-rr * 0.4}" rx="${rr * 0.25}" ry="${rr * 0.15}" fill="#fff" opacity="0.35" filter="url(#blur1)"/>`;
  } else {
    // raspberry: cluster of drupelets
    s += `<circle r="${rr}" fill="#b5223a"/>`;
    for (let i = 0; i < 16; i++) {
      const a = r() * Math.PI * 2, d = Math.sqrt(r()) * rr * 0.75;
      const px = Math.cos(a) * d, py = Math.sin(a) * d;
      s += `<circle cx="${f(px)}" cy="${f(py)}" r="${f(rr * 0.3)}" fill="${sc.radial([[0, '#f36a7c'], [0.7, '#cf2f48'], [1, '#8f1428']], 'cx="0.35" cy="0.3" r="0.7"')}"/>`;
    }
    s += `<circle r="${rr * 0.18}" fill="#7a1022" opacity="0.8"/>`;
  }
  sc.add(s + '</g>');
}

// spaghetti / linguine nest
function pastaNest(sc, cx, cy, R, { color = '#f1d48a', strands = 70, width = 8, coat = null, coatOp = 0.0, seedJ = 1 } = {}) {
  const r = sc.r;
  let s = '<g>';
  for (let i = 0; i < strands; i++) {
    const ccx = cx + r.gauss() * R * 0.32, ccy = cy + r.gauss() * R * 0.32;
    const rr0 = r.range(R * 0.12, R * 0.75);
    const a0 = r() * Math.PI * 2, sweep = r.range(0.6, 1.6) * Math.PI * (r() < 0.5 ? 1 : -1);
    const pts = [];
    const steps = 18;
    const wob = r.range(0.04, 0.12), ph = r() * 6;
    for (let k = 0; k <= steps; k++) {
      const t = k / steps, a = a0 + sweep * t;
      const rr = rr0 * (1 + wob * Math.sin(t * 7 + ph)) * (1 - 0.25 * t * r.range(0, 1));
      const px = ccx + Math.cos(a) * rr, py = ccy + Math.sin(a) * rr * 0.96;
      const dd = Math.hypot(px - cx, py - cy), lim = R * 0.98;
      pts.push(dd > lim ? [cx + (px - cx) * lim / dd, cy + (py - cy) * lim / dd] : [px, py]);
    }
    const d = smooth(pts);
    const c = jitterColor(r, color, 0.08);
    s += `<path d="${d}" stroke="#5a3a12" stroke-opacity="0.35" stroke-width="${width + 3}" fill="none" stroke-linecap="round"/>`;
    s += `<path d="${d}" stroke="${c}" stroke-width="${width}" fill="none" stroke-linecap="round"/>`;
    s += `<path d="${d}" stroke="#fff" stroke-opacity="0.45" stroke-width="${width * 0.28}" fill="none" stroke-linecap="round" transform="translate(-1.2,-1.6)"/>`;
    if (coat && r() < 0.85) s += `<path d="${d}" stroke="${coat}" stroke-opacity="${coatOp}" stroke-width="${width + 1}" fill="none" stroke-linecap="round" stroke-dasharray="${f(r.range(10, 40))} ${f(r.range(6, 30))}"/>`;
  }
  s += '</g>';
  sc.add(`<g filter="url(#organicFine)">${s}</g>`);
}
function moundShade(sc, cx, cy, R, op = 0.32) {
  sc.add(`<circle cx="${cx}" cy="${cy}" r="${R}" fill="${sc.radial([[0, '#fff', 0.28], [0.45, '#fff', 0], [0.75, '#000', 0], [1, '#000', op]], 'cx="0.38" cy="0.36" r="0.66"')}"/>`);
}

// penne
function penne(sc, x, y, rot, len, dia, color, end) {
  const r = sc.r;
  const L = len / 2, h = dia / 2, sk = dia * 0.55;
  const d = `M${-L + sk},${-h} L${L + sk},${-h} Q${L + sk + 3},0 ${L - sk},${h} L${-L - sk},${h} Q${-L - sk - 3},0 ${-L + sk},${-h}Z`;
  const g = sc.linear([[0, shade(color, 0.35)], [0.35, color], [1, shade(color, -0.35)]], 0, 0, 0, 1);
  let s = `<g transform="translate(${f(x)},${f(y)}) rotate(${f(rot)})">`;
  s += `<path d="${d}" transform="translate(3,4)" fill="#5a1a08" opacity="0.22" filter="url(#blur2)"/>`;
  s += `<path d="${d}" fill="${g}"/>`;
  for (let k = -2; k <= 2; k++) s += `<path d="M${-L + sk * (0.5 - k * 0.2)},${k * h * 0.35} L${L + sk * (0.5 - k * 0.2) - 4},${k * h * 0.35}" stroke="${shade(color, -0.3)}" stroke-width="1" opacity="0.35"/>`;
  s += `<ellipse cx="${f(L - 1)}" cy="0" rx="${f(sk * 0.55)}" ry="${f(h * 0.62)}" transform="rotate(14 ${f(L - 1)} 0)" fill="${shade(end, -0.15)}" opacity="0.75"/>`;
  s += `<path d="M${-L + sk},${-h + 2} L${L + sk - 4},${-h + 2}" stroke="#fff" stroke-width="2" opacity="0.5"/>`;
  sc.add(s + '</g>');
}
function grains(sc, cx, cy, rx, ry, n, color, size = [6, 3]) {
  const r = sc.r;
  let s = '<g>';
  for (let i = 0; i < n; i++) {
    const a = r() * Math.PI * 2, d = Math.sqrt(r());
    const x = cx + Math.cos(a) * rx * d, y = cy + Math.sin(a) * ry * d;
    const c = jitterColor(r, color, 0.08);
    const rot = r() * 180;
    s += `<ellipse cx="${f(x + 1)}" cy="${f(y + 1.5)}" rx="${size[0]}" ry="${size[1]}" transform="rotate(${f(rot)} ${f(x + 1)} ${f(y + 1.5)})" fill="#000" opacity="0.18"/>`;
    s += `<ellipse cx="${f(x)}" cy="${f(y)}" rx="${size[0]}" ry="${size[1]}" transform="rotate(${f(rot)} ${f(x)} ${f(y)})" fill="${c}"/>`;
    s += `<ellipse cx="${f(x - size[0] * 0.2)}" cy="${f(y - size[1] * 0.3)}" rx="${size[0] * 0.45}" ry="${size[1] * 0.35}" transform="rotate(${f(rot)} ${f(x)} ${f(y)})" fill="#fff" opacity="0.45"/>`;
  }
  sc.add(s + '</g>');
}
function shrimp(sc, x, y, s0, rot) {
  const R = 24 * s0;
  const segs = [];
  for (let i = 0; i < 6; i++) {
    const a = rad(205 - i * 44);
    segs.push({ x: Math.cos(a) * R, y: Math.sin(a) * R, rx: (20 - i * 2.2) * s0, ry: (15 - i * 1.6) * s0, rot: (205 - i * 44) + 90 });
  }
  const ta = rad(205 - 6 * 44 + 12);
  const tx = Math.cos(ta) * R * 1.05, ty = Math.sin(ta) * R * 1.05;
  let shadow = '', body = '';
  for (const g of segs) shadow += `<ellipse cx="${f(g.x)}" cy="${f(g.y)}" rx="${f(g.rx)}" ry="${f(g.ry)}" transform="rotate(${f(g.rot)} ${f(g.x)} ${f(g.y)})"/>`;
  const fill = sc.radial([[0, '#ffd9c2'], [0.55, '#f59a72'], [1, '#e0623f']], 'cx="0.45" cy="0.4" r="0.6"');
  const tail = `<path d="M${f(tx)},${f(ty)} l${f(-14 * s0)},${f(-20 * s0)} q${f(10 * s0)},${f(-4 * s0)} ${f(22 * s0)},${f(4 * s0)} z" fill="#e8613a"/><path d="M${f(tx)},${f(ty)} l${f(6 * s0)},${f(-24 * s0)} q${f(10 * s0)},${f(6 * s0)} ${f(12 * s0)},${f(18 * s0)} z" fill="#ef7a4f"/>`;
  for (let i = segs.length - 1; i >= 0; i--) {
    const g = segs[i];
    body += `<ellipse cx="${f(g.x)}" cy="${f(g.y)}" rx="${f(g.rx)}" ry="${f(g.ry)}" transform="rotate(${f(g.rot)} ${f(g.x)} ${f(g.y)})" fill="${fill}" stroke="#fde2d2" stroke-width="${f(1.6 * s0)}"/>`;
  }
  let s = `<g transform="translate(${f(x)},${f(y)}) rotate(${f(rot)})">`;
  s += `<g transform="translate(4,6)" fill="#2b0d02" opacity="0.32" filter="url(#blur2)">${shadow}</g>`;
  s += tail + body;
  s += `<path d="M${f(Math.cos(rad(200)) * R * 0.55)},${f(Math.sin(rad(200)) * R * 0.55)} A${f(R * 0.55)},${f(R * 0.55)} 0 0 1 ${f(Math.cos(rad(-10)) * R * 0.55)},${f(Math.sin(rad(-10)) * R * 0.55)}" stroke="#c94b2a" stroke-width="${f(2.2 * s0)}" fill="none" opacity="0.55"/>`;
  s += `<path d="M${f(Math.cos(rad(215)) * R * 1.35)},${f(Math.sin(rad(215)) * R * 1.35)} A${f(R * 1.35)},${f(R * 1.35)} 0 0 1 ${f(Math.cos(rad(290)) * R * 1.35)},${f(Math.sin(rad(290)) * R * 1.35)}" stroke="#fff" stroke-width="${f(3 * s0)}" fill="none" opacity="0.55" stroke-linecap="round" filter="url(#blur1)"/>`;
  sc.add(s + '</g>');
}
function sauceBase(sc, cx, cy, rx, ry, base, dark, light, seedRot = 0) {
  const r = sc.r;
  sc.add(`<g filter="url(#organic)"><path d="${blob(r, cx, cy, rx, ry, 0.1, 14, seedRot)}" fill="${sc.radial([[0, light], [0.6, base], [1, dark]], 'cx="0.42" cy="0.4" r="0.62"')}"/></g>`);
  let s = '<g filter="url(#blur4)">';
  for (let i = 0; i < 26; i++) {
    const a = r() * Math.PI * 2, d = Math.sqrt(r()) * 0.85;
    s += `<path d="${blob(r, cx + Math.cos(a) * rx * d, cy + Math.sin(a) * ry * d, r.range(10, 30), r.range(8, 22), 0.3, 7, r() * 3)}" fill="${r() < 0.5 ? dark : light}" opacity="${f(r.range(0.25, 0.6))}"/>`;
  }
  sc.add(s + '</g>');
}

// ---------- dishes ----------
const dishes = {};

dishes['lemon-herb-salmon'] = () => {
  const sc = new Scene(101);
  surfaceLinen(sc, '#d9dfe2');
  napkin(sc, 700, 420, 380, 380, -12, '#eef0ee', '#9fb3bd');
  fork(sc, 830, 120, 330, 18);
  lemonSlice(sc, 150, 610, 54, { half: true, rot: 200 });
  const cx = 470, cy = 380, R = 300;
  plate(sc, cx, cy, R);
  // asparagus bundle, laid diagonally under the fillet
  const r = sc.r;
  for (let i = 0; i < 8; i++) {
    const ox = 250 + i * 13 + r.range(-3, 3), oy = 262 + i * 15;
    const len = r.range(300, 330), rot = -24 + r.range(-3, 3);
    let s = `<g transform="translate(${f(ox)},${f(oy)}) rotate(${f(rot)})">`;
    s += `<rect x="0" y="-8" width="${f(len)}" height="17" rx="8" transform="translate(3,5)" fill="#000" opacity="0.25" filter="url(#blur2)"/>`;
    s += `<rect x="0" y="-8" width="${f(len)}" height="17" rx="8" fill="${sc.linear([[0, '#a9cf6a'], [0.5, '#6f9f37'], [1, '#3f6d22']], 0, 0, 0, 1)}"/>`;
    s += `<path d="M${f(len - 4)},-9 q26,9 0,18 q-15,-9 0,-18z" fill="#5b7f2c"/>`;
    for (let k = 1; k < 6; k++) s += `<path d="M${f(len - 26 - k * 32)},-5 l8,5 l-8,5" stroke="#4d7225" stroke-width="1.6" fill="none" opacity="0.6"/>`;
    s += `<path d="M6,-3 L${f(len - 10)},-3" stroke="#e6f5c8" stroke-width="2" opacity="0.6"/>`;
    for (let k = 0; k < 3; k++) s += `<rect x="${80 + k * 70}" y="-8" width="7" height="17" fill="#2d3a14" opacity="0.3" rx="2"/>`;
    sc.add(s + '</g>');
  }
  // roasted baby potatoes
  for (const [x, y, rr] of [[330, 520, 34], [395, 560, 30], [300, 455, 28], [455, 590, 27]]) {
    sc.add(`<circle cx="${x + 4}" cy="${y + 6}" r="${rr}" fill="#000" opacity="0.28" filter="url(#blur4)"/>`);
    sc.add(`<path d="${blob(r, x, y, rr, rr * 0.9, 0.1, 9)}" fill="${sc.radial([[0, '#f8dc8e'], [0.65, '#e3ae4f'], [1, '#b8752a']], 'cx="0.4" cy="0.38" r="0.7"')}"/>`);
    sc.add(`<path d="${blob(r, x + rr * 0.2, y + rr * 0.15, rr * 0.45, rr * 0.3, 0.3, 7)}" fill="#a8621f" opacity="0.45" filter="url(#blur2)"/>`);
  }
  // salmon fillet
  const fx = 585, fy = 405;
  const outline = `M-150,-70 C-90,-98 70,-104 150,-78 C182,-66 186,40 160,72 C110,104 -90,108 -150,84 C-182,62 -184,-50 -150,-70Z`;
  let s = `<g transform="translate(${fx},${fy}) rotate(-16) scale(1.1)">`;
  s += `<path d="${outline}" transform="translate(8,12)" fill="#3a1205" opacity="0.35" filter="url(#blur10)"/>`;
  s += `<path d="${outline}" fill="${sc.linear([[0, '#f6a37c'], [0.5, '#ec7b4c'], [1, '#d65a2c']], 0, 0, 0.3, 1)}"/>`;
  // seared crust patches
  s += `<g filter="url(#blur10)">`;
  for (let i = 0; i < 14; i++) s += `<path d="${blob(r, r.range(-130, 130), r.range(-70, 60), r.range(18, 40), r.range(12, 26), 0.3, 7)}" fill="${r.pick(['#b4481e', '#c45a2a', '#a33d16', '#d06a34'])}" opacity="${f(r.range(0.35, 0.7))}"/>`;
  s += `</g>`;
  // fat lines
  for (let i = 0; i < 8; i++) {
    const x0 = -130 + i * 37 + r.range(-6, 6);
    s += `<path d="M${f(x0)},-84 Q${f(x0 + r.range(26, 38))},${f(r.range(-20, 0))} ${f(x0 + r.range(-8, 2))},84" stroke="#ffe6d4" stroke-width="${f(r.range(3, 5.5))}" fill="none" opacity="${f(r.range(0.35, 0.6))}" filter="url(#blur1)"/>`;
  }
  s += `<path d="M-150,60 C-90,100 110,100 160,60 C150,90 110,104 -90,108 C-150,96 -168,80 -150,60Z" fill="#8f2f0c" opacity="0.35" filter="url(#blur4)"/>`;
  // glaze & butter sheen
  s += `<path d="${outline}" fill="${sc.radial([[0, '#fff', 0.55], [0.35, '#fff', 0.08], [1, '#fff', 0]], 'cx="0.35" cy="0.25" r="0.5"')}"/>`;
  s += `<path d="${outline}" fill="none" stroke="#9a3a12" stroke-width="5" opacity="0.4" filter="url(#blur2)"/>`;
  sc.add(`<g filter="url(#organic)">${s}</g></g>`);
  // glaze drips around
  lemonSlice(sc, 700, 330, 44, { rot: 10 });
  lemonSlice(sc, 645, 300, 38, { rot: 40 });
  sprigDill(sc, 500, 410, 120, 60);
  sprigDill(sc, 570, 390, 100, 105, '#6c9a40');
  herbFlecks(sc, 560, 360, 180, 100, 30, '#4a7d26', 3.5);
  herbFlecks(sc, 370, 530, 90, 70, 18, '#3f7a24', 3);
  pepper(sc, 560, 360, 190, 100, 60);
  sprigDill(sc, 110, 700, 150, 30);
  lighting(sc);
  return sc.svg();
};

dishes['creamy-tomato-pasta'] = () => {
  const sc = new Scene(202);
  surfaceLinen(sc, '#efe5d6');
  napkin(sc, -60, 470, 360, 330, 14, '#f7f1e8', '#d27b5a');
  fork(sc, 860, 140, 330, -16);
  leaf(sc, 860, 640, 70, 26, 200, '#3f7e2e');
  leaf(sc, 900, 610, 58, 22, 240, '#4b8a35');
  const cx = 490, cy = 375;
  const ri = bowl(sc, cx, cy, 300, { outer: '#7f97a8', inner: '#f6f3ee', rimW: 0.09 });
  bowlInnerShade(sc, cx, cy, ri);
  sauceBase(sc, cx + 5, cy + 5, 215, 205, '#e1693d', '#b8431f', '#f29462');
  const r = sc.r;
  for (let i = 0; i < 58; i++) {
    const a = r() * Math.PI * 2, d = Math.sqrt(r()) * 170;
    const x = cx + Math.cos(a) * d, y = cy + Math.sin(a) * d;
    penne(sc, x, y, r() * 180, r.range(62, 72), 22, jitterColor(r, '#ec7a45', 0.06), '#c84a20');
  }
  sc.add(`<g filter="url(#blur4)">${Array.from({ length: 30 }, () => { const a = r() * 6.28, d = Math.sqrt(r()) * 170; return `<path d="${blob(r, cx + Math.cos(a) * d, cy + Math.sin(a) * d, r.range(8, 22), r.range(6, 14), 0.3, 7)}" fill="#d9592c" opacity="0.6"/>`; }).join('')}</g>`);
  moundShade(sc, cx, cy, 225, 0.35);
  // cream swirl
  sc.add(`<path d="M${cx - 80},${cy - 20} C${cx - 40},${cy - 70} ${cx + 50},${cy - 60} ${cx + 70},${cy - 10}" stroke="#f8d8b8" stroke-width="10" fill="none" opacity="0.5" filter="url(#blur2)" stroke-linecap="round"/>`);
  // parmesan
  for (let i = 0; i < 22; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * 140;
    sc.add(`<path d="${blob(r, cx + Math.cos(a) * d, cy + Math.sin(a) * d, r.range(5, 11), r.range(3, 6), 0.35, 6, r() * 3)}" fill="#fbf0cc" opacity="0.95"/>`);
  }
  leaf(sc, cx - 20, cy - 10, 64, 26, 30, '#3d7d2c');
  leaf(sc, cx + 30, cy + 20, 56, 23, 150, '#468a34');
  leaf(sc, cx - 50, cy + 40, 46, 19, 250, '#3a7429');
  pepper(sc, cx, cy, 170, 170, 70);
  lighting(sc);
  return sc.svg();
};

dishes['basil-pesto-pasta'] = () => {
  const sc = new Scene(303);
  surfaceWood(sc, '#dcc19a');
  napkin(sc, 690, -40, 360, 300, 10, '#f3efe6', '#6f9a5a');
  fork(sc, 150, 120, 320, -24);
  const cx = 500, cy = 390;
  plate(sc, cx, cy, 300, { color: '#f4f2ee' });
  const r = sc.r;
  sc.add(`<g filter="url(#organic)"><path d="${blob(r, cx, cy, 200, 190, 0.08, 12)}" fill="#6d8a2a" opacity="0.6"/></g>`);
  pastaNest(sc, cx, cy, 200, { color: '#cfd47a', strands: 85, width: 8.5, coat: '#5e8a24', coatOp: 0.55 });
  moundShade(sc, cx, cy, 205, 0.4);
  // pesto specks
  herbFlecks(sc, cx, cy, 180, 175, 130, '#3f6e1c', 3.2);
  // pine nuts
  for (let i = 0; i < 18; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * 150;
    const x = cx + Math.cos(a) * d, y = cy + Math.sin(a) * d, rot = r() * 180;
    sc.add(`<g transform="translate(${f(x)},${f(y)}) rotate(${f(rot)})"><ellipse rx="9" ry="4.6" transform="translate(2,3)" fill="#000" opacity="0.25"/><ellipse rx="9" ry="4.6" fill="${sc.radial([[0, '#fff3d6'], [1, '#e4c287']])}"/></g>`);
  }
  cherryTomatoHalf(sc, cx + 70, cy - 40, 24, 20);
  cherryTomatoHalf(sc, cx - 60, cy + 60, 22, -30);
  cherryTomatoHalf(sc, cx + 20, cy + 95, 21, 70);
  leaf(sc, cx - 10, cy - 30, 70, 30, 20, '#2f7a2a');
  leaf(sc, cx + 30, cy - 50, 58, 25, 80, '#3a8b33');
  leaf(sc, cx - 40, cy - 10, 50, 22, -60, '#2c6f25');
  // parmesan shavings
  for (let i = 0; i < 9; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * 120;
    sc.add(`<path d="${blob(r, cx + Math.cos(a) * d, cy + Math.sin(a) * d, r.range(12, 20), r.range(5, 8), 0.3, 6, r() * 3)}" fill="#fbf1cf" opacity="0.92"/>`);
  }
  // basil on table
  leaf(sc, 860, 600, 80, 32, 210, '#2f7a2a');
  leaf(sc, 830, 650, 66, 28, 160, '#3a8b33');
  lighting(sc);
  return sc.svg();
};

dishes['garlic-shrimp-linguine'] = () => {
  const sc = new Scene(404);
  surfaceMarble(sc, '#eeece8');
  napkin(sc, -40, -60, 330, 300, -8, '#e9e4dc', null);
  fork(sc, 860, 430, 320, 22);
  lemonSlice(sc, 860, 150, 60, { half: true, rot: 160 });
  const cx = 480, cy = 385;
  const ri = bowl(sc, cx, cy, 300, { outer: '#f2efe9', inner: '#f8f6f2', rimW: 0.16 });
  bowlInnerShade(sc, cx, cy, ri);
  pastaNest(sc, cx, cy, 205, { color: '#efd38c', strands: 95, width: 9.5, coat: '#e7c06a', coatOp: 0.35 });
  moundShade(sc, cx, cy, 210, 0.35);
  const r = sc.r;
  const spots = [[-80, -70, 20], [70, -90, 70], [120, 10, 140], [40, 90, 200], [-90, 60, 260], [-120, -10, 320], [0, -10, 100]];
  for (const [dx, dy, rot] of spots) shrimp(sc, cx + dx, cy + dy, 1.05, rot);
  // garlic slivers
  for (let i = 0; i < 16; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * 160;
    sc.add(`<path d="${blob(r, cx + Math.cos(a) * d, cy + Math.sin(a) * d, r.range(6, 9), r.range(3, 5), 0.3, 6, r() * 3)}" fill="#f6e3b0" stroke="#c9a35a" stroke-width="1"/>`);
  }
  herbFlecks(sc, cx, cy, 185, 180, 120, '#3f7d22', 3.6);
  // chili flakes
  herbFlecks(sc, cx, cy, 175, 170, 40, '#c8321c', 2.2);
  pepper(sc, cx, cy, 180, 180, 40);
  leaf(sc, 210, 640, 60, 18, 120, '#4c8a2c', { vein: true });
  lighting(sc);
  return sc.svg();
};

dishes['baked-mac-and-cheese'] = () => {
  const sc = new Scene(505);
  surfaceWood(sc, '#d6b58a');
  napkin(sc, 720, 500, 340, 300, -10, '#f2ede4', '#c0533b');
  const r = sc.r;
  const x0 = 175, y0 = 120, w = 640, h = 500;
  // dish with handles
  dropShadow(sc, `<rect x="${x0 - 60}" y="${y0}" width="${w + 120}" height="${h}" rx="70" fill="#000"/>`, 18, 26, 0.38);
  sc.add(`<rect x="${x0 - 62}" y="${y0 + h / 2 - 70}" width="${w + 124}" height="140" rx="40" fill="${sc.linear([[0, '#f7f4ef'], [1, '#d9d4cc']])}"/>`);
  sc.add(`<rect x="${x0}" y="${y0}" width="${w}" height="${h}" rx="62" fill="${sc.linear([[0, '#fdfbf7'], [1, '#e2ddd5']], 0, 0, 1, 1)}"/>`);
  sc.add(`<rect x="${x0 + 26}" y="${y0 + 26}" width="${w - 52}" height="${h - 52}" rx="44" fill="#c9862f"/>`);
  // crust
  const cx0 = x0 + 26, cy0 = y0 + 26, cw = w - 52, ch = h - 52;
  const clip = sc.id('cr');
  sc.def(`<clipPath id="${clip}"><rect x="${cx0}" y="${cy0}" width="${cw}" height="${ch}" rx="44"/></clipPath>`);
  let s = `<g clip-path="url(#${clip})">`;
  s += `<rect x="${cx0}" y="${cy0}" width="${cw}" height="${ch}" fill="${sc.radial([[0, '#f3c565'], [0.7, '#e4a640'], [1, '#b8702a']], 'cx="0.45" cy="0.42" r="0.65"')}"/>`;
  // elbow macaroni peeking
  for (let i = 0; i < 120; i++) {
    const x = cx0 + r() * cw, y = cy0 + r() * ch, rot = r() * 360;
    const c = jitterColor(r, '#f4c766', 0.1);
    s += `<g transform="translate(${f(x)},${f(y)}) rotate(${f(rot)})"><path d="M-14,4 A16,16 0 0 1 14,4" stroke="#7a4512" stroke-opacity="0.4" stroke-width="15" fill="none" stroke-linecap="round"/><path d="M-14,4 A16,16 0 0 1 14,4" stroke="${c}" stroke-width="12" fill="none" stroke-linecap="round"/><path d="M-11,1 A13,13 0 0 1 11,1" stroke="#fff" stroke-opacity="0.45" stroke-width="2.5" fill="none"/></g>`;
  }
  // browned spots & breadcrumbs
  s += `<g filter="url(#blur4)">`;
  for (let i = 0; i < 90; i++) s += `<path d="${blob(r, cx0 + r() * cw, cy0 + r() * ch, r.range(8, 22), r.range(6, 16), 0.35, 7, r() * 3)}" fill="${r.pick(['#c98a3a', '#b5752a', '#d89a45', '#a8661f', '#8f5418'])}" opacity="${f(r.range(0.35, 0.65))}"/>`;
  s += `</g>`;
  for (let i = 0; i < 500; i++) s += `<circle cx="${f(cx0 + r() * cw)}" cy="${f(cy0 + r() * ch)}" r="${f(r.range(1.2, 3.4))}" fill="${r.pick(['#e9b866', '#c98a3a', '#f7d48a', '#9c5a1d'])}" opacity="0.85"/>`;
  s += `<rect x="${cx0}" y="${cy0}" width="${cw}" height="${ch}" fill="${sc.radial([[0, '#fff', 0.25], [0.5, '#fff', 0], [1, '#000', 0.25]], 'cx="0.35" cy="0.3" r="0.8"')}"/>`;
  s += `</g>`;
  sc.add(`<g filter="url(#organicFine)">${s}</g>`);
  sc.add(`<rect x="${cx0}" y="${cy0}" width="${cw}" height="${ch}" rx="44" fill="none" stroke="#6e3c10" stroke-width="6" opacity="0.35" filter="url(#blur2)"/>`);
  herbFlecks(sc, x0 + w / 2, y0 + h / 2, 260, 190, 90, '#3f6f22', 3);
  lighting(sc);
  return sc.svg();
};

dishes['shakshuka'] = () => {
  const sc = new Scene(606);
  surfaceStone(sc, '#d6d0c7');
  const r = sc.r;
  // bread
  for (const [x, y, rot] of [[830, 560, -20], [890, 470, 10]]) {
    const d = blob(r, 0, 0, 95, 60, 0.08, 10);
    sc.add(`<g transform="translate(${x},${y}) rotate(${rot})"><path d="${d}" transform="translate(6,9)" fill="#000" opacity="0.28" filter="url(#blur10)"/><path d="${d}" fill="#a5642a"/><path d="${blob(r, 0, 0, 82, 48, 0.08, 10)}" fill="${sc.radial([[0, '#f3dcae'], [1, '#e2bd7d']])}"/>${Array.from({ length: 40 }, () => `<ellipse cx="${f(r.range(-70, 70))}" cy="${f(r.range(-38, 38))}" rx="${f(r.range(2, 5))}" ry="${f(r.range(1.5, 3.5))}" fill="#c99a55" opacity="0.6"/>`).join('')}</g>`);
  }
  const cx = 440, cy = 360, R = 290;
  // pan handle
  dropShadow(sc, `<rect x="${cx - 35}" y="${cy - R - 230}" width="70" height="270" rx="30" transform="rotate(42 ${cx} ${cy})" fill="#000"/>`, 14, 20, 0.35, 'blur10');
  sc.add(`<rect x="${cx - 35}" y="${cy - R - 230}" width="70" height="270" rx="30" transform="rotate(42 ${cx} ${cy})" fill="${sc.linear([[0, '#4a4a4a'], [0.5, '#2a2a2a'], [1, '#161616']], 0, 0, 1, 0)}"/>`);
  dropShadow(sc, `<circle cx="${cx}" cy="${cy}" r="${R}" fill="#000"/>`, 18, 26, 0.45);
  sc.add(`<circle cx="${cx}" cy="${cy}" r="${R}" fill="${sc.radial([[0, '#3a3a3a'], [0.9, '#262626'], [1, '#121212']], 'cx="0.4" cy="0.4" r="0.6"')}"/>`);
  sc.add(`<circle cx="${cx}" cy="${cy}" r="${R - 26}" fill="#1b1b1b"/>`);
  sc.add(`<path d="M${cx - R * 0.95},${cy} A${R * 0.95},${R * 0.95} 0 0 1 ${cx},${cy - R * 0.95}" stroke="#8a8a8a" stroke-width="4" fill="none" opacity="0.6" filter="url(#blur2)"/>`);
  sauceBase(sc, cx, cy, R - 34, R - 36, '#c2361f', '#8f1f10', '#e0583a');
  // chunky tomato/pepper bits
  let s = '<g>';
  for (let i = 0; i < 90; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * (R - 50);
    s += `<path d="${blob(r, cx + Math.cos(a) * d, cy + Math.sin(a) * d, r.range(5, 14), r.range(4, 10), 0.4, 6, r() * 3)}" fill="${r.pick(['#e86a45', '#a8240f', '#d9472a', '#f08a5d'])}" opacity="${f(r.range(0.5, 0.9))}"/>`;
  }
  sc.add(`<g filter="url(#blur1)">${s}</g></g>`);
  // eggs
  for (const [dx, dy, sz] of [[-95, -80, 1], [100, -60, 0.95], [-70, 95, 0.92], [95, 110, 1.02]]) {
    const ex = cx + dx, ey = cy + dy;
    const wd = blob(r, ex, ey, 72 * sz, 64 * sz, 0.18, 11, r() * 3);
    sc.add(`<path d="${wd}" transform="translate(3,5)" fill="#5a1205" opacity="0.4" filter="url(#blur4)"/>`);
    sc.add(`<g filter="url(#organicFine)"><path d="${wd}" fill="${sc.radial([[0, '#ffffff'], [0.7, '#f7f2ea'], [1, '#e9dfd2']])}"/></g>`);
    const yx = ex + r.range(-8, 8), yy = ey + r.range(-8, 8);
    sc.add(`<circle cx="${f(yx + 2)}" cy="${f(yy + 4)}" r="${31 * sz}" fill="#8a5a10" opacity="0.35" filter="url(#blur2)"/>`);
    sc.add(`<circle cx="${f(yx)}" cy="${f(yy)}" r="${30 * sz}" fill="${sc.radial([[0, '#ffd36a'], [0.6, '#f7a823'], [1, '#e28a10']], 'cx="0.4" cy="0.38" r="0.65"')}"/>`);
    sc.add(`<ellipse cx="${f(yx - 9)}" cy="${f(yy - 11)}" rx="10" ry="6" transform="rotate(-30 ${f(yx - 9)} ${f(yy - 11)})" fill="#fff" opacity="0.7" filter="url(#blur1)"/>`);
  }
  // feta crumbles
  for (let i = 0; i < 22; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * 220;
    sc.add(`<path d="${blob(r, cx + Math.cos(a) * d, cy + Math.sin(a) * d, r.range(6, 11), r.range(5, 9), 0.4, 6, r() * 3)}" fill="#fbfaf5" stroke="#d9d2c3" stroke-width="1"/>`);
  }
  herbFlecks(sc, cx, cy, 230, 230, 120, '#3e7b25', 4);
  pepper(sc, cx, cy, 230, 230, 60);
  leaf(sc, 140, 640, 54, 22, 70, '#3e7b25');
  leaf(sc, 180, 680, 46, 19, 120, '#4a8a2f');
  lighting(sc);
  return sc.svg();
};

dishes['green-buddha-bowl'] = () => {
  const sc = new Scene(707);
  surfaceLinen(sc, '#dfe5d8');
  napkin(sc, 720, -60, 330, 320, 12, '#f4f2ea', '#b7c79c');
  leaf(sc, 860, 640, 60, 26, 210, '#4f8d33');
  const r = sc.r;
  const cx = 470, cy = 380;
  const ri = bowl(sc, cx, cy, 300, { outer: '#e9dfcf', inner: '#f7f3ec', rimW: 0.08 });
  bowlInnerShade(sc, cx, cy, ri);
  const clip = sc.id('bb');
  const RF = ri - 16;
  sc.def(`<clipPath id="${clip}"><circle cx="${cx}" cy="${cy}" r="${RF}"/></clipPath>`);
  // where does each topping sit (angle in degrees, distance from centre)
  const at = (deg, d) => [cx + Math.cos(rad(deg)) * d, cy + Math.sin(rad(deg)) * d];
  const inCluster = (deg, d, rx, ry) => {
    const [x0, y0] = at(deg, d);
    const a = r() * Math.PI * 2, k = Math.sqrt(r());
    return [x0 + Math.cos(a) * rx * k, y0 + Math.sin(a) * ry * k];
  };
  // base: quinoa everywhere
  let s = `<g clip-path="url(#${clip})"><circle cx="${cx}" cy="${cy}" r="${RF}" fill="#e3cf9e"/>`;
  for (let i = 0; i < 1500; i++) {
    const a = r() * Math.PI * 2, d = Math.sqrt(r()) * RF;
    s += `<circle cx="${f(cx + Math.cos(a) * d)}" cy="${f(cy + Math.sin(a) * d)}" r="${f(r.range(2.6, 3.6))}" fill="${r.pick(['#f1e2bd', '#e2cc96', '#d9bd84', '#f6ead0', '#f1e2bd', '#b8574a'])}" stroke="#a88a52" stroke-width="0.6" stroke-opacity="0.5"/>`;
  }
  s += '</g>';
  sc.add(s);
  // greens (top right)
  for (let i = 0; i < 34; i++) {
    const [x, y] = inCluster(-45, RF * 0.6, 95, 85);
    leaf(sc, x, y, r.range(42, 62), r.range(18, 27), r() * 360, r.pick(['#4f8d33', '#3f7a29', '#5f9c3e', '#6aa84a']), { vein: true });
  }
  // chickpeas (right/bottom-right)
  s = `<g clip-path="url(#${clip})">`;
  for (let i = 0; i < 46; i++) {
    const [x, y] = inCluster(35, RF * 0.6, 80, 75);
    s += `<circle cx="${f(x + 2)}" cy="${f(y + 3)}" r="15" fill="#5a3a10" opacity="0.3" filter="url(#blur2)"/><circle cx="${f(x)}" cy="${f(y)}" r="${f(r.range(13, 16))}" fill="${sc.radial([[0, '#f5dca2'], [0.7, '#dcae5c'], [1, '#b98336']], 'cx="0.38" cy="0.35" r="0.7"')}"/><path d="M${f(x - 6)},${f(y + 2)} q6,6 12,0" stroke="#a87533" stroke-width="1.4" fill="none" opacity="0.6"/>`;
  }
  sc.add(s + '</g>');
  // red cabbage + carrot (bottom)
  s = `<g clip-path="url(#${clip})">`;
  for (let i = 0; i < 110; i++) {
    const [x, y] = inCluster(105, RF * 0.62, 85, 70);
    const rot = r() * 180;
    const c = i % 3 === 0 ? r.pick(['#f08a2c', '#e9761e', '#f7a24a']) : r.pick(['#7b2f6b', '#9b4a8a', '#5a1f4f', '#a65a96']);
    s += `<rect x="${f(x)}" y="${f(y)}" width="${f(r.range(26, 44))}" height="4.5" rx="2.2" transform="rotate(${f(rot)} ${f(x)} ${f(y)})" fill="${c}" stroke="#2a0d24" stroke-opacity="0.25" stroke-width="0.8"/>`;
  }
  sc.add(s + '</g>');
  // edamame (left)
  s = `<g clip-path="url(#${clip})">`;
  for (let i = 0; i < 60; i++) {
    const [x, y] = inCluster(170, RF * 0.6, 75, 85);
    s += `<ellipse cx="${f(x + 2)}" cy="${f(y + 3)}" rx="13" ry="10" fill="#203a0a" opacity="0.28"/><ellipse cx="${f(x)}" cy="${f(y)}" rx="${f(r.range(11, 13))}" ry="${f(r.range(9, 10.5))}" transform="rotate(${f(r() * 180)} ${f(x)} ${f(y)})" fill="${sc.radial([[0, '#c5e98a'], [0.7, '#86c04a'], [1, '#5e9a2c']], 'cx="0.38" cy="0.35" r="0.7"')}"/>`;
  }
  sc.add(s + '</g>');
  // avocado fan (top-left, quinoa shows in between)
  const [ax, ay] = at(-130, RF * 0.15);
  for (let i = 0; i < 6; i++) {
    const rot = -150 + i * 12;
    const d = 'M0,0 C30,-20 120,-26 175,-8 C185,-2 182,10 170,12 C120,22 40,24 0,10Z';
    sc.add(`<g transform="translate(${f(ax)},${f(ay)}) rotate(${rot})"><path d="${d}" transform="translate(3,5)" fill="#000" opacity="0.3" filter="url(#blur2)"/><path d="${d}" fill="${sc.linear([[0, '#e2ec9a'], [0.6, '#b9d25e'], [0.9, '#6f9a2a'], [1, '#2f4a14']], 0, 0, 0, 1)}"/><path d="M8,2 C40,-12 120,-18 168,-4" stroke="#fffbe0" stroke-width="2.5" opacity="0.6" fill="none"/></g>`);
  }
  for (const [deg, d, rr, rot] of [[10, 40, 22, 10], [60, 60, 20, 60], [-10, 95, 21, -30], [140, 40, 20, 100]]) {
    const [x, y] = at(deg, d);
    cherryTomatoHalf(sc, x, y, rr, rot);
  }
  // tahini drizzle + sesame
  sc.add(`<path d="M${cx - 150},${cy + 30} C${cx - 60},${cy - 40} ${cx + 40},${cy + 60} ${cx + 150},${cy - 20}" stroke="#f3e2b6" stroke-width="7" fill="none" opacity="0.85" stroke-linecap="round" filter="url(#organicFine)"/>`);
  s = `<g clip-path="url(#${clip})">`;
  for (let i = 0; i < 120; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * (RF - 20);
    const x = cx + Math.cos(a) * d, y = cy + Math.sin(a) * d;
    s += `<ellipse cx="${f(x)}" cy="${f(y)}" rx="3" ry="1.7" transform="rotate(${f(r() * 180)} ${f(x)} ${f(y)})" fill="${r() < 0.7 ? '#fbf3dc' : '#2a2520'}"/>`;
  }
  sc.add(s + '</g>');
  moundShade(sc, cx, cy, RF, 0.22);
  lighting(sc);
  return sc.svg();
};

dishes['mushroom-risotto'] = () => {
  const sc = new Scene(808);
  surfaceLinen(sc, '#e8dfd0');
  napkin(sc, -50, 450, 330, 360, -10, '#efe9df', '#8c7a63');
  fork(sc, 870, 160, 320, -14);
  const cx = 500, cy = 380;
  plate(sc, cx, cy, 300, { color: '#f3f0ea', rim: 0.72 });
  const r = sc.r;
  sc.add(`<g filter="url(#organic)"><path d="${blob(r, cx, cy, 195, 185, 0.07, 12)}" fill="${sc.radial([[0, '#f4e9cf'], [0.8, '#e6d4ab'], [1, '#cdb680']])}"/></g>`);
  grains(sc, cx, cy, 185, 175, 900, '#f2e6c8', [6.5, 3.2]);
  moundShade(sc, cx, cy, 195, 0.3);
  // mushrooms (sliced, top view)
  for (let i = 0; i < 12; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * 140;
    const x = cx + Math.cos(a) * d, y = cy + Math.sin(a) * d, rot = r() * 360;
    const sz = r.range(0.85, 1.15);
    const cap = `M${-36 * sz},0 C${-36 * sz},${-34 * sz} ${36 * sz},${-34 * sz} ${36 * sz},0 L${12 * sz},0 L${10 * sz},${30 * sz} C${4 * sz},${34 * sz} ${-4 * sz},${34 * sz} ${-10 * sz},${30 * sz} L${-12 * sz},0Z`;
    let s = `<g transform="translate(${f(x)},${f(y)}) rotate(${f(rot)})">`;
    s += `<path d="${cap}" transform="translate(3,5)" fill="#2b1a0c" opacity="0.35" filter="url(#blur2)"/>`;
    s += `<path d="${cap}" fill="#e9d6b4"/>`;
    s += `<path d="M${-36 * sz},0 C${-36 * sz},${-34 * sz} ${36 * sz},${-34 * sz} ${36 * sz},0 C${24 * sz},${-16 * sz} ${-24 * sz},${-16 * sz} ${-36 * sz},0Z" fill="${sc.linear([[0, '#8a5a32'], [1, '#5e3a1c']])}"/>`;
    s += `<path d="M${-8 * sz},${-6 * sz} L${-6 * sz},${26 * sz} M${6 * sz},${-6 * sz} L${5 * sz},${26 * sz}" stroke="#cdb48c" stroke-width="1.4"/>`;
    s += `<path d="M${-30 * sz},${-6 * sz} C${-20 * sz},${-12 * sz} ${20 * sz},${-12 * sz} ${30 * sz},${-6 * sz}" stroke="#d8c09a" stroke-width="1.5" fill="none" opacity="0.6"/>`;
    sc.add(s + '</g>');
  }
  // parmesan shavings
  for (let i = 0; i < 8; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * 110;
    sc.add(`<path d="${blob(r, cx + Math.cos(a) * d, cy + Math.sin(a) * d, r.range(14, 22), r.range(5, 9), 0.25, 6, r() * 3)}" fill="#fbf2d4" stroke="#e2cf9c" stroke-width="1"/>`);
  }
  herbFlecks(sc, cx, cy, 170, 165, 110, '#3f7a24', 3.6);
  pepper(sc, cx, cy, 170, 165, 80);
  lighting(sc);
  return sc.svg();
};

dishes['berry-pancakes'] = () => {
  const sc = new Scene(909);
  surfaceLinen(sc, '#f1e4dc');
  napkin(sc, 700, 470, 360, 330, -14, '#fbf7f2', '#e2a3a6');
  fork(sc, 140, 160, 320, -20);
  const cx = 490, cy = 375;
  plate(sc, cx, cy, 300, { color: '#f8f6f2' });
  const r = sc.r;
  // stack edges visible as offset rings
  for (let k = 3; k >= 1; k--) {
    const ox = k * 6, oy = k * 8;
    sc.add(`<path d="${blob(r, cx + ox, cy + oy, 205, 198, 0.03, 14)}" fill="${mix('#c47f32', '#8f5520', k / 4)}" filter="url(#blur1)"/>`);
  }
  const top = blob(r, cx, cy, 205, 198, 0.03, 14);
  sc.add(`<path d="${top}" fill="${sc.radial([[0, '#b8661f'], [0.55, '#cf8a3a'], [0.85, '#e7b467'], [1, '#f2cf8c']], 'cx="0.5" cy="0.5" r="0.52"')}"/>`);
  sc.add(`<g opacity="0.28"><path d="${top}" fill="#7b3d0c" filter="url(#mottle)"/></g>`);
  // mottled browning spots
  let s = '<g filter="url(#blur2)">';
  for (let i = 0; i < 80; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * 170;
    s += `<circle cx="${f(cx + Math.cos(a) * d)}" cy="${f(cy + Math.sin(a) * d)}" r="${f(r.range(2, 7))}" fill="${r.pick(['#8e4a12', '#e7b467', '#a85a1a'])}" opacity="0.6"/>`;
  }
  sc.add(s + '</g>');
  // syrup
  sc.add(`<g filter="url(#organic)"><path d="${blob(r, cx - 10, cy - 5, 120, 105, 0.25, 10)}" fill="#9a4a0c" opacity="0.55"/><path d="M${cx + 90},${cy - 30} q60,40 90,140 q6,20 -10,22 q-14,-6 -10,-30 q-20,-80 -80,-120z" fill="#9a4a0c" opacity="0.5"/></g>`);
  sc.add(`<path d="${blob(r, cx - 40, cy - 40, 60, 30, 0.3, 8)}" fill="#fff" opacity="0.25" filter="url(#blur4)"/>`);
  // butter
  sc.add(`<g transform="translate(${cx - 10},${cy - 15}) rotate(14)"><rect x="-38" y="-30" width="76" height="60" rx="10" transform="translate(4,6)" fill="#6a3a08" opacity="0.4" filter="url(#blur2)"/><rect x="-38" y="-30" width="76" height="60" rx="10" fill="${sc.linear([[0, '#fff6cf'], [1, '#f6dc86']], 0, 0, 1, 1)}"/><rect x="-30" y="-24" width="40" height="8" rx="4" fill="#fff" opacity="0.7"/></g>`);
  // berries
  const pts = [[-110, -70], [-130, 20], [-80, 110], [20, 140], [120, 100], [150, 10], [100, -110], [-20, -140], [60, -40], [-60, 50]];
  pts.forEach(([dx, dy], i) => berry(sc, cx + dx, cy + dy, i % 3 === 0 ? 22 : 16, i % 3 === 0 ? 'rasp' : 'blue'));
  for (const [dx, dy] of [[-160, -150], [180, -170], [-200, 190]]) berry(sc, cx + dx, cy + dy, 17, 'blue');
  leaf(sc, cx + 40, cy + 20, 44, 18, -40, '#4c9a3c');
  leaf(sc, cx + 50, cy + 30, 38, 15, 20, '#5aa846');
  // powdered sugar
  let p = '<g>';
  for (let i = 0; i < 260; i++) {
    const a = r() * 6.28, d = Math.sqrt(r()) * 190;
    p += `<circle cx="${f(cx + Math.cos(a) * d)}" cy="${f(cy + Math.sin(a) * d)}" r="${f(r.range(0.8, 2))}" fill="#fff" opacity="${f(r.range(0.5, 0.95))}"/>`;
  }
  sc.add(p + '</g>');
  lighting(sc);
  return sc.svg();
};

const only = process.argv.slice(2);
for (const [name, fn] of Object.entries(dishes)) {
  if (only.length && !only.includes(name)) continue;
  fs.writeFileSync(path.join(OUT, `${name}.svg`), fn());
  console.log('wrote', name);
}
