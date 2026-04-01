import { NavLink, Outlet } from 'react-router-dom';
import './Layout.css';

const NAV = [
  {
    label: '概览',
    items: [
      { to: '/', icon: '◉', label: '总览' },
      { to: '/messages', icon: '◧', label: '消息记录' },
    ],
  },
  {
    label: '管理',
    items: [
      { to: '/contacts', icon: '◎', label: '联系人' },
      { to: '/groups', icon: '◫', label: '群聊' },
    ],
  },
  {
    label: '智能',
    items: [
      { to: '/reviews', icon: '◇', label: '审核' },
      { to: '/analyses', icon: '△', label: '分析' },
      { to: '/scheduler', icon: '◈', label: '调度' },
    ],
  },
  {
    label: '系统',
    items: [
      { to: '/settings', icon: '◎', label: '设置' },
    ],
  },
];

export default function Layout() {
  return (
    <div className="app-layout">
      <nav className="sidebar">
        <div className="sidebar-title">替我聊 <span>v1</span></div>
        {NAV.map((section) => (
          <div key={section.label} className="nav-section">
            <div className="nav-section-label">{section.label}</div>
            {section.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                end={item.to === '/'}
              >
                <span className="nav-icon">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
        <div className="sidebar-footer">macOS · Local</div>
      </nav>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
