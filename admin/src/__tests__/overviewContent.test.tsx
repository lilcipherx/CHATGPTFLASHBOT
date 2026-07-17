import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../pages/Dashboard", () => ({ Dashboard: () => null }));
vi.mock("../pages/Analytics", () => ({ Analytics: () => null }));
vi.mock("../pages/Effects", () => ({ Effects: () => null }));
vi.mock("../pages/Banners", () => ({ Banners: () => null }));
vi.mock("../pages/CustomButtons", () => ({ CustomButtons: () => null }));

import { Content } from "../pages/Content";
import { Overview } from "../pages/Overview";

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

describe("Overview / Content — role-gated tabs", () => {
  it("Overview: support sees ONLY Дашборд; moderator sees Дашборд + Аналитика", () => {
    localStorage.setItem("admin_role", "support");
    let el = render(<Overview />);
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(1);
    expect(labels(el)).toContain("Дашборд");
    expect(labels(el)).not.toContain("Аналитика");
    act(() => root?.unmount());
    container?.remove();

    localStorage.setItem("admin_role", "moderator");
    el = render(<Overview />);
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(2);
    expect(labels(el)).toContain("Аналитика");
  });

  it("Content: moderator sees Эффекты + Карусель + Кнопки-ссылки", () => {
    localStorage.setItem("admin_role", "moderator");
    const el = render(<Content />);
    expect(el.querySelectorAll(".seg-tabs button").length).toBe(3);
    const l = labels(el);
    expect(l).toContain("Эффекты");
    expect(l).toContain("Карусель");
    expect(l).toContain("Кнопки-ссылки");
  });
});
