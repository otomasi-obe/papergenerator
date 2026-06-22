import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import styles from './AppHeader.module.css';

const AppHeader = () => {
  const [quotaOpen, setQuotaOpen] = useState(false);
  const [bellOpen, setBellOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className={styles.header}>
      <div className={styles.headerInner}>
        {/* Logo & Nav */}
        <div className={styles.leftGroup}>
          <Link to="/dashboard" className={styles.logoLink}>
            <div className={styles.logoBox}>P</div>
            <span className={styles.logoText}>PaperFull</span>
          </Link>
          <nav className={styles.nav}>
            <Link to="/admin" className={styles.navLink}>Admin</Link>
          </nav>
        </div>

        {/* User Menu */}
        <div className={styles.rightGroup}>
          {/* Quota */}
          <div className={styles.relative}>
            <button 
              className={styles.quotaBtn}
              onClick={() => setQuotaOpen(!quotaOpen)}
            >
              <div className={styles.quotaBarBg}>
                <div className={styles.quotaBarFill} style={{ width: '25%' }}></div>
              </div>
              <span className={styles.quotaText}>25k/100k</span>
            </button>
            {quotaOpen && (
              <div className={styles.dropdown}>
                <div className={styles.dropdownTitle}>Token Usage</div>
                <div className={styles.dropdownGrid}>
                  <span>Today</span><span className={styles.textRight}>5k</span>
                  <span>Month</span><span className={styles.textRight}>25k</span>
                  <span>Left</span><span className={styles.textRight}>75k</span>
                </div>
              </div>
            )}
          </div>

          {/* Notifications */}
          <div className={styles.relative}>
            <button className={styles.iconBtn} onClick={() => setBellOpen(!bellOpen)}>
              <Bell size={20} />
            </button>
            {bellOpen && (
              <div className={styles.dropdown}>
                <div className={styles.dropdownTitle}>Paper Jobs</div>
                <div className={styles.dropdownEmpty}>No active jobs.</div>
              </div>
            )}
          </div>

          {/* Profile */}
          <div className={styles.relative}>
            <button className={styles.profileBtn} onClick={() => setMenuOpen(!menuOpen)}>
              <div className={styles.avatar}>SR</div>
              <span className={styles.userName}>Sirobo</span>
              <span className={styles.caret}>▾</span>
            </button>
            {menuOpen && (
              <div className={styles.dropdown}>
                <div className={styles.dropdownHeader}>
                  <p className={styles.userNameDark}>Sirobo</p>
                  <p className={styles.userEmail}>user@university.edu</p>
                </div>
                <Link to="/settings" className={styles.dropdownItem}>⚙️ Settings</Link>
                <div className={styles.dropdownDivider}></div>
                <button className={styles.dropdownItemDanger}>🚪 Sign Out</button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

export default AppHeader;
