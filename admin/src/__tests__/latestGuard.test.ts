import { describe, expect, it } from "vitest";

import { createLatestGuard } from "../lib/latestGuard";

describe("createLatestGuard", () => {
  it("marks an earlier request stale once a newer one begins", () => {
    const guard = createLatestGuard();
    const isLatestA = guard(); // request A
    expect(isLatestA()).toBe(true);
    const isLatestB = guard(); // request B (newer) supersedes A
    expect(isLatestB()).toBe(true);
    expect(isLatestA()).toBe(false); // A is now stale → its response must be ignored
  });

  it("keeps the single in-flight request latest", () => {
    const guard = createLatestGuard();
    const isLatest = guard();
    expect(isLatest()).toBe(true);
    expect(isLatest()).toBe(true); // idempotent while no newer request starts
  });

  it("simulates out-of-order resolution: only the newest result is applied", () => {
    const guard = createLatestGuard();
    let applied = "";
    const apply = (val: string, isLatest: () => boolean) => {
      if (isLatest()) applied = val;
    };
    const oldGuard = guard(); // filter=X
    const newGuard = guard(); // filter=Y (user changed the filter)
    // The newer request resolves first…
    apply("Y", newGuard);
    // …then the older, slower request resolves LATE — it must NOT clobber Y.
    apply("X", oldGuard);
    expect(applied).toBe("Y");
  });
});
