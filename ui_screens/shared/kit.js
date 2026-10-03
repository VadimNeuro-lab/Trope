// Small helpers shared by the three apps. Each app defines window.SCREENS = { name: (variant) => html }.
// The page reads ?screen=<name>&variant=<improved|weak> and renders a single 390x844 screen.
(function () {
  const K = {};

  K.icon = (name, opt = {}) => {
    const { size = 24, sw = 2, fill = 'none', cls = '', style = '' } = opt;
    const inner = window.ICONS[name];
    if (!inner) throw new Error('unknown icon ' + name);
    return `<svg class="icon ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="${fill}" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" style="${style}">${inner}</svg>`;
  };

  K.statusBar = (time, { light = false } = {}) => `
    <div class="statusbar ${light ? 'light' : ''}">
      <span class="time">${time}</span>
      <span class="sys">
        <svg width="18" height="12" viewBox="0 0 18 12" fill="currentColor"><rect x="0" y="8" width="3" height="4" rx="1"/><rect x="5" y="5.5" width="3" height="6.5" rx="1"/><rect x="10" y="3" width="3" height="9" rx="1"/><rect x="15" y="0" width="3" height="12" rx="1"/></svg>
        <svg width="16" height="12" viewBox="0 0 16 12" fill="currentColor"><path d="M8 2.4c2.3 0 4.4.9 6 2.4l1.1-1.1C13.2 1.9 10.7.8 8 .8S2.8 1.9.9 3.7L2 4.8c1.6-1.5 3.7-2.4 6-2.4z"/><path d="M8 5.6c1.4 0 2.7.5 3.7 1.4l1.1-1.1C11.5 4.7 9.8 4 8 4s-3.5.7-4.8 1.9L4.3 7c1-.9 2.3-1.4 3.7-1.4z"/><path d="M8 8.8c.6 0 1.2.2 1.6.6L8 11 6.4 9.4c.4-.4 1-.6 1.6-.6z"/></svg>
        <svg width="27" height="13" viewBox="0 0 27 13" fill="none"><rect x="0.5" y="0.5" width="23" height="12" rx="3.6" stroke="currentColor" opacity="0.4"/><rect x="2" y="2" width="20" height="9" rx="2.2" fill="currentColor"/><path d="M25 4.5v4c.8-.3 1.3-1.1 1.3-2s-.5-1.7-1.3-2z" fill="currentColor" opacity="0.45"/></svg>
      </span>
    </div>`;

  K.homeIndicator = ({ light = false } = {}) => `<div class="home-ind" style="${light ? 'background:#fff' : ''}"></div>`;

  // items: [{ key, label, icon }]
  K.tabbar = (items, active, opt = {}) => `
    <nav class="tabbar">
      ${items.map((t) => `<div class="tab ${t.key === active ? 'active' : ''}">${K.icon(t.icon, { size: opt.size || 24, sw: t.key === active ? 2.2 : 1.9 })}<span>${t.label}</span></div>`).join('')}
    </nav>`;

  K.render = () => {
    const q = new URLSearchParams(location.search);
    const names = Object.keys(window.SCREENS);
    const screen = q.get('screen') || names[0];
    const variant = q.get('variant') || 'improved';
    document.body.innerHTML = window.SCREENS[screen](variant);
    document.title = `${screen} (${variant})`;
    const imgs = [...document.images];
    Promise.all([document.fonts.ready, ...imgs.map((i) => (i.complete ? 1 : new Promise((r) => { i.onload = i.onerror = r; })))]).then(() => {
      document.body.dataset.ready = '1';
    });
  };

  window.K = K;
  window.addEventListener('DOMContentLoaded', K.render);
})();
