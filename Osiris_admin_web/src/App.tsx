/* ───────────────────────────────────────────────────────────
 *  Osiris Admin – App Root
 * ─────────────────────────────────────────────────────────── */
import { lazy, Suspense, useCallback, useState, useEffect } from "react";
import LoginPage from "./pages/LoginPage";
import Sidebar, { type PageKey } from "./components/Sidebar";
import ErrorBoundary from "./components/ErrorBoundary";
import { PageSkeleton } from "./components/Skeleton";
import { onUnauthorized } from "./api/client";
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

/** The saved session, read before the first render so a reload never flashes the login screen. */
function restoreSession(): AdminUser | null {
  try {
    const token = localStorage.getItem("admin_token");
    const raw = localStorage.getItem("admin_data");
    if (token && raw) return JSON.parse(raw) as AdminUser;
  } catch {
    /* Unreadable or blocked storage: fall through and sign in again. */
  }
  try {
    localStorage.removeItem("admin_token");
    localStorage.removeItem("admin_data");
  } catch {
    /* Storage unavailable. */
  }
  return null;
}

function App() {
  const [admin, setAdmin] = useState<AdminUser | null>(restoreSession);
  const [page, setPage] = useState<PageKey>("dashboard");

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

  /* An expired or revoked token signs the admin out instead of failing every request. */
  useEffect(() => onUnauthorized(handleLogout), [handleLogout]);

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
        <ErrorBoundary resetKey={page}>
          <Suspense fallback={<PageSkeleton />}>{renderPage()}</Suspense>
        </ErrorBoundary>
      </main>
    </div>
  );
}

export default App;
