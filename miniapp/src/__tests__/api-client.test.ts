import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@twa-dev/sdk", () => ({
  default: { initData: "auth_date=1&hash=x", ready: () => {}, expand: () => {} },
}));

import { api, newIdempotencyKey, pollJob } from "../api/client";

afterEach(() => vi.restoreAllMocks());

async function readFormField(init: RequestInit | undefined, name: string): Promise<string | null> {
  const body = init?.body as FormData;
  const v = body.get(name);
  return typeof v === "string" ? v : null;
}

describe("idempotency key (AUDIT-U3)", () => {
  it("newIdempotencyKey returns distinct non-empty tokens", () => {
    const a = newIdempotencyKey();
    const b = newIdempotencyKey();
    expect(a).toBeTruthy();
    expect(a).not.toBe(b);
  });

  it("effectGenerate forwards the idempotency_key as a form field", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ job_id: "j1", cost: 1 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.effectGenerate("photo", 5, "nano_banana", {}, "", [], undefined, "tok-123");
    const [, init] = fetchMock.mock.calls[0];
    expect(await readFormField(init, "idempotency_key")).toBe("tok-123");
  });

  it("omits idempotency_key when none is supplied (older behaviour)", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ job_id: "j1", cost: 1 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.effectGenerate("photo", 5, "nano_banana", {}, "", []);
    const [, init] = fetchMock.mock.calls[0];
    expect(await readFormField(init, "idempotency_key")).toBeNull();
  });
});

describe("api client", () => {
  it("sends X-Init-Data and parses the profile", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ user_id: 1, credits: 3 }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const profile = await api.profile();
    expect(profile.credits).toBe(3);
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>)["X-Init-Data"]).toContain("auth_date");
  });

  it("pollJob resolves on a terminal status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ status: "complete", result_url: "u", error: null }), {
          status: 200,
        }),
      ),
    );
    const res = await pollJob("job-1");
    expect(res.status).toBe("complete");
  });

  it("pollJob bails immediately on an already-aborted signal (no request)", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const ctrl = new AbortController();
    ctrl.abort();
    const res = await pollJob("job-1", undefined, ctrl.signal);
    expect(res.status).toBe("failed");
    expect(res.error).toBe("aborted");
    expect(fetchMock).not.toHaveBeenCalled();  // no wasted polling after unmount
  });

  it("pollJob stops polling once the signal aborts mid-run", async () => {
    const ctrl = new AbortController();
    let ticks = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ status: "processing", result_url: null, error: null }), {
          status: 200,
        }),
      ),
    );
    const res = await pollJob("job-1", () => { ticks += 1; ctrl.abort(); }, ctrl.signal);
    // First tick fires, then the post-tick abort check stops the loop before sleeping.
    expect(ticks).toBe(1);
    expect(res.error).toBe("aborted");
  });
});
