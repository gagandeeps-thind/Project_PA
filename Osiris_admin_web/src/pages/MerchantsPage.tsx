/* ───────────────────────────────────────────────────────────
 *  Merchants Page
 * ─────────────────────────────────────────────────────────── */
import { useState, useCallback } from "react";
import { Store } from "lucide-react";
import {
  apiErrorMessage,
  getMerchants,
  PAGE_SIZE,
  activateMerchant,
  deactivateMerchant,
} from "../api/client";
import type { Merchant } from "../api/types";
import { TableSkeleton } from "../components/Skeleton";
import ListFooter from "../components/ListFooter";
import { useFetch } from "../hooks/useFetch";

type FilterTab = "all" | "active" | "pending" | "declined";

export default function MerchantsPage() {
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<FilterTab>("all");
  /* The server sends the whole list, so paging here only limits how many rows are drawn. */
  const [visible, setVisible] = useState(PAGE_SIZE);

  /* Confirmation dialog state */
  const [dialog, setDialog] = useState<{
    open: boolean;
    action: "activate" | "deactivate";
    merchant: Merchant | null;
  }>({ open: false, action: "activate", merchant: null });
  const [actionLoading, setActionLoading] = useState(false);

  const list = useFetch(
    useCallback((signal: AbortSignal) => getMerchants(filter === "all" ? undefined : filter, signal), [filter]),
    "Failed to load merchants"
  );
  const merchants = list.data ?? [];
  const loading = list.loading;

  /* Badge helper */
  const statusBadge = (m: Merchant) => {
    if (m.is_active) return <span className="badge badge-success">Active</span>;
    if (m.payment_status === "payment_declined")
      return <span className="badge badge-error">Declined</span>;
    return <span className="badge badge-warning">Pending</span>;
  };

  /* The values the API stores (routers/payments.py). */
  const paymentBadge = (status: string) => {
    switch (status) {
      case "payment_successful":
        return <span className="badge badge-success">Paid</span>;
      case "payment_pending":
        return <span className="badge badge-warning">Pending</span>;
      case "payment_declined":
        return <span className="badge badge-error">Declined</span>;
      default:
        return <span className="badge badge-cyan">{status}</span>;
    }
  };

  /* Action handlers */
  const openDialog = (
    action: "activate" | "deactivate",
    merchant: Merchant
  ) => {
    setDialog({ open: true, action, merchant });
  };

  const confirmAction = async () => {
    if (!dialog.merchant) return;
    setActionLoading(true);
    setError("");
    try {
      if (dialog.action === "activate") {
        await activateMerchant(dialog.merchant.id);
      } else {
        await deactivateMerchant(dialog.merchant.id);
      }
      setDialog({ open: false, action: "activate", merchant: null });
      await list.reload();
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Action failed"));
    } finally {
      setActionLoading(false);
    }
  };

  const tabs: { key: FilterTab; label: string }[] = [
    { key: "all", label: "All" },
    { key: "active", label: "Active" },
    { key: "pending", label: "Pending" },
    { key: "declined", label: "Declined" },
  ];

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Merchant Management</h2>
        <p>Review, activate, or deactivate merchant accounts</p>
      </div>

      {/* Filter Tabs */}
      <div className="filter-tabs">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`filter-tab ${filter === t.key ? "active" : ""}`}
            onClick={() => {
              setFilter(t.key);
              setVisible(PAGE_SIZE);
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {(error || list.error) && <div className="error-message">{error || list.error}</div>}

      {loading ? (
        <TableSkeleton />
      ) : merchants.length === 0 ? (
        <div className="empty-state">
          <Store size={48} />
          <p>No merchants found for this filter.</p>
        </div>
      ) : (
        <>
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Business Type</th>
                <th>Status</th>
                <th>Payment</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {merchants.slice(0, visible).map((m) => (
                <tr key={m.id}>
                  <td style={{ fontWeight: 600 }}>{m.name}</td>
                  <td style={{ color: "var(--text-secondary)" }}>{m.email}</td>
                  <td>{m.business_type}</td>
                  <td>{statusBadge(m)}</td>
                  <td>{paymentBadge(m.payment_status)}</td>
                  <td style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                    {new Date(m.created_at).toLocaleDateString()}
                  </td>
                  <td>
                    <div className="btn-actions">
                      {!m.is_active && (
                        <button
                          className="btn-sm btn-activate"
                          onClick={() => openDialog("activate", m)}
                        >
                          Activate
                        </button>
                      )}
                      {m.is_active && (
                        <button
                          className="btn-sm btn-deactivate"
                          onClick={() => openDialog("deactivate", m)}
                        >
                          Deactivate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ListFooter
          shown={Math.min(visible, merchants.length)}
          total={merchants.length}
          hasMore={visible < merchants.length}
          onMore={() => setVisible(visible + PAGE_SIZE)}
        />
        </>
      )}

      {/* Confirmation Dialog */}
      {dialog.open && dialog.merchant && (
        <div className="dialog-overlay" onClick={() => !actionLoading && setDialog({ ...dialog, open: false })}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>
              {dialog.action === "activate"
                ? "Activate Merchant"
                : "Deactivate Merchant"}
            </h3>
            <p>
              Are you sure you want to{" "}
              <strong>{dialog.action}</strong>{" "}
              <strong>{dialog.merchant.name}</strong>? This action will take
              effect immediately.
            </p>
            <div className="dialog-actions">
              <button
                className="btn-cancel"
                onClick={() => setDialog({ ...dialog, open: false })}
                disabled={actionLoading}
              >
                Cancel
              </button>
              <button
                className={`btn-sm ${
                  dialog.action === "activate"
                    ? "btn-activate"
                    : "btn-deactivate"
                }`}
                onClick={confirmAction}
                disabled={actionLoading}
                style={{ padding: "10px 20px", fontSize: "0.85rem" }}
              >
                {actionLoading ? "Processing…" : `Yes, ${dialog.action}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
