import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Keep App's page/router graph out of this unit test.
vi.mock("../api", () => ({ isAuthed: () => false, logout: () => {} }));

import { ThemeToggle } from "../App";

let root: Root | null = null;
let container: HTMLElement | null = null;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<ThemeToggle />));
  return container;
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.dataset.theme = "dark";
});
afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
});

describe("ThemeToggle", () => {
  it("starts on dark and toggles to light (persists + sets <html data-theme>)", () => {
    const el = render();
    const btn = el.querySelector("button")!;
    // Dark active → the button offers 'light_mode' (switch to light).
    expect(btn.textContent).toContain("light_mode");

    act(() => btn.click());
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("admin_theme")).toBe("light");
    expect(btn.textContent).toContain("dark_mode");

    act(() => btn.click());
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("admin_theme")).toBe("dark");
    expect(btn.textContent).toContain("light_mode");
  });
});
