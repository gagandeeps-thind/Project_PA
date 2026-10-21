import { useEffect, useState } from "react";

/** `value`, updated only after it has stopped changing for `delayMs`. Keeps a filter typed
 *  key by key from sending one request per keystroke. */
export function useDebouncedValue<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}
