import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

// api.dashboard is mocked so we can assert the page renders real data into every
// KPI / panel (not a stub) and that the refresh interval is wired + cleaned up.
const { dashboardMock } = vi.hoisted(() => ({ dashboardMock: vi.fn() }));
// adminFetch (used by the /attention poll) delegates to the stubbed global fetch.
vi.mock("../api", () => ({
  api: { dashboard: dashboardMock },
  adminFetch: (path: string, init?: RequestInit) => fetch(path, init),
}));

import { Dashboard } from "../pages/Dashboard";

const DASH = {
  period: "all",
  total_users: 1234,
  new_users: 56,
  new_users_7d: 56,
  active_subscriptions: 78,
  banned_users: 3,
  credits_total: 99999,
  paid_transactions: 42,
  paying_users: 30,
  conversion_pct: 2.43,
  dau: 100,
  wau: 300,
  mau: 500,
  revenue_by_currency: {
    stars: { total: 1000, count: 20, avg_check: 50, by_gateway: { stars: 1000 } },
    rub: { total: 500, count: 5, avg_check: 100, by_gateway: { yookassa: 500 } },
  },
  revenue_by_gateway: { stars: 1000, yookassa: 500 },
  jobs_by_status: { complete: 10, processing: 2, pending: 1, failed: 4 },
  completed_generations: 10,
  pending_jobs: 3,
};
const ATT = {
  stuck_jobs: 2, open_complaints: 0, pending_gallery: 0,
  open_support: 0, failed_channel_posts: 0, total: 2,
};

function mockAttention() {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(ATT) })),
  );
}

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<Dashboard />); });
  await act(async () => { await Promise.resolve(); }); // flush the resolved fetches
}

describe("Dashboard — data wiring", () => {
  it("renders every KPI, the attention panel, revenue + jobs from the API (no stubs)", async () => {
    dashboardMock.mockResolvedValue(DASH);
    mockAttention();
    await render();

    const t = container.textContent ?? "";
    // skeleton replaced by real content
    expect(container.querySelector(".skeleton-row")).toBeNull();
    // KPI labels + values (use non-thousands-separated values to dodge locale spacing)
    expect(t).toContain("Всего пользователей");
    expect(t).toContain("Активные подписки");
    expect(t).toContain("78");                 // active_subscriptions
    expect(t).toContain("Оплат за");
    expect(t).toContain("42");                 // paid_transactions
    expect(t).toContain("Заблокировано");
    // engagement + conversion KPIs are wired
    expect(t).toContain("DAU");
    expect(t).toContain("100");                // dau
    expect(t).toContain("MAU");
    expect(t).toContain("Конверсия в оплату");
    // attention panel total + a category pill
    expect(t).toContain("Требует внимания");
    expect(t).toContain("Зависшие задачи: 2");
    // revenue panel — currency tabs + active-tab gateway label prove the
    // by-currency breakdown is wired (active tab = Stars, the higher-count currency)
    expect(t).toContain("Выручка по валютам");
    expect(t).toContain("Stars");
    expect(t).toContain("Рубли");
    expect(t).toContain("Telegram Stars");
    // jobs panel — status labels + active pill
    expect(t).toContain("Готово");
    expect(t).toContain("Ошибка");
    expect(t).toContain("3 активных");         // pending_jobs
  });

  it("refreshes on a 60s interval and clears the timer on unmount (no leak)", async () => {
    vi.useFakeTimers();
    dashboardMock.mockResolvedValue(DASH);
    mockAttention();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => { root.render(<Dashboard />); });

    expect(dashboardMock).toHaveBeenCalledTimes(1);   // initial load
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(dashboardMock).toHaveBeenCalledTimes(2);   // one refresh tick

    act(() => root.unmount());
    act(() => { vi.advanceTimersByTime(180_000); });
    expect(dashboardMock).toHaveBeenCalledTimes(2);   // no calls after unmount → timer cleared
    // re-point root so afterEach's unmount is a no-op on the already-unmounted tree
    root = createRoot(document.createElement("div"));
  });

  it("a failed refresh poll shows an error banner but keeps the last good data (no blanking)", async () => {
    vi.useFakeTimers();
    // First load succeeds; the next poll fails (transient 500 / network blip).
    dashboardMock.mockResolvedValueOnce(DASH).mockRejectedValue(new Error("API 500"));
    mockAttention();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => { root.render(<Dashboard />); });
    await act(async () => { await Promise.resolve(); });   // flush the first (good) load

    expect(container.textContent ?? "").toContain("Оплат за");   // data rendered

    // A refresh tick rejects — flush the rejected promise's catch microtasks.
    await act(async () => {
      vi.advanceTimersByTime(60_000);
      await Promise.resolve(); await Promise.resolve();
    });

    const t = container.textContent ?? "";
    expect(t).toContain("API 500");        // error surfaced as a banner
    expect(t).toContain("Оплат за");    // …and the previous KPIs are STILL visible
    expect(t).toContain("42");             // paid_transactions not blanked away

    act(() => root.unmount());
    root = createRoot(document.createElement("div"));
  });
});
