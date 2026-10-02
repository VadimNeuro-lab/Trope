// End-to-end checks of the user stories in headless Chromium at phone size.
//   u1 Browse doctors by specialty
//   u2 Book a doctor: choose an available time, review, confirm
//   u3 Book a doctor's next available time straight from the list
//   u4 View and cancel upcoming appointments
// Usage: npm test   (or: node tests/user-stories.cjs)
'use strict';

const { openApp, waitForScreen } = require('../scripts/harness.cjs');
const { DOCTORS, SPECIALTIES } = require('../src/data.js');

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const results = [];
async function story(id, name, fn) {
  const app = await openApp();
  try {
    await fn(app.page, app);
    assert(app.errors.length === 0, `script errors: ${app.errors.join(' | ')}`);
    results.push({ id, name, ok: true });
  } catch (err) {
    results.push({ id, name, ok: false, err: String(err.message).split('\n')[0] });
  } finally {
    await app.close();
  }
}

const text = (page, sel) => page.locator(sel).first().innerText();
const cardIds = (page) => page.$$eval('.doctor-card', (els) => els.map((el) => el.dataset.id));

async function noSidewaysScroll(page, where) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(over <= 0, `${where} scrolls sideways by ${over}px`);
}

async function pickDoctor(page, specialty, id) {
  await page.tap(`[data-action="specialty"][data-id="${specialty}"]`);
  await page.tap(`.doctor-card[data-id="${id}"]`);
  await page.waitForSelector('.selbar');
}

