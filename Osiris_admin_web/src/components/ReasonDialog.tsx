import { useState, type ReactNode } from "react";

/** Confirmation dialog with a required reason. It owns the text, so typing re-renders this
 *  dialog only and not the table behind it. Mount it while an action is pending. */
export default function ReasonDialog({
  title,
  body,
  label,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string;
  body: ReactNode;
  label: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [text, setText] = useState("");
  const reason = text.trim();
  return (
    <div className="dialog-overlay" onClick={() => !busy && onCancel()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <p>{body}</p>
        <div className="form-group">
          <label className="form-label" htmlFor="reason-dialog-input">{label}</label>
          <input
            id="reason-dialog-input"
            className="form-input"
            autoFocus
            value={text}
            maxLength={500}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="dialog-actions">
          <button className="btn-cancel" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            className="btn-sm btn-deactivate"
            onClick={() => onConfirm(reason)}
            disabled={busy || reason.length < 3}
            style={{ padding: "10px 20px", fontSize: "0.85rem" }}
          >
            {busy ? "Processing…" : "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}
