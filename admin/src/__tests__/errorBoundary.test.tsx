import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "../components/ErrorBoundary";

function Boom(): JSX.Element {
  throw new Error("kaboom");
}

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

function mount(node: JSX.Element): void {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(node));
}

describe("ErrorBoundary", () => {
  it("renders children when there is no error", () => {
    mount(
      <ErrorBoundary>
        <div>healthy-content</div>
      </ErrorBoundary>,
    );
    expect(container.textContent).toContain("healthy-content");
  });

  it("shows a recoverable fallback when a child throws", () => {
    // React logs the caught error to console.error even when an error boundary
    // handles it — silence it so the test output stays clean.
    vi.spyOn(console, "error").mockImplementation(() => {});
    mount(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(container.querySelector('[role="alert"]')).toBeTruthy();
    expect(container.textContent).toContain("Что-то пошло не так");
    expect(container.textContent).toContain("kaboom"); // the error message is surfaced
    // recovery affordances are present
    expect(container.textContent).toContain("Попробовать снова");
  });
});
