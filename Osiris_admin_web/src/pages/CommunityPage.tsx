/* ───────────────────────────────────────────────────────────
 *  Community – player reports, clubs and groups (verify or
 *  suspend), and city seasons. Every action needs a reason.
 * ─────────────────────────────────────────────────────────── */
import { useCallback, useEffect, useState } from "react";
import { Users } from "lucide-react";
import {
  apiErrorMessage,
  createSeason,
  getAdminCommunities,
  getReports,
  resetDisplayName,
  resolveReport,
  setCommunityStatus,
} from "../api/client";
import type { AdminCommunity, AdminReport } from "../api/types";

type Tab = "reports" | "communities" | "seasons";

type Pending =
  | { kind: "report"; item: AdminReport; status: "actioned" | "dismissed" }
  | { kind: "community"; item: AdminCommunity; change: { verified?: boolean; status?: "active" | "suspended" }; label: string }
  | { kind: "name"; userId: number };

const REASON_LABELS: Record<string, string> = {
  unsafe_route: "Unsafe route",
  harassment: "Harassment",
  cheating: "Cheating",
  spam: "Spam",
  inappropriate_name: "Inappropriate name",
  privacy: "Privacy",
  other: "Other",
};

export default function CommunityPage() {
  const [tab, setTab] = useState<Tab>("reports");
  const [reportStatus, setReportStatus] = useState("open");
  const [reports, setReports] = useState<AdminReport[]>([]);
  const [communities, setCommunities] = useState<AdminCommunity[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [season, setSeason] = useState({ name: "", city: "", description: "", starts_at: "", ends_at: "" });

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (tab === "reports") setReports(await getReports(reportStatus));
      if (tab === "communities") setCommunities(await getAdminCommunities());
    } catch (err) {
      setError(apiErrorMessage(err, "Failed to load"));
    } finally {
      setLoading(false);
    }
  }, [tab, reportStatus]);

  useEffect(() => {
    load();
  }, [load]);

  const confirm = async () => {
    if (!pending || reason.trim().length < 3) return;
    setBusy(true);
    setError("");
    try {
      if (pending.kind === "report") {
        const res = await resolveReport(pending.item.id, pending.status, reason.trim());
        setNotice(`${res.resolved} report(s) marked ${pending.status}.`);
      } else if (pending.kind === "community") {
        await setCommunityStatus(pending.item.id, pending.change, reason.trim());
        setNotice(`${pending.item.name}: ${pending.label.toLowerCase()} done.`);
      } else {
        await resetDisplayName(pending.userId, reason.trim());
        setNotice(`Player #${pending.userId} display name reset.`);
      }
      setPending(null);
      setReason("");
      await load();
    } catch (err) {
      setError(apiErrorMessage(err, "Action failed"));
    } finally {
      setBusy(false);
    }
  };

  const submitSeason = async () => {
    setError("");
    try {
      const s = await createSeason({
        name: season.name.trim(),
        city: season.city.trim(),
        description: season.description.trim() || undefined,
        starts_at: new Date(season.starts_at).toISOString(),
        ends_at: new Date(season.ends_at).toISOString(),
      });
      setNotice(`Season "${s.name}" created for ${s.city} (${s.status}).`);
      setSeason({ name: "", city: "", description: "", starts_at: "", ends_at: "" });
    } catch (err) {
      setError(apiErrorMessage(err, "Could not create the season"));
    }
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "reports", label: "Reports" },
    { key: "communities", label: "Clubs & groups" },
    { key: "seasons", label: "Seasons" },
  ];

  const dialogTitle = !pending
    ? ""
    : pending.kind === "report"
    ? `${pending.status === "actioned" ? "Mark actioned" : "Dismiss"}: report #${pending.item.id}`
    : pending.kind === "community"
    ? `${pending.label}: ${pending.item.name}`
    : `Reset display name of player #${pending.userId}`;

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Community</h2>
        <p>Review player reports, verify real clubs and gyms, and run city seasons</p>
      </div>

      <div className="filter-tabs">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`filter-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => {
              setTab(t.key);
              setNotice("");
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <div className="error-message">{error}</div>}
      {notice && <div className="badge badge-success" style={{ marginBottom: 16 }}>{notice}</div>}
      {loading && (
        <div className="spinner-wrapper">
          <div className="spinner" />
        </div>
      )}

      {!loading && tab === "reports" && (
        <>
          <div className="filter-tabs">
            {["open", "actioned", "dismissed"].map((s) => (
              <button key={s} className={`filter-tab ${reportStatus === s ? "active" : ""}`} onClick={() => setReportStatus(s)}>
                {s}
              </button>
            ))}
          </div>
          {reports.length === 0 ? (
            <div className="empty-state">
              <Users size={48} />
              <p>No {reportStatus} reports.</p>
            </div>
          ) : (
            <div className="data-table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Target</th>
                    <th>Reason</th>
                    <th>Details</th>
                    <th>Open on target</th>
                    <th>Received</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((r) => (
                    <tr key={r.id}>
                      <td>#{r.id}</td>
                      <td style={{ fontWeight: 600 }}>{r.target_summary}</td>
                      <td>
                        <span className={`badge ${r.reason === "unsafe_route" ? "badge-error" : "badge-warning"}`}>
                          {REASON_LABELS[r.reason] ?? r.reason}
                        </span>
                      </td>
                      <td style={{ maxWidth: 280 }}>{r.details ?? "—"}</td>
                      <td>{r.open_reports_on_target}</td>
                      <td style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                        {new Date(r.created_at + "Z").toLocaleString()}
                      </td>
                      <td>
                        {r.status === "open" && (
                          <div className="btn-actions">
                            <button className="btn-sm btn-activate" onClick={() => setPending({ kind: "report", item: r, status: "actioned" })}>
                              Actioned
                            </button>
                            <button className="btn-sm btn-deactivate" onClick={() => setPending({ kind: "report", item: r, status: "dismissed" })}>
                              Dismiss
                            </button>
                            {r.target_type === "user" && (
                              <button className="btn-sm btn-deactivate" onClick={() => setPending({ kind: "name", userId: r.target_id })}>
                                Reset name
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: 12 }}>
            Resolving one report closes every open report on the same target. To suspend a player or a
            challenge, use Trust &amp; Safety; three unsafe-route reports pause a challenge automatically.
          </p>
        </>
      )}

      {!loading && tab === "communities" && (
        communities.length === 0 ? (
          <div className="empty-state">
            <Users size={48} />
            <p>No clubs or groups yet.</p>
          </div>
        ) : (
          <div className="data-table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Kind</th>
                  <th>City</th>
                  <th>Members</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {communities.map((c) => (
                  <tr key={c.id}>
                    <td style={{ fontWeight: 600 }}>
                      {c.name} {c.verified && <span className="badge badge-cyan">verified</span>}
                      <div style={{ color: "var(--text-secondary)", fontSize: "0.8rem", fontWeight: 400 }}>
                        {c.slug} · owner user {c.owner_user_id}
                        {c.status_reason ? ` · ${c.status_reason}` : ""}
                      </div>
                    </td>
                    <td>{c.kind}</td>
                    <td>{c.city ?? "—"}</td>
                    <td>{c.member_count}</td>
                    <td>
                      <span className={`badge ${c.status === "active" ? "badge-success" : "badge-error"}`}>{c.status}</span>
                    </td>
                    <td>
                      <div className="btn-actions">
                        {!c.verified && (
                          <button className="btn-sm btn-activate" onClick={() => setPending({ kind: "community", item: c, change: { verified: true }, label: "Verify" })}>
                            Verify
                          </button>
                        )}
                        {c.status === "active" ? (
                          <button className="btn-sm btn-deactivate" onClick={() => setPending({ kind: "community", item: c, change: { status: "suspended" }, label: "Suspend" })}>
                            Suspend
                          </button>
                        ) : (
                          <button className="btn-sm btn-activate" onClick={() => setPending({ kind: "community", item: c, change: { status: "active" }, label: "Reinstate" })}>
                            Reinstate
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {tab === "seasons" && (
        <div className="form-card">
          <h3 className="section-title">New city season</h3>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Name</label>
              <input className="form-input" value={season.name} onChange={(e) => setSeason({ ...season, name: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">City</label>
              <input className="form-input" placeholder="Bedford NS" value={season.city} onChange={(e) => setSeason({ ...season, city: e.target.value })} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Starts</label>
              <input className="form-input" type="datetime-local" value={season.starts_at} onChange={(e) => setSeason({ ...season, starts_at: e.target.value })} />
            </div>
            <div className="form-group">
              <label className="form-label">Ends (at most 120 days later)</label>
              <input className="form-input" type="datetime-local" value={season.ends_at} onChange={(e) => setSeason({ ...season, ends_at: e.target.value })} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Description players see</label>
            <input className="form-input" maxLength={500} value={season.description} onChange={(e) => setSeason({ ...season, description: e.target.value })} />
          </div>
          <div className="form-actions">
            <button
              className="btn-sm btn-activate"
              disabled={!season.name || !season.city || !season.starts_at || !season.ends_at}
              onClick={submitSeason}
            >
              Create season
            </button>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: 12 }}>
            Players rank by capped points (1 per 100 m, at most 10 km a day, plus 10 per active day). Clubs rank
            by the average of their members who joined, and need at least three. To seed official routes and
            partner clubs for a new city, run <code>scripts/seed_city.py</code>.
          </p>
        </div>
      )}

      {pending && (
        <div className="dialog-overlay">
          <div className="dialog">
            <h3>{dialogTitle}</h3>
            <p>Your reason is stored in the audit log{pending.kind === "report" ? " and shown to the reporters" : ""}.</p>
            <div className="form-group">
              <label className="form-label">Reason (required)</label>
              <input className="form-input" autoFocus value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
            </div>
            <div className="dialog-actions">
              <button className="btn-cancel" onClick={() => { setPending(null); setReason(""); }}>
                Cancel
              </button>
              <button className="btn-sm btn-activate" disabled={busy || reason.trim().length < 3} onClick={confirm}>
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
