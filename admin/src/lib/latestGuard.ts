import { useRef } from "react";

// Guards against out-of-order async responses (a stale, slower request resolving
// AFTER a newer one and overwriting it with old data). The shared req() helper has
// no AbortController, so on rapid filter/search changes several fetches are in
// flight at once; without this the LAST-resolving — not the latest-requested —
// response wins, showing data that doesn't match the current filters.
//
// Usage:
//   const guard = useLatestGuard();
//   const isLatest = guard();              // call right before the fetch
//   api.x(...).then((r) => { if (isLatest()) setData(r); });
//
// Each guard() bumps an internal counter and returns an isLatest() closure that is
// true only while no later guard() has been issued.

export function createLatestGuard(): () => () => boolean {
  let current = 0;
  return function begin(): () => boolean {
    const mine = ++current;
    return () => current === mine;
  };
}

export function useLatestGuard(): () => () => boolean {
  const ref = useRef<ReturnType<typeof createLatestGuard>>();
  if (!ref.current) ref.current = createLatestGuard();
  return ref.current;
}
