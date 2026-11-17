/* ───────────────────────────────────────────────────────────
 *  Trust & Safety – review queue, challenge controls, user
 *  suspension, and audit search (PRD-008 / PRD-010)
 * ─────────────────────────────────────────────────────────── */
import { memo, useCallback, useState } from "react";
import { ShieldCheck } from "lucide-react";
import {
  apiErrorMessage,
  getAdminChallenges,
  getAuditEvents,
  getReviewQueue,
  reviewAttempt,
  setChallengeStatus,
  suspendCourse,
  suspendUser,
  unsuspendUser,
} from "../api/client";
import type { AdminChallenge, AuditEvent, ReviewQueueItem } from "../api/types";
import { TableSkeleton } from "../components/Skeleton";
import ListFooter from "../components/ListFooter";
import ReasonDialog from "../components/ReasonDialog";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { usePagedList } from "../hooks/useFetch";

type Tab = "review" | "challenges" | "users" | "audit";

type PendingAction =
  | { kind: "review"; item: ReviewQueueItem; decision: "accept" | "reject" }
  | { kind: "challenge"; item: AdminChallenge; action: "suspend" | "resume" | "void" }
  | { kind: "course"; courseId: number };

const fmtTime = (s: number | null) => {
  if (s === null) return "—";
  const r = Math.round(s);
  return `${Math.floor(r / 60)}:${String(r % 60).padStart(2, "0")}`;
};

const statusBadge = (status: string) => {
  const cls =
    status === "open"
      ? "badge-success"
      : status === "suspended" || status === "voided"
      ? "badge-error"
      : status === "closed"
      ? "badge-warning"
      : "badge-cyan";
  return <span className={`badge ${cls}`}>{status}</span>;
};

