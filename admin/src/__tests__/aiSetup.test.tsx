import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

// The three merged pages are stubbed so mounting a tab doesn't hit the API — this
// test only asserts AISetup's role-gated tab bar (the risky bit of the merge).
vi.mock("../pages/AIRouting", () => ({ AIRouting: () => null }));
vi.mock("../pages/Providers", () => ({ Providers: () => null }));
vi.mock("../pages/ApiKeys", () => ({ ApiKeys: () => null }));

import { AISetup } from "../pages/AISetup";

let root: Root | null = null;
let container: HTMLElement | null = null;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<MemoryRouter><AISetup /></MemoryRouter>));
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

describe("AISetup — role-gated tabs", () => {
  it("superadmin sees all three tabs (Роутинг + Провайдеры + Ключи API)", () => {
    localStorage.setItem("admin_role", "superadmin");
    const el = render();
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(3);
    const labels = tabLabels(el);
    expect(labels).toContain("Роутинг");
    expect(labels).toContain("Провайдеры");
    expect(labels).toContain("Ключи API");
  });

  it("admin does NOT see the superadmin-only Роутинг tab", () => {
    localStorage.setItem("admin_role", "admin");
    const el = render();
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(2);
    const labels = tabLabels(el);
    expect(labels).not.toContain("Роутинг");
    expect(labels).toContain("Провайдеры");
    expect(labels).toContain("Ключи API");
  });

  it("deep-links straight to a tab via ?tab= (opens Ключи API)", () => {
    localStorage.setItem("admin_role", "superadmin");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root!.render(
      <MemoryRouter initialEntries={["/?tab=keys"]}><AISetup /></MemoryRouter>,
    ));
    const active = container.querySelector(".seg-tabs button.on");
    expect(active?.textContent).toContain("Ключи API");
  });
});
