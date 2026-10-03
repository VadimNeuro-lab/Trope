// Renders every screen of the three apps to PNG.
//   node render.mjs                 -> 585x1266 (390x844 viewport at 1.5x)
//   node render.mjs --scale 1       -> 390x844 fallback size
//   node render.mjs --only recipes  -> one app (or e.g. --only recipes/home)
// Output: output/<set>/<variant>/<nn_screen>.png
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const ROOT = path.dirname(fileURLToPath(import.meta.url));

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const scale = Number(opt('--scale', '1.5'));
const only = opt('--only', '');
const outRoot = path.join(ROOT, opt('--out', scale === 1.5 ? 'output' : `output_${Math.round(390 * scale)}x${Math.round(844 * scale)}`));

const APPS = [
  { set: 'A_recipes', dir: 'recipes', screens: ['home', 'search', 'recipe', 'saved', 'profile'] },
  { set: 'B_fitness', dir: 'fitness', screens: ['dashboard', 'workouts', 'log', 'progress', 'profile'] },
  { set: 'C_clinic', dir: 'clinic', screens: ['home', 'specialty', 'doctor', 'datetime', 'confirm'], extras: ['confirmed'] },
];
const VARIANTS = ['improved', 'weak'];

// Flags anything that leaves the 390x844 frame or has clipped text.
function audit() {
  const issues = [];
  const W = 390, H = 844;
  for (const el of document.querySelectorAll('.screen *')) {
    if (el.closest('[data-bleed]') || el.closest('svg')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const name = el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ').join('.') : '');
    if (r.left < -0.5 || r.right > W + 0.5 || r.top < -0.5 || r.bottom > H + 0.5) issues.push(`out of frame: ${name} [${Math.round(r.left)},${Math.round(r.top)},${Math.round(r.right)},${Math.round(r.bottom)}]`);
    const cs = getComputedStyle(el);
    if (el.childElementCount === 0 && el.textContent.trim() && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 2) && cs.overflow !== 'visible') issues.push(`clipped text: ${name} "${el.textContent.trim().slice(0, 30)}"`);
  }
  // elements overlapping the bottom tab bar / bottom action bar
  const bar = document.querySelector('.tabbar, .bottom-bar');
  if (bar) {
    const top = bar.getBoundingClientRect().top;
    for (const el of document.querySelectorAll('.content > *')) {
      const r = el.getBoundingClientRect();
      if (r.bottom > top + 0.5) issues.push(`under bottom bar: ${el.className} bottom=${Math.round(r.bottom)} bar=${Math.round(top)}`);
    }
  }
  return issues;
}

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: scale });
const page = await ctx.newPage();
let count = 0, problems = 0;
for (const app of APPS) {
  for (const variant of VARIANTS) {
    const list = app.screens.map((s, i) => ({ s, file: `${String(i + 1).padStart(2, '0')}_${s}.png`, dir: variant }));
    if (variant === 'improved') for (const s of app.extras || []) list.push({ s, file: `${String(app.screens.length).padStart(2, '0')}b_${s}.png`, dir: 'extras' });
    for (const { s, file, dir } of list) {
      if (only && !(only === app.dir || only === `${app.dir}/${s}`)) continue;
      const url = pathToFileURL(path.join(ROOT, app.dir, 'index.html')).href + `?screen=${s}&variant=${variant}`;
      await page.goto(url);
      await page.waitForSelector('body[data-ready="1"]');
      await page.waitForTimeout(150);
      const issues = await page.evaluate(audit);
      const out = path.join(outRoot, app.set, dir, file);
      fs.mkdirSync(path.dirname(out), { recursive: true });
      await page.screenshot({ path: out, animations: 'disabled', caret: 'hide' });
      count++;
      if (issues.length) { problems++; console.log(`! ${app.set}/${dir}/${file}\n    ${issues.slice(0, 8).join('\n    ')}`); }
      else console.log(`  ${app.set}/${dir}/${file}`);
    }
  }
}
await browser.close();
console.log(`\n${count} screens rendered at ${Math.round(390 * scale)}x${Math.round(844 * scale)} -> ${path.relative(process.cwd(), outRoot)}${problems ? `, ${problems} with layout warnings` : ''}`);