/* Memoised: typing in the entity-id filter above it does not re-render the rows. */
const AuditTable = memo(function AuditTable({ events }: { events: AuditEvent[] }) {
  return (
    <div className="data-table-wrapper">
      <table className="data-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Entity</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id}>
              <td style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                {new Date(e.created_at + "Z").toLocaleString()}
              </td>
              <td>
                {e.actor_type}
                {e.actor_id !== null ? ` ${e.actor_id}` : ""}
              </td>
              <td>
                <span className="badge badge-purple">{e.action}</span>
              </td>
              <td>
                {e.entity_type} {e.entity_id ?? ""}
              </td>
              <td>
                <code style={{ fontSize: "0.75rem", whiteSpace: "pre-wrap" }}>{JSON.stringify(e.details)}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
});

export default function TrustPage() {
  const [tab, setTab] = useState<Tab>("review");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [challengeFilter, setChallengeFilter] = useState("open");
  const [auditType, setAuditType] = useState("");
  const [auditId, setAuditId] = useState("");
  const auditIdFilter = useDebouncedValue(auditId);

  const [userId, setUserId] = useState("");
  const [userReason, setUserReason] = useState("");

  const [pending, setPending] = useState<PendingAction | null>(null);
  const [busy, setBusy] = useState(false);

  /* One paged list per tab; only the open tab's list fetches. */
  const queue = usePagedList<ReviewQueueItem>(
    useCallback((loaded, signal) => getReviewQueue(loaded.length, signal), []),
    "Failed to load",
    tab === "review"
  );
  const challenges = usePagedList<AdminChallenge>(
    useCallback(
      (loaded, signal) => getAdminChallenges(challengeFilter || undefined, loaded.length, signal),
      [challengeFilter]
    ),
    "Failed to load",
    tab === "challenges"
  );
  const audit = usePagedList<AuditEvent>(
    useCallback(
      (loaded, signal) =>
        getAuditEvents(
          {
            entity_type: auditType || undefined,
            entity_id: auditIdFilter ? Number(auditIdFilter) : undefined,
            before_id: loaded.at(-1)?.id,
          },
          signal
        ),
      [auditType, auditIdFilter]
    ),
    "Failed to load",
    tab === "audit"
  );
  const active = tab === "review" ? queue : tab === "challenges" ? challenges : tab === "audit" ? audit : null;
  const loading = active?.loading ?? false;

  const confirm = async (reason: string) => {
    if (!pending) return;
    setBusy(true);
    setError("");
    try {
      if (pending.kind === "review") {
        await reviewAttempt(pending.item.attempt_id, pending.decision, reason);
        setNotice(`Attempt #${pending.item.attempt_id} ${pending.decision}ed.`);
      } else if (pending.kind === "challenge") {
        await setChallengeStatus(pending.item.id, pending.action, reason);
        setNotice(`Challenge #${pending.item.id}: ${pending.action} applied.`);
      } else {
        await suspendCourse(pending.courseId, reason);
        setNotice(`Course #${pending.courseId} suspended with its live challenges.`);
      }
      setPending(null);
      await active?.reload();
    } catch (err) {
      setError(apiErrorMessage(err, "Action failed"));
    } finally {
      setBusy(false);
    }
  };

  const changeUser = async (suspend: boolean) => {
    const id = Number(userId);
    if (!id) return;
    if (suspend && userReason.trim().length < 3) {
      setError("A suspension needs a reason of at least 3 characters.");
      return;
    }
    setError("");
    try {
      const res = suspend ? await suspendUser(id, userReason.trim()) : await unsuspendUser(id);
      setNotice(`${res.email} is now ${res.suspended ? "suspended" : "active"}.`);
      setUserReason("");
    } catch (err) {
      setError(apiErrorMessage(err, "Action failed"));
    }
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "review", label: `Review queue${queue.rows.length ? ` (${queue.rows.length}${queue.hasMore ? "+" : ""})` : ""}` },
    { key: "challenges", label: "Challenges" },
    { key: "users", label: "Users" },
    { key: "audit", label: "Audit log" },
  ];

  const dialogTitle = !pending
    ? ""
    : pending.kind === "review"
    ? `${pending.decision === "accept" ? "Accept" : "Reject"} attempt #${pending.item.attempt_id}`
    : pending.kind === "challenge"
    ? `${pending.action[0].toUpperCase()}${pending.action.slice(1)} challenge #${pending.item.id}`
    : `Suspend course #${pending.courseId}`;

  const dialogBody = !pending
    ? ""
    : pending.kind === "challenge" && pending.action === "void"
    ? "Voiding reverses every XP award from this challenge and marks all attempts voided. It cannot be undone."
    : pending.kind === "course"
    ? "The course leaves the map and its open challenges are suspended."
    : pending.kind === "review" && pending.decision === "accept"
    ? "The result counts and XP is awarded to the challenger (and defender if applicable)."
    : "Your note is stored in the audit log.";

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Trust &amp; Safety</h2>
        <p>Review flagged results, control challenges, suspend accounts, and search the audit trail</p>
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

      {(error || active?.error) && <div className="error-message">{error || active?.error}</div>}
      {notice && <div className="badge badge-success" style={{ marginBottom: 16 }}>{notice}</div>}

      {loading && tab !== "audit" && <TableSkeleton />}

      {!loading && tab === "review" && (
        queue.rows.length === 0 ? (
          <div className="empty-state">
            <ShieldCheck size={48} />
            <p>No attempts waiting for review.</p>
          </div>
        ) : (
          <>
          <div className="data-table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Attempt</th>
                  <th>Challenge</th>
                  <th>Player</th>
                  <th>Time / target</th>
                  <th>On course</th>
                  <th>Submitted</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {queue.rows.map((q) => (
                  <tr key={q.attempt_id}>
                    <td>#{q.attempt_id} (run {q.run_id ?? "—"})</td>
                    <td style={{ fontWeight: 600 }}>{q.challenge_title}</td>
                    <td>user {q.user_id}</td>
                    <td>
                      {fmtTime(q.elapsed_seconds)} / {fmtTime(q.target_seconds)}
                    </td>
                    <td>{q.course_coverage === null ? "—" : `${Math.round(q.course_coverage * 100)}%`}</td>
                    <td style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                      {q.submitted_at ? new Date(q.submitted_at + "Z").toLocaleString() : "—"}
                    </td>
                    <td>
                      <div className="btn-actions">
                        <button className="btn-sm btn-activate" onClick={() => setPending({ kind: "review", item: q, decision: "accept" })}>
                          Accept
                        </button>
                        <button className="btn-sm btn-deactivate" onClick={() => setPending({ kind: "review", item: q, decision: "reject" })}>
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ListFooter shown={queue.rows.length} hasMore={queue.hasMore} loading={queue.loadingMore} onMore={queue.loadMore} />
          </>
        )
      )}

      {!loading && tab === "challenges" && (
        <>
          <div className="filter-tabs">
            {["open", "closed", "suspended", "settled", "voided", ""].map((s) => (
              <button
                key={s || "all"}
                className={`filter-tab ${challengeFilter === s ? "active" : ""}`}
                onClick={() => setChallengeFilter(s)}
              >
                {s || "all"}
              </button>
            ))}
          </div>
          {challenges.rows.length === 0 ? (
            <div className="empty-state">
              <ShieldCheck size={48} />
              <p>No challenges for this filter.</p>
            </div>
          ) : (
            <>
            <div className="data-table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Creator / course</th>
                    <th>Attempts</th>
                    <th>Closes</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {challenges.rows.map((c) => (
                    <tr key={c.id}>
                      <td>#{c.id}</td>
                      <td style={{ fontWeight: 600 }}>
                        {c.title}
                        {c.status_reason && (
                          <div style={{ color: "var(--text-secondary)", fontSize: "0.8rem", fontWeight: 400 }}>
                            {c.status_reason}
                          </div>
                        )}
                      </td>
                      <td>{statusBadge(c.status)}</td>
                      <td>
                        user {c.creator_id} / course {c.course_id}
                      </td>
                      <td>{c.attempt_count}</td>
                      <td style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                        {new Date(c.closes_at + "Z").toLocaleString()}
                      </td>
                      <td>
                        <div className="btn-actions">
                          {(c.status === "open" || c.status === "closed") && (
                            <button className="btn-sm btn-deactivate" onClick={() => setPending({ kind: "challenge", item: c, action: "suspend" })}>
                              Suspend
                            </button>
                          )}
                          {c.status === "suspended" && (
                            <button className="btn-sm btn-activate" onClick={() => setPending({ kind: "challenge", item: c, action: "resume" })}>
                              Resume
                            </button>
                          )}
                          {c.status !== "voided" && (
                            <button className="btn-sm btn-deactivate" onClick={() => setPending({ kind: "challenge", item: c, action: "void" })}>
                              Void
                            </button>
                          )}
                          <button className="btn-sm btn-deactivate" onClick={() => setPending({ kind: "course", courseId: c.course_id })}>
                            Pull course
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ListFooter shown={challenges.rows.length} hasMore={challenges.hasMore} loading={challenges.loadingMore} onMore={challenges.loadMore} />
            </>
          )}
        </>
      )}

      {tab === "users" && (
        <div className="form-card">
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Player user ID</label>
              <input className="form-input" inputMode="numeric" value={userId} onChange={(e) => setUserId(e.target.value.replace(/\D/g, ""))} />
            </div>
            <div className="form-group">
              <label className="form-label">Reason (required to suspend)</label>
              <input className="form-input" value={userReason} maxLength={500} onChange={(e) => setUserReason(e.target.value)} />
            </div>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
            A suspended player is refused on every v2 endpoint from their next request. Suspension is logged.
          </p>
          <div className="form-actions">
            <button className="btn-sm btn-deactivate" disabled={!userId} onClick={() => changeUser(true)}>
              Suspend
            </button>
            <button className="btn-sm btn-activate" disabled={!userId} onClick={() => changeUser(false)}>
              Reinstate
            </button>
          </div>
        </div>
      )}

      {tab === "audit" && (
        <>
          <div className="form-row" style={{ marginBottom: 16 }}>
            <div className="form-group">
              <label className="form-label">Entity type</label>
              <select className="form-input" value={auditType} onChange={(e) => setAuditType(e.target.value)}>
                <option value="">any</option>
                {["challenge", "challenge_attempt", "course", "run_session", "user"].map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Entity ID</label>
              <input className="form-input" inputMode="numeric" value={auditId} onChange={(e) => setAuditId(e.target.value.replace(/\D/g, ""))} />
            </div>
          </div>
          {loading ? (
            <TableSkeleton />
          ) : (
            <>
              <AuditTable events={audit.rows} />
              <ListFooter shown={audit.rows.length} hasMore={audit.hasMore} loading={audit.loadingMore} onMore={audit.loadMore} />
            </>
          )}
        </>
      )}

      {pending && (
        <ReasonDialog
          title={dialogTitle}
          body={dialogBody}
          label="Reason / note (required)"
          busy={busy}
          onCancel={() => setPending(null)}
          onConfirm={confirm}
        />
      )}
    </div>
  );
}
