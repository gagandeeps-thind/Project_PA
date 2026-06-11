/* ───────────────────────────────────────────────────────────
 *  Osiris Admin – App Root
 * ─────────────────────────────────────────────────────────── */
import { useState, useEffect } from "react";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import MerchantsPage from "./pages/MerchantsPage";
import BountiesPage from "./pages/BountiesPage";
import Sidebar, { type PageKey } from "./components/Sidebar";
import type { AdminUser } from "./api/types";

function App() {
  const [admin, setAdmin] = useState<AdminUser | null>(null);
  const [page, setPage] = useState<PageKey>("dashboard");

  /* Restore session on mount */
  useEffect(() => {
    const token = localStorage.getItem("admin_token");
    const raw = localStorage.getItem("admin_data");
    if (token && raw) {
      try {
        setAdmin(JSON.parse(raw) as AdminUser);
      } catch {
        localStorage.removeItem("admin_token");
        localStorage.removeItem("admin_data");
      }
    }
  }, []);

  const handleLogin = (user: AdminUser, token: string) => {
    localStorage.setItem("admin_token", token);
    localStorage.setItem("admin_data", JSON.stringify(user));
    setAdmin(user);
    setPage("dashboard");
  };

  const handleLogout = () => {
    localStorage.removeItem("admin_token");
    localStorage.removeItem("admin_data");
    setAdmin(null);
    setPage("dashboard");
  };

  /* ── Not authenticated → Login screen ─────────────────── */
  if (!admin) {
    return <LoginPage onLogin={handleLogin} />;
  }

  /* ── Authenticated → Dashboard layout ─────────────────── */
  const renderPage = () => {
    switch (page) {
      case "dashboard":
        return <DashboardPage />;
      case "merchants":
        return <MerchantsPage />;
      case "bounties":
        return <BountiesPage />;
      default:
        return <DashboardPage />;
    }
  };

  return (
    <div className="app-layout">
      <Sidebar
        activePage={page}
        onNavigate={setPage}
        admin={admin}
        onLogout={handleLogout}
      />
      <main className="main-content">{renderPage()}</main>
    </div>
  );
}

export default App;
