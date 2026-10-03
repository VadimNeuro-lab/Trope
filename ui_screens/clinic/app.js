// Set C - clinic booking "Linden Clinic". Five screens + confirmation state, two variants:
//   improved - guided 4-step flow, large actions, full details on every step
//   weak     - same flow and data in a plainer list UI with weaker hierarchy and smaller controls
(function () {
  const { icon, statusBar, homeIndicator, tabbar } = K;
  const TIME = '9:41';

  const TABS = [
    { key: 'home', label: 'Home', icon: 'house' },
    { key: 'appointments', label: 'Appointments', icon: 'calendar-days' },
    { key: 'messages', label: 'Messages', icon: 'message-circle' },
    { key: 'profile', label: 'Profile', icon: 'user' },
  ];
  const shell = (body, active) => `<div class="screen">${statusBar(TIME)}${body}${active ? tabbar(TABS, active) : ''}${homeIndicator()}</div>`;

  const DOCS = [
    { name: 'Dr. Emily Hart', ini: 'EH', bg: '#DDF0EC', fg: '#0F766E', rating: '4.9', reviews: 128, years: 12, next: 'Tue 13 Oct, 09:30' },
    { name: 'Dr. Rahul Mehta', ini: 'RM', bg: '#E3ECFA', fg: '#1D4ED8', rating: '4.8', reviews: 94, years: 9, next: 'Wed 14 Oct, 11:00' },
    { name: 'Dr. Laura Chen', ini: 'LC', bg: '#FBEEDB', fg: '#B45309', rating: '4.7', reviews: 61, years: 15, next: 'Fri 16 Oct, 14:30' },
  ];
  const DOC = DOCS[0];
  const UPCOMING = [
    { doc: 'Dr. James Okafor', spec: 'General Practice', dow: 'TUE', day: 6, date: 'Tue, 6 Oct', time: '09:15', place: 'Floor 2, Room 204' },
    { doc: 'Dr. Sophie Laurent', spec: 'Ophthalmology', dow: 'THU', day: 22, date: 'Thu, 22 Oct', time: '14:00', place: 'Floor 1, Room 112' },
  ];
  const ADDRESS = 'Linden Clinic, 24 Harbour Street, Floor 3';
  const navBar = (t) => `<div class="w-nav"><span class="l">${icon('chevron-left', { size: 26, sw: 2.2 })}</span>${t}</div>`;
  const wChev = `<span style="color:#A9B6B9">${icon('chevron-right', { size: 18, sw: 2 })}</span>`;
  const avatar = (d, size = 56) => `<div class="avatar" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.34)}px;background:${d.bg};color:${d.fg}">${d.ini}</div>`;
  const flowHead = (step) => `
    <div class="flowbar"><span class="back">${icon('arrow-left', { size: 22, sw: 2.2 })}</span><span class="step">Step ${step} of 4</span></div>
    <div class="steps">${[1, 2, 3, 4].map((i) => `<i class="${i <= step ? 'on' : ''}"></i>`).join('')}</div>`;

  // ---------------- HOME ----------------
  const home = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        <div class="topline"><div class="brand" style="font-size:15.5px"><span class="logo" style="width:30px;height:30px;border-radius:9px">${icon('leaf', { size: 16, sw: 2.2 })}</span>Linden Clinic</div><div class="avatar" style="width:34px;height:34px;font-size:12.5px;background:var(--primary-soft);color:var(--primary)">SM</div></div>
        <h1 style="font-size:23px;font-weight:700;margin-top:18px;letter-spacing:-0.3px">Hello, Sarah</h1>
        <button class="btn-primary w-btn" style="margin-top:14px">${icon('calendar-plus', { size: 18, sw: 2.2 })}Book appointment</button>
        <p class="w-cap">Upcoming</p>
        <div class="card w-box">
          ${UPCOMING.map((u) => `<div class="w-li"><div style="flex:1"><b>${u.doc}</b><small>${u.spec} · ${u.date}, ${u.time}</small></div>${wChev}</div>`).join('')}
        </div>
        <p class="w-cap">Services</p>
        <div class="card w-box">
          <div class="w-li">${icon('stethoscope', { size: 20, sw: 2, style: 'color:var(--primary)' })}<b style="flex:1">Doctors</b>${wChev}</div>
          <div class="w-li">${icon('calendar-days', { size: 20, sw: 2, style: 'color:var(--primary)' })}<b style="flex:1">Appointments</b>${wChev}</div>
          <div class="w-li">${icon('message-circle', { size: 20, sw: 2, style: 'color:var(--primary)' })}<b style="flex:1">Messages</b><span class="w-badge">2</span>${wChev}</div>
        </div>
      </div>`, 'home');
    }
    return shell(`
    <div class="content">
      <div class="topline">
        <div class="brand"><span class="logo">${icon('leaf', { size: 20, sw: 2.2 })}</span>Linden Clinic</div>
        <div class="avatar" style="width:42px;height:42px;font-size:15px;background:var(--primary-soft);color:var(--primary)">SM</div>
      </div>
      <div class="hello"><h1 class="h1">Good morning, Sarah</h1><p class="lead">How can we help you today?</p></div>
      <div class="cta">
        <span class="ci">${icon('calendar-plus', { size: 24, sw: 2.2 })}</span>
        <div style="flex:1"><b>Book appointment</b><small>Choose a specialist and a time</small></div>
        ${icon('chevron-right', { size: 24, sw: 2.4 })}
      </div>
      <section style="margin-top:24px">
        <div class="sec-head"><h3>Upcoming appointments</h3><span>See all</span></div>
        ${UPCOMING.map((u) => `
        <div class="card appt">
          <div class="dateblock"><small>${u.dow}</small><b>${u.day}</b><small>OCT</small></div>
          <div style="flex:1;min-width:0">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px"><h4>${u.doc}</h4><span class="status">Confirmed</span></div>
            <div class="spec">${u.spec}</div>
            <div class="when"><span>${icon('clock', { size: 16, sw: 2.2 })}${u.time}</span><span>${icon('map-pin', { size: 16, sw: 2.2 })}${u.place}</span></div>
          </div>
        </div>`).join('')}
      </section>
      <section style="margin-top:22px">
        <div class="tiles">
          <div class="card tile"><span class="ti" style="background:var(--primary-soft);color:var(--primary)">${icon('stethoscope', { size: 24, sw: 2 })}</span><b>Doctors</b><small>28 doctors</small></div>
          <div class="card tile"><span class="ti" style="background:#E6EEFB;color:#1D4ED8">${icon('calendar-days', { size: 24, sw: 2 })}</span><b>Appointments</b><small>2 upcoming</small></div>
          <div class="card tile"><span class="count">2</span><span class="ti" style="background:#FBEEDB;color:#B45309">${icon('message-circle', { size: 24, sw: 2 })}</span><b>Messages</b><small>2 unread</small></div>
        </div>
      </section>
    </div>`, 'home');
  };

  // ---------------- CHOOSE SPECIALTY ----------------
  const SPECS = [
    ['General Practice', 'Everyday health', 'stethoscope', 8],
    ['Dermatology', 'Skin, hair, nails', 'hand', 3],
    ['Cardiology', 'Heart health', 'heart-pulse', 4],
    ['Dentistry', 'Teeth and gums', 'smile', 6],
    ['Ophthalmology', 'Eyes and vision', 'eye', 2],
    ['Pediatrics', "Children's health", 'baby', 5],
  ];
  const specialty = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        ${navBar('New appointment')}
        <div class="w-search">${icon('search', { size: 18, sw: 2 })}Search</div>
        <p class="w-cap">Specialties</p>
        <div class="card w-box">
          ${SPECS.map(([n, d, ic, c]) => `<div class="w-li">${icon(ic, { size: 20, sw: 1.9, style: 'color:var(--ink-2)' })}<div style="flex:1"><b>${n}</b><small>${d}</small></div><span class="w-count">${c} doctors</span>${wChev}</div>`).join('')}
        </div>
      </div>`);
    }
    return `<div class="screen">${statusBar(TIME)}
    <div class="content">
      ${flowHead(1)}
      <h1 class="h1">Choose a specialty</h1>
      <p class="lead">What kind of care do you need?</p>
      <div class="search">${icon('search', { size: 20, sw: 2.2 })}Search specialty or doctor</div>
      <div class="spec-grid">
        ${SPECS.map(([n, d, ic, c]) => `
        <div class="card sg ${n === 'Dermatology' ? 'sel' : ''}">
          ${n === 'Dermatology' ? `<span class="tick">${icon('check', { size: 14, sw: 3 })}</span>` : ''}
          <span class="si">${icon(ic, { size: 22, sw: 2 })}</span>
          <b>${n}</b><small>${d}</small>
          <span class="cnt">${c} doctors</span>
        </div>`).join('')}
      </div>
    </div>
    <div class="bottom-bar"><button class="btn-primary">Continue ${icon('arrow-right', { size: 20, sw: 2.4 })}</button></div>
    ${homeIndicator()}</div>`;
  };

  // ---------------- CHOOSE DOCTOR ----------------
  const star = icon('star', { size: 15, sw: 1.5, fill: '#F59E0B', style: 'color:#F59E0B' });
  const doctor = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        ${navBar('Dermatology')}
        <p class="w-cap" style="margin-top:12px">3 doctors</p>
        ${DOCS.map((d) => `
        <div class="card w-doc">
          ${avatar(d, 48)}
          <div style="flex:1;min-width:0">
            <b>${d.name}</b>
            <small>Dermatologist · ${d.years} yrs exp.</small>
            <small>Next: ${d.next}</small>
          </div>
          <span class="w-select">Select</span>
        </div>`).join('')}
      </div>`);
    }
    return `<div class="screen">${statusBar(TIME)}
    <div class="content">
      ${flowHead(2)}
      <h1 class="h1">Choose a doctor</h1>
      <div style="display:flex;align-items:center;gap:10px;margin:12px 0 18px"><span class="pill">${icon('hand', { size: 16, sw: 2.2 })}Dermatology</span><span style="font-size:14.5px;color:var(--ink-2)">3 doctors available</span></div>
      ${DOCS.map((d) => `
      <div class="card doc">
        <div class="dt">
          ${avatar(d)}
          <div style="flex:1;min-width:0">
            <h4>${d.name}</h4>
            <div class="role">Dermatologist</div>
            <div class="rate">${star}<b>${d.rating}</b>(${d.reviews}) · ${d.years} yrs experience</div>
          </div>
        </div>
        <div class="db">
          <div class="na"><small>Next available</small><b>${icon('calendar-check', { size: 16, sw: 2.2 })}${d.next}</b></div>
          <span class="select">Select</span>
        </div>
      </div>`).join('')}
    </div>
    ${homeIndicator()}</div>`;
  };

  // ---------------- DATE & TIME ----------------
  const DAYS = [['Mon', 12], ['Tue', 13], ['Wed', 14], ['Thu', 15], ['Fri', 16], ['Sat', 17], ['Sun', 18]];
  const MORNING = [['09:30'], ['10:00', 'taken'], ['10:30', 'sel'], ['11:00'], ['11:30'], ['12:00', 'taken']];
  const AFTERNOON = [['13:30'], ['14:00'], ['15:30', 'taken']];
  const datetime = (v) => {
    if (v === 'weak') {
      const free = [...MORNING, ...AFTERNOON].filter(([, st]) => st !== 'taken');
      return `<div class="screen">${statusBar(TIME)}
      <div class="content">
        ${navBar('Date & time')}
        <p class="w-sub" style="margin-top:8px">${DOC.name} · Dermatology</p>
        <p class="w-cap">October 2026</p>
        <div class="w-dates">
          ${DAYS.map(([d, n]) => `<div class="${n === 13 ? 'on' : ''} ${d === 'Sat' || d === 'Sun' ? 'off' : ''}"><small>${d}</small><b>${n}</b></div>`).join('')}
        </div>
        <p class="w-cap">Available times</p>
        <div class="w-slots">${free.map(([t, st]) => `<span class="${st === 'sel' ? 'on' : ''}">${t}</span>`).join('')}</div>
      </div>
      <div style="position:absolute;left:20px;right:20px;bottom:44px"><button class="btn-primary w-btn">Continue</button></div>
      ${homeIndicator()}</div>`;
    }
    const slot = ([t, s]) => `<span class="slot ${s || ''}">${s === 'sel' ? icon('check', { size: 16, sw: 3 }) : ''}${t}</span>`;
    return `<div class="screen">${statusBar(TIME)}
    <div class="content">
      ${flowHead(3)}
      <h1 class="h1">Select date & time</h1>
      <div class="card docmini" style="margin-top:14px">${avatar(DOC, 46)}<div><b>${DOC.name}</b><small>Dermatologist · Linden Clinic</small></div></div>
      <div class="monthrow"><b>October 2026</b><div class="arrows"><span>${icon('chevron-left', { size: 18, sw: 2.2 })}</span><span>${icon('chevron-right', { size: 18, sw: 2.2 })}</span></div></div>
      <div class="datestrip">
        ${DAYS.map(([d, n]) => `<div class="dd ${n === 13 ? 'sel' : ''} ${d === 'Sat' || d === 'Sun' ? 'off' : ''}"><small>${d}</small><b>${n}</b></div>`).join('')}
      </div>
      <div class="slot-head"><b>Available times</b><span>Tuesday, 13 October</span></div>
      <p class="part">${icon('sun', { size: 15, sw: 2.2 })}Morning</p>
      <div class="slots">${MORNING.map(slot).join('')}</div>
      <p class="part">${icon('clock', { size: 15, sw: 2.2 })}Afternoon</p>
      <div class="slots">${AFTERNOON.map(slot).join('')}</div>
    </div>
    <div class="bottom-bar">
      <div class="summary">${icon('calendar-check', { size: 17, sw: 2.2, style: 'color:var(--primary)' })}<span><b>Tue, 13 Oct</b> at <b>10:30</b></span></div>
      <button class="btn-primary">Continue ${icon('arrow-right', { size: 20, sw: 2.4 })}</button>
    </div>
    ${homeIndicator()}</div>`;
  };

  // ---------------- CONFIRM ----------------
  const drow = (ic, l, val) => `<div class="drow"><span class="di">${icon(ic, { size: 18, sw: 2.2 })}</span><div><small>${l}</small><b>${val}</b></div></div>`;
  const confirm = (v) => {
    if (v === 'weak') {
      const r = (l, val) => `<div class="w-kv"><span>${l}</span><b>${val}</b></div>`;
      return `<div class="screen">${statusBar(TIME)}
      <div class="content">
        ${navBar('Confirm appointment')}
        <p class="w-cap" style="margin-top:14px">Appointment details</p>
        <div class="card w-box">
          ${r('Doctor', DOC.name)}${r('Specialty', 'Dermatology')}${r('Date', 'Tue, 13 Oct 2026')}${r('Time', '10:30')}${r('Location', 'Linden Clinic, 24 Harbour St.')}
        </div>
        <p class="w-sub" style="margin-top:12px">You can cancel up to 24 hours before the visit.</p>
      </div>
      <div style="position:absolute;left:20px;right:20px;bottom:44px"><button class="btn-primary w-btn">Confirm booking</button></div>
      ${homeIndicator()}</div>`;
    }
    return `<div class="screen">${statusBar(TIME)}
    <div class="content">
      ${flowHead(4)}
      <h1 class="h1">Confirm appointment</h1>
      <p class="lead" style="margin-bottom:14px">Please check the details before booking.</p>
      <div class="card sumcard">
        <div class="who">${avatar(DOC, 50)}<div><b>${DOC.name}</b><small>Dermatology</small></div></div>
        ${drow('calendar', 'Date', 'Tuesday, 13 October 2026')}
        ${drow('clock', 'Time', '10:30 – 10:50')}
        ${drow('map-pin', 'In-person visit', ADDRESS)}
      </div>
      <div class="field-label">Reason for visit<span>Optional</span></div>
      <div class="textarea">Mole check on my left shoulder</div>
      <div class="note">${icon('info', { size: 17, sw: 2.2 })}Free cancellation up to 24 hours before.</div>
    </div>
    <div class="bottom-bar"><button class="btn-primary">${icon('circle-check', { size: 21, sw: 2.2 })}Confirm Booking</button></div>
    ${homeIndicator()}</div>`;
  };

  // ---------------- CONFIRMED (optional follow-up state) ----------------
  const confirmed = () => `<div class="screen">${statusBar(TIME)}
    <div class="content" style="text-align:center">
      <div style="height:72px"></div>
      <div class="okbig"><span>${icon('check', { size: 38, sw: 3 })}</span></div>
      <h1 class="h1" style="margin-top:22px">Appointment confirmed</h1>
      <p class="lead">We've sent the details to your email.</p>
      <div class="card sumcard" style="margin-top:26px;text-align:left">
        <div class="who">${avatar(DOC, 50)}<div><b>${DOC.name}</b><small>Dermatology</small></div></div>
        ${drow('calendar', 'Date', 'Tuesday, 13 October 2026')}
        ${drow('clock', 'Time', '10:30 – 10:50')}
        ${drow('map-pin', 'In-person visit', ADDRESS)}
      </div>
    </div>
    <div style="position:absolute;left:20px;right:20px;bottom:42px">
      <button class="btn-primary">View appointment</button>
      <button class="btn-ghost" style="margin-top:6px">Back to home</button>
    </div>
    ${homeIndicator()}</div>`;

  window.SCREENS = { home, specialty, doctor, datetime, confirm, confirmed };
})();
