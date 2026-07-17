import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

// Deep-linkable tabs: the active tab lives in the URL (?tab=<id>) so a consolidated
// page's tabs are bookmarkable / shareable and the command palette can jump straight
// to one (e.g. #/ai-setup?tab=keys). Falls back to `fallback` when the param is
// missing or names a tab that isn't currently visible (e.g. a role-hidden tab), so
// it stays role-safe. Uses replace: true so tab switches don't spam browser history.
export function useTabParam(
  validIds: string[],
  fallback: string,
): [string, (id: string) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab = raw && validIds.includes(raw) ? raw : fallback;
  const setTab = useCallback(
    (id: string) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("tab", id);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  return [tab, setTab];
}
