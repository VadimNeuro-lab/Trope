'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const S = require('../src/schedule.js');
const { DOCTORS, SEED } = require('../src/data.js');

// Friday, October 2, 2026, 08:00 local time.
const NOW = new Date(2026, 9, 2, 8, 0);
const ctx = (appointments = []) => ({ now: NOW, appointments });
const park = S.doctorById('elena-park');

test('the schedule is seeded with 29 and depends only on doctor and date', () => {
  assert.equal(SEED, 29);
  const a = S.daySchedule(park, '2026-10-05');
  S.daySchedule(S.doctorById('maya-thompson'), '2026-10-05');
  const b = S.daySchedule(park, '2026-10-05');
  assert.deepEqual(a, b);
  assert.ok(a.some((s) => s.taken) && a.some((s) => !s.taken), 'a working day has both taken and free slots');
});

test('no slots on days off, none over lunch, Saturdays end at 13:00', () => {
  assert.deepEqual(S.daySchedule(park, '2026-10-04'), [], 'Dr. Park does not work Sundays');
  for (const d of DOCTORS) {
    for (const date of S.bookingDates(NOW)) {
      for (const s of S.daySchedule(d, date)) {
        const m = S.toMinutes(s.time);
        assert.ok(m + 30 <= 12 * 60 + 30 || m >= 13 * 60 + 30, `${d.id} has a lunch slot at ${s.time}`);
        if (S.parseDate(date).getDay() === 6) assert.ok(m + 30 <= 13 * 60, `${d.id} works past 13:00 on Saturday`);
      }
    }
  }
});

test('slots inside the one-hour lead time are hidden', () => {
  const late = new Date(2026, 9, 2, 10, 40);
  const times = S.slotsFor(park, '2026-10-02', { now: late, appointments: [] }).map((s) => s.time);
  assert.ok(times.length > 0);
  assert.ok(times.every((t) => S.toMinutes(t) >= 11 * 60 + 40), times.join(' '));
});

test('own bookings show as yours, and overlapping times as conflicts', () => {
  const open = S.slotsFor(park, '2026-10-05', ctx()).filter((s) => s.state === 'open');
  const mine = { id: 'x', doctorId: 'elena-park', start: open[0].key, status: 'upcoming' };
  const slots = S.slotsFor(park, '2026-10-05', ctx([mine]));
  assert.equal(slots.find((s) => s.key === open[0].key).state, 'yours');

  const other = S.doctorById('maya-thompson');
  const time = S.slotsFor(other, '2026-10-05', ctx()).find((s) => s.state === 'open').key;
  const elsewhere = { id: 'y', doctorId: 'maya-thompson', start: time, status: 'upcoming' };
  const same = S.slotsFor(park, '2026-10-05', ctx([elsewhere])).find((s) => s.key === time);
  if (same && same.state !== 'taken') assert.equal(same.state, 'conflict');
});

test('next available is the earliest open slot in the booking window', () => {
  for (const d of DOCTORS) {
    const key = S.nextAvailable(d, ctx());
    assert.ok(key, `${d.id} has an open slot`);
    assert.ok(S.isBookable(d, key, ctx()));
    for (const date of S.bookingDates(NOW)) {
      for (const s of S.slotsFor(d, date, ctx())) {
        if (s.state === 'open') assert.ok(S.slotStart(s.key) >= S.slotStart(key), `${d.id}: ${s.key} is earlier than ${key}`);
      }
    }
  }
});

test('booking window is two weeks from today', () => {
  const dates = S.bookingDates(NOW);
  assert.equal(dates.length, 14);
  assert.equal(dates[0], '2026-10-02');
  assert.equal(dates[13], '2026-10-15');
  assert.equal(S.isBookable(park, '2026-10-19T09:00', ctx()), false);
  assert.equal(S.isBookable(park, 'not-a-slot', ctx()), false);
});

test('labels', () => {
  assert.equal(S.formatTime('09:30'), '9:30 AM');
  assert.equal(S.formatTime('12:00'), '12:00 PM');
  assert.equal(S.formatTime('00:15'), '12:15 AM');
  assert.equal(S.formatTimeRange('2026-10-05T10:30'), '10:30 – 11:00 AM');
  assert.equal(S.formatTimeRange('2026-10-05T11:30'), '11:30 AM – 12:00 PM');
  assert.equal(S.formatDay('2026-10-02', NOW), 'Today');
  assert.equal(S.formatDay('2026-10-03', NOW), 'Tomorrow');
  assert.equal(S.formatDay('2026-10-05', NOW), 'Mon, Oct 5');
  assert.equal(S.formatLongDate('2026-10-05'), 'Monday, October 5, 2026');
  assert.equal(S.formatSlot('2026-10-05T09:00', NOW), 'Mon, Oct 5 · 9:00 AM');
  assert.match(S.confirmationCode('elena-park', '2026-10-05T09:00', 1), /^LC-\d{4}$/);
});
