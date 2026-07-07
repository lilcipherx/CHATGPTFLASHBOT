import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// i18n reads the Telegram SDK at import — mock it so the boundary can translate.
vi.mock("@twa-dev/sdk", () => ({
  default: { initDataUnsafe: { user: { language_code: "ru" } }, ready: () => {}, expand: () => {} },
}));

import { ErrorBoundary } from "../components/ErrorBoundary";

function Boom(): JSX.Element {
  throw new Error("kaboom");
}

afterEach(() => vi.restoreAllMocks());

describe("ErrorBoundary", () => {
  it("renders children when healthy", () => {
    render(
      <ErrorBoundary>
        <div>healthy</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("healthy")).toBeInTheDocument();
  });

  it("shows a recoverable fallback when a child throws", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});  // silence React's logged error
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    // the reload affordance (reused "retry" key) is present
    expect(screen.getByRole("button")).toBeInTheDocument();
  });
});
