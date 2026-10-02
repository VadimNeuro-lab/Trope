// The patient's appointments: booking, cancelling and keeping them in localStorage.
// Every function returns a new list instead of changing the one it was given.
(function (root) {
  'use strict';

  const isNode = typeof module === 'object' && module.exports;
  const S = isNode ? require('./schedule.js') : root.ClinicSchedule;

  const STORAGE_KEY = 'linden-clinic.appointments.v1';

  function isAppointment(a) {
    return (
      a && typeof a === 'object' && typeof a.id === 'string' && S.doctorById(a.doctorId) &&
      S.isSlotKey(a.start) && (a.status === 'upcoming' || a.status === 'cancelled')
    );
  }

  // Storage can be missing or throw (private windows, blocked site data);
  // the app then works for the current visit only.
  function load(storage) {
    try {
      const raw = storage && storage.getItem(STORAGE_KEY);
      const list = raw ? JSON.parse(raw) : [];
      return Array.isArray(list) ? list.filter(isAppointment) : [];
    } catch (err) {
      return [];
    }
  }

  function save(storage, list) {
    try {
      if (!storage) return false;
      storage.setItem(STORAGE_KEY, JSON.stringify(list));
      return true;
    } catch (err) {
      return false;
    }
  }

  // via: 'review' when booked from the review screen, 'next-available' from the doctor list.
  function book(list, { doctorId, start, reason, via, now }) {
    const doctor = S.doctorById(doctorId);
    if (!S.isBookable(doctor, start, { now, appointments: list })) {
      const err = new Error('That time is no longer available.');
      err.code = 'unavailable';
      throw err;
    }
    const n = list.length + 1;
    const appointment = {
      id: `a${n}-${now.getTime().toString(36)}`,
      code: S.confirmationCode(doctorId, start, n),
      doctorId,
      start,
      minutes: 30,
      reason: String(reason || '').trim().slice(0, 300),
      via: via || 'review',
      status: 'upcoming',
      bookedAt: now.toISOString(),
    };
    return { list: list.concat(appointment), appointment };
  }

  function cancel(list, id, now) {
    return list.map((a) =>
      a.id === id && a.status === 'upcoming' ? { ...a, status: 'cancelled', cancelledAt: now.toISOString() } : a
    );
  }

  const byStart = (a, b) => S.slotStart(a.start) - S.slotStart(b.start);

  function upcoming(list, now) {
    return list.filter((a) => S.isUpcoming(a, now)).sort(byStart);
  }

  // Cancelled visits and visits whose time has passed, most recent first.
  function history(list, now) {
    return list.filter((a) => !S.isUpcoming(a, now)).sort((a, b) => byStart(b, a));
  }

  const api = { STORAGE_KEY, isAppointment, load, save, book, cancel, upcoming, history };
  if (isNode) module.exports = api;
  else root.ClinicStore = api;
})(typeof window !== 'undefined' ? window : globalThis);
