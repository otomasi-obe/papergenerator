// PaperFull app — shared icons + AppHeader. From frontend/src/components/AppHeader.vue
const Icon = {
  bell: (p) => <svg {...p} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/></svg>,
  send: (p) => <svg {...p} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/></svg>,
  export: (p) => <svg {...p} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>,
  stop: (p) => <svg {...p} fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1.5"/></svg>,
};

const THEMES = [
  { v: 'light', label: '☀️ Light' },
  { v: 'dark', label: '🌙 Dark' },
  { v: 'system', label: '🖥️ System' },
];

function AppHeader({ active, theme, setTheme, onNav, quota }) {
  const [menuOpen, setMenuOpen] = React.useState(false);
  const q = quota || { used: 17000, total: 50000 };
  const pct = Math.round((q.used / q.total) * 100);
  const fmt = (n) => n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
  const fillColor = pct >= 90 ? '#ef4444' : pct >= 70 ? 'var(--accent-warning)' : 'var(--accent-success)';

  return (
    <header className="hdr">
      <div className="hdr-in">
        <div className="hdr-left">
          <a className="hdr-brand" onClick={() => onNav('dashboard')} style={{ cursor: 'pointer' }}>
            <img src="../../assets/logo.png" alt="PaperFull" />
            <span>PaperFull</span>
          </a>
          <div className="quota" title={`${fmt(q.used)} / ${fmt(q.total)} tokens this month`}>
            <div className="track"><div className="fill" style={{ width: pct + '%', background: fillColor }}></div></div>
            <span className="num">{fmt(q.used)}/{fmt(q.total)}</span>
          </div>
          <nav className="hdr-nav">
            <a className={active === 'dashboard' ? 'active' : ''} onClick={() => onNav('dashboard')} style={{ cursor: 'pointer' }}>Papers</a>
          </nav>
        </div>
        <div className="hdr-right">
          <button className="iconbtn" title="3 papers recently finished">
            {Icon.bell({})}
            <span className="badge-dot">3</span>
          </button>
          <button className="usermenu-btn" onClick={() => setMenuOpen(!menuOpen)}>
            <span className="avatar">R</span>
            <span>Rofiq P.</span>
            <span style={{ color: 'var(--fg-muted)' }}>▾</span>
          </button>
          {menuOpen && (
            <div className="menu-pop">
              <div className="mh"><div className="nm">Rofiq P.</div><div className="em">rofiq@otomasi.app</div></div>
              <div className="menu-theme">
                <div className="t">Theme</div>
                <div className="seg">
                  {THEMES.map((t) => (
                    <button key={t.v} className={theme === t.v ? 'on' : ''} onClick={() => setTheme(t.v)}>{t.label}</button>
                  ))}
                </div>
              </div>
              <button className="mi" onClick={() => { onNav('dashboard'); setMenuOpen(false); }}>📄 My Papers</button>
              <button className="mi">📊 Admin</button>
              <button className="mi danger">🚪 Sign Out</button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

window.Icon = Icon;
window.AppHeader = AppHeader;
