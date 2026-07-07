import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

// login() is mocked to a promise that never resolves, so the in-flight guard stays
// engaged and we can assert a rapid double submit only fires one request.
const { loginMock } = vi.hoisted(() => ({
  loginMock: vi.fn(() => new Promise<{ role: string; mfaSetup: boolean }>(() => {})),
}));
vi.mock("../api", () => ({ login: loginMock, api: {} }));

import { Login } from "../pages/Login";

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
});

function setValue(el: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  setter.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("Login double-submit guard", () => {
  it("fires only one login request for a rapid double submit", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root.render(<Login onAuthed={() => {}} />));

    const inputs = container.querySelectorAll("input");
    act(() => {
      setValue(inputs[0] as HTMLInputElement, "admin@b.io");
      setValue(inputs[1] as HTMLInputElement, "password123");
    });

    const btn = container.querySelector('button[type="submit"]') as HTMLButtonElement;
    act(() => {
      btn.click();
      btn.click(); // second, rapid click must be ignored while the first is in flight
    });

    expect(loginMock).toHaveBeenCalledTimes(1);
    expect(btn.disabled).toBe(true); // button reflects the loading state
    expect(btn.textContent).toContain("Вход…");
  });
});
