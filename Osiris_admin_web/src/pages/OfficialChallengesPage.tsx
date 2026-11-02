/* ───────────────────────────────────────────────────────────
 *  Official challenges – Osiris group challenges every player
 *  sees on the Start tab's Challenge page. Progress counts the
 *  sessions players start from that page.
 * ─────────────────────────────────────────────────────────── */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Trophy } from "lucide-react";
import {
  apiErrorMessage,
  createOfficialChallenge,
  getOfficialChallenges,
  getTrainingActivities,
} from "../api/client";
import type { CreateOfficialChallengePayload, GroupChallenge, GroupMetric, TrainingActivity } from "../api/types";
import { TableSkeleton } from "../components/Skeleton";

const METRIC_LABELS: Record<GroupMetric, string> = {
  distance_m: "Distance (m)",
  duration_s: "Time (s)",
  reps: "Reps",
  sessions: "Sessions",
};

const EMPTY: CreateOfficialChallengePayload = { title: "", activity_key: "run", metric: "distance_m", target: 50000, days: 14 };

/** Goals that fit the activity: its own metric, plus time and session count for any activity. */
function metricsFor(activity?: TrainingActivity): GroupMetric[] {
  const own = activity?.metric ?? "distance_m";
  return Array.from(new Set<GroupMetric>([own, "duration_s", "sessions"]));
}

export default function OfficialChallengesPage() {
  const [rows, setRows] = useState<GroupChallenge[]>([]);
  const [activities, setActivities] = useState<TrainingActivity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CreateOfficialChallengePayload>(EMPTY);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [list, acts] = await Promise.all([getOfficialChallenges(), getTrainingActivities()]);
      setRows(list);
      setActivities(acts);
    } catch (err) {
      setError(apiErrorMessage(err, "Failed to load"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const names = useMemo(() => Object.fromEntries(activities.map((a) => [a.key, a.name])), [activities]);
  const selected = activities.find((a) => a.key === form.activity_key);
  const metrics = metricsFor(selected);

  const pickActivity = (key: string) => {
    const allowed = metricsFor(activities.find((a) => a.key === key));
    setForm((f) => ({ ...f, activity_key: key, metric: allowed.includes(f.metric) ? f.metric : allowed[0] }));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await createOfficialChallenge({ ...form, title: form.title.trim() });
      setNotice(`Published "${created.title}".`);
      setForm(EMPTY);
      setShowForm(false);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not publish"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Official challenges</h2>
        <p>Osiris group challenges shown to every player on the Start tab. Challenges never touch crystals.</p>
      </div>

      <button className="btn-create" onClick={() => setShowForm(!showForm)}>
        <Plus size={18} />
        New official challenge
      </button>

      {showForm && (
        <form className="form-card" onSubmit={submit}>
          <h3 className="section-title" style={{ marginBottom: 20 }}>
            New official challenge
          </h3>
          <div className="form-group">
            <label className="form-label" htmlFor="oc-title">Title</label>
            <input
              id="oc-title"
              className="form-input"
              placeholder="November 50 km"
              minLength={3}
              maxLength={80}
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              required
            />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="oc-activity">Activity</label>
              <select
                id="oc-activity"
                className="form-input"
                value={form.activity_key}
                onChange={(e) => pickActivity(e.target.value)}
              >
                {activities.map((a) => (
                  <option key={a.key} value={a.key}>{a.name}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="oc-metric">Goal</label>
              <select
                id="oc-metric"
                className="form-input"
                value={form.metric}
                onChange={(e) => setForm({ ...form, metric: e.target.value as GroupMetric })}
              >
                {metrics.map((m) => (
                  <option key={m} value={m}>{METRIC_LABELS[m]}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="oc-target">Target</label>
              <input
                id="oc-target"
                className="form-input"
                type="number"
                min={1}
                value={form.target}
                onChange={(e) => setForm({ ...form, target: Number(e.target.value) })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="oc-days">Length (days)</label>
              <input
                id="oc-days"
                className="form-input"
                type="number"
                min={1}
                max={90}
                value={form.days}
                onChange={(e) => setForm({ ...form, days: Number(e.target.value) })}
                required
              />
            </div>
          </div>
          <button className="btn-create" type="submit" disabled={busy}>
            {busy ? "Publishing…" : "Publish"}
          </button>
        </form>
      )}

      {error && <div className="error-message">{error}</div>}
      {notice && <div className="badge badge-success" style={{ marginBottom: 16 }}>{notice}</div>}

      {loading ? (
        <TableSkeleton />
      ) : rows.length === 0 ? (
        <div className="empty-state">
          <Trophy size={48} />
          <p>No official challenges yet.</p>
        </div>
      ) : (
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Activity</th>
                <th>Goal</th>
                <th>Window</th>
                <th>Members</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td>{c.title}</td>
                  <td>{names[c.activity_key] ?? c.activity_key}</td>
                  <td>{c.target.toLocaleString()} {METRIC_LABELS[c.metric]}</td>
                  <td>
                    {new Date(c.starts_at).toLocaleDateString()} – {new Date(c.ends_at).toLocaleDateString()}
                  </td>
                  <td>{c.members}</td>
                  <td>{c.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
