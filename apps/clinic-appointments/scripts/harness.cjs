// Shared browser setup for the user-story tests and the screenshot script:
// a phone-sized Chromium context with a clean profile and a pinned clock.
'use strict';

const { chromium } = require('playwright');
const { serve } = require('./serve.cjs');

// Friday, October 2, 2026, 08:00. Pinning the clock keeps "Today", the open
// slots and the confirmation numbers the same on every run.
const FIXED_NOW = '2026-10-02T08:00:00Z';

const PHONE = {
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
  locale: 'en-US',
  timezoneId: 'UTC',
  colorScheme: 'light',
  reducedMotion: 'no-preference',
};

// A fresh browser and an empty context: no cookies, no storage, no history.
async function openApp() {
  const server = await serve();
  const browser = await chromium.launch();
  const context = await browser.newContext(PHONE);
  await context.clock.setFixedTime(new Date(FIXED_NOW));
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  await page.goto(server.url);
  await waitForScreen(page, 'doctors');
  return {
    page,
    errors,
    url: server.url,
    async close() {
      await browser.close();
      await server.close();
    },
  };
}

// Waits until the screen has rendered, fonts are in and every animation and
// transition has finished.
async function waitForScreen(page, route) {
  await page.waitForFunction((r) => document.body.dataset.route === r, route);
  await page.evaluate(async () => {
    await document.fonts.ready;
    const frame = () => new Promise((r) => requestAnimationFrame(r));
    await frame();
    await Promise.all(document.getAnimations().map((a) => a.finished.catch(() => {})));
    await frame();
    await frame();
  });
}

module.exports = { FIXED_NOW, PHONE, openApp, waitForScreen };
