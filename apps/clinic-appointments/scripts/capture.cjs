// Captures the booking paths as phone screenshots, straight from the browser.
//
//   variant-1  DoctorList → TimeSlot → Review → Confirmation
//   variant-2  DoctorList → Confirmation   (Book next available)
//
// Each variant runs in a freshly launched browser with an empty profile. A
// screen that leads on is captured just before the control that leaves it is
// tapped; Confirmation is captured once its entrance animation has finished.
// The PNGs are written as the browser returns them, viewport only, and the
// script will not overwrite existing files unless given --force.
//
// Usage: npm run screenshots [-- --out <dir>] [-- --force]
'use strict';

const fs = require('fs');
const path = require('path');
const { PHONE, openApp, waitForScreen } = require('./harness.cjs');

const args = process.argv.slice(2);
const OUT = path.resolve(args.includes('--out') ? args[args.indexOf('--out') + 1] : path.join(__dirname, '..', 'screenshots'));
const FORCE = args.includes('--force');

const SPECIALTY = 'cardiology';
const DOCTOR = 'elena-park';
const SLOT = '2026-10-02T11:00'; // Variant 1 picks 11:00 AM today

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

// Fails unless every selector is fully inside the viewport and not under the
// fixed bottom bar (controls inside the bar itself are checked against the
// whole viewport).
async function assertVisible(page, selectors) {
  const problems = await page.evaluate((sels) => {
    const vh = window.innerHeight;
    const vw = window.innerWidth;
    const dock = document.getElementById('dock');
    const dockTop = dock.hidden ? vh : dock.getBoundingClientRect().top;
    const out = [];
    for (const sel of sels) {
      const el = document.querySelector(sel);
      if (!el) {
        out.push(`${sel} is missing`);
        continue;
      }
      const r = el.getBoundingClientRect();
      const bottom = dock.contains(el) ? vh : dockTop;
      if (r.top < 0 || r.left < 0 || r.right > vw || r.bottom > bottom) out.push(`${sel} is not fully visible`);
    }
    return out;
  }, selectors);
  assert(problems.length === 0, problems.join('; '));
}

async function shoot(page, variantDir, name, shots) {
  const file = path.join(variantDir, name);
  await page.screenshot({ path: file, type: 'png', fullPage: false, caret: 'hide', scale: 'device' });
  shots.push(path.relative(OUT, file));
}

async function startBooking(page) {
  await page.tap(`[data-action="specialty"][data-id="${SPECIALTY}"]`);
  await page.tap(`.doctor-card[data-id="${DOCTOR}"]`);
  await page.waitForSelector('.selbar');
  await waitForScreen(page, 'doctors');
  assert((await page.getAttribute(`.doctor-card[data-id="${DOCTOR}"]`, 'aria-checked')) === 'true', 'doctor is not selected');
}

async function runVariant(name, steps) {
  const dir = path.join(OUT, name);
  fs.mkdirSync(dir, { recursive: true });
  const app = await openApp();
  const { page } = app;
  const visited = ['#/doctors'];
  page.on('framenavigated', (f) => {
    if (f === page.mainFrame()) visited.push(new URL(f.url()).hash.split('?')[0]);
  });
  const shots = [];
  try {
    const stored = await page.evaluate(() => localStorage.length);
    assert(stored === 0, 'browser storage is not empty');
    await steps(page, dir, shots);
    assert(app.errors.length === 0, `script errors: ${app.errors.join(' | ')}`);
  } finally {
    await app.close();
  }
  return { shots, visited: visited.filter((h, i) => h !== visited[i - 1]) };
}

(async () => {
  const targets = ['variant-1', 'variant-2'].map((v) => path.join(OUT, v));
  const existing = targets.flatMap((d) => (fs.existsSync(d) ? fs.readdirSync(d).filter((f) => f.endsWith('.png')) : []));
  if (existing.length && !FORCE) {
    console.error(`${OUT} already holds ${existing.length} screenshots. Pass --force to replace them.`);
    process.exit(1);
  }
  for (const d of targets) fs.rmSync(d, { recursive: true, force: true });

  const v1 = await runVariant('variant-1', async (page, dir, shots) => {
    await startBooking(page);
    await assertVisible(page, [`.doctor-card[data-id="${DOCTOR}"]`, '[data-action="choose-time"]']);
    await shoot(page, dir, '1-DoctorList.png', shots);
    await page.tap('[data-action="choose-time"]');

    await waitForScreen(page, 'time');
    await page.tap(`[data-slot="${SLOT}"]`);
    await waitForScreen(page, 'time');
    assert((await page.getAttribute(`[data-slot="${SLOT}"]`, 'aria-checked')) === 'true', 'slot is not selected');
    await assertVisible(page, [`[data-slot="${SLOT}"]`, '[data-action="to-review"]']);
    await shoot(page, dir, '2-TimeSlot.png', shots);
    await page.tap('[data-action="to-review"]');

    await waitForScreen(page, 'review');
    assert((await page.innerText('[data-action="confirm"]')) === 'Confirm appointment', 'confirm button label');
    assert(await page.isEnabled('[data-action="confirm"]'), 'confirm button is disabled');
    await assertVisible(page, ['.review-card', '[data-action="confirm"]']);
    await shoot(page, dir, '3-Review.png', shots);
    await page.tap('[data-action="confirm"]');

    await waitForScreen(page, 'confirmed');
    assert((await page.innerText('h1')) === 'Appointment confirmed', 'not on Confirmation');
    await assertVisible(page, ['.success-badge', '.success h1', '.ticket']);
    await shoot(page, dir, '4-Confirmation.png', shots);
  });
  const screens = (v) => v.visited.map((h) => h.split('/')[1]).join(' → ');
  assert(screens(v1) === 'doctors → book → review → confirmed', `variant-1 went through ${screens(v1)}`);

  const v2 = await runVariant('variant-2', async (page, dir, shots) => {
    await startBooking(page);
    await assertVisible(page, [`.doctor-card[data-id="${DOCTOR}"]`, '[data-action="book-next"]']);
    await shoot(page, dir, '1-DoctorList.png', shots);
    await page.tap('[data-action="book-next"]');

    await waitForScreen(page, 'confirmed');
    assert((await page.innerText('h1')) === 'Appointment confirmed', 'not on Confirmation');
    await assertVisible(page, ['.success-badge', '.success h1', '.ticket']);
    await shoot(page, dir, '2-Confirmation.png', shots);
  });
  assert(screens(v2) === 'doctors → confirmed', `variant-2 went through ${screens(v2)}`);

  const { width, height } = PHONE.viewport;
  const scale = PHONE.deviceScaleFactor;
  for (const rel of [...v1.shots, ...v2.shots]) {
    const png = fs.readFileSync(path.join(OUT, rel));
    const w = png.readUInt32BE(16);
    const h = png.readUInt32BE(20);
    assert(w === width * scale && h === height * scale, `${rel} is ${w}×${h}`);
  }

  console.log(`Viewport ${width}×${height} at ${scale}x → ${width * scale}×${height * scale} PNG`);
  console.log(`variant-1  ${screens(v1)}`);
  for (const s of v1.shots) console.log(`  ${s}`);
  console.log(`variant-2  ${screens(v2)}`);
  for (const s of v2.shots) console.log(`  ${s}`);
})().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
