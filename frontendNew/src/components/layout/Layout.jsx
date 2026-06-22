import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, FileText, Image, Settings, LogOut, Bell, Search } from 'lucide-react';
import styles from './Layout.module.css';
import Input from '../ui/Input';

const navItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/dashboard' },
  { icon: FileText, label: 'Editor', path: '/editor' },
  { icon: Image, label: 'Assets & Files', path: '/files' },
];

const Layout = () => {
  return (
    <div className="layout">
      {/* Sidebar */}
      <aside className={`sidebar ${styles.sidebar}`}>
        <div className={styles.logoContainer}>
          <div className={styles.logoBox}>P</div>
          <span className={styles.logoText}>PaperFull</span>
        </div>

        <nav className={styles.nav}>
          <p className={styles.navSection}>Main Menu</p>
          <ul>
            {navItems.map((item) => (
              <li key={item.path}>
                <NavLink 
                  to={item.path} 
                  className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
                >
                  <item.icon size={20} />
                  <span>{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className={styles.sidebarFooter}>
          <div className={styles.quotaBox}>
            <div className={styles.quotaHeader}>
              <span>Token Quota</span>
              <span>256/1000</span>
            </div>
            <div className={styles.quotaBar}>
              <div className={styles.quotaFill} style={{ width: '25.6%' }}></div>
            </div>
            <button className={styles.upgradeBtn}>Upgrade Plan</button>
          </div>
          
          <button className={styles.logoutBtn}>
            <LogOut size={18} />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className={`header ${styles.header}`}>
          <div className={styles.searchContainer}>
            <Input 
              placeholder="Search papers or files..." 
              icon={Search}
              className={styles.searchInput}
            />
          </div>
          <div className={styles.headerRight}>
            <button className={styles.iconBtn}>
              <Bell size={20} />
              <span className={styles.badge}></span>
            </button>
            <div className={styles.userProfile}>
              <div className={styles.avatar}>SR</div>
              <div className={styles.userInfo}>
                <span className={styles.userName}>Sirobo</span>
                <span className={styles.userRole}>Researcher</span>
              </div>
            </div>
          </div>
        </header>

        <div className="page-content animate-fade-in">
          <Outlet />
        </div>
      </main>
    </div>
  );
};

export default Layout;
