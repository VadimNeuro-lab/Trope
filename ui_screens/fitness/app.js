// Set B - fitness tracker "Forma". Five screens, two variants (improved / weak).
(function () {
  const { icon, statusBar, homeIndicator, tabbar } = K;
  const TIME = '7:42';

  const TABS = [
    { key: 'home', label: 'Home', icon: 'house' },
    { key: 'workouts', label: 'Workouts', icon: 'dumbbell' },
    { key: 'progress', label: 'Progress', icon: 'chart-column' },
    { key: 'profile', label: 'Profile', icon: 'user' },
  ];
  const shell = (body, active) => `<div class="screen">${statusBar(TIME)}${body}${active ? tabbar(TABS, active) : ''}${homeIndicator()}</div>`;

  // Week of 28 Sep - 4 Oct, today is Saturday 3 Oct.
  const WEEK = [
    { d: 'M', min: 45 }, { d: 'T', min: 0 }, { d: 'W', min: 30 }, { d: 'T', min: 50 },
    { d: 'F', min: 25 }, { d: 'S', min: 0, today: true }, { d: 'S', min: 0 },
  ];
  const MAX = 50;
  const TODAY = { name: 'Upper Body Strength', time: '45 min', ex: '4 exercises', level: 'Intermediate' };

  const bars = ({ values = false, weak = false } = {}) => `
    <div class="bars" style="${weak ? 'height:80px' : ''}">
      ${WEEK.map((w) => {
        const h = Math.round((w.min / MAX) * (values ? 74 : 92));
        if (weak) return `<div class="bar"><i style="height:${Math.max(h, 4)}px;background:${w.min === MAX ? '#A8A1F2' : '#DFE1E8'}"></i></div>`;
        if (w.today) return `<div class="bar">${values ? '<small style="color:var(--primary)">Today</small>' : ''}<i class="plan" style="height:${values ? 74 : 92}px"></i></div>`;
        if (!w.min) return `<div class="bar">${values ? '<small style="color:var(--ink-3)">0</small>' : ''}<i class="zero"></i></div>`;
        return `<div class="bar">${values ? `<small>${w.min}</small>` : ''}<i style="height:${h}px"></i></div>`;
      }).join('')}
    </div>
    ${weak ? '' : `<div class="days">${WEEK.map((w) => `<span class="${w.today ? 'now' : ''}">${w.d}</span>`).join('')}</div>`}`;

  // ---------------- DASHBOARD ----------------
  const dashboard = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        <div class="dash-head" style="padding-top:14px">
          <h1 style="font-size:21px;font-weight:800">Good morning, Alex</h1>
          <div class="avatar" style="width:36px;height:36px;font-size:13px">AC</div>
        </div>
        <div class="card" style="margin-top:18px;padding:16px;display:flex;align-items:center;gap:12px">
          <div style="flex:1">
            <div style="font-size:12px;font-weight:700;color:var(--ink-3)">Today's workout</div>
            <div style="font-size:17px;font-weight:800;margin-top:3px">${TODAY.name}</div>
            <div style="font-size:13px;font-weight:600;color:var(--ink-3);margin-top:3px">${TODAY.time} · ${TODAY.ex}</div>
          </div>
          <span style="height:30px;padding:0 14px;border-radius:15px;background:var(--primary);color:#fff;font-size:13px;font-weight:800;display:flex;align-items:center">Start</span>
        </div>
        <div class="card week" style="margin-top:14px">
          <div class="top"><b style="font-size:16px;font-weight:800">Activity</b><span style="font-size:12px;color:var(--ink-3)">This week</span></div>
          <div style="height:150px;display:flex;align-items:flex-end;margin-top:10px"><div class="bars" style="height:150px;width:100%;margin:0">${WEEK.map((w) => `<div class="bar"><i style="height:${Math.max(4, Math.round((w.min / MAX) * 140))}px;background:${w.min === MAX ? '#A8A1F2' : '#DFE1E8'}"></i></div>`).join('')}</div></div>
          <p style="font-size:13px;color:var(--ink-3);font-weight:600;margin-top:14px">Weekly goal: 4/5 workouts</p>
        </div>
      </div>`, 'home');
    }
    return shell(`
    <div class="content">
      <div class="dash-head">
        <div><div class="date">Saturday, 3 October</div><h1>Good morning, Alex</h1></div>
        <div class="avatar" style="width:46px;height:46px;font-size:16px">AC</div>
      </div>
      <section class="today">
        <div class="top"><span class="eyebrow">${icon('calendar', { size: 14, sw: 2.4 })}Today's workout</span><span class="lvl">${icon('signal', { size: 15, sw: 2.6 })}${TODAY.level}</span></div>
        <h2>${TODAY.name}</h2>
        <div class="facts">
          <span class="fact">${icon('clock', { size: 16, sw: 2.4 })}${TODAY.time}</span>
          <span class="fact">${icon('list-checks', { size: 16, sw: 2.4 })}${TODAY.ex}</span>
        </div>
        <div class="start">${icon('play', { size: 18, sw: 2.4, fill: 'currentColor' })}Start workout</div>
      </section>
      <section class="card week">
        <div class="top"><span class="sec-title">This week</span><span>150 min active</span></div>
        ${bars()}
      </section>
      <section class="card goal">
        <div class="row1">
          <span class="ic-tile" style="background:var(--orange-soft);color:var(--orange)">${icon('target', { size: 21, sw: 2.2 })}</span>
          <b>Weekly goal</b>
          <span class="val">4 <span>/ 5 workouts</span></span>
        </div>
        <div class="progress"><i style="width:80%"></i></div>
        <p>1 more workout to reach your goal</p>
      </section>
    </div>`, 'home');
  };

  // ---------------- WORKOUT LIBRARY ----------------
  const LIB = [
    { name: 'Upper Body Strength', time: '45 min', level: ['Intermediate', 'b-int'], ic: 'dumbbell', tile: ['var(--primary-soft)', 'var(--primary)'] },
    { name: 'Full Body Circuit', time: '35 min', level: ['Advanced', 'b-adv'], ic: 'zap', tile: ['var(--red-soft)', 'var(--red)'] },
    { name: 'Core Stability', time: '20 min', level: ['Beginner', 'b-beg'], ic: 'target', tile: ['var(--orange-soft)', 'var(--orange)'] },
    { name: 'Mobility Flow', time: '25 min', level: ['All levels', 'b-all'], ic: 'person-standing', tile: ['var(--green-soft)', 'var(--green)'] },
    { name: 'Lower Body Power', time: '40 min', level: ['Intermediate', 'b-int'], ic: 'footprints', tile: ['#E8F1FD', '#1D5FC2'] },
  ];
  const workouts = (v) => {
    if (v === 'weak') {
      return shell(`
      <div class="content">
        <div class="w-nav">Workout Library</div>
        <div class="chips" style="margin-top:8px">
          <span class="chip on" style="height:32px;font-size:13px;padding:0 12px">All</span><span class="chip" style="height:32px;font-size:13px;padding:0 12px">Strength</span><span class="chip" style="height:32px;font-size:13px;padding:0 12px">Mobility</span><span class="chip" style="height:32px;font-size:13px;padding:0 12px">Core</span>
        </div>
        <div style="margin-top:12px">
          ${LIB.map((w) => `
          <div style="display:flex;align-items:center;gap:12px;padding:14px 0;border-bottom:1px solid var(--line)">
            <span class="ic-tile" style="width:40px;height:40px;background:#ECEEF3;color:var(--ink-2)">${icon(w.ic, { size: 19, sw: 2 })}</span>
            <div style="flex:1"><div style="font-size:15px;font-weight:700">${w.name}</div><div style="font-size:12.5px;color:var(--ink-3);font-weight:600;margin-top:2px">${w.time}</div></div>
          </div>`).join('')}
        </div>
      </div>`, 'workouts');
    }
    return shell(`
    <div class="content">
      <h1 class="h1" style="padding-top:12px">Workout Library</h1>
      <div class="search">
        <div class="field">${icon('search', { size: 20, sw: 2.2 })}Search workouts</div>
        <div class="filter">${icon('sliders-horizontal', { size: 20, sw: 2.2 })}</div>
      </div>
      <div class="chips"><span class="chip on">All</span><span class="chip">Strength</span><span class="chip">Mobility</span><span class="chip">Core</span></div>
      <div style="margin-top:16px">
        ${LIB.map((w) => `
        <div class="card wk">
          <span class="ic-tile" style="background:${w.tile[0]};color:${w.tile[1]}">${icon(w.ic, { size: 26, sw: 2 })}</span>
          <div class="wb">
            <h3>${w.name}</h3>
            <div class="wm"><span class="t">${icon('clock', { size: 16, sw: 2.2 })}${w.time}</span><span class="badge ${w.level[1]}">${icon('signal', { size: 13, sw: 2.6 })}${w.level[0]}</span></div>
          </div>
          <span class="chev">${icon('chevron-right', { size: 22, sw: 2.2 })}</span>
        </div>`).join('')}
      </div>
    </div>`, 'workouts');
  };

  // ---------------- LOG WORKOUT ----------------
  const EX = [
    { name: 'Bench Press', sets: 4, reps: 8, kg: 60, done: true },
    { name: 'Bent-over Row', sets: 4, reps: 10, kg: 50, done: true },
    { name: 'Overhead Press', sets: 3, reps: 10, kg: 35, done: true },
    { name: 'Lat Pulldown', sets: 3, reps: 12, kg: 45, done: false, focus: 'reps' },
  ];
  const log = (v) => {
    if (v === 'weak') {
      const inp = (l, val) => `<div style="flex:1"><div style="font-size:11px;color:var(--ink-3);font-weight:600;margin-bottom:3px">${l}</div><div style="height:34px;border-radius:8px;border:1px solid var(--line);background:#fff;display:flex;align-items:center;padding:0 10px;font-size:14px;font-weight:700">${val}</div></div>`;
      return `<div class="screen">${statusBar(TIME)}
      <div class="content">
        <div class="w-nav"><span class="l">${icon('chevron-left', { size: 26, sw: 2.2 })}</span>Log Workout<span class="r">Save</span></div>
        <p style="font-size:13px;color:var(--ink-3);font-weight:600;margin:6px 0 4px">Upper Body Strength</p>
        ${EX.map((e) => `
        <div style="padding:14px 0;border-bottom:1px solid var(--line)">
          <div style="font-size:15px;font-weight:700">${e.name}</div>
          <div style="display:flex;gap:10px;margin-top:8px">${inp('Sets', e.sets)}${inp('Reps', e.reps)}${inp('Weight', e.kg + ' kg')}</div>
        </div>`).join('')}
      </div>${homeIndicator()}</div>`;
    }
    const fld = (e, k, label, val, unit) => `<div class="fld ${e.focus === k ? 'focus' : ''}"><label>${label}</label><b>${val}${unit ? `<span>${unit}</span>` : ''}</b></div>`;
    return `<div class="screen">${statusBar(TIME)}
    <div class="content">
      <div class="log-head"><span class="back">${icon('arrow-left', { size: 22, sw: 2.2 })}</span><h1>Log Workout</h1></div>
      <div class="log-sub">${icon('dumbbell', { size: 17, sw: 2.2, style: 'color:var(--primary)' })}${TODAY.name} · Sat, 3 Oct</div>
      ${EX.map((e, i) => `
      <div class="card ex">
        <div class="eh"><h3>${e.name}<small>Exercise ${i + 1} of 4</small></h3><span class="done ${e.done ? 'on' : ''}">${icon('check', { size: 20, sw: 3 })}</span></div>
        <div class="fields">${fld(e, 'sets', 'Sets', e.sets)}${fld(e, 'reps', 'Reps', e.reps)}${fld(e, 'kg', 'Weight', e.kg, 'kg')}</div>
      </div>`).join('')}
    </div>
    <div class="bottom-bar"><button class="btn-primary">${icon('check', { size: 21, sw: 2.8 })}Save Workout</button></div>
    ${homeIndicator()}</div>`;
  };

  // ---------------- WEEKLY PROGRESS ----------------
  const ring = (pct, size = 72, stroke = 9) => {
    const r = (size - stroke) / 2, c = 2 * Math.PI * r;
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="flex:none"><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#ECEBFD" stroke-width="${stroke}"/><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#4B3FE0" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${(c * pct) / 100} ${c}" transform="rotate(-90 ${size / 2} ${size / 2})"/><text x="50%" y="53%" text-anchor="middle" dominant-baseline="middle" font-family="Manrope" font-weight="800" font-size="17" fill="#12131A">${pct}%</text></svg>`;
  };
  const progress = (v) => {
    if (v === 'weak') {
      const r = (l, val) => `<div style="display:flex;justify-content:space-between;padding:11px 0;border-bottom:1px solid var(--line);font-size:13.5px;font-weight:600"><span style="color:var(--ink-3)">${l}</span><span>${val}</span></div>`;
      return shell(`
      <div class="content">
        <div class="w-nav">Weekly Progress</div>
        <div class="card" style="margin-top:10px;padding:16px">
          <div style="font-size:13px;font-weight:700;color:var(--ink-3)">Activity</div>
          <div class="bars" style="height:190px;margin-top:10px">
            ${WEEK.map((w) => `<div class="bar"><i style="height:${Math.max(4, Math.round((w.min / MAX) * 180))}px;background:${w.min === MAX ? '#A8A1F2' : '#E3E5EC'}"></i></div>`).join('')}
          </div>
          <div class="days" style="font-size:10px;color:#B4B8C5;font-weight:600">${WEEK.map((w) => `<span>${w.d}</span>`).join('')}</div>
        </div>
        <div class="card" style="margin-top:12px;padding:4px 16px">
          ${r('Workouts', '4')}${r('Weekly goal', '80%')}${r('Active minutes', '150')}<div style="display:flex;justify-content:space-between;padding:11px 0;font-size:13.5px;font-weight:600"><span style="color:var(--ink-3)">Streak</span><span>3 days</span></div>
        </div>
      </div>`, 'progress');
    }
    const W5 = [['24 Aug', 'y'], ['31 Aug', 'y'], ['7 Sep', 'n'], ['14 Sep', 'y'], ['21 Sep', 'y']];
    return shell(`
    <div class="content">
      <div style="padding-top:12px"><h1 class="h1">Weekly Progress</h1><p class="subtle" style="margin-top:4px">28 Sep – 4 Oct</p></div>
      <section class="card goal-big">
        ${ring(80)}
        <div class="txt"><b>4 of 5 workouts</b><span>80% of your weekly goal</span></div>
      </section>
      <section class="card chart">
        <div class="week" style="margin:0;padding:0"><div class="top"><span class="sec-title">Active minutes</span><span>150 min total</span></div></div>
        ${bars({ values: true })}
      </section>
      <div class="tiles">
        <section class="card tile">
          <div class="tl">${icon('weight', { size: 18, sw: 2.2, style: 'color:var(--primary)' })}Volume</div>
          <div class="tv">9,840 kg</div>
          <div class="tn" style="color:var(--green)">${icon('trending-up', { size: 16, sw: 2.6 })}+12% vs last week</div>
        </section>
        <section class="card tile">
          <div class="tl">${icon('flame', { size: 18, sw: 2.2, style: 'color:var(--orange)' })}Streak</div>
          <div class="tv">3 days</div>
          <div class="tn" style="color:var(--ink-3)">Best: 9 days</div>
        </section>
      </div>
      <section class="card consist">
        <div class="top"><span class="sec-title">Consistency</span><span>Goal met 4 of 5 weeks</span></div>
        <div class="weeks">
          ${W5.map(([d, s]) => `<div class="w"><i class="${s}">${icon(s === 'y' ? 'check' : 'x', { size: 17, sw: 3 })}</i><small>${d}</small></div>`).join('')}
          <div class="w"><i class="c">80%</i><small style="color:var(--primary)">Now</small></div>
        </div>
      </section>
    </div>`, 'progress');
  };

  // ---------------- PROFILE & GOALS ----------------
  const profile = (v) => {
    const chev = icon('chevron-right', { size: 18, sw: 2.2 });
    if (v === 'weak') {
      const row = (l, val) => `<div class="row" style="min-height:44px;font-size:14.5px;font-weight:600"><span class="rl">${l}</span><span class="rv" style="font-size:14px;font-weight:600">${val}</span></div>`;
      return shell(`
      <div class="content">
        <div class="w-nav">Profile</div>
        <div style="display:flex;flex-direction:column;align-items:center;margin-top:18px">
          <div class="avatar" style="width:84px;height:84px;font-size:27px">AC</div>
          <div style="font-size:19px;font-weight:800;margin-top:12px">Alex Carter</div><div style="font-size:13px;color:var(--ink-3);font-weight:600;margin-top:2px">alex.carter@mail.com</div>
        </div>
        <div class="card rows" style="margin-top:18px;border-radius:16px">
          ${row('Weekly goal', '5 workouts')}
          ${row('Training goal', 'Build strength')}
          ${row('Reminders', '<span class="switch sm on"></span>')}
        </div>
        <div class="card rows" style="margin-top:14px;border-radius:16px">
          ${row('Account', chev)}
          ${row('Privacy', chev)}
          ${row('<span style="color:#C2410C">Log out</span>', '')}
        </div>
      </div>`, 'profile');
    }
    const row = (ic, l, val, sub, color) => `<div class="row"><span class="ri" style="${color || ''}">${icon(ic, { size: 18, sw: 2.2 })}</span><span class="rl">${l}${sub ? `<small>${sub}</small>` : ''}</span><span class="rv">${val}</span></div>`;
    return shell(`
    <div class="content">
      <h1 class="h1" style="padding-top:12px">Profile</h1>
      <section class="card prof">
        <div class="avatar" style="width:64px;height:64px;font-size:22px">AC</div>
        <div style="flex:1">
          <h2>Alex Carter</h2>
          <div class="lv"><span class="badge b-int">${icon('signal', { size: 13, sw: 2.6 })}Intermediate</span><span class="since">Since Mar 2025</span></div>
        </div>
      </section>
      <p class="group-label">Goals</p>
      <div class="card rows">
        ${row('target', 'Weekly goal', `5 workouts${chev}`, '', 'background:var(--orange-soft);color:var(--orange)')}
        ${row('trophy', 'Training goal', `Build strength${chev}`, '', 'background:var(--orange-soft);color:var(--orange)')}
      </div>
      <p class="group-label">Preferences</p>
      <div class="card rows">
        ${row('bell', 'Workout reminders', '<span class="switch on"></span>', 'Daily at 07:30')}
        ${row('chart-column', 'Weekly summary', '<span class="switch on"></span>', 'Every Sunday')}
        ${row('ruler', 'Units', `Metric (kg)${chev}`)}
      </div>
      <p class="group-label">Account</p>
      <div class="card rows">
        ${row('user', 'Account details', chev, '', 'background:#EEF0F4;color:#4B5160')}
        ${row('log-out', '<span style="color:#C2410C">Log out</span>', '', '', 'background:var(--red-soft);color:var(--red)')}
      </div>
    </div>`, 'profile');
  };

  window.SCREENS = { dashboard, workouts, log, progress, profile };
})();
