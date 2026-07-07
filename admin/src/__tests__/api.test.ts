import { afterEach, describe, expect, it, vi } from "vitest";

import { api, isAuthed, logout } from "../api";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

function stubFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(typeof body === "string" ? body : JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
}

describe("api error surfacing", () => {
  it("surfaces the server `detail` message on a failed request", async () => {
    stubFetch(400, { detail: "title required" });
    await expect(api.dashboard()).rejects.toThrow("title required");
  });

  it("falls back to the status code when there is no detail", async () => {
    stubFetch(500, "not json");
    await expect(api.dashboard()).rejects.toThrow("API 500");
  });

  it("joins FastAPI 422 validation detail arrays", async () => {
    stubFetch(422, { detail: [{ msg: "field required" }, { msg: "too short" }] });
    await expect(api.dashboard()).rejects.toThrow("field required; too short");
  });

  it("maps 401 to a session-expired error", async () => {
    localStorage.setItem("admin_authed", "1");
    stubFetch(401, { detail: "token revoked" });
    await expect(api.dashboard()).rejects.toThrow("session expired");
  });
});

describe("admin api auth state", () => {
  it("is not authed by default", () => {
    expect(isAuthed()).toBe(false);
  });

  it("reflects the persisted authed flag", () => {
    localStorage.setItem("admin_authed", "1");
    expect(isAuthed()).toBe(true);
  });

  it("logout clears local auth state", () => {
    localStorage.setItem("admin_authed", "1");
    localStorage.setItem("admin_role", "superadmin");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    logout();
    expect(isAuthed()).toBe(false);
    expect(localStorage.getItem("admin_role")).toBeNull();
  });
});
