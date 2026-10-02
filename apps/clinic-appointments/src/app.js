// Linden Clinic: screens, routing and event handling.
//
// Routes (URL hash):
//   #/doctors                    DoctorList
//   #/book/:doctor[?date=|slot=] TimeSlot
//   #/review/:doctor/:slot       Review
//   #/confirmed/:appointment     Confirmation
//   #/appointments               upcoming, past and cancelled visits
(function () {
  'use strict';

  const { CLINIC, SPECIALTIES, DOCTORS } = window.ClinicData;
  const S = window.ClinicSchedule;
  const Store = window.ClinicStore;

  const storage = (() => {
    try {
      return window.localStorage;
    } catch (err) {
      return null;
    }
  })();

  const state = {
    appointments: Store.load(storage),
    specialty: 'all',
    selectedDoctorId: null,
    reasons: {}, // slot key -> text typed on Review
    sheet: null, // { type: 'cancel', id }
    lastRoute: null,
  };

  const $screen = document.getElementById('screen');
  const $dock = document.getElementById('dock');
  const $sheet = document.getElementById('sheet-root');
  const $toast = document.getElementById('toast');

  const now = () => new Date();
  const ctx = () => ({ now: now(), appointments: state.appointments });

  // ---- helpers -----------------------------------------------------------

  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ESC[c]);

  const ICONS = {
    back: '<path d="M15 18l-6-6 6-6"/>',
    next: '<path d="M9 18l6-6-6-6"/>',
    check: '<path d="M20 6L9 17l-5-5"/>',
    close: '<path d="M18 6L6 18M6 6l12 12"/>',
    calendar: '<rect x="3" y="4.5" width="18" height="16.5" rx="3"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/>',
    calendarCheck: '<rect x="3" y="4.5" width="18" height="16.5" rx="3"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4M9 15l2 2 4-4"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
    pin: '<path d="M12 21.5s-7-6.1-7-11.6a7 7 0 0 1 14 0c0 5.5-7 11.6-7 11.6z"/><circle cx="12" cy="9.8" r="2.6"/>',
    star: '<path d="M12 3.2l2.7 5.5 6 .9-4.35 4.25 1.03 6L12 17l-5.38 2.85 1.03-6L3.3 9.6l6-.9z" fill="currentColor" stroke="none"/>',
    stethoscope: '<path d="M6 3.5H4.8v5.2a4.7 4.7 0 0 0 9.4 0V3.5H13"/><path d="M9.5 13.4v1.4a4.8 4.8 0 0 0 9.6 0v-2.4"/><circle cx="19.1" cy="10.4" r="2"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.6v.4"/>',
    visit: '<path d="M4 20.5v-1a5 5 0 0 1 5-5h6a5 5 0 0 1 5 5v1"/><circle cx="12" cy="7.5" r="4"/>',
    note: '<path d="M14.5 4.5l5 5L9 20H4v-5z"/><path d="M12.5 6.5l5 5"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.6 3.8 5.6 3.8 9s-1.2 6.4-3.8 9c-2.6-2.6-3.8-5.6-3.8-9S9.4 5.6 12 3z"/>',
    leaf: '<path d="M5.5 18.5C5.5 10.3 10.6 5 19 5c0 8.4-5.3 13.5-13.5 13.5z"/><path d="M5.5 18.5L13 11"/>',
  };

  function icon(name, cls) {
    return `<svg class="icon${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[name]}</svg>`;
  }

  function initials(doctor) {
    return doctor.name
      .replace(/^Dr\.\s*/, '')
      .split(/\s+/)
      .map((p) => p[0])
      .join('')
      .slice(0, 2);
  }

  function avatar(doctor, size) {
    return `<span class="avatar${size ? ' avatar-' + size : ''}" style="--hue:${doctor.hue}" aria-hidden="true">${esc(initials(doctor))}</span>`;
  }

  function plural(n, one, many) {
    return `${n} ${n === 1 ? one : many || one + 's'}`;
  }

  function shortDate(iso) {
    const d = S.parseDate(iso);
    return `${S.WEEKDAYS[d.getDay()].slice(0, 3)}, ${S.MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}`;
  }

  function brand() {
    return `<div class="brand"><span class="brand-mark">${icon('leaf')}</span><span>${esc(CLINIC.name)}</span></div>`;
  }

  // ---- routing -----------------------------------------------------------

  function parseRoute() {
    const raw = location.hash.replace(/^#\/?/, '');
    const [path, query] = raw.split('?');
    const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
    const params = new URLSearchParams(query || '');
    const [name, a, b] = parts;
    if (name === 'book' && a) return { name: 'time', doctorId: a, date: params.get('date'), slot: params.get('slot') };
    if (name === 'review' && a && b) return { name: 'review', doctorId: a, slot: b };
    if (name === 'confirmed' && a) return { name: 'confirmed', id: a };
    if (name === 'appointments') return { name: 'appointments' };
    return { name: 'doctors' };
  }

  function go(hash, { replace } = {}) {
    if (replace) location.replace(hash);
    else location.hash = hash;
  }

  // Update the address without a new history entry or a hashchange render.
  function setHashQuietly(hash) {
    history.replaceState(history.state, '', hash);
  }

  const timeHash = (doctorId, q) => `#/book/${encodeURIComponent(doctorId)}${q ? '?' + q : ''}`;
  const reviewHash = (doctorId, slot) => `#/review/${encodeURIComponent(doctorId)}/${encodeURIComponent(slot)}`;

  // ---- DoctorList --------------------------------------------------------

  function viewDoctors() {
    const c = ctx();
    const list = S.doctorsIn(state.specialty);
    const spec = S.specialtyById(state.specialty);
    const chips = [{ id: 'all', name: 'All' }].concat(SPECIALTIES);
    return `
      <div class="view">
        <header class="page-head">
          ${brand()}
          <h1 tabindex="-1">Find a doctor</h1>
          <p class="lede">Browse by specialty, choose a doctor and book a visit.</p>
        </header>
        <div class="chips" role="radiogroup" aria-label="Specialty" data-keep-scroll="chips">
          ${chips
            .map((s) => {
              const on = state.specialty === s.id;
              return `<button type="button" class="chip" role="radio" aria-checked="${on}" data-action="specialty" data-id="${s.id}" data-key="chip-${s.id}">${esc(s.name)}</button>`;
            })
            .join('')}
        </div>
        <div class="list-head">
          <h2>${spec ? esc(spec.name) : 'All specialties'}</h2>
          <span>${plural(list.length, 'doctor')}</span>
        </div>
        <ul class="doctor-list" role="radiogroup" aria-label="Doctors">
          ${list.map((d) => doctorCard(d, c)).join('')}
        </ul>
      </div>`;
  }

  function doctorCard(d, c) {
    const on = state.selectedDoctorId === d.id;
    const next = S.nextAvailable(d, c);
    return `
      <li>
        <button type="button" class="doctor-card" role="radio" aria-checked="${on}" data-action="select-doctor" data-id="${d.id}" data-key="doc-${d.id}">
          ${avatar(d)}
          <span class="doctor-body">
            <span class="doctor-name">${esc(d.name)}</span>
            <span class="doctor-role">${esc(d.title)} · ${d.years} years</span>
            <span class="doctor-meta"><span class="rating">${icon('star')}${d.rating.toFixed(1)}</span><span class="muted">(${d.reviews})</span><span class="sep">·</span><span>Room ${esc(d.room)}</span></span>
          </span>
          <span class="radio" aria-hidden="true">${icon('check')}</span>
          <span class="doctor-next${next ? '' : ' is-none'}">
            ${icon('clock')}<span>Next available</span><strong>${next ? esc(S.formatSlot(next, c.now)) : 'No open times'}</strong>
          </span>
        </button>
      </li>`;
  }

  function dockDoctors(enter) {
    const d = S.doctorById(state.selectedDoctorId);
    let sel = '';
    if (d) {
      const next = S.nextAvailable(d, ctx());
      sel = `
        <section class="selbar${enter ? ' enter' : ''}" aria-label="Selected doctor">
          <div class="selbar-head">
            ${avatar(d, 'sm')}
            <div class="selbar-text">
              <strong>${esc(d.name)}</strong>
              <span>${next ? 'Next available: ' + esc(S.formatSlot(next, now())) : 'No open times in the next two weeks'}</span>
            </div>
            <button type="button" class="icon-btn" data-action="clear-selection" data-key="clear-selection" aria-label="Clear selection">${icon('close')}</button>
          </div>
          <div class="selbar-actions">
            <button type="button" class="btn btn-secondary" data-action="book-next" data-key="book-next"${next ? '' : ' disabled'}>Book next available</button>
            <button type="button" class="btn btn-primary" data-action="choose-time" data-key="choose-time">Choose a time${icon('next')}</button>
          </div>
        </section>`;
    }
    return sel + tabbar('doctors');
  }

  function tabbar(active) {
    const count = Store.upcoming(state.appointments, now()).length;
    const tab = (id, href, ic, label, extra) =>
      `<a class="tab" href="${href}" data-key="tab-${id}"${active === id ? ' aria-current="page"' : ''}>${icon(ic)}<span>${label}</span>${extra || ''}</a>`;
    return `
      <nav class="tabbar" aria-label="Main">
        ${tab('doctors', '#/doctors', 'stethoscope', 'Doctors')}
        ${tab('appointments', '#/appointments', 'calendarCheck', 'Appointments', count ? `<span class="badge" aria-label="${plural(count, 'upcoming appointment')}">${count}</span>` : '')}
      </nav>`;
  }

  // ---- TimeSlot ----------------------------------------------------------

  // Picks the date and slot TimeSlot shows: a valid ?slot= wins, then ?date=,
  // then the day of the doctor's next open slot.
  function timeSelection(route, d, c) {
    const dates = S.bookingDates(c.now);
    if (route.slot && S.isBookable(d, route.slot, c)) return { date: S.splitKey(route.slot).date, slot: route.slot };
    if (route.date && dates.includes(route.date)) return { date: route.date, slot: null };
    const next = S.nextAvailable(d, c);
    return { date: next ? S.splitKey(next).date : dates[0], slot: null };
  }

  function flowHead(backHref, backLabel, step) {
    return `
      <header class="flow-head">
        <a class="back" href="${backHref}" data-key="back" aria-label="${esc(backLabel)}">${icon('back')}</a>
        <div class="steps" aria-hidden="true"><span class="on"></span><span${step > 1 ? ' class="on"' : ''}></span></div>
        <span class="step-label">Step ${step} of 2</span>
      </header>`;
  }

  function doctorStrip(d) {
    const spec = S.specialtyById(d.specialty);
    return `
      <div class="doctor-strip">
        ${avatar(d, 'sm')}
        <div>
          <strong>${esc(d.name)}</strong>
          <span>${esc(spec ? spec.name : d.title)} · Room ${esc(d.room)}</span>
        </div>
      </div>`;
  }

  function viewTime(route) {
    const d = S.doctorById(route.doctorId);
    if (!d) return viewMissing('We couldn’t find that doctor.', '#/doctors', 'Back to doctors');
    const c = ctx();
    const sel = timeSelection(route, d, c);
    const dates = S.bookingDates(c.now);
    const slots = S.slotsFor(d, sel.date, c);
    const open = slots.filter((s) => s.state === 'open').length;
    const morning = slots.filter((s) => S.toMinutes(s.time) < 12 * 60);
    const afternoon = slots.filter((s) => S.toMinutes(s.time) >= 12 * 60);

    const dayButtons = dates
      .map((iso) => {
        const n = S.openCount(d, iso, c);
        const works = S.workingHours(d, iso) !== null;
        const on = iso === sel.date;
        const dd = S.parseDate(iso);
        const note = n ? `${n} open` : works ? 'Full' : 'Off';
        return `<button type="button" class="day${n ? '' : ' is-empty'}" role="radio" aria-checked="${on}" data-action="select-date" data-date="${iso}" data-key="day-${iso}" aria-label="${esc(S.formatLongDate(iso))}, ${note}">
            <span class="dow">${iso === dates[0] ? 'Today' : S.weekdayShort(iso)}</span>
            <span class="dom">${dd.getDate()}</span>
            <span class="cnt">${note}</span>
          </button>`;
      })
      .join('');

    const slotButton = (s) => {
      const label = S.formatTime(s.time);
      if (s.state === 'open') {
        const on = s.key === sel.slot;
        return `<button type="button" class="slot" role="radio" aria-checked="${on}" data-action="select-slot" data-slot="${s.key}" data-key="slot-${s.key}">${on ? icon('check') : ''}${label}</button>`;
      }
      const why = { taken: 'booked', yours: 'your appointment', conflict: 'you have another visit' }[s.state];
      return `<button type="button" class="slot is-${s.state}" disabled aria-label="${label}, ${why}">${label}${s.state === 'yours' ? '<small>Your visit</small>' : ''}</button>`;
    };

    const group = (title, list) =>
      list.length
        ? `<div class="slot-group">
            <h3>${title}<span>${list.filter((s) => s.state === 'open').length} open</span></h3>
            <div class="slot-grid" role="radiogroup" aria-label="${title} times">${list.map(slotButton).join('')}</div>
          </div>`
        : '';

    let body;
    if (!slots.length) {
      const works = S.workingHours(d, sel.date) !== null;
      body = `<div class="empty-inline">${icon('calendar')}<p>${works ? 'No more times today.' : `${esc(d.name)} doesn’t see patients on ${S.WEEKDAYS[S.parseDate(sel.date).getDay()]}s.`} Pick another day.</p></div>`;
    } else {
      body = group('Morning', morning) + group('Afternoon', afternoon);
      if (!open) body = `<p class="notice notice-warn">${icon('info')}<span>This day is fully booked. Pick another day.</span></p>` + body;
    }

    return `
      <div class="view">
        ${flowHead('#/doctors', 'Back to doctors', 1)}
        <h1 tabindex="-1">Choose a time</h1>
        ${doctorStrip(d)}
        <section class="dates" aria-label="Date">
          <div class="section-row"><h2>${esc(S.formatMonth(sel.date))}</h2><span>Next 2 weeks</span></div>
          <div class="datestrip" role="radiogroup" aria-label="Date" data-keep-scroll="dates">${dayButtons}</div>
        </section>
        <section class="times" aria-label="Times">
          <div class="section-row"><h2>${esc(S.formatLongDate(sel.date).replace(/, \d{4}$/, ''))}</h2><span>${CLINIC.visitMinutes}-min visits</span></div>
          ${body}
          <div class="legend" aria-hidden="true"><span><i class="key key-open"></i>Available</span><span><i class="key key-taken"></i>Booked</span><span><i class="key key-on"></i>Selected</span></div>
        </section>
      </div>`;
  }

  function dockTime(route) {
    const d = S.doctorById(route.doctorId);
    if (!d) return '';
    const sel = timeSelection(route, d, ctx());
    return `
      <div class="actionbar">
        <div class="actionbar-summary">
          <span>Selected time</span>
          <strong>${sel.slot ? esc(S.formatSlot(sel.slot, now())) : 'None yet'}</strong>
        </div>
        <button type="button" class="btn btn-primary" data-action="to-review" data-key="to-review"${sel.slot ? '' : ' disabled'}>Review appointment</button>
      </div>`;
  }

  // ---- Review ------------------------------------------------------------

  function viewReview(route) {
    const d = S.doctorById(route.doctorId);
    if (!d || !S.isSlotKey(route.slot)) return viewMissing('This booking link is incomplete.', '#/doctors', 'Back to doctors');
    const c = ctx();
    const ok = S.isBookable(d, route.slot, c);
    const { date } = S.splitKey(route.slot);
    const spec = S.specialtyById(d.specialty);
    const back = timeHash(d.id, ok ? 'slot=' + encodeURIComponent(route.slot) : 'date=' + date);
    const reason = state.reasons[route.slot] || '';
    return `
      <div class="view">
        ${flowHead(back, 'Back to times', 2)}
        <h1 tabindex="-1">Review appointment</h1>
        <p class="lede">Check the details below before you confirm.</p>
        ${ok ? '' : `<p class="notice notice-warn">${icon('info')}<span>This time is no longer available. Go back and choose another one.</span></p>`}
        <section class="card review-card" aria-label="Appointment details">
          <div class="review-doctor">
            ${avatar(d, 'lg')}
            <div>
              <strong>${esc(d.name)}</strong>
              <span>${esc(d.title)} · ${esc(spec ? spec.name : '')}</span>
              <span class="doctor-meta"><span class="rating">${icon('star')}${d.rating.toFixed(1)}</span><span class="muted">(${d.reviews} reviews)</span></span>
            </div>
          </div>
          <dl class="details">
            <div class="detail">
              <span class="detail-icon">${icon('calendar')}</span>
              <div><dt>Date</dt><dd>${esc(S.formatLongDate(date))}</dd></div>
            </div>
            <div class="detail">
              <span class="detail-icon">${icon('clock')}</span>
              <div><dt>Time · ${CLINIC.visitMinutes} minutes</dt><dd>${esc(S.formatTimeRange(route.slot))}</dd></div>
              <a class="detail-link" href="${back}" data-key="change-time">Change</a>
            </div>
            <div class="detail">
              <span class="detail-icon">${icon('pin')}</span>
              <div><dt>Location · ${esc(CLINIC.name)}</dt><dd>Room ${esc(d.room)}, ${esc(d.floor)}</dd></div>
            </div>
            <div class="detail">
              <span class="detail-icon">${icon('visit')}</span>
              <div><dt>Visit type</dt><dd>In-person consultation</dd></div>
            </div>
          </dl>
        </section>
        <label class="field">
          <span class="field-label">Reason for visit <span class="muted">(optional)</span></span>
          <textarea rows="2" maxlength="300" data-input="reason" data-slot="${route.slot}" data-key="reason" placeholder="For example, a follow-up on test results">${esc(reason)}</textarea>
        </label>
        <p class="notice">${icon('info')}<span>Please arrive 10 minutes early. You can cancel any time before the visit from Appointments.</span></p>
      </div>`;
  }

  function dockReview(route) {
    const d = S.doctorById(route.doctorId);
    if (!d || !S.isSlotKey(route.slot)) return '';
    const ok = S.isBookable(d, route.slot, ctx());
    return `
      <div class="actionbar actionbar-stack">
        <button type="button" class="btn btn-primary btn-lg btn-block" data-action="confirm" data-key="confirm"${ok ? '' : ' disabled'}>Confirm appointment</button>
      </div>`;
  }

  // ---- Confirmation ------------------------------------------------------

  function viewConfirmed(route) {
    const a = state.appointments.find((x) => x.id === route.id);
    const d = a && S.doctorById(a.doctorId);
    if (!a || !d) return viewMissing('We couldn’t find that appointment.', '#/appointments', 'View my appointments');
    const { date, time } = S.splitKey(a.start);
    const spec = S.specialtyById(d.specialty);
    const cancelled = a.status === 'cancelled';
    return `
      <div class="view view-confirmed">
        <div class="success${cancelled ? ' is-cancelled' : ''}">
          <div class="success-badge" aria-hidden="true">
            <svg viewBox="0 0 52 52"><circle class="ring" cx="26" cy="26" r="24"/><path class="tick" d="M15 27l7.5 7.5L37.5 19"/></svg>
          </div>
          <h1 tabindex="-1">${cancelled ? 'Appointment cancelled' : 'Appointment confirmed'}</h1>
          <p class="lede">${cancelled ? 'This visit was cancelled.' : `You’re booked with ${esc(d.name)}.`}</p>
        </div>
        <section class="card ticket" aria-label="Appointment summary">
          <div class="ticket-doctor">
            ${avatar(d)}
            <div><strong>${esc(d.name)}</strong><span>${esc(d.title)} · ${esc(spec ? spec.name : '')}</span></div>
          </div>
          <div class="ticket-grid">
            <div><span>Date</span><strong>${esc(shortDate(date))}</strong></div>
            <div><span>Time</span><strong>${esc(S.formatTime(time))}</strong></div>
            <div><span>Location</span><strong>Room ${esc(d.room)}</strong><em>${esc(d.floor)}</em></div>
            <div><span>Confirmation no.</span><strong class="code">${esc(a.code)}</strong></div>
          </div>
        </section>
        <p class="fineprint">Please arrive 10 minutes early. Need to change plans? You can cancel from Appointments.</p>
        <div class="stack">
          <a class="btn btn-primary btn-block" href="#/appointments" data-key="to-appointments">View my appointments</a>
          <a class="btn btn-ghost btn-block" href="#/doctors" data-key="to-doctors">Back to doctors</a>
        </div>
      </div>`;
  }

  // ---- Appointments ------------------------------------------------------

  function apptCard(a, past) {
    const d = S.doctorById(a.doctorId);
    const { date } = S.splitKey(a.start);
    const dd = S.parseDate(date);
    const n = now();
    const isToday = date === S.isoDate(n);
    const tag = a.status === 'cancelled' ? '<span class="tag tag-muted">Cancelled</span>' : past ? '<span class="tag tag-muted">Completed</span>' : isToday ? '<span class="tag">Today</span>' : '';
    return `
      <li class="appt-card${past ? ' is-past' : ''}">
        <div class="appt-date" aria-hidden="true">
          <span>${S.MONTHS[dd.getMonth()].slice(0, 3)}</span>
          <strong>${dd.getDate()}</strong>
          <span>${S.weekdayShort(date)}</span>
        </div>
        <div class="appt-body">
          <div class="appt-title"><strong>${esc(d.name)}</strong>${tag}</div>
          <span class="appt-role">${esc(d.title)}</span>
          <span class="appt-meta">${icon('clock')}${esc(shortDate(date))} · ${esc(S.formatTimeRange(a.start, a.minutes))}</span>
          <span class="appt-meta">${icon('pin')}Room ${esc(d.room)} · ${esc(d.floor)}</span>
          ${a.reason ? `<span class="appt-meta">${icon('note')}${esc(a.reason)}</span>` : ''}
        </div>
        ${
          past
            ? ''
            : `<div class="appt-foot">
                <span class="code">${esc(a.code)}</span>
                <button type="button" class="btn btn-danger-soft btn-sm" data-action="ask-cancel" data-id="${esc(a.id)}" data-key="cancel-${esc(a.id)}">Cancel appointment</button>
              </div>`
        }
      </li>`;
  }

  function viewAppointments() {
    const n = now();
    const up = Store.upcoming(state.appointments, n);
    const hist = Store.history(state.appointments, n);
    return `
      <div class="view">
        <header class="page-head">
          ${brand()}
          <h1 tabindex="-1">Appointments</h1>
          <p class="lede">Your visits at ${esc(CLINIC.name)}.</p>
        </header>
        <section aria-label="Upcoming appointments">
          <div class="list-head"><h2>Upcoming</h2><span>${plural(up.length, 'visit')}</span></div>
          ${
            up.length
              ? `<ul class="appt-list">${up.map((a) => apptCard(a, false)).join('')}</ul>`
              : `<div class="empty">
                  <span class="empty-icon">${icon('calendar')}</span>
                  <strong>No upcoming appointments</strong>
                  <p>Find a doctor and pick a time that suits you.</p>
                  <a class="btn btn-primary" href="#/doctors" data-key="empty-find">Find a doctor</a>
                </div>`
          }
        </section>
        ${
          hist.length
            ? `<section aria-label="Past and cancelled appointments">
                <div class="list-head"><h2>Past and cancelled</h2><span>${plural(hist.length, 'visit')}</span></div>
                <ul class="appt-list">${hist.map((a) => apptCard(a, true)).join('')}</ul>
              </section>`
            : ''
        }
      </div>`;
  }

  function viewMissing(message, href, label) {
    return `
      <div class="view">
        <div class="empty empty-page">
          <span class="empty-icon">${icon('info')}</span>
          <h1 tabindex="-1">Not found</h1>
          <p>${esc(message)}</p>
          <a class="btn btn-primary" href="${href}">${esc(label)}</a>
        </div>
      </div>`;
  }

  // ---- sheet and toast ---------------------------------------------------

  function renderSheet() {
    const s = state.sheet;
    const a = s && state.appointments.find((x) => x.id === s.id);
    if (!a) {
      $sheet.innerHTML = '';
      return;
    }
    const d = S.doctorById(a.doctorId);
    $sheet.innerHTML = `
      <div class="sheet-backdrop" data-action="close-sheet"></div>
      <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title" aria-describedby="sheet-desc">
        <span class="sheet-grip" aria-hidden="true"></span>
        <h2 id="sheet-title">Cancel this appointment?</h2>
        <p id="sheet-desc"><strong>${esc(d.name)}</strong> · ${esc(S.formatSlot(a.start, now()))}<br>The time will be released for other patients.</p>
        <div class="stack">
          <button type="button" class="btn btn-danger btn-block" data-action="confirm-cancel" data-id="${esc(a.id)}">Cancel appointment</button>
          <button type="button" class="btn btn-ghost btn-block" data-action="close-sheet">Keep appointment</button>
        </div>
      </div>`;
    const first = $sheet.querySelector('.sheet .btn-ghost');
    if (first) first.focus({ preventScroll: true });
  }

  let toastTimer = 0;
  function toast(message) {
    $toast.textContent = message;
    $toast.classList.add('is-on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $toast.classList.remove('is-on'), 3200);
  }

  // ---- render ------------------------------------------------------------

  const VIEWS = {
    doctors: [viewDoctors, (r, enter) => dockDoctors(enter)],
    time: [viewTime, dockTime],
    review: [viewReview, dockReview],
    confirmed: [viewConfirmed, () => ''],
    appointments: [viewAppointments, () => tabbar('appointments')],
  };

  const TITLES = {
    doctors: 'Find a doctor',
    time: 'Choose a time',
    review: 'Review appointment',
    confirmed: 'Appointment confirmed',
    appointments: 'Appointments',
  };

  // Re-renders the current route. A route change animates in, scrolls to the
  // top and moves focus to the heading; an update inside the same screen keeps
  // scroll positions and the focused control.
  function render(opts) {
    const route = parseRoute();
    const key = location.hash.split('?')[0] || '#/doctors';
    const changed = key !== state.lastRoute;
    state.lastRoute = key;

    const scrolls = {};
    document.querySelectorAll('[data-keep-scroll]').forEach((el) => (scrolls[el.dataset.keepScroll] = el.scrollLeft));
    const active = document.activeElement;
    const focusKey = !changed && active && active.dataset ? active.dataset.key : null;

    const [view, dock] = VIEWS[route.name];
    $screen.innerHTML = view(route);
    $dock.innerHTML = dock(route, opts && opts.enter);
    $dock.hidden = !$dock.innerHTML.trim();
    document.title = `${TITLES[route.name]} · ${CLINIC.name}`;

    const viewEl = $screen.firstElementChild;
    if (changed) {
      viewEl.classList.add('is-entering');
      window.scrollTo(0, 0);
    } else {
      document.querySelectorAll('[data-keep-scroll]').forEach((el) => {
        if (scrolls[el.dataset.keepScroll] != null) el.scrollLeft = scrolls[el.dataset.keepScroll];
      });
    }
    fitDock();

    if (changed) {
      if (route.name === 'time') revealSelected('.datestrip', '.day[aria-checked="true"]');
      const h1 = $screen.querySelector('h1');
      if (h1 && state.lastRoute && document.body.dataset.ready) h1.focus({ preventScroll: true });
    } else if (focusKey) {
      const el = document.querySelector(`[data-key="${CSS.escape(focusKey)}"]`);
      if (el && !el.disabled) el.focus({ preventScroll: true });
    }
    document.body.dataset.route = route.name;
    document.body.dataset.ready = '1';
  }

  // Keeps the chosen day in view inside a horizontal strip.
  function revealSelected(stripSel, itemSel) {
    const strip = $screen.querySelector(stripSel);
    const item = strip && strip.querySelector(itemSel);
    if (!strip || !item) return;
    const left = item.offsetLeft - strip.offsetLeft;
    if (left + item.offsetWidth > strip.scrollLeft + strip.clientWidth || left < strip.scrollLeft) {
      strip.scrollLeft = Math.max(0, left - 20);
    }
  }

  // Leaves room under the content for whatever the dock is showing.
  function fitDock() {
    const h = $dock.hidden ? 0 : $dock.offsetHeight;
    document.documentElement.style.setProperty('--dock-h', h + 'px');
  }

  function persist() {
    Store.save(storage, state.appointments);
  }

  // ---- actions -----------------------------------------------------------

  const actions = {
    specialty(el) {
      state.specialty = el.dataset.id;
      const sel = S.doctorById(state.selectedDoctorId);
      if (sel && state.specialty !== 'all' && sel.specialty !== state.specialty) state.selectedDoctorId = null;
      render();
    },
    'select-doctor'(el) {
      const was = state.selectedDoctorId;
      state.selectedDoctorId = was === el.dataset.id ? null : el.dataset.id;
      render({ enter: !was && !!state.selectedDoctorId });
    },
    'clear-selection'() {
      const id = state.selectedDoctorId;
      state.selectedDoctorId = null;
      render();
      const card = id && document.querySelector(`[data-key="doc-${CSS.escape(id)}"]`);
      if (card) card.focus({ preventScroll: true });
    },
    'choose-time'() {
      if (state.selectedDoctorId) go(timeHash(state.selectedDoctorId));
    },
    // One tap from the doctor list: books the earliest open slot and goes
    // straight to Confirmation, without TimeSlot or Review.
    'book-next'() {
      const d = S.doctorById(state.selectedDoctorId);
      if (!d) return;
      const slot = S.nextAvailable(d, ctx());
      if (!slot) return;
      bookAndConfirm(d.id, slot, '', 'next-available');
    },
    'select-date'(el) {
      const route = parseRoute();
      setHashQuietly(timeHash(route.doctorId, 'date=' + el.dataset.date));
      render();
    },
    'select-slot'(el) {
      const route = parseRoute();
      setHashQuietly(timeHash(route.doctorId, 'slot=' + encodeURIComponent(el.dataset.slot)));
      render();
    },
    'to-review'() {
      const route = parseRoute();
      const d = S.doctorById(route.doctorId);
      const sel = d && timeSelection(route, d, ctx());
      if (sel && sel.slot) go(reviewHash(d.id, sel.slot));
    },
    confirm() {
      const route = parseRoute();
      bookAndConfirm(route.doctorId, route.slot, state.reasons[route.slot] || '', 'review');
    },
    'ask-cancel'(el) {
      state.sheet = { type: 'cancel', id: el.dataset.id, returnKey: el.dataset.key };
      renderSheet();
    },
    'close-sheet'() {
      closeSheet();
    },
    'confirm-cancel'(el) {
      state.appointments = Store.cancel(state.appointments, el.dataset.id, now());
      persist();
      state.sheet = null;
      renderSheet();
      render();
      toast('Appointment cancelled. The time is free again.');
      const h = $screen.querySelector('.list-head h2');
      if (h) h.setAttribute('tabindex', '-1'), h.focus({ preventScroll: true });
    },
  };

  function bookAndConfirm(doctorId, slot, reason, via) {
    try {
      const res = Store.book(state.appointments, { doctorId, start: slot, reason, via, now: now() });
      state.appointments = res.list;
      persist();
      state.selectedDoctorId = null;
      delete state.reasons[slot];
      go('#/confirmed/' + encodeURIComponent(res.appointment.id), { replace: via === 'review' });
    } catch (err) {
      toast(err.message || 'That time could not be booked.');
      render();
    }
  }

  function closeSheet() {
    const key = state.sheet && state.sheet.returnKey;
    state.sheet = null;
    renderSheet();
    const el = key && document.querySelector(`[data-key="${CSS.escape(key)}"]`);
    if (el) el.focus({ preventScroll: true });
  }

  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-action]');
    if (!el || el.disabled) return;
    const fn = actions[el.dataset.action];
    if (fn) {
      e.preventDefault();
      fn(el);
    }
  });

  document.addEventListener('input', (e) => {
    const el = e.target;
    if (el.dataset && el.dataset.input === 'reason') state.reasons[el.dataset.slot] = el.value;
  });

  document.addEventListener('keydown', (e) => {
    if (!state.sheet) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeSheet();
    } else if (e.key === 'Tab') {
      const items = [...$sheet.querySelectorAll('.sheet button')];
      const i = items.indexOf(document.activeElement);
      const j = e.shiftKey ? (i <= 0 ? items.length - 1 : i - 1) : i === items.length - 1 ? 0 : i + 1;
      e.preventDefault();
      items[j].focus();
    }
  });

  window.addEventListener('hashchange', () => {
    state.sheet = null;
    renderSheet();
    render();
  });

  window.addEventListener('storage', (e) => {
    if (e.key !== Store.STORAGE_KEY) return;
    state.appointments = Store.load(storage);
    render();
  });

  window.addEventListener('resize', fitDock);

  render();
})();
