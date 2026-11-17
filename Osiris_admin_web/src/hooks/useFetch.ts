import { useCallback, useEffect, useRef, useState } from "react";
import { apiErrorMessage, PAGE_SIZE } from "../api/client";

/** Loads `fn` on mount and whenever it changes (so wrap it in useCallback). A newer load, or
 *  leaving the page, aborts the request before it, so a slow answer for an old filter never
 *  overwrites a newer one. */
export function useFetch<T>(fn: (signal: AbortSignal) => Promise<T>, fallback: string) {
  const [state, setState] = useState<{ data: T | null; loading: boolean; error: string }>({
    data: null,
    loading: true,
    error: "",
  });
  const ctrl = useRef<AbortController | null>(null);

  const reload = useCallback(async () => {
    ctrl.current?.abort();
    const c = (ctrl.current = new AbortController());
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const data = await fn(c.signal);
      if (!c.signal.aborted) setState({ data, loading: false, error: "" });
    } catch (err) {
      if (!c.signal.aborted) setState((s) => ({ ...s, loading: false, error: apiErrorMessage(err, fallback) }));
    }
  }, [fn, fallback]);

  useEffect(() => {
    reload();
    return () => ctrl.current?.abort();
  }, [reload]);

  return { ...state, reload };
}

/** A server-paged list. `fetchPage` gets the rows loaded so far (their count is the next offset,
 *  the last one the cursor) and returns the next page of up to PAGE_SIZE rows. `reload` starts
 *  again from the first page; `loadMore` appends. Same abort rule as useFetch.
 *  shortcut: offset paging can repeat or skip a row when rows are added between two pages;
 *  move the backend lists to id cursors (as audit events have) if that shows up. */
export function usePagedList<T>(
  fetchPage: (loaded: T[], signal: AbortSignal) => Promise<T[]>,
  fallback: string,
  enabled = true
) {
  const [state, setState] = useState({ rows: [] as T[], loading: enabled, loadingMore: false, hasMore: false, error: "" });
  const ctrl = useRef<AbortController | null>(null);

  const run = useCallback(
    async (loaded: T[]) => {
      ctrl.current?.abort();
      const c = (ctrl.current = new AbortController());
      setState((s) => ({ ...s, loading: loaded.length === 0, loadingMore: loaded.length > 0, error: "" }));
      try {
        const page = await fetchPage(loaded, c.signal);
        if (c.signal.aborted) return;
        setState({
          rows: [...loaded, ...page],
          loading: false,
          loadingMore: false,
          hasMore: page.length >= PAGE_SIZE,
          error: "",
        });
      } catch (err) {
        if (c.signal.aborted) return;
        setState((s) => ({ ...s, loading: false, loadingMore: false, error: apiErrorMessage(err, fallback) }));
      }
    },
    [fetchPage, fallback]
  );

  const reload = useCallback(() => run([]), [run]);

  useEffect(() => {
    if (enabled) reload();
    return () => ctrl.current?.abort();
  }, [enabled, reload]);

  return { ...state, reload, loadMore: () => run(state.rows) };
}
