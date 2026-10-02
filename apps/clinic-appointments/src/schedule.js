// Doctors' schedules, open slots and the date and time labels the screens show.
// Pure functions: anything that depends on the clock or on bookings takes them
// as arguments, so the node tests can pin both.
(function (root) {
  'use strict';

  const isNode = typeof module === 'object' && module.exports;
  const { SEED, CLINIC, DOCTORS, SPECIALTIES } = isNode ? require('./data.js') : root.ClinicData;

  // Share of slots already held by other patients.
  const TAKEN_SHARE = 0.45;
  const LUNCH = ['12:30', '13:30'];
  const SATURDAY = ['09:00', '13:00'];

  const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

  // ---- seeded randomness -------------------------------------------------

  function hash32(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function mulberry32(a) {
    return function () {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // One stream per label, so a day's slots never depend on which day was looked at first.
  function rngFor(...parts) {
    return mulberry32(hash32([SEED, ...parts].join('|')));
  }

  // ---- dates and times ---------------------------------------------------

  const pad = (n) => String(n).padStart(2, '0');

  function isoDate(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function parseDate(iso) {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d);
  }

  function addDays(iso, n) {
    const d = parseDate(iso);
    d.setDate(d.getDate() + n);
    return isoDate(d);
  }

  function toMinutes(hhmm) {
    const [h, m] = hhmm.split(':').map(Number);
    return h * 60 + m;
  }

  function fromMinutes(min) {
    return `${pad(Math.floor(min / 60))}:${pad(min % 60)}`;
  }

  function slotKey(dateIso, time) {
    return `${dateIso}T${time}`;
  }

  function splitKey(key) {
    const [date, time] = String(key).split('T');
    return { date, time };
  }

  function isSlotKey(key) {
    return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(String(key));
  }

  function slotStart(key) {
    const { date, time } = splitKey(key);
    const d = parseDate(date);
    const m = toMinutes(time);
    d.setHours(Math.floor(m / 60), m % 60, 0, 0);
    return d;
  }

  // ---- doctors -----------------------------------------------------------

  function doctorById(id) {
    return DOCTORS.find((d) => d.id === id) || null;
  }

  function specialtyById(id) {
    return SPECIALTIES.find((s) => s.id === id) || null;
  }

  function doctorsIn(specialtyId) {
    if (!specialtyId || specialtyId === 'all') return DOCTORS.slice();
    return DOCTORS.filter((d) => d.specialty === specialtyId);
  }

  function workingHours(doctor, dateIso) {
    const dow = parseDate(dateIso).getDay();
    if (!doctor.days.includes(dow)) return null;
    if (dow !== 6) return doctor.hours;
    const start = Math.max(toMinutes(doctor.hours[0]), toMinutes(SATURDAY[0]));
    const end = Math.min(toMinutes(doctor.hours[1]), toMinutes(SATURDAY[1]));
    return end > start ? [fromMinutes(start), fromMinutes(end)] : null;
  }

  // The day's book as the clinic sees it: every visit slot in working hours,
  // and whether another patient already holds it. Depends only on SEED, the
  // doctor and the date.
  function daySchedule(doctor, dateIso) {
    const hours = workingHours(doctor, dateIso);
    if (!hours) return [];
    const rng = rngFor(doctor.id, dateIso);
    const len = CLINIC.visitMinutes;
    const lunch = LUNCH.map(toMinutes);
    const slots = [];
    for (let m = toMinutes(hours[0]); m + len <= toMinutes(hours[1]); m += len) {
      if (m < lunch[1] && m + len > lunch[0]) continue;
      const time = fromMinutes(m);
      slots.push({ time, key: slotKey(dateIso, time), taken: rng() < TAKEN_SHARE });
    }
    return slots;
  }

  function isUpcoming(appt, now) {
    return appt.status === 'upcoming' && slotStart(appt.start).getTime() > now.getTime();
  }

  function overlaps(keyA, keyB) {
    const a = slotStart(keyA).getTime();
    const b = slotStart(keyB).getTime();
    return Math.abs(a - b) < CLINIC.visitMinutes * 60000;
  }

  // Slots a patient can see for one day. States:
  //   open      bookable
  //   taken     held by another patient
  //   yours     the patient's own appointment with this doctor
  //   conflict  the patient has another visit at this time
  // Slots that start within the lead time are left out.
  function slotsFor(doctor, dateIso, ctx) {
    const earliest = ctx.now.getTime() + CLINIC.leadMinutes * 60000;
    const mine = (ctx.appointments || []).filter((a) => isUpcoming(a, ctx.now));
    return daySchedule(doctor, dateIso)
      .filter((s) => slotStart(s.key).getTime() >= earliest)
      .map((s) => {
        let state = 'open';
        if (mine.some((a) => a.doctorId === doctor.id && a.start === s.key)) state = 'yours';
        else if (s.taken) state = 'taken';
        else if (mine.some((a) => overlaps(a.start, s.key))) state = 'conflict';
        return { time: s.time, key: s.key, state };
      });
  }

  function bookingDates(now) {
    const today = isoDate(now);
    return Array.from({ length: CLINIC.bookingDays }, (_, i) => addDays(today, i));
  }

  function openCount(doctor, dateIso, ctx) {
    return slotsFor(doctor, dateIso, ctx).filter((s) => s.state === 'open').length;
  }

  function nextAvailable(doctor, ctx) {
    for (const date of bookingDates(ctx.now)) {
      const slot = slotsFor(doctor, date, ctx).find((s) => s.state === 'open');
      if (slot) return slot.key;
    }
    return null;
  }

  function isBookable(doctor, key, ctx) {
    if (!doctor || !isSlotKey(key)) return false;
    const { date } = splitKey(key);
    if (!bookingDates(ctx.now).includes(date)) return false;
    return slotsFor(doctor, date, ctx).some((s) => s.key === key && s.state === 'open');
  }

  function confirmationCode(doctorId, key, n) {
    return `LC-${(hash32(`${SEED}|${doctorId}|${key}|${n}`) % 9000) + 1000}`;
  }

  // ---- labels ------------------------------------------------------------

  function formatTime(time) {
    const m = toMinutes(time);
    const h = Math.floor(m / 60);
    const h12 = h % 12 === 0 ? 12 : h % 12;
    return `${h12}:${pad(m % 60)} ${h < 12 ? 'AM' : 'PM'}`;
  }

  // "10:30 – 11:00 AM", or "11:30 AM – 12:00 PM" across noon.
  function formatTimeRange(key, minutes) {
    const { time } = splitKey(key);
    const end = fromMinutes(toMinutes(time) + (minutes || CLINIC.visitMinutes));
    const a = formatTime(time);
    const b = formatTime(end);
    return a.slice(-2) === b.slice(-2) ? `${a.slice(0, -3)} – ${b}` : `${a} – ${b}`;
  }

  function weekdayShort(iso) {
    return WEEKDAYS[parseDate(iso).getDay()].slice(0, 3);
  }

  // "Today", "Tomorrow" or "Mon, Oct 5".
  function formatDay(iso, now) {
    const today = isoDate(now);
    if (iso === today) return 'Today';
    if (iso === addDays(today, 1)) return 'Tomorrow';
    const d = parseDate(iso);
    return `${WEEKDAYS[d.getDay()].slice(0, 3)}, ${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}`;
  }

  // "Monday, October 5, 2026".
  function formatLongDate(iso) {
    const d = parseDate(iso);
    return `${WEEKDAYS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
  }

  function formatMonth(iso) {
    const d = parseDate(iso);
    return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  }

  // "Mon, Oct 5 · 9:30 AM".
  function formatSlot(key, now) {
    const { date, time } = splitKey(key);
    return `${formatDay(date, now)} · ${formatTime(time)}`;
  }

  const api = {
    hash32, rngFor, isoDate, parseDate, addDays, toMinutes, fromMinutes, slotKey, splitKey, isSlotKey,
    slotStart, doctorById, specialtyById, doctorsIn, workingHours, daySchedule, isUpcoming, overlaps,
    slotsFor, bookingDates, openCount, nextAvailable, isBookable, confirmationCode, formatTime,
    formatTimeRange, weekdayShort, formatDay, formatLongDate, formatMonth, formatSlot, MONTHS, WEEKDAYS,
  };
  if (isNode) module.exports = api;
  else root.ClinicSchedule = api;
})(typeof window !== 'undefined' ? window : globalThis);
