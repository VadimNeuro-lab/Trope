// Set B - fitness tracker "Forma". Five screens in four versions of increasing quality:
//   base   - plain list UI, less information, small controls
//   sft    - card layout and more components, but some user flows still have gaps
//   dpo    - clearer layout and actions, consistent screens, a few secondary details missing
//   specpo - complete version: every main action obvious, large controls, structured information
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
  const pick = (table) => (v) => (table[v] || table.specpo)();
  const chev = (s = 18) => icon('chevron-right', { size: s, sw: 2.2 });

  // ---------- shared data: week of 28 Sep - 4 Oct, today is Saturday 3 Oct ----------
  const WEEK = [
    { d: 'M', min: 45 }, { d: 'T', min: 0 }, { d: 'W', min: 30 }, { d: 'T', min: 50 },
    { d: 'F', min: 25 }, { d: 'S', min: 0, today: true }, { d: 'S', min: 0 },
  ];
  const MAX = 50;
  const TODAY = { name: 'Upper Body Strength', time: '45 min', ex: '4 exercises', level: 'Intermediate' };
  const LIB = [
    { name: 'Upper Body Strength', time: '45 min', type: 'Strength', level: ['Intermediate', 'b-int', 'var(--primary)'], ic: 'dumbbell', tile: ['var(--primary-soft)', 'var(--primary)'] },
    { name: 'Full Body Circuit', time: '35 min', type: 'HIIT', level: ['Advanced', 'b-adv', 'var(--red)'], ic: 'zap', tile: ['var(--red-soft)', 'var(--red)'] },
    { name: 'Core Stability', time: '20 min', type: 'Core', level: ['Beginner', 'b-beg', 'var(--green)'], ic: 'target', tile: ['var(--orange-soft)', 'var(--orange)'] },
    { name: 'Mobility Flow', time: '25 min', type: 'Mobility', level: ['All levels', 'b-all', '#4B5160'], ic: 'person-standing', tile: ['var(--green-soft)', 'var(--green)'] },
    { name: 'Lower Body Power', time: '40 min', type: 'Strength', level: ['Intermediate', 'b-int', 'var(--primary)'], ic: 'footprints', tile: ['#E8F1FD', '#1D5FC2'] },
  ];
  const EX = [
    { name: 'Bench Press', muscles: 'Chest · Triceps', sets: 4, reps: 8, kg: 60, done: true },
    { name: 'Bent-over Row', muscles: 'Back · Biceps', sets: 4, reps: 10, kg: 50, done: true },
    { name: 'Overhead Press', muscles: 'Shoulders', sets: 3, reps: 10, kg: 35, done: true },
    { name: 'Lat Pulldown', muscles: 'Back', sets: 3, reps: 12, kg: 45, done: false, focus: 'reps' },
  ];

  // bar chart; opts: values (labels above bars), labels (day letters), muted (grey bars), h (chart height)
  const bars = ({ values = false, labels = true, muted = false, h = 100 } = {}) => {
    const area = values ? h - 26 : h - 8;
    return `
    <div class="bars" style="height:${h}px">
      ${WEEK.map((w) => {
        const bh = Math.round((w.min / MAX) * area);
        if (muted) return `<div class="bar"><i style="height:${Math.max(bh, 6)}px;background:${w.min === MAX ? '#A8A1F2' : '#DFE1E8'}"></i></div>`;
        if (w.today) return `<div class="bar">${values ? '<small style="color:var(--primary)">Today</small>' : ''}<i class="plan" style="height:${area}px"></i></div>`;
        if (!w.min) return `<div class="bar">${values ? '<small style="color:var(--ink-3)">0</small>' : ''}<i class="zero"></i></div>`;
        return `<div class="bar">${values ? `<small>${w.min}</small>` : ''}<i style="height:${bh}px"></i></div>`;
      }).join('')}
    </div>
    ${labels ? `<div class="days">${WEEK.map((w) => `<span class="${w.today && !muted ? 'now' : ''}">${w.d}</span>`).join('')}</div>` : ''}`;
  };
  const ring = (pct, size = 72, stroke = 9) => {
    const r = (size - stroke) / 2, c = 2 * Math.PI * r;
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="flex:none"><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#ECEBFD" stroke-width="${stroke}"/><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#4B3FE0" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${(c * pct) / 100} ${c}" transform="rotate(-90 ${size / 2} ${size / 2})"/><text x="50%" y="53%" text-anchor="middle" dominant-baseline="middle" font-family="Manrope" font-weight="800" font-size="${Math.round(size / 4.2)}" fill="#12131A">${pct}%</text></svg>`;
  };
  const navTitle = (t, l = '', r = '') => `<div class="w-nav">${l ? `<span class="l">${l}</span>` : ''}${t}${r ? `<span class="r">${r}</span>` : ''}</div>`;
  const baseRow = (l, val) => `<div class="b-row"><span>${l}</span><span>${val}</span></div>`;

  // =====================================================================
  // DASHBOARD
  // =====================================================================
  const dashboard = pick({
    base: () => shell(`
      <div class="content">
        <div class="dash-head" style="padding-top:14px">
          <h1 style="font-size:22px;font-weight:800">Good morning, Alex</h1>
          <div class="avatar" style="width:36px;height:36px;font-size:13px">AC</div>
        </div>
        <div class="card b-card" style="margin-top:18px;display:flex;align-items:center;gap:12px">
          <div style="flex:1">
            <div class="b-cap">Today's workout</div>
            <div style="font-size:17px;font-weight:800;margin-top:3px">${TODAY.name}</div>
            <div class="b-cap" style="margin-top:3px">${TODAY.time} · ${TODAY.ex}</div>
          </div>
          <span class="b-pill">Start</span>
        </div>
        <div class="card b-card" style="margin-top:12px">
          <div style="display:flex;justify-content:space-between;align-items:baseline"><b style="font-size:16px;font-weight:800">Activity</b><span class="b-cap">This week</span></div>
          <div style="margin-top:14px">${bars({ muted: true, labels: false, h: 200 })}</div>
          <p class="b-cap" style="margin-top:14px">Weekly goal: 4/5 workouts</p>
        </div>
      </div>`, 'home'),

    sft: () => shell(`
      <div class="content">
        <div class="dash-head">
          <div><div class="date">Saturday, 3 October</div><h1>Hi, Alex</h1></div>
          <div class="avatar" style="width:42px;height:42px;font-size:15px">AC</div>
        </div>
        <section class="card" style="margin-top:16px;padding:16px">
          <div style="display:flex;align-items:center;gap:14px">
            <span class="ic-tile" style="width:52px;height:52px;border-radius:16px;background:var(--primary-soft);color:var(--primary)">${icon('dumbbell', { size: 26, sw: 2 })}</span>
            <div><div class="s-cap">Today's workout</div><div style="font-size:19px;font-weight:800;margin-top:2px">${TODAY.name}</div><div class="s-cap" style="margin-top:2px">${TODAY.time} · ${TODAY.ex} · ${TODAY.level}</div></div>
          </div>
          <div class="btn-outline" style="margin-top:14px">View workout</div>
        </section>
        <div class="mstats">
          <div class="card mstat">${icon('target', { size: 20, sw: 2.2, style: 'color:var(--orange)' })}<b>4/5</b><small>Weekly goal</small></div>
          <div class="card mstat">${icon('clock', { size: 20, sw: 2.2, style: 'color:var(--primary)' })}<b>150</b><small>Minutes</small></div>
          <div class="card mstat">${icon('flame', { size: 20, sw: 2.2, style: 'color:var(--orange)' })}<b>3</b><small>Day streak</small></div>
        </div>
        <section class="card week" style="margin-top:12px">
          <div class="top"><span class="sec-title">This week</span></div>
          ${bars({ h: 96 })}
        </section>
      </div>`, 'home'),

    dpo: () => shell(`
      <div class="content">
        <div class="dash-head">
          <div><div class="date">Saturday, 3 October</div><h1>Good morning, Alex</h1></div>
          <div class="avatar" style="width:44px;height:44px;font-size:15px">AC</div>
        </div>
        <section class="today-soft">
          <span class="eyebrow">Today's workout</span>
          <h2>${TODAY.name}</h2>
          <div class="facts">
            <span class="fact">${icon('clock', { size: 16, sw: 2.4 })}${TODAY.time}</span>
            <span class="fact">${icon('list-checks', { size: 16, sw: 2.4 })}${TODAY.ex}</span>
          </div>
          <button class="btn-primary" style="margin-top:16px;height:52px;box-shadow:none">${icon('play', { size: 18, sw: 2.4, fill: 'currentColor' })}Start workout</button>
        </section>
        <section class="card week">
          <div class="top"><span class="sec-title">This week</span><span>150 min active</span></div>
          ${bars()}
        </section>
        <section class="card goal">
          <div class="row1"><b>Weekly goal</b><span class="val">4 <span>/ 5 workouts</span></span></div>
          <div class="progress"><i style="width:80%"></i></div>
        </section>
      </div>`, 'home'),

    specpo: () => shell(`
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
      </div>`, 'home'),
  });

  // =====================================================================
  // WORKOUT LIBRARY
  // =====================================================================
  const chipsRow = (style = '') => `<div class="chips" style="${style}">${['All', 'Strength', 'Mobility', 'Core'].map((c, i) => `<span class="chip ${i ? '' : 'on'}">${c}</span>`).join('')}</div>`;
  const workouts = pick({
    base: () => shell(`
      <div class="content">
        ${navTitle('Workout Library')}
        <div class="chips b-chips" style="margin-top:8px">${['All', 'Strength', 'Mobility', 'Core'].map((c, i) => `<span class="chip ${i ? '' : 'on'}">${c}</span>`).join('')}</div>
        <div style="margin-top:10px">
          ${LIB.map((w) => `
          <div class="b-list-row">
            <span class="ic-tile" style="width:40px;height:40px;background:#ECEEF3;color:var(--ink-2)">${icon(w.ic, { size: 19, sw: 2 })}</span>
            <div style="flex:1"><div style="font-size:15px;font-weight:700">${w.name}</div><div class="b-cap" style="margin-top:2px">${w.time}</div></div>
            <span style="color:#B9BECB">${chev(18)}</span>
          </div>`).join('')}
        </div>
      </div>`, 'workouts'),

    sft: () => shell(`
      <div class="content">
        <h1 class="t-title">Workout Library</h1>
        <div class="search"><div class="field">${icon('search', { size: 20, sw: 2.2 })}Search workouts</div></div>
        ${chipsRow()}
        <div style="margin-top:14px">
          ${LIB.map((w) => `
          <div class="card wk" style="padding:12px 14px">
            <span class="ic-tile" style="width:46px;height:46px;border-radius:14px;background:var(--primary-soft);color:var(--primary)">${icon(w.ic, { size: 22, sw: 2 })}</span>
            <div class="wb"><h3>${w.name}</h3><div class="wm" style="margin-top:4px">${w.time} · ${w.type}</div></div>
            <span class="chev">${chev(20)}</span>
          </div>`).join('')}
        </div>
      </div>`, 'workouts'),

    dpo: () => shell(`
      <div class="content">
        <h1 class="h1" style="padding-top:12px">Workout Library</h1>
        <div class="search"><div class="field">${icon('search', { size: 20, sw: 2.2 })}Search workouts</div></div>
        ${chipsRow()}
        <div style="margin-top:16px">
          ${LIB.map((w) => `
          <div class="card wk">
            <span class="ic-tile" style="background:${w.tile[0]};color:${w.tile[1]}">${icon(w.ic, { size: 26, sw: 2 })}</span>
            <div class="wb">
              <h3>${w.name}</h3>
              <div class="wm"><span class="t">${icon('clock', { size: 16, sw: 2.2 })}${w.time}</span><span style="color:${w.level[2]}">${w.level[0]}</span></div>
            </div>
            <span class="chev">${chev(22)}</span>
          </div>`).join('')}
        </div>
      </div>`, 'workouts'),

    specpo: () => shell(`
      <div class="content">
        <h1 class="h1" style="padding-top:12px">Workout Library</h1>
        <div class="search">
          <div class="field">${icon('search', { size: 20, sw: 2.2 })}Search workouts</div>
          <div class="filter">${icon('sliders-horizontal', { size: 20, sw: 2.2 })}</div>
        </div>
        ${chipsRow()}
        <div style="margin-top:16px">
          ${LIB.map((w) => `
          <div class="card wk">
            <span class="ic-tile" style="background:${w.tile[0]};color:${w.tile[1]}">${icon(w.ic, { size: 26, sw: 2 })}</span>
            <div class="wb">
              <h3>${w.name}</h3>
              <div class="wm"><span class="t">${icon('clock', { size: 16, sw: 2.2 })}${w.time}</span><span class="badge ${w.level[1]}">${icon('signal', { size: 13, sw: 2.6 })}${w.level[0]}</span></div>
            </div>
            <span class="chev">${chev(22)}</span>
          </div>`).join('')}
        </div>
      </div>`, 'workouts'),
  });

  // =====================================================================
  // LOG WORKOUT
  // =====================================================================
  const fld = (e, k, label, val, unit, focus = true) => `<div class="fld ${focus && e.focus === k ? 'focus' : ''}"><label>${label}</label><b>${val}${unit ? `<span>${unit}</span>` : ''}</b></div>`;
  const log = pick({
    base: () => {
      const inp = (l, val) => `<div style="flex:1"><div class="b-cap" style="font-size:11.5px;margin-bottom:4px">${l}</div><div class="b-input">${val}</div></div>`;
      return `<div class="screen">${statusBar(TIME)}
      <div class="content">
        ${navTitle('Log Workout', icon('chevron-left', { size: 26, sw: 2.2 }), 'Save')}
        <p class="b-cap" style="margin:8px 0 2px">${TODAY.name}</p>
        ${EX.map((e) => `
        <div style="padding:14px 0;border-bottom:1px solid var(--line)">
          <div style="font-size:15.5px;font-weight:700">${e.name}</div>
          <div style="display:flex;gap:10px;margin-top:8px">${inp('Sets', e.sets)}${inp('Reps', e.reps)}${inp('Weight', e.kg + ' kg')}</div>
        </div>`).join('')}
      </div>${homeIndicator()}</div>`;
    },

    sft: () => {
      const inp = (l, val) => `<div><div class="s-cap" style="margin-bottom:5px">${l}</div><div class="s-input">${val}</div></div>`;
      return `<div class="screen">${statusBar(TIME)}
      <div class="content">
        <div class="log-head"><span class="back" style="width:40px;height:40px">${icon('chevron-left', { size: 22, sw: 2.2 })}</span><h1 style="font-size:24px">Log Workout</h1></div>
        <div class="log-sub">${TODAY.name}</div>
        ${EX.map((e) => `
        <div class="card" style="padding:14px 16px;margin-bottom:10px;border-radius:18px">
          <div style="font-size:16.5px;font-weight:800">${e.name}</div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:10px">${inp('Sets', e.sets)}${inp('Reps', e.reps)}${inp('Weight, kg', e.kg)}</div>
        </div>`).join('')}
      </div>
      <div class="bottom-bar"><button class="btn-primary" style="height:50px;font-size:16px;box-shadow:none">Save Workout</button></div>
      ${homeIndicator()}</div>`;
    },

    dpo: () => `<div class="screen">${statusBar(TIME)}
      <div class="content">
        <div class="log-head"><span class="back">${icon('arrow-left', { size: 22, sw: 2.2 })}</span><h1>Log Workout</h1></div>
        <div class="log-sub">${icon('dumbbell', { size: 17, sw: 2.2, style: 'color:var(--primary)' })}${TODAY.name} · Sat, 3 Oct</div>
        ${EX.map((e) => `
        <div class="card ex" style="padding-top:14px">
          <div class="eh"><h3>${e.name}</h3><span class="done ${e.done ? 'on' : ''}">${icon('check', { size: 20, sw: 3 })}</span></div>
          <div class="fields">${fld(e, 'sets', 'Sets', e.sets, '', false)}${fld(e, 'reps', 'Reps', e.reps, '', false)}${fld(e, 'kg', 'Weight', e.kg, 'kg', false)}</div>
        </div>`).join('')}
      </div>
      <div class="bottom-bar"><button class="btn-primary">${icon('check', { size: 21, sw: 2.8 })}Save Workout</button></div>
      ${homeIndicator()}</div>`,

    specpo: () => `<div class="screen">${statusBar(TIME)}
      <div class="content">
        <div class="log-head"><span class="back">${icon('arrow-left', { size: 22, sw: 2.2 })}</span><h1>Log Workout</h1></div>
        <div class="log-sub">${icon('dumbbell', { size: 17, sw: 2.2, style: 'color:var(--primary)' })}${TODAY.name} · Sat, 3 Oct<span class="log-count">3 of 4 done</span></div>
        ${EX.map((e) => `
        <div class="card ex">
          <div class="eh"><h3>${e.name}<small>${e.muscles}</small></h3><span class="done ${e.done ? 'on' : ''}">${icon('check', { size: 20, sw: 3 })}</span></div>
          <div class="fields">${fld(e, 'sets', 'Sets', e.sets)}${fld(e, 'reps', 'Reps', e.reps)}${fld(e, 'kg', 'Weight', e.kg, 'kg')}</div>
        </div>`).join('')}
      </div>
      <div class="bottom-bar"><button class="btn-primary">${icon('check', { size: 21, sw: 2.8 })}Save Workout</button></div>
      ${homeIndicator()}</div>`,
  });

  // =====================================================================
  // WEEKLY PROGRESS
  // =====================================================================
  const progress = pick({
    base: () => shell(`
      <div class="content">
        ${navTitle('Weekly Progress')}
        <div class="card b-card" style="margin-top:10px">
          <div class="b-cap" style="font-weight:700">Activity</div>
          <div style="margin-top:12px">${bars({ muted: true, h: 190 })}</div>
        </div>
        <div class="card" style="margin-top:12px;padding:2px 16px;border-radius:16px">
          ${baseRow('Workouts', '4')}${baseRow('Weekly goal', '80%')}${baseRow('Active minutes', '150')}${baseRow('Streak', '3 days')}
        </div>
      </div>`, 'progress'),

    sft: () => shell(`
      <div class="content">
        <h1 class="t-title">Weekly Progress</h1>
        <p class="subtle" style="margin-top:2px">28 Sep – 4 Oct</p>
        <section class="card chart" style="margin-top:14px">
          <div class="week" style="margin:0;padding:0"><div class="top"><span class="sec-title">Active minutes</span></div></div>
          ${bars({ h: 130 })}
        </section>
        <div class="tiles">
          ${[['check', '4', 'Workouts', 'var(--primary)'], ['target', '80%', 'Weekly goal', 'var(--orange)'], ['clock', '150', 'Minutes', 'var(--primary)'], ['flame', '3 days', 'Streak', 'var(--orange)']].map(([ic, val, l, c]) => `
          <section class="card tile" style="padding:14px 16px">
            <div class="tl">${icon(ic, { size: 18, sw: 2.2, style: `color:${c}` })}${l}</div>
            <div class="tv" style="font-size:22px;margin-top:6px">${val}</div>
          </section>`).join('')}
        </div>
      </div>`, 'progress'),

    dpo: () => shell(`
      <div class="content">
        <div style="padding-top:12px"><h1 class="h1">Weekly Progress</h1><p class="subtle" style="margin-top:4px">28 Sep – 4 Oct</p></div>
        <section class="card goal-big">
          ${ring(80)}
          <div class="txt"><b>4 of 5 workouts</b><span>Weekly goal</span></div>
        </section>
        <section class="card chart">
          <div class="week" style="margin:0;padding:0"><div class="top"><span class="sec-title">Active minutes</span><span>150 min total</span></div></div>
          ${bars({ h: 112 })}
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
      </div>`, 'progress'),

    specpo: () => {
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
    },
  });

  // =====================================================================
  // PROFILE & GOALS
  // =====================================================================
  const row = (ic, l, val, sub, color) => `<div class="row"><span class="ri" style="${color || ''}">${icon(ic, { size: 18, sw: 2.2 })}</span><span class="rl">${l}${sub ? `<small>${sub}</small>` : ''}</span><span class="rv">${val}</span></div>`;
  const ORANGE = 'background:var(--orange-soft);color:var(--orange)';
  const GREY = 'background:#EEF0F4;color:#4B5160';
  const RED = 'background:var(--red-soft);color:var(--red)';
  const logout = '<span style="color:#C2410C">Log out</span>';
  const profile = pick({
    base: () => {
      const r = (l, val) => `<div class="row" style="min-height:46px;font-size:15px;font-weight:600"><span class="rl">${l}</span><span class="rv" style="font-size:14.5px;font-weight:600">${val}</span></div>`;
      return shell(`
      <div class="content">
        ${navTitle('Profile')}
        <div style="display:flex;flex-direction:column;align-items:center;margin-top:16px">
          <div class="avatar" style="width:80px;height:80px;font-size:26px">AC</div>
          <div style="font-size:19px;font-weight:800;margin-top:12px">Alex Carter</div><div class="b-cap" style="margin-top:2px">alex.carter@mail.com</div>
        </div>
        <div class="card rows" style="margin-top:18px;border-radius:16px">
          ${r('Weekly goal', '5 workouts')}
          ${r('Training goal', 'Build strength')}
          ${r('Reminders', '<span class="switch sm on"></span>')}
        </div>
        <div class="card rows" style="margin-top:12px;border-radius:16px">
          ${r('Account', chev())}
          ${r('Privacy', chev())}
          ${r(logout, '')}
        </div>
      </div>`, 'profile');
    },

    sft: () => shell(`
      <div class="content">
        <h1 class="t-title">Profile</h1>
        <section class="card prof" style="padding:16px">
          <div class="avatar" style="width:56px;height:56px;font-size:19px">AC</div>
          <div style="flex:1"><h2 style="font-size:18px">Alex Carter</h2><div class="s-cap" style="margin-top:2px">alex.carter@mail.com</div></div>
        </section>
        <p class="group-label">Goals</p>
        <div class="card rows">
          ${row('target', 'Weekly goal', `5 workouts${chev()}`, '', ORANGE)}
          ${row('trophy', 'Training goal', `Build strength${chev()}`, '', ORANGE)}
        </div>
        <p class="group-label">Notifications</p>
        <div class="card rows">
          ${row('bell', 'Workout reminders', '<span class="switch on"></span>', 'Daily at 07:30')}
        </div>
        <p class="group-label">Account</p>
        <div class="card rows">
          ${row('user', 'Account details', chev(), '', GREY)}
          ${row('log-out', logout, '', '', RED)}
        </div>
      </div>`, 'profile'),

    dpo: () => shell(`
      <div class="content">
        <h1 class="h1" style="padding-top:12px">Profile</h1>
        <section class="card prof">
          <div class="avatar" style="width:60px;height:60px;font-size:21px">AC</div>
          <div style="flex:1"><h2>Alex Carter</h2><div class="lv"><span class="badge b-int">${icon('signal', { size: 13, sw: 2.6 })}Intermediate</span></div></div>
        </section>
        <p class="group-label">Goals</p>
        <div class="card rows">
          ${row('target', 'Weekly goal', `5 workouts${chev()}`, '', ORANGE)}
          ${row('trophy', 'Training goal', `Build strength${chev()}`, '', ORANGE)}
        </div>
        <p class="group-label">Preferences</p>
        <div class="card rows">
          ${row('bell', 'Workout reminders', '<span class="switch on"></span>', 'Daily at 07:30')}
          ${row('ruler', 'Units', `Metric (kg)${chev()}`)}
        </div>
        <p class="group-label">Account</p>
        <div class="card rows">
          ${row('log-out', logout, '', '', RED)}
        </div>
      </div>`, 'profile'),

    specpo: () => shell(`
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
          ${row('target', 'Weekly goal', `5 workouts${chev()}`, '', ORANGE)}
          ${row('trophy', 'Training goal', `Build strength${chev()}`, '', ORANGE)}
        </div>
        <p class="group-label">Preferences</p>
        <div class="card rows">
          ${row('bell', 'Workout reminders', '<span class="switch on"></span>', 'Daily at 07:30')}
          ${row('chart-column', 'Weekly summary', '<span class="switch on"></span>', 'Every Sunday')}
          ${row('ruler', 'Units', `Metric (kg)${chev()}`)}
        </div>
        <p class="group-label">Account</p>
        <div class="card rows">
          ${row('user', 'Account details', chev(), '', GREY)}
          ${row('log-out', logout, '', '', RED)}
        </div>
      </div>`, 'profile'),
  });

  window.SCREENS = { dashboard, workouts, log, progress, profile };
})();
