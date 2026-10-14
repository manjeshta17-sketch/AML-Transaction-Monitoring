import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import knectLogo from "../assets/knect-logo.svg";

const navigation = [
  { label: "Dashboard", path: "/dashboard", icon: DashboardIcon },
  { label: "Transactions", path: "/transactions", icon: TransactionsIcon },
  { label: "Alerts", path: "/alerts", icon: AlertsIcon },
  { label: "Cases", path: "/cases", icon: CasesIcon },
  { label: "File Processing", path: "/file-processing", icon: FilesIcon },
  { label: "Reports", path: "/reports", icon: ReportsIcon },
  { label: "Rules", path: "/rules", icon: RulesIcon },
];

const pageCopy: Record<string, { title: string; subtitle: string }> = {
  "/dashboard": { title: "Dashboard", subtitle: "Operational view of monitoring activity." },
  "/transactions": { title: "Transactions", subtitle: "All transactions are displayed below." },
  "/alerts": { title: "Alert Management", subtitle: "All alerts are displayed below." },
  "/cases": { title: "Case Management", subtitle: "All Cases are displayed below." },
  "/rules": { title: "Rules", subtitle: "Configured monitoring rules are displayed below." },
  "/file-processing": { title: "File Processing", subtitle: "Import and monitor transaction reports." },
  "/reports": { title: "Reports", subtitle: "Operational monitoring reports." },
};

function currentCopy(pathname: string) {
  const match = Object.keys(pageCopy)
    .sort((a, b) => b.length - a.length)
    .find((path) => pathname === path || pathname.startsWith(`${path}/`));
  if (pathname.includes("/") && match && pathname !== match) {
    return { title: pageCopy[match].title, subtitle: "Review the selected record." };
  }
  return pageCopy[match ?? "/dashboard"];
}

export function AppShell() {
  const [expanded, setExpanded] = useState(false);
  const location = useLocation();
  const copy = currentCopy(location.pathname);

  return (
    <div className={`app-shell ${expanded ? "sidebar-expanded" : ""}`}>
      <aside className="sidebar">
        <NavLink to="/dashboard" className="brand" aria-label="KNECT home">
          <img src={knectLogo} alt="KNECT" />
          <span>AML Intelligence</span>
        </NavLink>
        <div className="sidebar-menu-label">
          <span>Workspace</span>
          <button
            className="sidebar-toggle"
            type="button"
            aria-label={expanded ? "Collapse navigation" : "Expand navigation"}
            onClick={() => setExpanded((current) => !current)}
          >
            <PanelIcon />
          </button>
        </div>
        <nav aria-label="Primary navigation">
          {navigation.slice(0, -1).map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                title={item.label}
                className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              >
                <Icon />
                <span className="nav-text">{item.label}</span>
              </NavLink>
            );
          })}
          <div className="nav-separator" />
          {navigation.slice(-1).map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                title={item.label}
                className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              >
                <Icon />
                <span className="nav-text">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <div className="shell-main">
        <header className="top-header">
          <div className="header-context">
            <span className="header-product">KNECT</span>
            <span className="header-divider">/</span>
            <strong>{copy.title}</strong>
            <span className="header-muted">{copy.subtitle}</span>
          </div>
          <div className="header-actions">
            <span className="system-status"><i />Monitoring live</span>
            <button className="icon-button notification-button" type="button" aria-label="Notifications">
              <BellIcon />
              <span>3</span>
            </button>
            <button className="profile-menu" type="button" aria-label="Open analyst profile">
              <span className="avatar" aria-hidden="true">AN</span>
              <span className="profile-copy"><strong>Analyst</strong><small>Compliance team</small></span>
              <ChevronIcon />
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function DashboardIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h7v7H4V4zm9 0h7v4h-7V4zM4 13h7v7H4v-7zm9 6h7v4h-7v-4zm0-6h7v4h-7v-4z" /></svg>
  );
}
function TransactionsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7h13l-3-3m3 3-3 3M17 17H4l3 3m-3-3 3-3" /></svg>
  );
}
function AlertsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 3 20h18L12 3zm0 6v5m0 3h.01" /></svg>
  );
}
function CasesIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2h5v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7h5zm2 0h4V5h-4v2z" /></svg>
  );
}
function RulesIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v3H5V5zm0 6h14v3H5v-3zm0 6h10v3H5v-3z" /></svg>
  );
}
function FilesIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6V3zm8 1.5V8h3.5" /></svg>
  );
}
function ReportsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19V9h3v10H5zm6 0V5h3v14h-3zm6 0v-6h3v6h-3z" /></svg>
  );
}
function PanelIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h11M4 18h16" /></svg>
  );
}
function BellIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
  );
}
function ChevronIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 10 4 4 4-4" /></svg>
  );
}
