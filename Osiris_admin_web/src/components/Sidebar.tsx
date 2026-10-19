/* ───────────────────────────────────────────────────────────
 *  Sidebar Navigation
 * ─────────────────────────────────────────────────────────── */
import {
  Shield,
  LayoutDashboard,
  Store,
  MapPin,
  ShieldCheck,
  LogOut,
  TrendingUp,
  Users,
  Dumbbell,
} from "lucide-react";
import type { AdminUser } from "../api/types";

export type PageKey = "dashboard" | "growth" | "community" | "trust" | "exercise" | "merchants" | "bounties";

interface SidebarProps {
  activePage: PageKey;
  onNavigate: (page: PageKey) => void;
  admin: AdminUser;
  onLogout: () => void;
}

const navItems: { key: PageKey; label: string; icon: typeof LayoutDashboard }[] = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { key: "growth", label: "Growth", icon: TrendingUp },
  { key: "community", label: "Community", icon: Users },
  { key: "trust", label: "Trust & Safety", icon: ShieldCheck },
  { key: "exercise", label: "Exercise review", icon: Dumbbell },
  { key: "merchants", label: "Merchants", icon: Store },
  { key: "bounties", label: "Bounties", icon: MapPin },
];

export default function Sidebar({
  activePage,
  onNavigate,
  admin,
  onLogout,
}: SidebarProps) {
  const initials = admin.name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <aside className="sidebar">
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">
          <Shield size={22} />
        </div>
        <div>
          <h1>OSIRIS</h1>
          <p>Command Center</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {navItems.map(({ key, label, icon: Icon }) => (
          <div
            key={key}
            className={`sidebar-nav-item ${activePage === key ? "active" : ""}`}
            onClick={() => onNavigate(key)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && onNavigate(key)}
          >
            <Icon size={19} />
            {label}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="sidebar-user">
          <div className="sidebar-avatar">{initials}</div>
          <div className="sidebar-user-info">
            <div className="sidebar-user-name">{admin.name}</div>
            <div className="sidebar-user-role">Admin</div>
          </div>
        </div>
        <button className="btn-disconnect" onClick={onLogout}>
          <LogOut size={15} />
          Disconnect
        </button>
      </div>
    </aside>
  );
}
