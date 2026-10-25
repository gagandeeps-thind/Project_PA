/* ───────────────────────────────────────────────────────────
 *  Merchants Page
 * ─────────────────────────────────────────────────────────── */
import { useEffect, useState, useCallback } from "react";
import { Store } from "lucide-react";
import {
  apiErrorMessage,
  getMerchants,
  activateMerchant,
  deactivateMerchant,
} from "../api/client";
import type { Merchant } from "../api/types";
import { TableSkeleton } from "../components/Skeleton";

type FilterTab = "all" | "active" | "pending" | "declined";

export default function MerchantsPage() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<FilterTab>("all");

  /* Confirmation dialog state */
  const [dialog, setDialog] = useState<{
    open: boolean;
    action: "activate" | "deactivate";
    merchant: Merchant | null;
  }>({ open: false, action: "activate", merchant: null });
  const [actionLoading, setActionLoading] = useState(false);

  const fetchMerchants = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const status = filter === "all" ? undefined : filter;
      const data = await getMerchants(status);
      setMerchants(data);
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Failed to load merchants"));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchMerchants();
  }, [fetchMerchants]);

  /* Badge helper */
  const statusBadge = (m: Merchant) => {
    if (m.is_active) return <span className="badge badge-success">Active</span>;
    if (m.payment_status === "declined")
      return <span className="badge badge-error">Declined</span>;
    return <span className="badge badge-warning">Pending</span>;
  };

  const paymentBadge = (status: string) => {
    switch (status) {
      case "paid":
        return <span className="badge badge-success">Paid</span>;
      case "pending":
        return <span className="badge badge-warning">Pending</span>;
      case "declined":
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
    try {
      if (dialog.action === "activate") {
        await activateMerchant(dialog.merchant.id);
      } else {
        await deactivateMerchant(dialog.merchant.id);
      }
      setDialog({ open: false, action: "activate", merchant: null });
      await fetchMerchants();
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
            onClick={() => setFilter(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <TableSkeleton />
      ) : merchants.length === 0 ? (
        <div className="empty-state">
          <Store size={48} />
          <p>No merchants found for this filter.</p>
        </div>
      ) : (
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
              {merchants.map((m) => (
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
