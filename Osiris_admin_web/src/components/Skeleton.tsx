/* ───────────────────────────────────────────────────────────
 *  Loading skeletons: grey shapes where content will appear, so
 *  the layout does not jump when data arrives.
 * ─────────────────────────────────────────────────────────── */
import { memo } from "react";

export const TableSkeleton = memo(function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="data-table-wrapper" aria-busy="true" aria-label="Loading">
      <table className="data-table">
        <tbody>
          {Array.from({ length: rows }, (_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }, (_, c) => (
                <td key={c}>
                  <span className="skeleton skeleton-text" style={{ width: `${55 + ((r + c) % 4) * 10}%` }} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
});

export const CardsSkeleton = memo(function CardsSkeleton({ cards = 4 }: { cards?: number }) {
  return (
    <div className="kpi-grid" aria-busy="true" aria-label="Loading">
      {Array.from({ length: cards }, (_, i) => (
        <div className="kpi-card" key={i}>
          <span className="skeleton skeleton-text" style={{ width: "40%" }} />
          <span className="skeleton skeleton-value" />
        </div>
      ))}
    </div>
  );
});

/** Shown while a page's code is being fetched. */
export function PageSkeleton() {
  return (
    <div>
      <div className="page-header">
        <span className="skeleton skeleton-title" />
        <span className="skeleton skeleton-text" style={{ width: "45%" }} />
      </div>
      <TableSkeleton />
    </div>
  );
}
