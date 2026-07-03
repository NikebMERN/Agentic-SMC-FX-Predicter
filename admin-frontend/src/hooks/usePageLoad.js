import { useCallback, useEffect, useState } from "react";

/** Load data on mount + expose loading/error/success helpers for admin pages. */
export function usePageLoad(loadFn, deps = []) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      await loadFn();
    } catch (e) {
      setError(e.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }, deps);

  useEffect(() => {
    reload();
  }, [reload]);

  return { loading, error, notice, setNotice, setError, reload };
}

export async function withNotice(setNotice, setError, fn, successMsg) {
  setError("");
  try {
    const result = await fn();
    if (successMsg) setNotice(successMsg);
    return result;
  } catch (e) {
    setError(e.message || "Request failed");
    throw e;
  }
}
