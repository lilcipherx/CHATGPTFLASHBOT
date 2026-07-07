# Mini App + Admin — Responsive / Performance / UX Refactor

**Date:** 2026-06-20
**Decision:** Targeted refactor; **preserve** the existing dark + acid-lime
(Higgsfield) aesthetic. No business-logic changes — only CSS, render-level
(`React.lazy`/`memo`/image attrs) and `data-label` attributes.

## Problem
Both SPAs already have a consistent design system and partial responsiveness, but:
- **Mini App:** no max-width cap → stretches edge-to-edge on tablet/desktop; all
  pages + images load eagerly; no `prefers-reduced-motion`.
- **Admin:** tables only get horizontal scroll on mobile (must be eliminated); no
  max-width cap on ultra-wide monitors; all 13 page components load eagerly
  (~211 KB initial JS).

## Goals
Mobile-first 320px+ → large monitors, no horizontal scroll, faster first paint,
fewer re-renders, smooth on weak devices. Visual language unchanged.

## Changes

### Mini App (`miniapp/`)
1. **Responsive shell** — `.app` content centered with `max-width` (~640px) from
   tablet up; fluid type with `clamp()`; keep the 2-col portrait grid (Mini App
   is portrait) but allow 3 cols ≥560px within the cap.
2. **Code-split** — `React.lazy` for Trends/History/Profile (Home stays eager) +
   `Suspense` fallback (existing `.center` spinner).
3. **Render perf** — `React.memo` on `EffectCard`; thumbnails get
   `loading="lazy"` + `decoding="async"`.
4. **Motion** — `@media (prefers-reduced-motion: reduce)` disables transitions/
   animations.

### Admin (`admin/`)
1. **Responsive tables** — at ≤640px each `table.tbl` becomes stacked cards: rows
   render as bordered blocks, each `td` shows its column name via `data-label`.
   No horizontal scroll. Applied to Users, Payments, Promos, Audit, Referrals.
2. **Large-screen cap** — `.main` content capped (~1400px) and centered for
   readability on wide monitors.
3. **Code-split** — `React.lazy` for all 13 page components + `Suspense`.
4. **Polish** — toolbar/form wrapping on small screens; `prefers-reduced-motion`.

## Non-goals
No palette/typography change, no router introduction, no API/endpoint changes, no
component behavior changes.

## Verification
`npm run build` (both) clean; existing Vitest suites pass; manual responsive check
at 320 / 768 / 1440px (DevTools); no horizontal scroll; CI `frontend` job green.

## Risk
Low — additive CSS + render wrappers + `data-label` attributes. Tables without
`data-label` keep the current scroll fallback, so nothing breaks.
