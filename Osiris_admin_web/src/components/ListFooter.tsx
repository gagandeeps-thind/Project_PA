/** Row count under a list, with the button that fetches or reveals the next page. */
export default function ListFooter({
  shown,
  total,
  hasMore,
  loading = false,
  onMore,
  note,
}: {
  shown: number;
  /** Known only when the server sent the whole list. */
  total?: number;
  hasMore: boolean;
  loading?: boolean;
  onMore?: () => void;
  note?: string;
}) {
  return (
    <div className="list-footer" role="status">
      <span>
        Showing {shown}
        {total !== undefined ? ` of ${total}` : hasMore ? " so far" : ""}
        {note ? `. ${note}` : ""}
      </span>
      {hasMore && onMore && (
        <button className="btn-cancel" type="button" disabled={loading} onClick={onMore}>
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
