/* ───────────────────────────────────────────────────────────
 *  Growth – activation funnel and retention. Answers "where do
 *  new players drop off?" before any money goes into ads.
 * ─────────────────────────────────────────────────────────── */
import { useCallback, useEffect, useState } from "react";
import { TrendingUp } from "lucide-react";
import { apiErrorMessage, getFunnel } from "../api/client";
import type { Funnel } from "../api/types";
import { CardsSkeleton } from "../components/Skeleton";

const STEP_LABELS: Record<string, string> = {
  account_created: "Account created",
  onboarding_completed: "Onboarding complete",
  first_activity: "Started a first activity",
  first_verified_result: "First verified run",
  second_challenge: "Joined a second challenge",
};

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);

export default function GrowthPage() {
  const [days, setDays] = useState(30);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setFunnel(await getFunnel(days));
    } catch (err) {
      setError(apiErrorMessage(err, "Failed to load the funnel"));
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  const top = funnel?.steps[0]?.users ?? 0;

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Growth</h2>
        <p>Players who signed up in the window, and how far they got. Prove this loop before paying for installs.</p>
      </div>

      <div className="filter-tabs">
        {[7, 30, 90].map((d) => (
          <button key={d} className={`filter-tab ${days === d ? "active" : ""}`} onClick={() => setDays(d)}>
            Last {d} days
          </button>
        ))}
      </div>

      {error && <div className="error-message">{error}</div>}
      {loading && (
        <CardsSkeleton />
      )}

      {!loading && funnel && (
        <>
          <div className="kpi-grid">
            <div className="kpi-card">
              <div className="kpi-label">Installs</div>
              <div className="kpi-value">{funnel.installs}</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Returned in week 2</div>
              <div className="kpi-value">{pct(funnel.week1_retention)}</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Active in week 5</div>
              <div className="kpi-value">{pct(funnel.week4_retention)}</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Players who invited someone</div>
              <div className="kpi-value">{funnel.inviters}</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Challenges joined → completed</div>
              <div className="kpi-value">
                {funnel.challenges_joined} → {funnel.challenges_completed} ({pct(funnel.challenge_completion_rate)})
              </div>
            </div>
          </div>

          <h3 className="section-title">Activation funnel</h3>
          {top === 0 ? (
            <div className="empty-state">
              <TrendingUp size={48} />
              <p>No sign-ups in this window yet.</p>
            </div>
          ) : (
            <div className="data-table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Step</th>
                    <th>Players</th>
                    <th style={{ width: "40%" }}>Share of sign-ups</th>
                    <th>From previous step</th>
                  </tr>
                </thead>
                <tbody>
                  {funnel.steps.map((s) => (
                    <tr key={s.step}>
                      <td style={{ fontWeight: 600 }}>{STEP_LABELS[s.step] ?? s.step}</td>
                      <td>{s.users}</td>
                      <td>
                        <div style={{ background: "var(--border, #333)", borderRadius: 6, height: 10 }}>
                          <div
                            style={{
                              width: `${top ? (100 * s.users) / top : 0}%`,
                              background: "var(--accent, #9d4edd)",
                              height: 10,
                              borderRadius: 6,
                            }}
                          />
                        </div>
                      </td>
                      <td>{pct(s.rate_from_previous)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: 12 }}>
            Week-N retention counts players with a verified run 7N to 7N+6 days after sign-up, among those
            who signed up long enough ago to measure. Only the server records milestone events, so the app
            cannot inflate them.
          </p>
        </>
      )}
    </div>
  );
}
