import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

// Stub the three merged pages so mounting a tab doesn't hit the API — this test
// only asserts AccessSecurity's role-gated tab bar.
vi.mock("../pages/Admins", () => ({ Admins: () => null }));
vi.mock("../pages/Security", () => ({ Security: () => null }));
vi.mock("../pages/Audit", () => ({ Audit: () => null }));

import { AccessSecurity } from "../pages/AccessSecurity";

let root: Root | null = null;
let container: HTMLElement | null = null;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<AccessSecurity />));
  return container;
}

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  localStorage.clear();
});

function tabLabels(el: HTMLElement): string {
  return [...el.querySelectorAll(".seg-tabs button")].map((b) => b.textContent).join("|");
}

describe("AccessSecurity — role-gated tabs", () => {
  it("superadmin sees all three tabs (Админы + Безопасность + Аудит-лог)", () => {
    localStorage.setItem("admin_role", "superadmin");
    const el = render();
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(3);
    const labels = tabLabels(el);
    expect(labels).toContain("Админы");
    expect(labels).toContain("Безопасность");
    expect(labels).toContain("Аудит-лог");
  });

  it("support sees ONLY the Аудит-лог tab (no Админы / Безопасность)", () => {
    localStorage.setItem("admin_role", "support");
    const el = render();
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(1);
    const labels = tabLabels(el);
    expect(labels).toContain("Аудит-лог");
    expect(labels).not.toContain("Админы");
    expect(labels).not.toContain("Безопасность");
  });
});
