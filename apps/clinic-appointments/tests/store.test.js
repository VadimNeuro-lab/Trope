'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const S = require('../src/schedule.js');
const Store = require('../src/store.js');

const NOW = new Date(2026, 9, 2, 8, 0);
const park = S.doctorById('elena-park');
const openSlots = (list = [], date = '2026-10-05') =>
  S.slotsFor(park, date, { now: NOW, appointments: list }).filter((s) => s.state === 'open').map((s) => s.key);

function memoryStorage() {
  const data = new Map();
  return { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => data.set(k, String(v)) };
}

test('booking an open slot adds an upcoming appointment and takes the slot', () => {
  const [slot] = openSlots();
  const { list, appointment } = Store.book([], { doctorId: 'elena-park', start: slot, reason: '  Follow-up  ', via: 'review', now: NOW });
  assert.equal(list.length, 1);
  assert.equal(appointment.status, 'upcoming');
  assert.equal(appointment.reason, 'Follow-up');
  assert.equal(appointment.via, 'review');
  assert.match(appointment.code, /^LC-\d{4}$/);
  assert.ok(!openSlots(list).includes(slot));
  assert.throws(() => Store.book(list, { doctorId: 'elena-park', start: slot, now: NOW }), /no longer available/);
});

test('a slot held by another patient cannot be booked', () => {
  const taken = S.slotsFor(park, '2026-10-05', { now: NOW, appointments: [] }).find((s) => s.state === 'taken');
  assert.ok(taken);
  assert.throws(() => Store.book([], { doctorId: 'elena-park', start: taken.key, now: NOW }), (err) => err.code === 'unavailable');
});

test('cancelling frees the slot and moves the visit to history', () => {
  const [a, b] = openSlots();
  let list = Store.book([], { doctorId: 'elena-park', start: b, now: NOW }).list;
  list = Store.book(list, { doctorId: 'elena-park', start: a, now: NOW }).list;
  assert.deepEqual(Store.upcoming(list, NOW).map((x) => x.start), [a, b], 'upcoming is sorted by time');

  const target = Store.upcoming(list, NOW)[0];
  const after = Store.cancel(list, target.id, NOW);
  assert.equal(list[1].status, 'upcoming', 'cancel does not change the list it was given');
  assert.deepEqual(Store.upcoming(after, NOW).map((x) => x.start), [b]);
  assert.deepEqual(Store.history(after, NOW).map((x) => x.status), ['cancelled']);
  assert.ok(openSlots(after).includes(a), 'the cancelled time is open again');
});

test('visits whose time has passed leave the upcoming list', () => {
  const [slot] = openSlots();
  const { list } = Store.book([], { doctorId: 'elena-park', start: slot, now: NOW });
  const later = new Date(2026, 9, 6, 9, 0);
  assert.equal(Store.upcoming(list, later).length, 0);
  assert.equal(Store.history(list, later).length, 1);
});

test('appointments survive a save and load, and bad storage is ignored', () => {
  const storage = memoryStorage();
  const [slot] = openSlots();
  const { list } = Store.book([], { doctorId: 'elena-park', start: slot, now: NOW });
  assert.equal(Store.save(storage, list), true);
  assert.deepEqual(Store.load(storage), list);

  storage.setItem(Store.STORAGE_KEY, '{not json');
  assert.deepEqual(Store.load(storage), []);
  storage.setItem(Store.STORAGE_KEY, JSON.stringify([{ id: 1 }, list[0], { ...list[0], doctorId: 'nobody' }]));
  assert.deepEqual(Store.load(storage), [list[0]]);

  const throwing = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  assert.deepEqual(Store.load(throwing), []);
  assert.equal(Store.save(throwing, list), false);
  assert.equal(Store.save(null, list), false);
});
