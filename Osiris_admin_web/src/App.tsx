/* ───────────────────────────────────────────────────────────
 *  Osiris Admin – App Root
 * ─────────────────────────────────────────────────────────── */
import { lazy, Suspense, useCallback, useState, useEffect } from "react";
import LoginPage from "./pages/LoginPage";
import Sidebar, { type PageKey } from "./components/Sidebar";
import { PageSkeleton } from "./components/Skeleton";
import type { AdminUser } from "./api/types";

/* Each page is its own chunk, fetched the first time it is opened, so signing in
 * downloads the shell and the dashboard only. */
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const MerchantsPage = lazy(() => import("./pages/MerchantsPage"));
const BountiesPage = lazy(() => import("./pages/BountiesPage"));
const TrustPage = lazy(() => import("./pages/TrustPage"));
const GrowthPage = lazy(() => import("./pages/GrowthPage"));
const CommunityPage = lazy(() => import("./pages/CommunityPage"));
const ExerciseReviewPage = lazy(() => import("./pages/ExerciseReviewPage"));

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

  const handleLogin = useCallback((user: AdminUser, token: string) => {
    localStorage.setItem("admin_token", token);
    localStorage.setItem("admin_data", JSON.stringify(user));
    setAdmin(user);
    setPage("dashboard");
  }, []);

  /* Stable, so the memoised Sidebar re-renders only when the page or admin changes. */
  const handleLogout = useCallback(() => {
    localStorage.removeItem("admin_token");
    localStorage.removeItem("admin_data");
    setAdmin(null);
    setPage("dashboard");
  }, []);

  /* ── Not authenticated → Login screen ─────────────────── */
  if (!admin) {
    return <LoginPage onLogin={handleLogin} />;
  }

  /* ── Authenticated → Dashboard layout ─────────────────── */
  const renderPage = () => {
    switch (page) {
      case "dashboard":
        return <DashboardPage />;
      case "growth":
        return <GrowthPage />;
      case "community":
        return <CommunityPage />;
      case "trust":
        return <TrustPage />;
      case "exercise":
        return <ExerciseReviewPage />;
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
      <main className="main-content">
        <Suspense fallback={<PageSkeleton />}>{renderPage()}</Suspense>
      </main>
    </div>
  );
}

export default App;
