import test from 'node:test';
import assert from 'node:assert/strict';
import {
  addDays,
  dayKey,
  diffDays,
  formatRange,
  isDayKey,
  isoWeek,
  parseDayKey,
  relativeDay,
  startOfWeek,
  weekDays,
} from '../src/dates.js';

const FRIDAY = new Date(2026, 9, 2, 15, 30); // Friday 2 October 2026, mid-afternoon

test('day keys round-trip in local time', () => {
  assert.equal(dayKey(FRIDAY), '2026-10-02');
  assert.equal(dayKey(parseDayKey('2026-10-02')), '2026-10-02');
  assert.ok(isDayKey('2026-02-28'));
  assert.ok(!isDayKey('2026-02-30'));
  assert.ok(!isDayKey('yesterday'));
});

test('weeks start on Monday or Sunday', () => {
  assert.equal(dayKey(startOfWeek(FRIDAY, 1)), '2026-09-28');
  assert.equal(dayKey(startOfWeek(FRIDAY, 0)), '2026-09-27');
  const sunday = new Date(2026, 9, 4);
  assert.equal(dayKey(startOfWeek(sunday, 1)), '2026-09-28');
  assert.equal(dayKey(startOfWeek(sunday, 0)), '2026-10-04');
  assert.deepEqual(weekDays(FRIDAY, 1).map(dayKey), [
    '2026-09-28',
    '2026-09-29',
    '2026-09-30',
    '2026-10-01',
    '2026-10-02',
    '2026-10-03',
    '2026-10-04',
  ]);
});

test('day arithmetic crosses month ends and daylight-saving changes', () => {
  assert.equal(dayKey(addDays(FRIDAY, -2)), '2026-09-30');
  assert.equal(diffDays(new Date(2026, 2, 30), new Date(2026, 2, 28)), 2);
  assert.equal(diffDays(new Date(2026, 9, 26), new Date(2026, 9, 24)), 2);
});

test('ISO week numbers', () => {
  assert.equal(isoWeek(FRIDAY), 40);
  assert.equal(isoWeek(new Date(2026, 0, 1)), 1);
  assert.equal(isoWeek(new Date(2027, 0, 1)), 53);
});

test('labels', () => {
  assert.equal(formatRange(new Date(2026, 8, 28), new Date(2026, 9, 4)), '28 Sep – 4 Oct');
  assert.equal(formatRange(new Date(2026, 9, 5), new Date(2026, 9, 11)), '5–11 Oct');
  assert.equal(relativeDay(FRIDAY, FRIDAY), 'Today');
  assert.equal(relativeDay(addDays(FRIDAY, -1), FRIDAY), 'Yesterday');
  assert.equal(relativeDay(addDays(FRIDAY, -3), FRIDAY), 'Tue 29 Sep');
});
