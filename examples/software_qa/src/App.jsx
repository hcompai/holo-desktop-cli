import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth, useAuth } from "./auth.jsx";
import ChatWidget from "./components/ChatWidget.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Login from "./pages/Login.jsx";
import Settings from "./pages/Settings.jsx";
import Tickets from "./pages/Tickets.jsx";
import { activeRegressions } from "./regressions.js";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <Shell />
          </RequireAuth>
        }
      />
    </Routes>
  );
}

function Shell() {
  const { user, logout } = useAuth();
  const regressions = activeRegressions();

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/dashboard" className="brand">
          ☁️ Nimbus Desk
        </Link>
        <nav>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/tickets">Tickets</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="topbar-right">
          <span className="user-email">{user}</span>
          <button className="btn btn-ghost" onClick={logout} data-testid="logout">
            Log out
          </button>
        </div>
      </header>

      {regressions.length > 0 && (
        <div className="regression-banner" data-testid="regression-banner">
          ⚠️ Simulated regressions active: {regressions.join(", ")}
        </div>
      )}

      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/tickets" element={<Tickets />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>

      <ChatWidget />
    </div>
  );
}