(async () => {
  await story('u1', 'Browse doctors by specialty', async (page) => {
    assert((await cardIds(page)).length === DOCTORS.length, 'All should list every doctor');
    await noSidewaysScroll(page, 'DoctorList');
    for (const s of SPECIALTIES) {
      await page.tap(`[data-action="specialty"][data-id="${s.id}"]`);
      const ids = await cardIds(page);
      const want = DOCTORS.filter((d) => d.specialty === s.id).map((d) => d.id);
      assert(JSON.stringify(ids) === JSON.stringify(want), `${s.name} lists ${ids.join(', ')}`);
      assert((await text(page, '.list-head h2')) === s.name, `${s.name} heading`);
      const checked = await page.$$eval('.chip[aria-checked="true"]', (els) => els.map((e) => e.dataset.id));
      assert(checked.join() === s.id, `chip ${s.id} should be the only one checked`);
    }
    const next = await text(page, '.doctor-next strong');
    assert(/^(Today|Tomorrow|[A-Z][a-z]{2}, [A-Z][a-z]{2} \d{1,2}) · \d{1,2}:\d{2} [AP]M$/.test(next), `next available reads "${next}"`);
    await page.tap('[data-action="specialty"][data-id="all"]');
    assert((await cardIds(page)).length === DOCTORS.length, 'All should list every doctor again');
  });

  await story('u2', 'Book a doctor by choosing a time and reviewing it', async (page) => {
    await pickDoctor(page, 'cardiology', 'elena-park');
    assert((await page.getAttribute('.doctor-card[data-id="elena-park"]', 'aria-checked')) === 'true', 'card is selected');
    await page.tap('[data-action="choose-time"]');
    await waitForScreen(page, 'time');
    await noSidewaysScroll(page, 'TimeSlot');
    assert((await text(page, '.doctor-strip strong')) === 'Dr. Elena Park', 'TimeSlot names the doctor');
    assert(await page.isDisabled('[data-action="to-review"]'), 'Review is disabled until a time is chosen');
    assert((await page.locator('.slot.is-taken').count()) > 0, 'taken slots are shown');
    assert(await page.locator('.slot.is-taken').first().isDisabled(), 'taken slots cannot be chosen');

    // Another day, then a time on it.
    await page.tap('.day[data-date="2026-10-05"]');
    await page.tap('[data-slot="2026-10-05T10:30"]');
    assert((await page.getAttribute('[data-slot="2026-10-05T10:30"]', 'aria-checked')) === 'true', 'slot is selected');
    assert((await text(page, '.actionbar-summary strong')) === 'Mon, Oct 5 · 10:30 AM', 'summary shows the time');
    await page.tap('[data-action="to-review"]');
    await waitForScreen(page, 'review');

    const review = await text(page, '.review-card');
    for (const s of ['Dr. Elena Park', 'Monday, October 5, 2026', '10:30 – 11:00 AM', 'Room 214']) {
      assert(review.includes(s), `Review is missing "${s}"`);
    }
    // Change goes back with the time still chosen.
    await page.tap('[data-key="change-time"]');
    await waitForScreen(page, 'time');
    assert((await page.getAttribute('[data-slot="2026-10-05T10:30"]', 'aria-checked')) === 'true', 'time kept after Change');
    await page.tap('[data-action="to-review"]');
    await waitForScreen(page, 'review');

    await page.fill('textarea', 'Follow-up on blood pressure');
    await page.tap('[data-action="confirm"]');
    await waitForScreen(page, 'confirmed');
    assert((await text(page, 'h1')) === 'Appointment confirmed', 'Confirmation heading');
    assert(/^LC-\d{4}$/.test(await text(page, '.ticket .code')), 'confirmation number');

    await page.tap('[data-key="to-appointments"]');
    await waitForScreen(page, 'appointments');
    const card = await text(page, '.appt-card');
    assert(card.includes('Dr. Elena Park') && card.includes('Mon, Oct 5') && card.includes('Follow-up on blood pressure'), 'appointment listed');
    assert((await text(page, '.tab .badge')) === '1', 'tab badge counts it');

    await page.goto(page.url().split('#')[0] + '#/book/elena-park?date=2026-10-05');
    await waitForScreen(page, 'time');
    assert((await page.locator('[data-key="slot-2026-10-05T10:30"], .slot.is-yours').count()) === 1, 'booked time shows as yours');
    assert((await text(page, '.slot.is-yours')).includes('Your visit'), 'booked time is labeled');
  });

  await story('u3', 'Book the next available time from the doctor list', async (page) => {
    const visited = [];
    page.on('framenavigated', (f) => f === page.mainFrame() && visited.push(new URL(f.url()).hash));
    await pickDoctor(page, 'cardiology', 'elena-park');
    const next = (await text(page, '.selbar-text span')).replace('Next available: ', '');
    await page.tap('[data-action="book-next"]');
    await waitForScreen(page, 'confirmed');
    assert(!visited.some((h) => h.startsWith('#/book') || h.startsWith('#/review')), `went through ${visited.join(' ')}`);
    const ticket = await text(page, '.ticket');
    const [day, time] = next.split(' · ');
    assert(ticket.includes(time), `confirmation shows ${time}`);
    assert(day === 'Today' && ticket.includes('Fri, Oct 2'), `confirmation shows ${day}`);
  });

  await story('u4', 'View and cancel upcoming appointments', async (page) => {
    await page.tap('[data-key="tab-appointments"]');
    await waitForScreen(page, 'appointments');
    assert((await page.locator('.empty').count()) === 1, 'empty state with no bookings');

    // Two bookings, made out of order.
    await page.tap('[data-key="empty-find"]');
    await waitForScreen(page, 'doctors');
    await pickDoctor(page, 'dermatology', 'priya-nair');
    await page.tap('[data-action="book-next"]');
    await waitForScreen(page, 'confirmed');
    await page.tap('[data-key="to-doctors"]');
    await waitForScreen(page, 'doctors');
    await pickDoctor(page, 'primary', 'maya-thompson');
    await page.tap('[data-action="book-next"]');
    await waitForScreen(page, 'confirmed');
    await page.tap('[data-key="to-appointments"]');
    await waitForScreen(page, 'appointments');
    await noSidewaysScroll(page, 'Appointments');

    const names = () => page.$$eval('.appt-card:not(.is-past) .appt-title strong', (els) => els.map((e) => e.textContent));
    assert(JSON.stringify(await names()) === JSON.stringify(['Dr. Maya Thompson', 'Dr. Priya Nair']), `upcoming order: ${await names()}`);

    // Keep, then cancel.
    await page.tap('.appt-card [data-action="ask-cancel"]');
    await page.waitForSelector('.sheet');
    await page.tap('.sheet .btn-ghost');
    assert((await page.locator('.sheet').count()) === 0, 'Keep closes the sheet');
    assert((await names()).length === 2, 'Keep leaves the appointment');

    await page.tap('.appt-card [data-action="ask-cancel"]');
    await page.tap('[data-action="confirm-cancel"]');
    await page.waitForSelector('.appt-card.is-past');
    assert(JSON.stringify(await names()) === JSON.stringify(['Dr. Priya Nair']), 'cancelled visit leaves Upcoming');
    assert((await text(page, '.appt-card.is-past .tag')) === 'Cancelled', 'cancelled visit is marked');
    assert((await text(page, '.tab .badge')) === '1', 'badge drops to 1');
    assert((await text(page, '#toast')).startsWith('Appointment cancelled'), 'toast confirms');

    await page.reload();
    await waitForScreen(page, 'appointments');
    assert(JSON.stringify(await names()) === JSON.stringify(['Dr. Priya Nair']), 'state survives a reload');

    // The cancelled time is open again.
    await page.tap('[data-key="tab-doctors"]');
    await waitForScreen(page, 'doctors');
    await pickDoctor(page, 'primary', 'maya-thompson');
    assert((await text(page, '.selbar-text span')) === 'Next available: Today · 9:00 AM', 'freed slot is next available again');
  });

  let failed = 0;
  for (const r of results) {
    console.log(`${r.ok ? 'ok  ' : 'FAIL'} ${r.id} ${r.name}${r.ok ? '' : `\n     ${r.err}`}`);
    if (!r.ok) failed++;
  }
  console.log(`\n${results.length - failed}/${results.length} user stories pass`);
  process.exit(failed ? 1 : 0);
})();
