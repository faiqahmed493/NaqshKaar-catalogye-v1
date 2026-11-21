import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/products", label: "Products" },
  { to: "/products/new", label: "Add product" },
  { to: "/jobs", label: "3D jobs" },
  { to: "/engines", label: "Engines & workers" },
  { to: "/settings", label: "Settings" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <nav className="side" aria-label="Main">
        <div className="brand">
          <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="6" fill="#2b6a88" />
            <path d="M8 22V10l8 6 8-6v12" fill="none" stroke="#f5f1e8" strokeWidth="2.4" strokeLinejoin="round" />
          </svg>
          <div><b>Naqshkaar</b><span>Catalogue Studio</span></div>
        </div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}>{n.label}</NavLink>
        ))}
        <div className="spacer" />
        <div className="who">
          <b>{user?.display_name}</b>
          {user?.email} · {user?.role.replace("_", " ")}
          <div><button className="btn small ghost" style={{ color: "#9fb2bd", paddingLeft: 0 }} onClick={logout}>Sign out</button></div>
        </div>
      </nav>
      <main className="main"><Outlet /></main>
    </div>
  );
}
