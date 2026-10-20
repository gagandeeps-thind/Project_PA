/* ───────────────────────────────────────────────────────────
 *  Exercise review – camera-verified sets the server re-check
 *  flagged (replayed timing, low valid ratio, …). Approve to
 *  grant the set's capped XP, or reject. Each set is decided once.
 * ─────────────────────────────────────────────────────────── */
import { useCallback, useEffect, useState } from "react";
import { Dumbbell } from "lucide-react";
import { apiErrorMessage, getExerciseSets, reviewExerciseSet } from "../api/client";
import type { AdminExerciseSet } from "../api/types";
import { TableSkeleton } from "../components/Skeleton";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

type Pending = { item: AdminExerciseSet; decision: "approve" | "reject" };

const REASONS: Record<string, string> = {
  replay_suspected: "Machine-regular rep timing",
  low_valid_ratio: "Most reps did not count",
  too_fast: "Reps too fast",
  too_slow: "Rep too slow",
  form_break: "Form broke",
  wrong_position: "Wrong body position",
  low_visibility: "Partly out of view",
  tracking_glitch: "Tracking glitch",
  unsteady_tracking: "Unsteady tracking",
  partial_range: "Partial range",
};

const amount = (s: AdminExerciseSet) =>
  s.exercise_key === "plank" ? `${Math.round(s.hold_s)} s hold` : `${s.reps_valid} / ${s.reps_attempted} reps`;

export default function ExerciseReviewPage() {
  const [status, setStatus] = useState("review");
  const [player, setPlayer] = useState("");
  const [sets, setSets] = useState<AdminExerciseSet[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const playerFilter = useDebouncedValue(player);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setSets(await getExerciseSets(status, Number(playerFilter) || undefined));
    } catch (err) {
      setError(apiErrorMessage(err, "Failed to load"));
    } finally {
      setLoading(false);
    }
  }, [status, playerFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const confirm = async () => {
    if (!pending || note.trim().length < 3) return;
    setBusy(true);
    setError("");
    try {
      const res = await reviewExerciseSet(pending.item.id, pending.decision, note.trim());
      setNotice(
        `Set #${res.id} ${res.status}${res.status === "verified" ? ` (+${res.xp_awarded} XP)` : ""}.`
      );
      setPending(null);
      setNote("");
      await load();
    } catch (err) {
      setError(apiErrorMessage(err, "Action failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Exercise review</h2>
        <p>Camera-verified sets flagged by the server re-check. No video exists: decide from timings and reasons.</p>
      </div>

      <div className="filter-tabs">
        {["review", "rejected", "verified"].map((s) => (
          <button
            key={s}
            className={`filter-tab ${status === s ? "active" : ""}`}
            onClick={() => {
              setStatus(s);
              setNotice("");
            }}
          >
            {s === "review" ? `Waiting${status === "review" && sets.length ? ` (${sets.length})` : ""}` : s}
          </button>
        ))}
        <input
          className="form-input"
          style={{ maxWidth: 160, marginLeft: "auto" }}
          placeholder="Player id"
          inputMode="numeric"
          value={player}
          onChange={(e) => setPlayer(e.target.value.replace(/[^0-9]/g, ""))}
        />
      </div>

      {error && <div className="error-message">{error}</div>}
      {notice && <div className="badge badge-success" style={{ marginBottom: 16 }}>{notice}</div>}

      {loading ? (
        <TableSkeleton />
      ) : sets.length === 0 ? (
        <div className="empty-state">
          <Dumbbell size={48} />
          <p>No {status === "review" ? "sets waiting for review" : `${status} sets`}.</p>
        </div>
      ) : (
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Set</th>
                <th>Player</th>
                <th>Exercise</th>
                <th>Flags</th>
                <th>Rep timings (s)</th>
                <th>Player history</th>
                {status === "review" && <th>Decision</th>}
              </tr>
            </thead>
            <tbody>
              {sets.map((s) => (
                <tr key={s.id}>
                  <td>
                    #{s.id}
                    <div style={{ color: "var(--text-secondary)", fontSize: "0.8rem" }}>
                      {new Date(s.created_at + "Z").toLocaleString()}
                    </div>
                  </td>
                  <td>
                    {s.display_name}
                    <div style={{ color: "var(--text-secondary)", fontSize: "0.8rem" }}>user {s.user_id}</div>
                  </td>
                  <td style={{ fontWeight: 600 }}>
                    {s.exercise_name}
                    <div style={{ fontWeight: 400, fontSize: "0.85rem" }}>
                      {amount(s)} · {Math.round(s.duration_s)} s · form {Math.round(s.form_score * 100)}%
                    </div>
                  </td>
                  <td>
                    {s.reason_codes.length === 0
                      ? "—"
                      : s.reason_codes.map((r) => (
                          <span key={r} className="badge badge-warning" style={{ marginRight: 4 }}>
                            {REASONS[r] ?? r}
                          </span>
                        ))}
                  </td>
                  <td>
                    <code style={{ fontSize: "0.75rem" }}>
                      {s.rep_durations_s.length ? s.rep_durations_s.map((d) => d.toFixed(2)).join(" ") : "—"}
                    </code>
                    {s.rep_duration_cv !== null && (
                      <div style={{ color: "var(--text-secondary)", fontSize: "0.8rem" }}>
                        variation {(s.rep_duration_cv * 100).toFixed(1)}%
                      </div>
                    )}
                  </td>
                  <td>
                    {s.player_flagged_sets} of {s.player_sets} sets flagged
                  </td>
                  {status === "review" && (
                    <td>
                      <div className="btn-actions">
                        <button className="btn-sm btn-activate" onClick={() => setPending({ item: s, decision: "approve" })}>
                          Approve (+{s.xp_if_approved} XP)
                        </button>
                        <button className="btn-sm btn-deactivate" onClick={() => setPending({ item: s, decision: "reject" })}>
                          Reject
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pending && (
        <div className="dialog-overlay" onClick={() => !busy && setPending(null)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>
              {pending.decision === "approve" ? "Approve" : "Reject"} set #{pending.item.id}
            </h3>
            <p>
              {pending.decision === "approve"
                ? `The set counts and ${pending.item.xp_if_approved} XP is granted (within the player's daily caps).`
                : "The set stays without XP. Your note is stored in the audit log."}
            </p>
            <div className="form-group">
              <label className="form-label">Note (required)</label>
              <input className="form-input" autoFocus value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
            </div>
            <div className="dialog-actions">
              <button className="btn-cancel" onClick={() => setPending(null)} disabled={busy}>
                Cancel
              </button>
              <button
                className="btn-sm btn-deactivate"
                onClick={confirm}
                disabled={busy || note.trim().length < 3}
                style={{ padding: "10px 20px", fontSize: "0.85rem" }}
              >
                {busy ? "Processing…" : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
