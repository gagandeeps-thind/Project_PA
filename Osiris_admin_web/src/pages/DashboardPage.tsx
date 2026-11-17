/* ───────────────────────────────────────────────────────────
 *  Dashboard Page – Platform KPIs
 * ─────────────────────────────────────────────────────────── */
import {
  Gem,
  BarChart3,
  Store,
  Activity,
} from "lucide-react";
import { getPlatformRevenue, getMerchants } from "../api/client";
import type { PlatformRevenue } from "../api/types";
import { CardsSkeleton } from "../components/Skeleton";
import { useFetch } from "../hooks/useFetch";

/* The API has no merchant count, so this asks for the active ones only and counts them. */
const loadDashboard = (signal: AbortSignal) =>
  Promise.all([getPlatformRevenue(signal), getMerchants("active", signal)]);

export default function DashboardPage() {
  const { data, loading, error } = useFetch(loadDashboard, "Failed to load data");
  const revenue: PlatformRevenue | null = data?.[0] ?? null;
  const merchantCount = data?.[1].length ?? 0;

  if (loading) {
    return <CardsSkeleton />;
  }

  if (error) {
    return <div className="error-message">{error}</div>;
  }

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Platform Overview</h2>
        <p>Real-time Osiris ecosystem metrics</p>
      </div>

      {/* KPI Cards */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-icon cyan">
            <Gem size={22} />
          </div>
          <div className="kpi-label">Total Revenue</div>
          <div className="kpi-value">
            {revenue?.total_crystals.toLocaleString() ?? 0}
            <span style={{ fontSize: "0.7em", color: "var(--text-secondary)", marginLeft: 6 }}>
              crystals
            </span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon purple">
            <BarChart3 size={22} />
          </div>
          <div className="kpi-label">Revenue Events</div>
          <div className="kpi-value">{revenue?.row_count.toLocaleString() ?? 0}</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon pink">
            <Store size={22} />
          </div>
          <div className="kpi-label">Active Merchants</div>
          <div className="kpi-value">{merchantCount}</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-icon success">
            <Activity size={22} />
          </div>
          <div className="kpi-label">Platform Status</div>
          <div className="kpi-value" style={{ color: "var(--success)" }}>
            Online
          </div>
        </div>
      </div>

      {/* Revenue by Source */}
      {revenue && Object.keys(revenue.by_source).length > 0 && (
        <>
          <h3 className="section-title">Revenue by Source</h3>
          <div className="source-grid">
            {Object.entries(revenue.by_source).map(([source, amount], i) => (
              <div
                className="source-card"
                key={source}
                style={{ animationDelay: `${i * 0.06}s` }}
              >
                <div className="source-name">{source.replace(/_/g, " ")}</div>
                <div className="source-value">
                  {amount.toLocaleString()}{" "}
                  <span style={{ fontSize: "0.65em", color: "var(--text-secondary)" }}>
                    crystals
                  </span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
