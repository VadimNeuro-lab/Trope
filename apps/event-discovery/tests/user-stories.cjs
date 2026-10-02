// End-to-end checks for the five user stories, run against index.html in headless Chromium.
//   u1 Browse upcoming events
//   u2 Filter events by date
//   u3 View event details
//   u4 Save an event for later
//   u5 Purchase a ticket for an event
// Usage: npm test   (or: node tests/user-stories.cjs)
'use strict';

const path = require('path');
const { chromium } = require('playwright');

const APP_URL = 'file://' + path.resolve(__dirname, '..', 'index.html');

const pad = (n) => String(n).padStart(2, '0');
function iso(offset) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
// Same rule as the app: Friday through Sunday, starting today from Friday on.
function weekendRange() {
  const dow = new Date().getDay();
  const toSunday = (7 - dow) % 7;
  const toFriday = dow === 0 || dow >= 5 ? 0 : 5 - dow;
  return [iso(toFriday), iso(toSunday)];
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const results = [];
async function story(id, name, fn) {
  try {
    await fn();
    results.push({ id, name, ok: true });
  } catch (err) {
    results.push({ id, name, ok: false, err: process.env.DEBUG ? String(err.message) : String(err.message).split('\n')[0] });
  }
}

async function noSidewaysScroll(page, where) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(over <= 0, `${where} scrolls sideways by ${over}px`);
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  // Run offline: web fonts are blocked and the page falls back to system faces.
  await context.route(/fonts\.(googleapis|gstatic)\.com/, (route) => route.abort());
  const page = await context.newPage();

  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/fonts\.(googleapis|gstatic)/.test(m.location().url || '')) errors.push(m.text());
  });

  await page.goto(APP_URL);
  await page.waitForSelector('.feature');
  const total = await page.evaluate(() => window.DOORS_DATA.events.length);

  const resultDays = () => page.$$eval('#results .row', (els) => els.map((el) => el.dataset.day));
  const savedIds = () => page.$$eval('#seg-panel .row', (els) => els.map((el) => el.dataset.event));

  await story('u1', 'Browse upcoming events', async () => {
    const featured = await page.$$eval('.feature', (els) =>
      els.map((el) => ({
        title: el.querySelector('.feature-title').textContent.trim(),
        metas: [...el.querySelectorAll('.meta')].map((m) => m.textContent.trim()),
        cat: el.querySelector('.cat').textContent.trim(),
      }))
    );
    assert(featured.length >= 3, `expected featured events, got ${featured.length}`);
    for (const f of featured) {
      assert(f.title && f.cat, 'a featured card is missing its name or category');
      assert(/^(Today|Tomorrow|[A-Z][a-z]{2}, [A-Z][a-z]{2} \d{1,2}) · \d/.test(f.metas[0]), `featured date reads "${f.metas[0]}"`);
      assert(f.metas[1] && f.metas[1].includes(','), `featured location reads "${f.metas[1]}"`);
    }

    const rows = await page.$$eval('.upcoming .row', (els) =>
      els.map((el) => ({
        day: el.dataset.day,
        title: el.querySelector('.row-title').textContent.trim(),
        when: el.querySelector('.row-when').textContent.trim(),
        where: el.querySelector('.row-where').textContent.trim(),
        cat: el.querySelector('.cat').textContent.trim(),
      }))
    );
    assert(rows.length >= 8, `expected an upcoming list, got ${rows.length} rows`);
    assert(rows.every((r) => r.title && r.when && r.where && r.cat), 'an upcoming row is missing name, time, location or category');
    assert(rows.every((r, i) => i === 0 || rows[i - 1].day <= r.day), 'upcoming events are not in date order');
    assert(rows[0].day >= iso(0), 'upcoming list starts with a past event');
    await noSidewaysScroll(page, 'Discover');

    await page.click('.feature .stretch');
    await page.waitForSelector('#ev-title');
    assert((await page.textContent('#ev-title')).trim() === featured[0].title, 'the featured card opened a different event');
    await page.click('[data-action="back"]');
    await page.waitForSelector('.feature');

    await page.click('.see-all');
    await page.waitForSelector('#results .row');
    const n = (await resultDays()).length;
    assert(n === total, `"See all" listed ${n} of ${total} events`);
  });

  await story('u2', 'Filter events by date', async () => {
    await page.click('[data-action="tab"][data-tab="search"]');

    await page.click('[data-action="set-date"][data-date="today"]');
    let days = await resultDays();
    assert(days.length && days.every((d) => d === iso(0)), `Today returned ${days.join(', ') || 'nothing'}`);

    await page.click('[data-action="set-date"][data-date="tomorrow"]');
    days = await resultDays();
    assert(days.length && days.every((d) => d === iso(1)), `Tomorrow returned ${days.join(', ') || 'nothing'}`);

    const [ws, we] = weekendRange();
    await page.click('[data-action="set-date"][data-date="weekend"]');
    days = await resultDays();
    assert(days.length && days.every((d) => d >= ws && d <= we), `This weekend returned ${days.join(', ') || 'nothing'}`);

    await page.click('[data-action="set-date"][data-date="week"]');
    days = await resultDays();
    assert(days.length && days.every((d) => d >= iso(0) && d <= iso(6)), 'Next 7 days returned events outside the week');

    const target = await page.$eval('.day:not(.no-events):nth-child(n+3)', (el) => el.dataset.day);
    await page.click(`.day[data-day="${target}"]`);
    assert((await page.getAttribute(`.day[data-day="${target}"]`, 'aria-pressed')) === 'true', 'the picked day is not marked selected');
    days = await resultDays();
    assert(days.length && days.every((d) => d === target), `day ${target} returned ${days.join(', ')}`);
    await page.click(`.day[data-day="${target}"]`);
    assert((await resultDays()).length === total, 'tapping the selected day again should clear the date filter');

    await page.fill('#date-pick', iso(9));
    days = await resultDays();
    assert(days.length && days.every((d) => d === iso(9)), `the date picker returned ${days.join(', ') || 'nothing'}`);

    await page.click('[data-action="set-date"][data-date="month"]');
    await page.click('[data-action="toggle-cat"][data-cat="music"]');
    const rows = await page.$$eval('#results .row', (els) => els.map((el) => [el.dataset.day, el.dataset.cat]));
    assert(rows.length && rows.every(([d, c]) => c === 'music' && d <= iso(29)), 'date and category filters did not combine');

    await page.fill('#q', 'foundry');
    const where = await page.$$eval('#results .row .row-where', (els) => els.map((el) => el.textContent));
    assert(where.length && where.every((w) => w.includes('Foundry')), 'search text did not narrow the results');
    assert((await page.inputValue('#q')) === 'foundry', 'the search box lost its text');

    await page.click('.filter-head [data-action="clear-filters"]');
    assert((await resultDays()).length === total, 'Clear all did not reset the filters');
    await noSidewaysScroll(page, 'Search');
  });

  await story('u3', 'View event details', async () => {
    await page.click('[data-action="set-date"][data-date="weekend"]');
    const title = (await page.textContent('#results .row .row-title')).trim();
    await page.click('#results .row .stretch');
    await page.waitForSelector('#ev-title');
    assert((await page.textContent('#ev-title')).trim() === title, 'opened a different event');

    const facts = await page.$$eval('.fact', (els) => els.map((el) => el.innerText.replace(/\s+/g, ' ').trim()));
    assert(/^Date \w+day, \w+ \d{1,2}, \d{4}/i.test(facts[0] || ''), `date reads "${facts[0]}"`);
    assert(/^Time .*\d{1,2}(:\d{2})? (AM|PM)/i.test(facts[1] || ''), `time reads "${facts[1]}"`);
    assert(/^Venue \S/i.test(facts[2] || ''), `venue reads "${facts[2]}"`);
    const paragraphs = await page.$$eval('[aria-labelledby="h-about"] p', (ps) => ps.length);
    assert(paragraphs >= 1, 'description is missing');
    assert(await page.isVisible('#actionbar [data-action="buy"]'), 'the ticket button is not visible');
    assert(await page.isVisible('#actionbar [data-action="toggle-save"]'), 'the save button is not visible');
    assert(await page.isVisible('.tier'), 'ticket options are missing');
    assert(await page.isHidden('#tabbar'), 'the tab bar should hide on the event screen');
    await noSidewaysScroll(page, 'Event');

    await page.click('[data-action="back"]');
    await page.waitForSelector('#results');
    const pressed = await page.getAttribute('[data-action="set-date"][data-date="weekend"]', 'aria-pressed');
    assert(pressed === 'true', 'filters were lost after going back');
  });

  await story('u4', 'Save an event for later', async () => {
    const id = await page.$eval('#results .row .save-btn[aria-pressed="false"]', (b) => b.dataset.id);
    await page.click(`#results .row[data-event="${id}"] .stretch`);
    await page.waitForSelector('#ev-title');
    await page.click('#actionbar [data-action="toggle-save"]');
    assert((await page.getAttribute('#actionbar .save-btn', 'aria-pressed')) === 'true', 'the save button did not turn on');
    assert((await page.getAttribute('.hero-bar .save-btn', 'aria-pressed')) === 'true', 'the two save buttons disagree');
    assert((await page.textContent('#toast')).includes('Saved'), 'no confirmation after saving');

    await page.click('[data-action="back"]');
    await page.waitForSelector('#results');
    await page.click('[data-action="tab"][data-tab="saved"]');
    assert((await savedIds()).includes(id), 'the event is not on the Saved screen');
    const badge = await page.textContent('.tab-badge');
    assert(Number(badge) === (await savedIds()).length, 'the Saved tab badge does not match the list');

    await page.reload();
    await page.waitForSelector('#seg-panel');
    assert((await savedIds()).includes(id), 'the saved event did not survive a reload');

    await page.click(`#seg-panel .row[data-event="${id}"] .save-btn`);
    assert(!(await savedIds()).includes(id), 'removing from Saved did not work');
    await page.click('.toast-btn');
    assert((await savedIds()).includes(id), 'Undo did not restore the event');
    await noSidewaysScroll(page, 'Saved');
  });

  await story('u5', 'Purchase a ticket for an event', async () => {
    await page.click('[data-action="tab"][data-tab="discover"]');
    await page.click('.feature[data-event="e01"] .stretch');
    await page.waitForSelector('#ev-title');
    await page.click('#actionbar [data-action="buy"]');
    await page.waitForSelector('.sheet input[name="tier"]');

    await page.check('.sheet input[name="tier"][value="bal"]');
    await page.click('.sheet [data-action="qty"][data-delta="1"]');
    assert((await page.textContent('#qty-out')).trim() === '2', 'quantity did not change to 2');
    // Balcony is $45; the fee is 10% + $1.50 = $6.00 a ticket.
    assert((await page.textContent('#checkout-total')).trim() === '$102.00', 'the total is wrong');

    await page.click('.sheet [data-action="checkout-next"]');
    await page.waitForSelector('.sheet input[name="paycard"]:checked');
    await page.click('.sheet [data-action="pay"]');
    await page.waitForSelector('.sheet .stub');
    const code = (await page.textContent('.sheet .stub-code')).trim();
    const m = /^ORDER (DR-[A-Z2-9]{6})$/.exec(code);
    assert(m, `unexpected order code "${code}"`);
    assert((await page.textContent('.sheet .stub-kicker')).includes('Admit 2'), 'the ticket does not show 2 admissions');

    await page.click('.sheet [data-action="view-tickets"]');
    await page.waitForSelector('#seg-panel .stub');
    const codes = await page.$$eval('#seg-panel .stub-code', (els) => els.map((el) => el.textContent.trim()));
    assert(codes.includes(code), 'the ticket is not listed under Saved, then Tickets');

    await page.click(`#seg-panel .stub[data-order="${m[1]}"] .stretch`);
    await page.waitForSelector('.owned');
    assert((await page.textContent('.owned')).includes('2 tickets'), 'the event page does not show the tickets you own');

    // A free event goes through the same flow without a payment method.
    await page.click('[data-action="back"]');
    await page.click('[data-action="tab"][data-tab="search"]');
    await page.fill('#q', 'synth');
    await page.click('#results .row .stretch');
    await page.waitForSelector('#ev-title');
    assert((await page.textContent('#actionbar [data-action="buy"]')).trim() === 'Reserve a spot', 'free events should offer a reservation');
    await page.click('#actionbar [data-action="buy"]');
    await page.click('.sheet [data-action="checkout-next"]');
    assert((await page.$('.sheet input[name="paycard"]')) === null, 'a free reservation should not ask for a card');
    await page.click('.sheet [data-action="pay"]');
    await page.waitForSelector('.sheet .stub');
    await page.click('.sheet [data-action="close-sheet"]');
    await noSidewaysScroll(page, 'Event after purchase');
  });

  await story('-', 'No script errors', async () => {
    assert(errors.length === 0, errors.join(' | '));
  });

  await browser.close();

  for (const r of results) {
    console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.id.padEnd(3)} ${r.name}${r.ok ? '' : `\n        ${r.err}`}`);
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(failed ? `\n${failed} failing` : `\nAll ${results.length} checks passed`);
  process.exit(failed ? 1 : 0);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
