import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../pages/Pricing", () => ({ Pricing: () => null }));
vi.mock("../pages/Promos", () => ({ Promos: () => null }));

import { PricingPromos } from "../pages/PricingPromos";

let root: Root | null = null;
let container: HTMLElement | null = null;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<MemoryRouter><PricingPromos /></MemoryRouter>));
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

describe("PricingPromos — role-gated tabs", () => {
  it("superadmin sees both tabs (Цены + Промокоды)", () => {
    localStorage.setItem("admin_role", "superadmin");
    const el = render();
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(2);
    const labels = tabLabels(el);
    expect(labels).toContain("Цены");
    expect(labels).toContain("Промокоды");
  });

  it("moderator sees ONLY Промокоды (Цены is superadmin-only)", () => {
    localStorage.setItem("admin_role", "moderator");
    const el = render();
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(1);
    const labels = tabLabels(el);
    expect(labels).toContain("Промокоды");
    expect(labels).not.toContain("Цены");
  });
});
