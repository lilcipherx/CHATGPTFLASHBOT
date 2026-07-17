import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

// Stub the merged pages so mounting a tab doesn't hit the API.
vi.mock("../pages/Broadcasts", () => ({ Broadcasts: () => null }));
vi.mock("../pages/ChannelPosts", () => ({ ChannelPosts: () => null }));
vi.mock("../pages/Maintenance", () => ({ Maintenance: () => null }));
vi.mock("../pages/Scheduler", () => ({ Scheduler: () => null }));

import { Outreach } from "../pages/Outreach";
import { SystemOps } from "../pages/SystemOps";

let root: Root | null = null;
let container: HTMLElement | null = null;

function render(el: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<MemoryRouter>{el}</MemoryRouter>));
  return container;
}

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  localStorage.clear();
});

function labels(el: HTMLElement): string {
  return [...el.querySelectorAll(".seg-tabs button")].map((b) => b.textContent).join("|");
}

describe("consolidated tabbed pages", () => {
  it("Outreach shows Рассылки + Автопостинг for a moderator", () => {
    localStorage.setItem("admin_role", "moderator");
    const el = render(<Outreach />);
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(2);
    expect(labels(el)).toContain("Рассылки");
    expect(labels(el)).toContain("Автопостинг");
  });

  it("SystemOps shows Обслуживание + Планировщик for a superadmin", () => {
    localStorage.setItem("admin_role", "superadmin");
    const el = render(<SystemOps />);
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(2);
    expect(labels(el)).toContain("Обслуживание");
    expect(labels(el)).toContain("Планировщик");
  });
});
